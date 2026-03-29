import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from backend.db.pool import get_pool
from backend.utils.logger import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("")
@handle_errors
async def upload_documents(files: List[UploadFile] = File(...)):
    """
    Simulate document upload and ingestion.
    In a real system, this would trigger an async ingestion pipeline.
    """
    pool = get_pool()
    uploaded_ids = []
    
    async with pool.acquire() as conn:
        for file in files:
            doc_id = uuid.uuid4()
            # Mock hash and type for now
            content_hash = f"hash_{doc_id.hex[:10]}"
            source_type = file.filename.split('.')[-1] if '.' in file.filename else 'text'
            if source_type not in ['pdf','docx','image','csv','url','text']:
                source_type = 'text'
                
            await conn.execute(
                """
                INSERT INTO documents (id, filename, source_type, content_hash, status, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                """,
                doc_id, file.filename, source_type, content_hash, "processing"
            )
            uploaded_ids.append(str(doc_id))
            
    return {"message": f"Uploaded {len(files)} files", "document_ids": uploaded_ids}

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
