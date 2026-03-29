import json
import asyncio
import logging
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from redis.asyncio import Redis
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evaluations", tags=["evaluations"])

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
