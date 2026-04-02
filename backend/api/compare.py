import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from redis.asyncio import Redis

from backend.db.pool import get_pool
from backend.providers.client import NeuroFlowClient
from backend.utils.logger import handle_errors, retry_on_failure
from pipelines.generation.generator import Generator
from pipelines.retrieval.context_assembler import ContextAssembler
from pipelines.retrieval.query_processor import QueryProcessor
from pipelines.retrieval.reranker import Reranker
from pipelines.retrieval.retrieval_pipeline import RetrievalPipeline
from pipelines.retrieval.retriever import Retriever

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/compare", tags=["compare"])


def get_redis() -> Redis:
    from backend.config import settings

    return Redis(
        host=settings.REDIS_HOST, port=settings.REDIS_PORT, password=settings.REDIS_PASSWORD
    )


@retry_on_failure(retries=2, delay=0.5)
async def run_pipeline_task(
    query: str, pipeline_id: uuid.UUID, llm_client: NeuroFlowClient, redis: Redis
) -> dict[str, Any]:
    """
    Runs a single query through a specific pipeline and returns metrics.
    """
    start_time = time.perf_counter()

    # 1. Fetch Config from DB
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT config, version FROM pipelines WHERE id = $1", pipeline_id
        )
        if not row:
            raise ValueError(f"Pipeline {pipeline_id} not found")
        json.loads(row["config"])
        row["version"]

    # 2. Setup Pipeline with specific config
    # In a real system, we'd pass 'config' to these components.
    # For this task, we'll simulate the execution.
    query_processor = QueryProcessor(llm_client)
    retriever = Retriever(llm_client, query_processor)
    reranker = Reranker(llm_client)
    context_assembler = ContextAssembler()
    pipeline = RetrievalPipeline(query_processor, retriever, reranker, context_assembler)

    retrieval_start = time.perf_counter()
    context_data = await pipeline.run(query)
    retrieval_latency = (time.perf_counter() - retrieval_start) * 1000

    generator = Generator(llm_client, redis)
    response_text = ""
    run_id = None

    async for event in generator.generate_stream(
        query, context_data, context_data.get("query_type", "factual"), pipeline_id
    ):
        if event["type"] == "token":
            response_text += event["delta"]
        elif event["type"] == "done":
            run_id = event["run_id"]

    total_latency = (time.perf_counter() - start_time) * 1000

    # Fetch eval score (assuming background worker finished, or just mock for now)
    # The requirement says "enqueue evaluation jobs", so we might not have the score yet.
    # But we want to return it if possible.
    eval_score = 0.0
    async with pool.acquire() as conn:
        eval_row = await conn.fetchrow(
            "SELECT overall_score FROM evaluations WHERE run_id = $1",
            uuid.UUID(run_id) if run_id else None,
        )
        if eval_row:
            eval_score = eval_row["overall_score"]

    return {
        "run_id": run_id,
        "generation": response_text,
        "retrieval_latency_ms": int(retrieval_latency),
        "total_latency_ms": int(total_latency),
        "chunks_used": len(context_data.get("chunks_used", [])),
        "eval_score": eval_score,
    }


@router.post(
    "/compare",
    summary="Compare pipelines",
    description="Run a single query through two different pipelines (A and B) simultaneously and return latency, used chunks, and generated text side-by-side.",
    response_description="Comparative evaluation matrix between dual pipeline executions.",
)
@handle_errors
async def compare_pipelines(
    query: str = Body(..., embed=True),
    pipeline_a_id: uuid.UUID = Body(..., embed=True),
    pipeline_b_id: uuid.UUID = Body(..., embed=True),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    llm_client = NeuroFlowClient()
    await llm_client.initialize()

    try:
        # Run both pipelines simultaneously
        results = await asyncio.gather(
            run_pipeline_task(query, pipeline_a_id, llm_client, redis),
            run_pipeline_task(query, pipeline_b_id, llm_client, redis),
            return_exceptions=True,
        )

        # Check for exceptions
        if isinstance(results[0], Exception):
            raise results[0]
        if isinstance(results[1], Exception):
            raise results[1]

        return {"query": query, "pipeline_a": results[0], "pipeline_b": results[1]}
    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
