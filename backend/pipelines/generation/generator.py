import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Optional

from opentelemetry import trace
from redis.asyncio import Redis

from backend.db.pool import get_pool
from backend.providers.client import NeuroFlowClient
from backend.providers.base import ChatMessage
from backend.providers.router import RoutingCriteria
from backend.pipelines.generation.prompt_builder import PromptBuilder
from backend.pipelines.generation.citations import CitationProcessor
from backend.monitoring.metrics import (
    queries_total, 
    generation_latency, 
    llm_calls_total, 
    llm_cost
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("neuroflow.generation")

class Generator:
    """Manages RAG response generation with streaming and citations."""
    
    def __init__(self, llm_client: NeuroFlowClient, redis: Redis):
        self.llm_client = llm_client
        self.redis = redis
        self.prompt_builder = PromptBuilder()
        self.citation_processor = CitationProcessor()
        self.pool = get_pool()

    async def generate_stream(
        self, 
        query: str, 
        context_data: dict[str, Any], 
        query_type: str,
        pipeline_id: uuid.UUID
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Streams tokens and metadata, then processes citations and logs results."""
        
        with tracer.start_as_current_span("generation.pipeline") as span:
            run_id = uuid.uuid4()
            span.set_attribute("run_id", str(run_id))
            span.set_attribute("pipeline_id", str(pipeline_id))
            span.set_attribute("query", query)
            
            with tracer.start_as_current_span("generation.prompt_build"):
                messages = self.prompt_builder.assemble_messages(query, context_data["context_string"], query_type)
            
            # 1. Log prompt to pipeline_runs
            with tracer.start_as_current_span("generation.log_run"):
                await self._log_initial_run(run_id, pipeline_id, messages)
            
            full_response = ""
            start_time = time.perf_counter()
            model_used = "gpt-4o-mini"
            
            # 2. Stream tokens
            try:
                with tracer.start_as_current_span("generation.llm_call") as llm_span:
                    llm_span.set_attribute("model", model_used)
                    async for token in self.llm_client.stream(
                        messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages],
                        routing_criteria=RoutingCriteria(task_type="rag_generation")
                    ):
                        full_response += token
                        yield {"type": "token", "delta": token}
                    
                    llm_calls_total.labels(provider="openai", model=model_used, task_type="rag_generation").inc()
                    
                latency_s = time.perf_counter() - start_time
                generation_latency.labels(model=model_used).observe(latency_s)
                
                # 3. Post-processing
                clean_response = full_response
                thinking = ""
                if "<think>" in full_response and "</think>" in full_response:
                    thinking = full_response.split("<think>")[1].split("</think>")[0]
                    clean_response = full_response.split("</think>")[1].strip()
                
                # 4. Parse Citations
                with tracer.start_as_current_span("generation.citation_parse") as cite_span:
                    citations = self.citation_processor.parse_citations(clean_response, context_data)
                    cite_span.set_attribute("citation_count", len(citations))
                
                # 5. Final update to pipeline_runs
                input_tokens = sum(len(m["content"]) // 4 for m in messages) 
                output_tokens = len(full_response) // 4
                
                # Estimate cost
                cost = (input_tokens * 0.00015 / 1000) + (output_tokens * 0.0006 / 1000)
                llm_cost.labels(model=model_used).observe(cost)
                
                with tracer.start_as_current_span("generation.log_run"):
                    await self._update_final_run(
                        run_id=run_id,
                        generation=clean_response,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_s * 1000,
                        metadata={
                            "thinking": thinking,
                            "raw_response": full_response,
                            "query_type": query_type,
                            "citations": [c.__dict__ for c in citations]
                        }
                    )
                
                # 6. Asynchronous evaluation enqueue
                await self._enqueue_evaluation(run_id, clean_response, context_data)
                
                queries_total.labels(pipeline_id=str(pipeline_id), status="success").inc()
                
                yield {
                    "type": "done", 
                    "run_id": str(run_id), 
                    "citations": [
                        {
                            "source": c.reference, 
                            "chunk_id": c.chunk_id, 
                            "document": c.document_name, 
                            "page": c.page_number,
                            "invalid": c.invalid_citation
                        } for c in citations
                    ]
                }
                
            except Exception as e:
                logger.error(f"Generation failed: {e}")
                queries_total.labels(pipeline_id=str(pipeline_id), status="error").inc()
                await self._update_run_status(run_id, "failed", error=str(e))
                yield {"type": "error", "message": str(e)}

    async def _log_initial_run(self, run_id: uuid.UUID, pipeline_id: uuid.UUID, messages: list[dict]):
        async with self.pool.acquire() as conn:
            # Fetch version for the given pipeline_id
            version = await conn.fetchval("SELECT version FROM pipelines WHERE id = $1", pipeline_id)
            
            await conn.execute(
                """
                INSERT INTO pipeline_runs (id, pipeline_id, pipeline_version, prompt, status, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                """,
                run_id, pipeline_id, version, json.dumps(messages), "running"
            )

    async def _update_final_run(self, run_id: uuid.UUID, generation: str, input_tokens: int, output_tokens: int, latency_ms: float, metadata: dict):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE pipeline_runs
                SET generation = $2, input_tokens = $3, output_tokens = $4, 
                    latency_ms = $5, status = $6, metadata = $7, updated_at = NOW()
                WHERE id = $1
                """,
                run_id, generation, input_tokens, output_tokens, latency_ms, "complete", json.dumps(metadata)
            )

    async def _update_run_status(self, run_id: uuid.UUID, status: str, error: Optional[str] = None):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE pipeline_runs SET status = $2, metadata = metadata || $3::jsonb WHERE id = $1",
                run_id, status, json.dumps({"error": error}) if error else "{}"
            )

    async def _enqueue_evaluation(self, run_id: uuid.UUID, response: str, context_data: dict):
        """Asynchronously enqueues an evaluation job in Redis."""
        job = {
            "run_id": str(run_id),
            "response": response,
            "context_chunks": context_data.get("chunks_used", []),
            "timestamp": time.time()
        }
        await self.redis.lpush("evaluation_queue", json.dumps(job))
        logger.info(f"Enqueued evaluation job for run {run_id}")
