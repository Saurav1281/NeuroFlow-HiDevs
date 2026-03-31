import asyncio
import json
import os
import uuid
from typing import Any

from fastapi import APIRouter, Security

from backend.db.pool import get_pool
from backend.security.auth import get_current_user

router = APIRouter(prefix="/finetune", tags=["finetune"])


@router.post("/jobs")
async def create_finetune_job(
    current_user: Any = Security(get_current_user, scopes=["admin"]),  # noqa: ANN401
) -> dict[str, Any]:
    """
    Extract high-quality training pairs and create a JSONL file for fine-tuning.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Fetch training pairs with high quality score
        rows = await conn.fetch(
            """
            SELECT query, pos_chunk_id, neg_chunk_ids FROM training_pairs 
            WHERE quality_score >= 0.9
            """
        )

        if not rows:
            return {"message": "No high-quality training pairs found", "job_id": None}

        training_data = []
        for row in rows:
            training_data.append(
                {
                    "query": row["query"],
                    "pos": str(row["pos_chunk_id"]),
                    "neg": [str(nid) for nid in row["neg_chunk_ids"]]
                    if row["neg_chunk_ids"]
                    else [],
                }
            )

        # Create a temporary JSONL file
        job_id = str(uuid.uuid4())
        file_path = f"tmp/finetune_{job_id}.jsonl"
        os.makedirs("tmp", exist_ok=True)

        def write_data():
            with open(file_path, "w") as f:
                for item in training_data:
                    f.write(json.dumps(item) + "\n")

        await asyncio.to_thread(write_data)

        return {
            "message": f"Fine-tuning job created with {len(training_data)} pairs",
            "job_id": job_id,
            "file_path": file_path,
            "count": len(training_data),
        }
