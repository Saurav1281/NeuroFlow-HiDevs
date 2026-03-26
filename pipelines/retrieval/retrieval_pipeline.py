import logging
from typing import Any
from opentelemetry import trace

from pipelines.retrieval.query_processor import QueryProcessor
from pipelines.retrieval.retriever import Retriever
from pipelines.retrieval.reranker import Reranker
from pipelines.retrieval.context_assembler import ContextAssembler

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

    async def run(self, query: str, k: int = 10, use_local_reranker: bool = True) -> dict[str, Any]:
        """Runs the full retrieval pipeline with tracing."""
        with tracer.start_as_current_span("retrieval_pipeline.run") as span:
            span.set_attribute("query", query)
            span.set_attribute("k", k)
            
            logger.info(f"Running retrieval pipeline for: '{query}'")
            
            # Step 1-3: Process and Retrieve
            fused_results = await self.retriever.retrieve(query, k=40)
            span.set_attribute("num_fused_results", len(fused_results))
            
            # Step 4: Reranking
            reranked_results = await self.reranker.rerank(
                query=query,
                candidates=fused_results,
                top_n=40,
                use_local=use_local_reranker
            )
            span.set_attribute("num_reranked_results", len(reranked_results))
            
            # Step 5: Context assembly
            top_k = reranked_results[:k]
            context_data = self.context_assembler.assemble(top_k)
            span.set_attribute("total_tokens", context_data.get("total_tokens", 0))
            
            return context_data
