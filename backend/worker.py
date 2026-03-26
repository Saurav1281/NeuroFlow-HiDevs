import asyncio
import json
import logging
import os
import signal
from redis.asyncio import Redis

from backend.db.pool import get_pool
from backend.providers.client import NeuroFlowClient
from evaluation.judge import EvaluationJudge
from backend.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("neuroflow.worker")

class EvaluationWorker:
    def __init__(self):
        self.redis = Redis(
            host=settings.REDIS_HOST, 
            port=settings.REDIS_PORT, 
            password=settings.REDIS_PASSWORD
        )
        self.llm_client = NeuroFlowClient(self.redis)
        self.judge = None
        self.running = False

    async def setup(self):
        await self.llm_client.initialize()
        self.judge = EvaluationJudge(self.llm_client)
        logger.info("EvaluationWorker initialized and ready.")

    async def run(self):
        self.running = True
        logger.info("Worker started, listening for evaluation jobs...")
        
        while self.running:
            try:
                # BLPOP blocks until an item is available
                # 0 means wait indefinitely
                job_data = await self.redis.blpop("evaluation_queue", timeout=5)
                
                if job_data:
                    _, payload = job_data
                    job = json.loads(payload)
                    run_id = job.get("run_id")
                    query = job.get("query")
                    response = job.get("response")
                    context_chunks = job.get("context_chunks", [])
                    
                    if not query:
                        # Fetch query from DB if not in job
                        async with get_pool().acquire() as conn:
                            row = await conn.fetchrow("SELECT query FROM pipeline_runs WHERE id = $1", uuid.UUID(run_id))
                            if row:
                                query = row['query']
                    
                    logger.info(f"Processing evaluation for run {run_id}")
                    
                    # Run judge
                    try:
                        result = await self.judge.evaluate_run(
                            run_id=run_id,
                            query=query,
                            answer=response,
                            context_chunks=context_chunks
                        )
                        logger.info(f"Evaluation complete for run {run_id}: {result['overall_score']:.4f}")
                    except Exception as e:
                        logger.error(f"Error evaluating run {run_id}: {e}")
                
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(1)

    def stop(self):
        self.running = False

async def main():
    worker = EvaluationWorker()
    await worker.setup()
    
    # Handle termination signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.stop)
        
    await worker.run()

if __name__ == "__main__":
    import uuid # For evaluation of run_id in fetching query if needed
    asyncio.run(main())
