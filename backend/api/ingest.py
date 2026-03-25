import hashlib
import json
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Request, Body
from pydantic import BaseModel
from arq.connections import ArqRedis

from db.pool import get_pool

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingestion"])

class URLIngestRequest(BaseModel):
    url: str

@router.post("/ingest")
async def ingest_document(
    request: Request,
    file: Optional[UploadFile] = File(None),
    url_body: Optional[URLIngestRequest] = Body(None)
):
    """Ingest a document from a file upload or a URL.
    
    Checks for duplicates using SHA256 hashing. New files are enqueued for processing.
    """
    if not file and not url_body:
        raise HTTPException(status_code=400, detail="Must provide either 'file' or 'url'")
        
    pool = get_pool()
    arq_pool: ArqRedis = request.app.state.arq_pool
    
    content_hash = None
    file_bytes = None
    source_type = None
    filename = None
    url = None
    
    if file:
        file_bytes = await file.read()
        
        # Validate size (100MB limit)
        if len(file_bytes) > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large (max 100MB)")
            
        content_hash = hashlib.sha256(file_bytes).hexdigest()
        filename = file.filename
        
        # Determine source_type from filename extension
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext in ("pdf", "docx", "csv"):
            source_type = ext
        elif ext in ("jpg", "jpeg", "png", "webp"):
            source_type = "image"
        elif ext in ("pptx",):
            source_type = "pptx"
        else:
            source_type = "text"
    else:
        url = url_body.url
        content_hash = hashlib.sha256(url.encode()).hexdigest()
        filename = url
        source_type = "url"
        
    # Deduplication Check
    async with pool.acquire() as conn:
        existing_doc = await conn.fetchrow(
            "SELECT id FROM documents WHERE content_hash = $1", 
            content_hash
        )
        
        if existing_doc:
            return {
                "document_id": str(existing_doc["id"]),
                "status": "queued", # or complete, based on current state
                "duplicate": True
            }
            
        # Create queued document
        document_id = str(uuid.uuid4())
        await conn.execute(
            """
            INSERT INTO documents (id, filename, source_type, content_hash, status, pipeline_id)
            VALUES ($1, $2, $3, $4, 'queued', NULL)
            """,
            document_id, filename, source_type, content_hash
        )
        
    # If it's a file, we need a way to pass the bytes to the worker.
    # We'll save it to a temporary location or send bytes through Arq. Arq supports passing bytes.
    # However, for huge 100MB files, saving to disk is safer.
    # The requirement says: "worker pulls from the queue...".
    # Since `file_bytes` can be up to 100MB, passing large payload in Redis might be heavy.
    # But Arq serializes args. We will pass bytes. Arq uses pickle, which is fine.
    
    import tempfile
    import os
    file_path = None
    if file_bytes:
        # Save to a temporary file shared with the worker.
        # Assuming Docker volume or local filesystem shared.
        fd, file_path = tempfile.mkstemp(suffix=f"_{filename}")
        with os.fdopen(fd, 'wb') as f:
            f.write(file_bytes)
            
    # Enqueue job
    await arq_pool.enqueue_job("process_document", document_id=document_id, file_path=file_path, source_type=source_type, url=url)
    
    return {
        "document_id": document_id,
        "status": "queued",
        "duplicate": False
    }

@router.get("/documents/{document_id}")
async def get_document(document_id: str):
    """Retrieve document status and stats."""
    pool = get_pool()
    async with pool.acquire() as conn:
        doc = await conn.fetchrow(
            "SELECT status, chunk_count, metadata FROM documents WHERE id = $1",
            document_id
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
            
        return dict(doc)
