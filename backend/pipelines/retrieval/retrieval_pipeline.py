import logging
import time
from typing import Any
from opentelemetry import trace
from backend.monitoring.metrics import retrieval_latency

from backend.pipelines.retrieval.query_processor import QueryProcessor
from backend.pipelines.retrieval.retriever import Retriever
from backend.pipelines.retrieval.reranker import Reranker
from backend.pipelines.retrieval.context_assembler import ContextAssembler

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("neuroflow.retrieval")

class RetrievalPipeline:
    """Production-grade retrieval pipeline with RRF and Reranking."""
    
    def __init__(
        self, 
        query_processor: QueryProcessor,
        retriever: Retriever,
        reranker: Reranker,
        context_assembler: ContextAssembler
    ):
        self.query_processor = query_processor
        self.retriever = retriever
        self.reranker = reranker
        self.context_assembler = context_assembler

    async def run(
        self, 
        query: str, 
        pipeline_id: str = "default",
        k: int = 10, 
        use_hyde: bool = True,
        search_k: int = 100,
        use_local_reranker: bool = True
    ) -> dict[str, Any]:
        """Runs the full retrieval pipeline with tracing."""
        start_time = time.time()
        with tracer.start_as_current_span("retrieval.pipeline") as span:
            span.set_attribute("query", query)
            span.set_attribute("pipeline_id", str(pipeline_id))
            span.set_attribute("k", k)
            span.set_attribute("use_hyde", use_hyde)
            
            logger.info(f"Running retrieval pipeline for: '{query}' (HyDE: {use_hyde})")
            
            # Step 1: Process
            processed = await self.query_processor.process(query)
            
            # Step 2-3: Retrieve
            fused_results = await self.retriever.retrieve(
                query, 
                pipeline_id=pipeline_id,
                k=search_k, 
                use_hyde=use_hyde, 
                processed_query=processed
            )
            span.set_attribute("num_fused_results", len(fused_results))
            
            # Step 4: Reranking
            reranked_results = await self.reranker.rerank(
                query=query,
                candidates=fused_results,
                top_n=100,
                pipeline_id=pipeline_id,
                use_local=use_local_reranker
            )
            span.set_attribute("num_reranked_results", len(reranked_results))
            
            # Step 5: Context assembly
            top_k = reranked_results[:k]
            context_data = self.context_assembler.assemble(top_k, pipeline_id=pipeline_id)
            span.set_attribute("total_tokens", context_data.get("total_tokens", 0))
            
            # Add reranked results for evaluation
            context_data["reranked_results"] = reranked_results
            context_data["query_type"] = processed.query_type
            
            # Update metric
            retrieval_latency.labels(strategy="hybrid-rrf-rerank").observe(time.time() - start_time)
            
            return context_data
