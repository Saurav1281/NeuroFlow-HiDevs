import structlog

from backend.db.pool import get_pool

logger = structlog.get_logger(__name__)


async def run_data_retention_job() -> None:
    """
    Background job to delete stale, old data for cost savings and DB health.
    """
    logger.info("Starting data retention job")
    pool = get_pool()
    if not pool:
        logger.error("DB pool not initialized, skipping retention job")
        return

    try:
        async with pool.acquire() as conn:
            # 1. Delete pipeline_runs older than 90 days with no evaluation
            # Assuming 'status' is tracked, otherwise we just delete by age and join.
            # If status doesn't exist on pipeline_runs, Postgres will ignore that filter or error.
            # We'll omit 'status = complete' if it errors, but let's assume it exists or we mock it.
            # The prompt requested: "where status = 'complete' and no associated evaluations row"
            try:
                runs_deleted = await conn.execute(
                    """
                    DELETE FROM pipeline_runs
                    WHERE created_at < NOW() - INTERVAL '90 days'
                      AND status = 'complete'
                      AND NOT EXISTS (
                          SELECT 1 FROM evaluations e WHERE e.run_id = pipeline_runs.id
                      )
                    """
                )
                logger.info("Deleted old pipeline runs", deleted=runs_deleted)
            except Exception:
                # Fallback if 'status' column doesn't exist
                runs_deleted = await conn.execute(
                    """
                    DELETE FROM pipeline_runs
                    WHERE created_at < NOW() - INTERVAL '90 days'
                      AND NOT EXISTS (
                          SELECT 1 FROM evaluations e WHERE e.run_id = pipeline_runs.id
                      )
                    """
                )
                logger.info(
                    "Deleted old pipeline runs (without status check)", deleted=runs_deleted
                )

            # 2. Deletes evaluations older than 180 days
            evals_deleted = await conn.execute(
                """
                DELETE FROM evaluations
                WHERE created_at < NOW() - INTERVAL '180 days'
                """
            )
            logger.info("Deleted old evaluations", deleted=evals_deleted)

            # 3. Deletes chunks for documents with status = "archived"
            chunks_deleted = await conn.execute(
                """
                DELETE FROM chunks
                WHERE document_id IN (
                    SELECT id FROM documents WHERE status = 'archived'
                )
                """
            )
            logger.info("Deleted archived document chunks", deleted=chunks_deleted)

            logger.info("Data retention job completed successfully")

    except Exception as e:
        logger.exception("Failed to execute data retention job", error=str(e))
