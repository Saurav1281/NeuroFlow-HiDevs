import json
import uuid
import logging
from fastapi import APIRouter, HTTPException, Body
from backend.db.pool import get_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["runs"])

@router.patch("/{run_id}/rating")
async def update_user_rating(
    run_id: str,
    rating: int = Body(..., ge=1, le=5, embed=True)
):
    """
    Updates user rating for a run and flags for calibration if necessary.
    """
    pool = get_pool()
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    async with pool.acquire() as conn:
        # 1. Fetch existing evaluation
        eval_row = await conn.fetchrow(
            "SELECT id, overall_score, metadata FROM evaluations WHERE run_id = $1",
            run_uuid
        )
        
        if not eval_row:
            # If no evaluation exists yet, we just store the rating if we can.
            # But the requirement implies comparing them.
            # We'll handle both cases.
            pass

        # 2. Update user_rating
        await conn.execute(
            "UPDATE evaluations SET user_rating = $1 WHERE run_id = $2",
            rating, run_uuid
        )
        
        # 3. Calibration logic
        if eval_row:
            automated_score = eval_row['overall_score']
            user_normalized = rating / 5.0
            diff = abs(automated_score - user_normalized)
            
            if diff > 0.3:
                metadata = json.loads(eval_row['metadata'] or '{}')
                metadata['calibration_needed'] = True
                metadata['calibration_diff'] = diff
                
                await conn.execute(
                    "UPDATE evaluations SET metadata = $1 WHERE id = $2",
                    json.dumps(metadata), eval_row['id']
                )
                logger.info(f"Run {run_id} marked as calibration_needed (diff: {diff:.4f})")

        return {"status": "success", "run_id": run_id, "rating": rating}
