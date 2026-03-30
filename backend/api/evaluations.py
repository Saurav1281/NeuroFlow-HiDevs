import json
import asyncio
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from redis.asyncio import Redis
from backend.config import settings
from backend.db.pool import get_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evaluations", tags=["evaluations"])

@router.get("/{run_id}")
async def get_evaluation(run_id: uuid.UUID):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, run_id, overall_score, faithfulness_score, relevance_score, metadata, created_at FROM evaluations WHERE run_id = $1",
            run_id
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
            "created_at": row["created_at"]
        }

def get_redis():
    return Redis(
        host=settings.REDIS_HOST, 
        port=settings.REDIS_PORT, 
        password=settings.REDIS_PASSWORD
    )

@router.get("/stream")
async def stream_evaluations(redis: Redis = Depends(get_redis)):
    """
    SSE endpoint that streams new evaluation records as they are created.
    Uses Redis Pub/Sub channel 'evaluations:new'.
    """
    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe("evaluations:new")
        
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is not None:
                    data = message['data']
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')
                    yield {
                        "event": "message",
                        "data": data
                    }
                await asyncio.sleep(0.1) # Prevent tight loop
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
