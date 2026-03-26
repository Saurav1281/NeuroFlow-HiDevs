import asyncio
import json
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Body
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from redis.asyncio import Redis

from backend.db.pool import get_pool
from backend.providers.client import NeuroFlowClient
from pipelines.retrieval.query_processor import QueryProcessor
from pipelines.retrieval.retriever import Retriever
from pipelines.retrieval.reranker import Reranker
from pipelines.retrieval.context_assembler import ContextAssembler
from pipelines.retrieval.retrieval_pipeline import RetrievalPipeline
from pipelines.generation.generator import Generator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/query", tags=["query"])

# In-memory store for pending queries (could use Redis for production)
pending_queries = {}

def get_redis():
    from backend.config import settings
    return Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, password=settings.REDIS_PASSWORD)

async def get_pipeline_tools():
    llm_client = NeuroFlowClient()
    await llm_client.initialize()
    
    query_processor = QueryProcessor(llm_client)
    retriever = Retriever(llm_client, query_processor)
    reranker = Reranker(llm_client)
    context_assembler = ContextAssembler()
    
    pipeline = RetrievalPipeline(query_processor, retriever, reranker, context_assembler)
    return pipeline, llm_client

@router.post("")
async def create_query(
    query: str = Body(..., embed=True),
    pipeline_id: uuid.UUID = Body(..., embed=True),
    stream: bool = Body(True, embed=True),
    pipeline_tools = Depends(get_pipeline_tools),
    redis = Depends(get_redis)
):
    pipeline, llm_client = pipeline_tools
    
    if not stream:
        # Synchronous execution
        context_data = await pipeline.run(query)
        generator = Generator(llm_client, redis)
        
        # Collect all tokens
        response_text = ""
        citations = []
        run_id = None
        
        async for event in generator.generate_stream(query, context_data, context_data.get("query_type", "factual"), pipeline_id):
            if event["type"] == "token":
                response_text += event["delta"]
            elif event["type"] == "done":
                citations = event["citations"]
                run_id = event["run_id"]
        
        return {
            "run_id": run_id,
            "response": response_text,
            "citations": citations,
            "sources": context_data.get("sources", [])
        }
    
    # SSE flow: Store query and return run_id
    run_id = str(uuid.uuid4())
    pending_queries[run_id] = {
        "query": query,
        "pipeline_id": pipeline_id
    }
    return {"run_id": run_id}

@router.get("/{run_id}/stream")
async def stream_query(
    run_id: str,
    pipeline_tools = Depends(get_pipeline_tools),
    redis = Depends(get_redis)
):
    if run_id not in pending_queries:
        raise HTTPException(status_code=404, detail="Run not found")
        
    query_data = pending_queries.pop(run_id)
    query = query_data["query"]
    pipeline_id = query_data["pipeline_id"]
    
    pipeline, llm_client = pipeline_tools
    generator = Generator(llm_client, redis)

    async def event_generator():
        # 1. Retrieval Start
        yield {"event": "message", "data": json.dumps({"type": "retrieval_start"})}
        
        # 2. Run Retrieval
        context_data = await pipeline.run(query)
        yield {
            "event": "message", 
            "data": json.dumps({
                "type": "retrieval_complete", 
                "chunk_count": len(context_data.get("chunks_used", [])),
                "sources": [s["document_name"] for s in context_data.get("sources", [])]
            })
        }
        
        # 3. Generation with Keepalive
        # We'll use a task to run the generator and a timer for keepalive
        gen_iter = generator.generate_stream(query, context_data, context_data.get("query_type", "factual"), pipeline_id)
        
        last_event_time = asyncio.get_event_loop().time()
        
        while True:
            try:
                # Wait for next token or timeout for keepalive
                now = asyncio.get_event_loop().time()
                timeout = max(0.1, 15.0 - (now - last_event_time))
                
                try:
                    event = await asyncio.wait_for(gen_iter.__anext__(), timeout=timeout)
                    last_event_time = asyncio.get_event_loop().time()
                    yield {"event": "message", "data": json.dumps(event)}
                    if event["type"] in ["done", "error"]:
                        break
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"event": "keepalive", "data": ""}
                    last_event_time = asyncio.get_event_loop().time()
            except StopAsyncIteration:
                break
            except Exception as e:
                logger.error(f"Stream error: {e}")
                yield {"event": "message", "data": json.dumps({"type": "error", "message": str(e)})}
                break

    return EventSourceResponse(event_generator())
