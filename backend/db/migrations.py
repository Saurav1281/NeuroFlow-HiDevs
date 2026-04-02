import logging

from backend.db.pool import get_pool

logger = logging.getLogger(__name__)


async def check_migrations() -> None:
    """Verify if the expected tables have been created by docker initdb"""
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT to_regclass('public.chunks')")
            if not val:
                logger.warning(
                    "Tables not found. Ensure infra/init SQL scripts successfully executed."
                )
            else:
                logger.info("Database schema validated.")
    except Exception as e:
        logger.error(f"Error checking migrations: {e}")
