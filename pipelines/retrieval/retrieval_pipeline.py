import logging
from typing import Any

from pipelines.retrieval.query_processor import QueryProcessor
from pipelines.retrieval.retriever import Retriever
from pipelines.retrieval.reranker import Reranker
from pipelines.retrieval.context_assembler import ContextAssembler

logger = logging.getLogger(__name__)

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
        """Runs the full retrieval pipeline:
        1. Query processing (expansion, filters, type)
        2. Parallel retrieval (dense, sparse, metadata)
        3. RRF Fusion
        4. Cross-encoder reranking
        5. Context assembly
        """
        logger.info(f"Running retrieval pipeline for: '{query}'")
        
        # Steps 1-3 happen inside retriever.retrieve()
        fused_results = await self.retriever.retrieve(query, k=40)
        
        # Step 4: Reranking
        reranked_results = await self.reranker.rerank(
            query=query,
            candidates=fused_results,
            top_n=40,
            use_local=use_local_reranker
        )
        
        # Step 5: Context assembly (top k)
        top_k = reranked_results[:k]
        context_data = self.context_assembler.assemble(top_k)
        
        return context_data
