import asyncpg
from typing import Optional
from backend.config import settings

_pool: Optional[asyncpg.Pool] = None

async def init_pool() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
        min_size=10,
        max_size=50
    )
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()

def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise Exception("Database pool is not initialized")
    return _pool
