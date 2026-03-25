import time
import json
import logging
from typing import Dict, Any

from opentelemetry import trace

from db.pool import get_pool
from providers.client import NeuroFlowClient
from .chunker import Chunker
from .extractors import (
    PDFExtractor, 
    DocxExtractor, 
    ImageExtractor, 
    CSVExtractor, 
    URLExtractor, 
    PPTXExtractor
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("neuroflow.ingestion")

async def process_document(
    ctx: dict, 
    document_id: str, 
    file_path: str = None, 
    source_type: str = "pdf", 
    url: str = None
) -> None:
    """Arq background task to process a document.
    
    1. Extracts pages using appropriate extractor
    2. Chunks the pages using auto-selection
    3. Embeds chunks via LLM provider
    4. Saves to PostgreSQL DB
    """
    start_time = time.perf_counter()
    pool = get_pool()
    client = NeuroFlowClient()
    
    with tracer.start_as_current_span("ingestion.process") as span:
        span.set_attribute("document_id", document_id)
        span.set_attribute("source_type", source_type)
        
        try:
            # Update status to processing
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE documents SET status = 'processing' WHERE id = $1", 
                    document_id
                )
            
            # 1. Select Extractor
            if source_type == "pdf":
                extractor = PDFExtractor()
            elif source_type == "docx":
                extractor = DocxExtractor()
            elif source_type in ("image", "jpeg", "png", "webp"):
                extractor = ImageExtractor()
            elif source_type == "csv":
                extractor = CSVExtractor()
            elif source_type == "url":
                extractor = URLExtractor()
            elif source_type == "pptx":
                extractor = PPTXExtractor()
            else:
                raise ValueError(f"Unknown source_type: {source_type}")
                
            # Execute Extraction
            if url and source_type == "url":
                pages = await extractor.extract(url)
            else:
                pages = await extractor.extract(file_path)
                
            span.set_attribute("page_count", len(pages))
            
            if not pages:
                raise ValueError("Extractor returned 0 pages.")
                
            # 2. Chunking
            chunker = Chunker()
            chunks = await chunker.auto_chunk(pages, document_source=source_type)
            
            span.set_attribute("chunk_count", len(chunks))
            
            if not chunks:
                raise ValueError("Chunker returned 0 chunks.")
                
            # 3. Embedding (batch)
            chunk_texts = [c.content for c in chunks]
            embeddings = await client.embed(chunk_texts)
            
            span.set_attribute("embedding_calls", 1)  # Batching internally
            
            # 4. Save chunks to DB
            total_tokens = 0
            async with pool.acquire() as conn:
                async with conn.transaction():
                    for idx, chunk in enumerate(chunks):
                        total_tokens += chunk.token_count
                        # Ensure embedding is valid size (1536)
                        emb = embeddings[idx] if idx < len(embeddings) else None
                        
                        await conn.execute(
                            """
                            INSERT INTO chunks (document_id, content, embedding, chunk_index, token_count, metadata)
                            VALUES ($1, $2, $3::vector, $4, $5, $6::jsonb)
                            """,
                            document_id, 
                            chunk.content, 
                            str(emb) if emb else None, 
                            idx, 
                            chunk.token_count, 
                            json.dumps(chunk.metadata)
                        )
                        
                    # Update document record
                    await conn.execute(
                        """
                        UPDATE documents 
                        SET status = 'complete', chunk_count = $1 
                        WHERE id = $2
                        """,
                        len(chunks), document_id
                    )
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Structured Logging
            log_data = {
                "event": "ingestion_complete",
                "document_id": document_id,
                "duration_ms": round(duration_ms, 2),
                "chunks": len(chunks),
                "tokens": total_tokens
            }
            logger.info(json.dumps(log_data))

        except Exception as e:
            logger.error(f"Failed to process document {document_id}: {e}")
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            
            # Update status to error
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE documents SET status = 'error', metadata = jsonb_set(metadata, '{error}', $1) WHERE id = $2",
                    json.dumps(str(e)), document_id
                )
