import asyncio
import json
import logging
import signal
import uuid

from redis.asyncio import Redis

from backend.config import settings
from backend.db.pool import get_pool
from backend.monitoring.anomaly_observer import AnomalyObserver
from backend.monitoring.metrics import queue_depth
from backend.providers.client import NeuroFlowClient
from evaluation.judge import EvaluationJudge

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("neuroflow.worker")


class EvaluationWorker:
    def __init__(self) -> None:
        self.redis: Redis = Redis(
            host=settings.REDIS_HOST, port=settings.REDIS_PORT, password=settings.REDIS_PASSWORD
        )
        self.llm_client: NeuroFlowClient = NeuroFlowClient(self.redis)
        self.judge: EvaluationJudge | None = None
        self.anomaly_observer: AnomalyObserver = AnomalyObserver()
        self.running: bool = False

    async def setup(self) -> None:
        await self.llm_client.initialize()
        self.judge = EvaluationJudge(self.llm_client, self.redis)
        logger.info("EvaluationWorker initialized and ready.")

    async def run(self) -> None:
        self.running = True
        logger.info("Worker started, listening for evaluation jobs...")

        # Start AnomalyObserver in the background
        asyncio.create_task(self.anomaly_observer.start())

        while self.running:
            try:
                # Update queue depth metric
                depth = await self.redis.llen("evaluation_queue")
                queue_depth.set(depth)

                # BLPOP blocks until an item is available
                job_data = await self.redis.blpop("evaluation_queue", timeout=5)

                if job_data:
                    # Metric update immediately after popping
                    queue_depth.set(await self.redis.llen("evaluation_queue"))

                    _, payload = job_data
                    job = json.loads(payload)
                    run_id = job.get("run_id")
                    query = job.get("query")
                    response = job.get("response")
                    context_chunks = job.get("context_chunks", [])

                    if not query:
                        # Fetch query from DB if not in job
                        async with get_pool().acquire() as conn:
                            row = await conn.fetchrow(
                                "SELECT query FROM pipeline_runs WHERE id = $1", uuid.UUID(run_id)
                            )
                            if row:
                                query = row["query"]

                    logger.info(f"Processing evaluation for run {run_id}")

                    # Run judge
                    try:
                        result = await self.judge.evaluate_run(
                            run_id=run_id,
                            query=query,
                            answer=response,
                            context_chunks=context_chunks,
                        )
                        logger.info(
                            f"Evaluation complete for run {run_id}: {result['overall_score']:.4f}"
                        )
                    except Exception as e:
                        logger.error(f"Error evaluating run {run_id}: {e}")

            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(1)

    def stop(self) -> None:
        self.running = False


async def main() -> None:
    worker = EvaluationWorker()
    await worker.setup()

    # Handle termination signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.stop)

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
