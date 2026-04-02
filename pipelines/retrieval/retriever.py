import asyncio
import logging
import json
import time
from typing import Any, Optional
from opentelemetry import trace
from backend.monitoring.metrics import retrieval_latency

from backend.db.pool import get_pool
from backend.providers.client import NeuroFlowClient
from backend.providers.base import ChatMessage
from backend.providers.router import RoutingCriteria
from pipelines.retrieval.query_processor import QueryProcessor, ProcessedQuery
from pipelines.retrieval.fusion import RetrievalResult, reciprocal_rank_fusion

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("neuroflow.retrieval")

class Retriever:
    """Orchestrates multi-strategy parallel retrieval."""
    
    def __init__(self, llm_client: NeuroFlowClient, query_processor: QueryProcessor):
        self.llm_client = llm_client
        self.query_processor = query_processor
        self.pool = get_pool()

    async def retrieve(self, query: str, pipeline_id: str = "default", k: int = 100, use_hyde: bool = True, processed_query: Optional[ProcessedQuery] = None) -> list[RetrievalResult]:
        """Runs four retrieval strategies (Dense, Sparse, Step-Back, Metadata) and fuses results."""
        with tracer.start_as_current_span("retrieval.pipeline") as span:
            span.set_attribute("query", query)
            span.set_attribute("pipeline_id", str(pipeline_id))
            span.set_attribute("use_hyde", use_hyde)
            
            processed = processed_query or await self.query_processor.process(query)
            
            # 1. Get embeddings for all query phrasings
            queries_to_embed = [query] + processed.expanded_queries + processed.step_back_queries + processed.sub_queries
            
            if use_hyde:
                hyde_answer = await self._generate_hypothetical_answer(query, pipeline_id=pipeline_id)
                queries_to_embed.append(hyde_answer)
                
            embeddings = await self.llm_client.embed(queries_to_embed)
            
            # 2. Parallel retrieval across strategies
            sparse_query_text = " ".join([query] + processed.expanded_queries[:4] + processed.sub_queries[:2])
            
            results = await asyncio.gather(
                self._dense_retrieval(embeddings, k, pipeline_id=pipeline_id),
                self._sparse_retrieval(sparse_query_text, k, pipeline_id=pipeline_id),
                self._metadata_retrieval(processed.metadata_filters, embeddings[0], k, pipeline_id=pipeline_id)
            )
            
            with tracer.start_as_current_span("retrieval.fusion") as fspan:
                fspan.set_attribute("pipeline_id", str(pipeline_id))
                start_fusion = time.time()
                fused = reciprocal_rank_fusion(results)
                retrieval_latency.labels(strategy="fusion").observe(time.time() - start_fusion)
                fspan.set_attribute("num_results", len(fused))
            
            return fused

    async def _generate_hypothetical_answer(self, query: str, pipeline_id: str = "default") -> str:
        """Generates a high-quality hypothetical technical answer for HyDE."""
        with tracer.start_as_current_span("retriever._generate_hyde") as span:
            span.set_attribute("pipeline_id", str(pipeline_id))
            prompt = f"""Write a detailed, high-quality hypothetical technical documentation paragraph that answers the query below. 
The paragraph should sound like it comes from a professional AI research paper or technical manual. Use technical terminology appropriately.

Query: {query}

Hypothetical Documentation:"""
            try:
                result = await self.llm_client.chat(
                    messages=[ChatMessage(role="user", content=prompt)],
                    routing_criteria=RoutingCriteria(task_type="rag_generation")
                )
                return result.content
            except Exception as e:
                logger.warning(f"HyDE failed: {e}")
                span.record_exception(e)
                return query

    async def _dense_retrieval(self, query_embeddings: list[list[float]], k: int, pipeline_id: str = "default") -> list[RetrievalResult]:
        """HNSW dense search with tracing."""
        start_time = time.time()
        with tracer.start_as_current_span("retrieval.dense") as span:
            span.set_attribute("pipeline_id", str(pipeline_id))
            all_results = []
            async with self.pool.acquire() as conn:
                for embedding in query_embeddings:
                    rows = await conn.fetch(
                        """
                        SELECT c.id, c.content, c.metadata, (c.embedding <=> $1) as distance, d.filename
                        FROM chunks c
                        JOIN documents d ON c.document_id = d.id
                        ORDER BY c.embedding <=> $1
                        LIMIT $2
                        """,
                        embedding, k
                    )
                    for row in rows:
                        all_results.append(RetrievalResult(
                            chunk_id=str(row['id']),
                            content=row['content'],
                            metadata=row['metadata'],
                            score=1.0 - float(row['distance']), 
                            document_name=row['filename'],
                            page_number=row['metadata'].get('page_number')
                        ))
            
            seen = {}
            for r in all_results:
                if r.chunk_id not in seen or r.score > seen[r.chunk_id].score:
                    seen[r.chunk_id] = r
            
            results = sorted(seen.values(), key=lambda x: x.score, reverse=True)[:k]
            retrieval_latency.labels(strategy="dense").observe(time.time() - start_time)
            return results

    async def _sparse_retrieval(self, query: str, k: int, pipeline_id: str = "default") -> list[RetrievalResult]:
        """Sparse search with tracing."""
        start_time = time.time()
        with tracer.start_as_current_span("retrieval.sparse") as span:
            span.set_attribute("pipeline_id", str(pipeline_id))
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT c.id, c.content, c.metadata, d.filename,
                           ts_rank_cd(to_tsvector('english', c.content), plainto_tsquery('english', $1)) as rank
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.id
                    WHERE to_tsvector('english', c.content) @@ plainto_tsquery('english', $1)
                    ORDER BY rank DESC
                    LIMIT $2
                    """,
                    query, k
                )
                results = [RetrievalResult(
                    chunk_id=str(row['id']), content=row['content'], metadata=row['metadata'],
                    score=float(row['rank']), document_name=row['filename'],
                    page_number=row['metadata'].get('page_number')
                ) for row in rows]
                retrieval_latency.labels(strategy="sparse").observe(time.time() - start_time)
                return results

    async def _metadata_retrieval(self, filters: dict[str, Any], query_embedding: list[float], k: int, pipeline_id: str = "default") -> list[RetrievalResult]:
        """Metadata search with tracing."""
        if not filters: return []
        start_time = time.time()
        with tracer.start_as_current_span("retrieval.metadata") as span:
            span.set_attribute("pipeline_id", str(pipeline_id))
            span.set_attribute("filters", json.dumps(filters))
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT c.id, c.content, c.metadata, d.filename, (c.embedding <=> $2) as distance
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.id
                    WHERE c.metadata @> $1::jsonb
                    ORDER BY c.embedding <=> $2
                    LIMIT $3
                    """,
                    json.dumps(filters), query_embedding, k
                )
                results = [RetrievalResult(
                    chunk_id=str(row['id']), content=row['content'], metadata=row['metadata'],
                    score=1.0 - float(row['distance']), document_name=row['filename'],
                    page_number=row['metadata'].get('page_number')
                ) for row in rows]
                retrieval_latency.labels(strategy="metadata").observe(time.time() - start_time)
                return results
