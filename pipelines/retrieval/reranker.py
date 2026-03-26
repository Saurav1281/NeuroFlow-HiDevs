import asyncio
import logging
from typing import Optional

from sentence_transformers import CrossEncoder

from backend.providers.client import NeuroFlowClient
from backend.providers.base import ChatMessage
from backend.providers.router import RoutingCriteria
from pipelines.retrieval.fusion import RetrievalResult

logger = logging.getLogger(__name__)

class Reranker:
    """Reranks retrieved chunks using cross-encoders or LLM-as-a-judge."""
    
    def __init__(self, llm_client: NeuroFlowClient, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.llm_client = llm_client
        self._local_model: Optional[CrossEncoder] = None
        self._local_model_name = model_name

    def _load_local_model(self):
        """Lazy load the local cross-encoder model."""
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
        if not candidates:
            return []
            
        candidates_to_rank = candidates[:top_n]
        
        if use_local:
            return await self._rerank_local(query, candidates_to_rank)
        else:
            return await self._rerank_api(query, candidates_to_rank)

    async def _rerank_local(self, query: str, candidates: list[RetrievalResult]) -> list[RetrievalResult]:
        """Rerank using a local sentence-transformers cross-encoder."""
        self._load_local_model()
        
        # Run in a thread pool since it's CPU intensive
        pairs = [(query, c.content) for c in candidates]
        scores = await asyncio.to_thread(self._local_model.predict, pairs) # type: ignore
        
        for i, score in enumerate(scores):
            candidates[i].score = float(score)
            
        return sorted(candidates, key=lambda x: x.score, reverse=True)

    async def _rerank_api(self, query: str, candidates: list[RetrievalResult]) -> list[RetrievalResult]:
        """Rerank using LLM-as-a-judge for higher precision."""
        
        async def score_one(candidate: RetrievalResult) -> tuple[RetrievalResult, float]:
            prompt = f"""Rate the relevance of this passage to the query on a scale of 0-10.
Query: {query}
Passage: {candidate.content}

Return ONLY the number (e.g. 8 or 4.5)."""
            
            try:
                result = await self.llm_client.chat(
                    messages=[ChatMessage(role="user", content=prompt)],
                    routing_criteria=RoutingCriteria(task_type="evaluation")
                )
                score_str = result.content.strip()
                # Extract first float/int found in case LLM added words
                import re
                match = re.search(r"(\d+(\.\d+)?)", score_str)
                score = float(match.group(1)) if match else 0.0
                return candidate, score
            except Exception as e:
                logger.warning(f"Failed to score chunk {candidate.chunk_id}: {e}")
                return candidate, 0.0

        # Score all candidates in parallel
        tasks = [score_one(c) for c in candidates]
        results = await asyncio.gather(*tasks)
        
        for candidate, score in results:
            candidate.score = score
            
        return sorted(candidates, key=lambda x: x.score, reverse=True)
