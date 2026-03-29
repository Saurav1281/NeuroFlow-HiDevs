import asyncio
import json
import logging
import uuid
import numpy as np
from typing import Any, Optional
from opentelemetry import trace

from backend.db.pool import get_pool
from evaluation.metrics.faithfulness import evaluate_faithfulness
from evaluation.metrics.answer_relevance import evaluate_answer_relevance
from evaluation.metrics.context_precision import evaluate_context_precision
from evaluation.metrics.context_recall import evaluate_context_recall

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("neuroflow.evaluation")

class EvaluationJudge:
    """
    Automated Evaluation Judge — LLM-as-Judge with RAGAS Metrics.
    Runs faithfulness, relevance, precision, and recall in parallel.
    """
    
    def __init__(self, llm_client: Any, redis: Optional[Any] = None):
        self.llm_client = llm_client
        self.pool = get_pool()
        self.redis = redis

    async def evaluate_run(
        self, 
        run_id: str, 
        query: str, 
        answer: str, 
        context_chunks: list[str],
        self_consistency: bool = True
    ) -> dict[str, Any]:
        """Runs the full evaluation suite for a single pipeline run."""
        
        with tracer.start_as_current_span("evaluation.judge") as span:
            span.set_attribute("run_id", run_id)
            
            num_runs = 3 if self_consistency else 1
            all_metrics_runs = []
            
            # Faithfulness needs the full context string
            context_str = "\n\n".join(context_chunks)
            
            for i in range(num_runs):
                # Run all four metrics in parallel via asyncio.gather
                # Total time should be ~1 LLM call latency (as they run in parallel)
                metrics_tasks = [
                    evaluate_faithfulness(query, answer, context_str, self.llm_client),
                    evaluate_answer_relevance(query, answer, self.llm_client),
                    evaluate_context_precision(query, context_chunks, answer, self.llm_client),
                    evaluate_context_recall(query, context_chunks, answer, self.llm_client)
                ]
                
                results = await asyncio.gather(*metrics_tasks)
                all_metrics_runs.append({
                    "faithfulness": results[0],
                    "answer_relevance": results[1],
                    "context_precision": results[2],
                    "context_recall": results[3]
                })

            # Average results across runs
            avg_faithfulness = float(np.mean([r["faithfulness"] for r in all_metrics_runs]))
            avg_relevance = float(np.mean([r["answer_relevance"] for r in all_metrics_runs]))
            avg_precision = float(np.mean([r["context_precision"] for r in all_metrics_runs]))
            avg_recall = float(np.mean([r["context_recall"] for r in all_metrics_runs]))
            
            # Weighted overall score calculation
            overall_score = (
                0.35 * avg_faithfulness + 
                0.30 * avg_relevance + 
                0.20 * avg_precision + 
                0.15 * avg_recall
            )
            
            # Self-consistency check (standard deviation across runs)
            all_run_overalls = [
                0.35 * r["faithfulness"] + 0.30 * r["answer_relevance"] + 
                0.20 * r["context_precision"] + 0.15 * r["context_recall"]
                for r in all_metrics_runs
            ]
            std_dev = float(np.std(all_run_overalls)) if len(all_run_overalls) > 1 else 0.0
            high_variance = std_dev > 0.2
            
            # Set span attributes for observability
            span.set_attribute("faithfulness", avg_faithfulness)
            span.set_attribute("answer_relevance", avg_relevance)
            span.set_attribute("context_precision", avg_precision)
            span.set_attribute("context_recall", avg_recall)
            span.set_attribute("overall_score", overall_score)
            span.set_attribute("std_dev", std_dev)
            span.set_attribute("high_variance", high_variance)

            # Record result in evaluations table
            judge_model = "gpt-4o" 
            eval_metadata = {
                "std_dev": std_dev,
                "high_variance": high_variance,
                "num_consistency_runs": num_runs
            }
            
            await self._save_evaluation(
                run_id=uuid.UUID(run_id),
                faithfulness=avg_faithfulness,
                relevance=avg_relevance,
                precision=avg_precision,
                recall=avg_recall,
                overall=overall_score,
                judge_model=judge_model,
                metadata=eval_metadata
            )
            
            # If high quality, extract as training pair candidate
            if overall_score > 0.8:
                await self._extract_training_pair(run_id, overall_score)
                
            return {
                "faithfulness": avg_faithfulness,
                "answer_relevance": avg_relevance,
                "context_precision": avg_precision,
                "context_recall": avg_recall,
                "overall_score": overall_score,
                "high_variance": high_variance
            }

    async def _save_evaluation(self, run_id, faithfulness, relevance, precision, recall, overall, judge_model, metadata):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO evaluations (
                    run_id, faithfulness, answer_relevance, context_precision, 
                    context_recall, overall_score, judge_model, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                run_id, faithfulness, relevance, precision, recall, overall, judge_model, json.dumps(metadata)
            )
            
            # Publish to Redis for real-time SSE feed
            if self.redis:
                try:
                    # Fetch extra details for the feed
                    row = await conn.fetchrow(
                        """
                        SELECT pr.query, p.name as pipeline_name 
                        FROM pipeline_runs pr
                        JOIN pipelines p ON pr.pipeline_id = p.id
                        WHERE pr.id = $1
                        """,
                        run_id
                    )
                    
                    event_data = {
                        "run_id": str(run_id),
                        "query": row["query"] if row else "Unknown",
                        "pipeline_name": row["pipeline_name"] if row else "Unknown",
                        "faithfulness": faithfulness,
                        "relevance": relevance,
                        "precision": precision,
                        "recall": recall,
                        "overall_score": overall,
                        "timestamp": "now" # Frontend will handle or we can use ISO
                    }
                    await self.redis.publish("evaluations:new", json.dumps(event_data))
                except Exception as e:
                    logger.error(f"Failed to publish evaluation to Redis: {e}")

    async def _extract_training_pair(self, run_id, score):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT query, generation FROM pipeline_runs WHERE id = $1",
                uuid.UUID(run_id)
            )
            if row:
                system_prompt = "You are a helpful assistant for NeuroFlow. Answer the user prompt accurately based on the provided context."
                await conn.execute(
                    """
                    INSERT INTO training_pairs (run_id, system_prompt, user_message, assistant_message, quality_score)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    uuid.UUID(run_id), system_prompt, row['query'], row['generation'], score
                )
