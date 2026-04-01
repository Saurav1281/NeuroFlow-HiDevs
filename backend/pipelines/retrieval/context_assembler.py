import logging
from typing import Any

import tiktoken

from opentelemetry import trace
from backend.pipelines.retrieval.fusion import RetrievalResult

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("neuroflow.retrieval")

class ContextAssembler:
    """Assembles retrieved chunks into a context window respecting token limits."""
    
    def __init__(self, token_budget: int = 4000, model_name: str = "gpt-4o"):
        self.token_budget = token_budget
        try:
            self.encoding = tiktoken.encoding_for_model(model_name)
        except Exception:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def assemble(self, chunks: list[RetrievalResult], pipeline_id: str = "default") -> dict[str, Any]:
        """Assembles chunks into a formatted string within the token budget.
        
        Uses 'Lost-in-the-Middle' re-ordering: places most relevant chunks 
        at the beginning and end of the context window.
        
        Returns:
            Dict with context string, chunks used, total tokens, and sources.
        """
        with tracer.start_as_current_span("retrieval.assemble") as span:
            span.set_attribute("pipeline_id", str(pipeline_id))
            span.set_attribute("num_chunks", len(chunks))
            
            # Re-order chunks: [1, 3, 5, ..., 6, 4, 2]
            if len(chunks) > 2:
                reordered = []
                for i in range(len(chunks)):
                    if i % 2 == 0:
                        reordered.append(chunks[i])
                    else:
                        reordered.insert(0, chunks[i])
                chunks = reordered

            assembled_context = []
            chunks_used = []
            sources = []
            current_tokens = 0
            
            for i, chunk in enumerate(chunks):
                # Format: [Source N — document_name.pdf, page M] {chunk.content}
                source_label = f"Source {i+1}"
                metadata_str = f"{chunk.document_name}"
                if chunk.page_number:
                    metadata_str += f", page {chunk.page_number}"
                    
                header = f"\n[{source_label} — {metadata_str}]\n"
                content = f"{chunk.content}\n"
                
                chunk_text = header + content
                chunk_tokens = len(self.encoding.encode(chunk_text))
                
                if current_tokens + chunk_tokens > self.token_budget:
                    logger.info(f"Token budget reached: {current_tokens}/{self.token_budget}. Skipping remaining chunks.")
                    break
                    
                assembled_context.append(chunk_text)
                chunks_used.append(chunk.chunk_id)
                sources.append({
                    "label": source_label,
                    "document_name": chunk.document_name,
                    "page_number": chunk.page_number,
                    "chunk_id": chunk.chunk_id
                })
                current_tokens += chunk_tokens

            span.set_attribute("total_tokens", current_tokens)
            return {
                "context_string": "".join(assembled_context).strip(),
                "chunks_used": chunks_used,
                "total_tokens": current_tokens,
                "sources": sources
            }
