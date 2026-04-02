import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.db.pool import get_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.get(
    "/{run_id}",
    summary="Get run evaluation",
    description="Fetch automated evaluation scores (faithfulness, relevance) and metadata for a specific query run.",
    response_description="Detailed assessment metrics for the query execution."
)
async def get_evaluation(run_id: uuid.UUID) -> dict[str, Any]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, run_id, overall_score, faithfulness_score, relevance_score, 
                   metadata, created_at FROM evaluations WHERE run_id = $1
            """,
            run_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Evaluation not found")

        return {
            "id": str(row["id"]),
            "run_id": str(row["run_id"]),
            "overall_score": row["overall_score"],
            "faithfulness_score": row["faithfulness_score"],
            "relevance_score": row["relevance_score"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
        }


def get_redis() -> Redis:
    return Redis(
        host=settings.REDIS_HOST, port=settings.REDIS_PORT, password=settings.REDIS_PASSWORD
    )


@router.get(
    "/stream",
    summary="Stream live evaluations",
    description="Subscribe to a Server-Sent Events (SSE) stream of real-time evaluation results as they complete.",
    response_description="An EventSource stream yielding live, real-time evaluation data chunks."
)
async def stream_evaluations(redis: Redis = Depends(get_redis)) -> EventSourceResponse:
    """
    SSE endpoint that streams new evaluation records as they are created.
    Uses Redis Pub/Sub channel 'evaluations:new'.
    """

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        pubsub = redis.pubsub()
        await pubsub.subscribe("evaluations:new")

        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is not None:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield {"event": "message", "data": data}
                await asyncio.sleep(0.1)  # Prevent tight loop
        except asyncio.CancelledError:
            await pubsub.unsubscribe("evaluations:new")
            await pubsub.close()
            raise
        except Exception as e:
            logger.error(f"Evaluation stream error: {e}")
            yield {"event": "error", "data": str(e)}
        finally:
            await pubsub.unsubscribe("evaluations:new")
            await pubsub.close()

    return EventSourceResponse(event_generator())
