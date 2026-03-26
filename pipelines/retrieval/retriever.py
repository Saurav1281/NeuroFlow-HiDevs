import asyncio
import logging
from typing import Any

from backend.db.pool import get_pool
from backend.providers.client import NeuroFlowClient
from backend.providers.base import ChatMessage
from backend.providers.router import RoutingCriteria
from pipelines.retrieval.query_processor import QueryProcessor, ProcessedQuery
from pipelines.retrieval.fusion import RetrievalResult, reciprocal_rank_fusion

logger = logging.getLogger(__name__)

class Retriever:
    """Orchestrates multi-strategy parallel retrieval."""
    
    def __init__(self, llm_client: NeuroFlowClient, query_processor: QueryProcessor):
        self.llm_client = llm_client
        self.query_processor = query_processor
        self.pool = get_pool()

    async def retrieve(self, query: str, k: int = 20, use_hyde: bool = False) -> list[RetrievalResult]:
        """Runs three retrieval strategies in parallel and fuses results.
        
        If use_hyde is True, it generates a hypothetical answer and uses it for dense retrieval.
        """
        processed = await self.query_processor.process(query)
        
        # Get embeddings for all query phrasings
        queries_to_embed = [query] + processed.expanded_queries
        
        if use_hyde:
            hyde_answer = await self._generate_hypothetical_answer(query)
            queries_to_embed.append(hyde_answer)
            
        embeddings = await self.llm_client.embed(queries_to_embed)
        
        # Run three strategies in parallel
        results = await asyncio.gather(
            self._dense_retrieval(embeddings, k),
            self._sparse_retrieval(query, k),
            self._metadata_retrieval(processed.metadata_filters, embeddings[0], k)
        )
        
        return reciprocal_rank_fusion(results)

    async def _generate_hypothetical_answer(self, query: str) -> str:
        """Generates a hypothetical answer to the query for HyDE retrieval."""
        prompt = f"Write a brief hypothetical answer to this question to improve semantic search: {query}"
        try:
            result = await self.llm_client.chat(
                messages=[ChatMessage(role="user", content=prompt)],
                routing_criteria=RoutingCriteria(task_type="rag_generation")
            )
            return result.content
        except Exception as e:
            logger.warning(f"HyDE generation failed: {e}")
            return query # Fallback to original query

    async def _dense_retrieval(self, query_embeddings: list[list[float]], k: int) -> list[RetrievalResult]:
        """HNSW dense search for all query phrasings, then union results."""
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
                        score=1.0 - float(row['distance']), # Convert distance to similarity
                        document_name=row['filename'],
                        page_number=row['metadata'].get('page_number')
                    ))
        
        # Deduplicate and keep highest similarity for each chunk
        seen = {}
        for r in all_results:
            if r.chunk_id not in seen or r.score > seen[r.chunk_id].score:
                seen[r.chunk_id] = r
                
        # Return top k after union
        return sorted(seen.values(), key=lambda x: x.score, reverse=True)[:k]

    async def _sparse_retrieval(self, query: str, k: int) -> list[RetrievalResult]:
        """PostgreSQL full-text search with cover density ranking."""
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
            return [RetrievalResult(
                chunk_id=str(row['id']),
                content=row['content'],
                metadata=row['metadata'],
                score=float(row['rank']),
                document_name=row['filename'],
                page_number=row['metadata'].get('page_number')
            ) for row in rows]

    async def _metadata_retrieval(self, filters: dict[str, Any], query_embedding: list[float], k: int) -> list[RetrievalResult]:
        """Filtered search using GIN index on metadata and HNSW for vector similarity."""
        if not filters:
            return []
            
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
            return [RetrievalResult(
                chunk_id=str(row['id']),
                content=row['content'],
                metadata=row['metadata'],
                score=1.0 - float(row['distance']),
                document_name=row['filename'],
                page_number=row['metadata'].get('page_number')
            ) for row in rows]
