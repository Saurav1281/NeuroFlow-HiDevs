import asyncio
import logging
import re
from typing import Optional
from opentelemetry import trace

from backend.providers.client import NeuroFlowClient
from backend.providers.base import ChatMessage
from backend.providers.router import RoutingCriteria
from pipelines.retrieval.fusion import RetrievalResult

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("neuroflow.retrieval")

# Try to import CrossEncoder, fallback to None if not available
try:
    from sentence_transformers import CrossEncoder
except ImportError:
    CrossEncoder = None
    logger.warning("sentence-transformers not installed. Local reranking will be unavailable.")

class Reranker:
    """Reranks retrieved chunks using cross-encoders or LLM-as-a-judge."""
    
    def __init__(self, llm_client: NeuroFlowClient, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.llm_client = llm_client
        self._local_model: Optional[Any] = None # type: ignore
        self._local_model_name = model_name

    def _load_local_model(self):
        """Lazy load the local cross-encoder model."""
        if CrossEncoder is None:
            raise ImportError("sentence-transformers is required for local reranking")
            
        if self._local_model is None:
            try:
                self._local_model = CrossEncoder(self._local_model_name)
                logger.info(f"Loaded local cross-encoder model: {self._local_model_name}")
            except Exception as e:
                logger.error(f"Failed to load local model {self._local_model_name}: {e}")
                raise

    async def rerank(
        self, 
        query: str, 
        candidates: list[RetrievalResult], 
        top_n: int = 40,
        use_local: bool = True
    ) -> list[RetrievalResult]:
        """Rerank the top-N candidates using either a local model or LLM API."""
        with tracer.start_as_current_span("reranker.rerank") as span:
            span.set_attribute("query", query)
            span.set_attribute("num_candidates", len(candidates))
            span.set_attribute("use_local", use_local)
            
            if not candidates:
                return []
                
            candidates_to_rank = candidates[:top_n]
            
            try:
                if use_local and CrossEncoder:
                    return await self._rerank_local(query, candidates_to_rank)
                else:
                    return await self._rerank_api(query, candidates_to_rank)
            except Exception as e:
                logger.error(f"Reranking failed: {e}. Returning original order.")
                span.record_exception(e)
                return candidates_to_rank

    async def _rerank_local(self, query: str, candidates: list[RetrievalResult]) -> list[RetrievalResult]:
        """Rerank using a local sentence-transformers cross-encoder."""
        with tracer.start_as_current_span("reranker._local_rerank") as span:
            self._load_local_model()
            
            pairs = [(query, c.content) for c in candidates]
            scores = await asyncio.to_thread(self._local_model.predict, pairs) # type: ignore
            
            for i, score in enumerate(scores):
                candidates[i].score = float(score)
                
            return sorted(candidates, key=lambda x: x.score, reverse=True)

    async def _rerank_api(self, query: str, candidates: list[RetrievalResult]) -> list[RetrievalResult]:
        """Rerank using LLM-as-a-judge."""
        with tracer.start_as_current_span("reranker._api_rerank") as span:
            async def score_one(candidate: RetrievalResult) -> tuple[RetrievalResult, float]:
                prompt = f"""Rate the relevance of this passage to the query on a scale of 0-10.
Query: {query}
Passage: {candidate.content}

Return ONLY the number."""
                
                try:
                    result = await self.llm_client.chat(
                        messages=[ChatMessage(role="user", content=prompt)],
                        routing_criteria=RoutingCriteria(task_type="evaluation")
                    )
                    score_str = result.content.strip()
                    match = re.search(r"(\d+(\.\d+)?)", score_str)
                    score = float(match.group(1)) if match else 0.0
                    return candidate, score
                except Exception as e:
                    logger.warning(f"Failed to score chunk {candidate.chunk_id}: {e}")
                    return candidate, 0.0

            tasks = [score_one(c) for c in candidates]
            results = await asyncio.gather(*tasks)
            
            for candidate, score in results:
                candidate.score = score
                
            return sorted(candidates, key=lambda x: x.score, reverse=True)
