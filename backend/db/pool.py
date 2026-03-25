import asyncpg
from typing import Optional
from config import settings
import logging

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None

async def init_pool() -> Optional[asyncpg.Pool]:
    global _pool
    try:
        _pool = await asyncpg.create_pool(
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            database=settings.POSTGRES_DB,
            min_size=1,
            max_size=10
        )
    except Exception as e:
        logger.error(f"Failed to initialize pool: {e}")
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()

def get_pool() -> Optional[asyncpg.Pool]:
    if _pool is None:
        logger.warning("Database pool is not initialized")
    return _pool
