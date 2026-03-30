import uuid
import logging
import hashlib
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from opentelemetry import trace
from backend.db.pool import get_pool
from backend.utils.logger import handle_errors
from backend.monitoring.metrics import ingestion_docs_total
from backend.security.auth import get_current_user
from backend.security.validators import validate_url, validate_file
from backend.security.secret_detector import scan_and_redact_secrets
from backend.security.prompt_injection import check_injection_patterns
from backend.security.sandbox import process_document_sandboxed
from fastapi import Security, Body

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("neuroflow.ingestion")
router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("")
@handle_errors
async def upload_documents(
    files: List[UploadFile] = File(...),
    current_user = Security(get_current_user, scopes=["ingest"])
):
    """
    Simulate document upload and ingestion with instrumentation and security hardening.
    """
    with tracer.start_as_current_span("ingestion.process") as span:
        span.set_attribute("file_count", len(files))
        pool = get_pool()
        uploaded_ids = []
        
        async with pool.acquire() as conn:
            for file in files:
                # 1. File type and magic bytes validation
                await validate_file(file)
                
                content = await file.read()
                await file.seek(0)
                content_hash = hashlib.sha256(content).hexdigest()
                
                # Check for existing document with same hash
                existing_doc = await conn.fetchrow(
                    "SELECT id FROM documents WHERE content_hash = $1 LIMIT 1",
                    content_hash
                )
                
                if existing_doc:
                    uploaded_ids.append({
                        "id": str(existing_doc["id"]),
                        "duplicate": True,
                        "metadata": {"status": "existing"}
                    })
                    continue

                doc_id = uuid.uuid4()
                source_type = file.filename.split('.')[-1] if '.' in file.filename else 'text'
                if source_type not in ['pdf','docx','image','csv','url','text']:
                    source_type = 'text'
                
                # Nested spans for the pipeline steps
                with tracer.start_as_current_span(f"ingestion.extract.{source_type}"):
                    # Simulation: extract content
                    content = await file.read()
                    await file.seek(0)
                    
                    # Real Sandbox Extraction
                    extracted_text = process_document_sandboxed(content, file.filename)
                    span.set_attribute("extracted_text_length", len(extracted_text))
                
                with tracer.start_as_current_span(f"ingestion.security_check"):
                    # 1. Prompt Injection Detection (L1)
                    injection_result = check_injection_patterns(extracted_text)
                    if injection_result["prompt_injection_detected"]:
                        logger.warning(f"Prompt injection detected in document {file.filename}: {injection_result['pattern']}")
                        # In real app, we'd add this to metadata
                    
                    # 2. Secret Redaction
                    sanitized_content = scan_and_redact_secrets(extracted_text, str(doc_id))
                
                with tracer.start_as_current_span("ingestion.chunk"):
                    await conn.execute(
                        """
                        INSERT INTO documents (id, filename, source_type, content_hash, status, created_at)
                        VALUES ($1, $2, $3, $4, $5, NOW())
                        """,
                        doc_id, file.filename, source_type, content_hash, "processing"
                    )
                
                # Simulation outputs for testing
                doc_metadata = {"prompt_injection_detected": injection_result["prompt_injection_detected"]}
                
                # 2. Update metrics
                ingestion_docs_total.labels(source_type=source_type).inc()
                uploaded_ids.append({
                    "id": str(doc_id),
                    "sanitized_content": sanitized_content,
                    "metadata": doc_metadata
                })
            
        return {"message": f"Uploaded {len(files)} files", "documents": uploaded_ids}

@router.post("/ingest")
@handle_errors
async def ingest_url(
    url: str = Body(..., embed=True),
    current_user = Security(get_current_user, scopes=["ingest"])
):
    """
    Ingest document from URL with SSRF protection.
    """
    validate_url(url)
    
    # Simulate ingestion
    doc_id = uuid.uuid4()
    return {"message": "URL ingestion initiated", "document_id": str(doc_id), "url": url}

@router.get("")
@handle_errors
async def list_documents():
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, filename, source_type, status, chunk_count, created_at FROM documents ORDER BY created_at DESC"
        )
        return [
            {
                "id": str(row["id"]),
                "filename": row["filename"],
                "type": row["source_type"],
                "status": row["status"],
                "chunk_count": row["chunk_count"] or 0,
                "created_at": row["created_at"]
            }
            for row in rows
        ]

@router.get("/{document_id}/chunks")
@handle_errors
async def get_document_chunks(document_id: uuid.UUID):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, content, chunk_index, token_count, metadata FROM chunks WHERE document_id = $1 ORDER BY chunk_index ASC",
            document_id
        )
        return [
            {
                "id": str(row["id"]),
                "content": row["content"],
                "index": row["chunk_index"],
                "tokens": row["token_count"],
                "metadata": row["metadata"]
            }
            for row in rows
        ]

@router.get("/chunks/search")
@handle_errors
async def search_similar_chunks(
    chunk_id: uuid.UUID,
    limit: int = 5
):
    """
    Find chunks similar to a given chunk using vector similarity.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # 1. Get embedding of target chunk
        target_embedding = await conn.fetchval(
            "SELECT embedding FROM chunks WHERE id = $1",
            chunk_id
        )
        
        if not target_embedding:
            raise HTTPException(status_code=404, detail="Chunk not found")
            
        # 2. Search for similar chunks using vector cosine similarity
        # Using <-> operator for Euclidean distance on normalized vectors or <=> for cosine
        # The schema uses hnsw with vector_cosine_ops
        rows = await conn.fetch(
            """
            SELECT id, document_id, content, chunk_index, 
                   (embedding <=> $1) as distance
            FROM chunks
            WHERE id != $2
            ORDER BY embedding <=> $1
            LIMIT $3
            """,
            target_embedding, chunk_id, limit
        )
        
        return [
            {
                "id": str(row["id"]),
                "document_id": str(row["document_id"]),
                "content": row["content"],
                "index": row["chunk_index"],
                "similarity": 1 - row["distance"]
            }
            for row in rows
        ]
