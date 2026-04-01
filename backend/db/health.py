import logging

import httpx
from redis.asyncio import Redis

from backend.config import settings
from backend.db.pool import get_pool

logger = logging.getLogger(__name__)


async def check_postgres() -> bool:
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Postgres health check failed: {e}")
        return False


async def check_redis() -> bool:
    try:
        redis = Redis.from_url(
            settings.get_redis_url(),
            socket_connect_timeout=2.0,
        )
        await redis.ping()
        await redis.aclose()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


async def check_mlflow() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(settings.MLFLOW_TRACKING_URI)
            return True if response.status_code >= 200 else False
    except Exception as e:
        logger.error(f"MLflow health check failed: {e}")
        return False
