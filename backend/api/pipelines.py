import json
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Security

from backend.db.pool import get_pool
from backend.models.pipeline import PipelineConfig
from backend.security.auth import ClientProfile, get_current_user
from backend.security.validators import sanitize_text, validate_pipeline_name
from backend.utils.logger import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.post(
    "",
    response_model=dict,
    summary="Create a pipeline",
    description="Create a new RAG pipeline or insert a new version if the name already exists. Parses the comprehensive `PipelineConfig`.",
    response_description="Confirmation dictionary containing the new pipeline ID, name, and version."
)
@handle_errors
async def create_pipeline(
    config: PipelineConfig, 
    current_user: ClientProfile = Security(get_current_user, scopes=["admin"])
) -> dict[str, Any]:
    """
    Create a new pipeline or a new version if name already exists.
    """
    pool = get_pool()

    # Sanitize inputs
    config.name = validate_pipeline_name(config.name)
    if config.description:
        config.description = sanitize_text(config.description)

    async with pool.acquire() as conn:
        # Check if pipeline exists to determine version
        existing = await conn.fetchval(
            "SELECT MAX(version) FROM pipelines WHERE name = $1", config.name
        )
        version = (existing or 0) + 1

        pipeline_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO pipelines (id, name, version, config, description, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            pipeline_id,
            config.name,
            version,
            config.model_dump_json(),
            config.description,
            "active",
            datetime.now(),
        )

        return {"pipeline_id": str(pipeline_id), "name": config.name, "version": version}


@router.get(
    "",
    response_model=list[dict],
    summary="List all pipelines",
    description="Retrieve a list of the latest active versions of all RAG pipelines, including aggregate scores from their execution history.",
    response_description="A list of pipeline dictionaries with their most recent configuration and metadata."
)
@handle_errors
async def list_pipelines() -> list[dict[str, Any]]:
    """
    List latest active version of all pipelines with last-run metrics.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Get latest version for each name
        rows = await conn.fetch("""
            WITH latest_pipelines AS (
                SELECT id, name, version, config, description, created_at,
                       ROW_NUMBER() OVER(PARTITION BY name ORDER BY version DESC) as rn
                FROM pipelines
                WHERE status = 'active'
            )
            SELECT lp.*, 
                   (SELECT AVG(overall_score) FROM evaluations e 
                    JOIN pipeline_runs pr ON e.run_id = pr.id 
                    WHERE pr.pipeline_id = lp.id) as avg_score,
                   (SELECT COUNT(*) FROM pipeline_runs WHERE pipeline_id = lp.id) as run_count
            FROM latest_pipelines lp
            WHERE rn = 1
        """)

        return [
            {
                "id": str(row["id"]),
                "name": row["name"],
                "version": row["version"],
                "description": row["description"],
                "avg_score": row["avg_score"] or 0.0,
                "run_count": row["run_count"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]


@router.get(
    "/{pipeline_id}",
    response_model=dict,
    summary="Get pipeline by ID",
    description="Get the full configuration, version details, and aggregate metric scores (faithfulness, relevance, precision, recall) for a specific pipeline version.",
    response_description="A dictionary containing the pipeline details and average quality metrics."
)
@handle_errors
async def get_pipeline(pipeline_id: uuid.UUID) -> dict[str, Any]:
    """
    Get full config and aggregate scores for a specific pipeline version.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT p.*,
                   (SELECT AVG(faithfulness) FROM evaluations e 
                    JOIN pipeline_runs pr ON e.run_id = pr.id WHERE pr.pipeline_id = p.id) as avg_faithfulness,
                   (SELECT AVG(answer_relevance) FROM evaluations e 
                    JOIN pipeline_runs pr ON e.run_id = pr.id WHERE pr.pipeline_id = p.id) as avg_relevance,
                   (SELECT AVG(context_precision) FROM evaluations e 
                    JOIN pipeline_runs pr ON e.run_id = pr.id WHERE pr.pipeline_id = p.id) as avg_precision,
                   (SELECT AVG(context_recall) FROM evaluations e 
                    JOIN pipeline_runs pr ON e.run_id = pr.id WHERE pr.pipeline_id = p.id) as avg_recall
            FROM pipelines p
            WHERE p.id = $1
            """,
            pipeline_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Pipeline version not found")

        return {
            "id": str(row["id"]),
            "name": row["name"],
            "version": row["version"],
            "config": json.loads(row["config"]),
            "metrics": {
                "faithfulness": row["avg_faithfulness"] or 0,
                "relevance": row["avg_relevance"] or 0,
                "precision": row["avg_precision"] or 0,
                "recall": row["avg_recall"] or 0,
            },
        }


@router.patch(
    "/{pipeline_id}",
    response_model=dict,
    summary="Update pipeline config",
    description="Update a pipeline's configuration by deep merging updates and creating a new version. Preserves history.",
    response_description="Details of the newly created pipeline version based on the updates."
)
@handle_errors
async def update_pipeline(
    pipeline_id: uuid.UUID,
    updates: dict[str, Any] = Body(...),
    current_user: ClientProfile = Security(get_current_user, scopes=["admin"]),
) -> dict[str, Any]:
    """
    Update config by creating a new version.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # 1. Fetch current config
        existing = await conn.fetchrow(
            "SELECT name, config, description FROM pipelines WHERE id = $1", pipeline_id
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        current_config = json.loads(existing["config"])
        # Deep merge updates or just replace (Pydantic validation handles structure)
        # For simplicity, we'll merge top-level keys
        for key, value in updates.items():
            if key in current_config:
                if isinstance(value, dict) and isinstance(current_config[key], dict):
                    current_config[key].update(value)
                else:
                    current_config[key] = value

        # Validate with Pydantic
        try:
            full_config = PipelineConfig(
                name=existing["name"], description=existing["description"], **current_config
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid config: {str(e)}")

        # 2. Get next version
        next_version = await conn.fetchval(
            "SELECT MAX(version) + 1 FROM pipelines WHERE name = $1", existing["name"]
        )

        # 3. Insert new row
        new_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO pipelines (id, name, version, config, description, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            new_id,
            existing["name"],
            next_version,
            full_config.model_dump_json(),
            existing["description"],
            "active",
            datetime.now(),
        )

        return {"pipeline_id": str(new_id), "version": next_version}


@router.delete(
    "/{pipeline_id}",
    summary="Archive pipeline",
    description="Soft-delete a pipeline by setting its status to 'archived', preserving historical metric data.",
    response_description="Status object confirming the pipeline was archived."
)
@handle_errors
async def delete_pipeline(
    pipeline_id: uuid.UUID, 
    current_user: ClientProfile = Security(get_current_user, scopes=["admin"])
) -> dict[str, Any]:
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE pipelines SET status = 'archived' WHERE id = $1", pipeline_id
        )
        if "UPDATE 0" in result:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return {"status": "archived", "pipeline_id": str(pipeline_id)}


@router.get(
    "/{pipeline_id}/runs",
    summary="Get pipeline executed runs",
    description="Retrieve a paginated list of executed runs tied to a specific pipeline, ordered chronologically.",
    response_description="A paginated list of run summary objects detailing latencies, token counts, and scores."
)
@handle_errors
async def get_pipeline_runs(
    pipeline_id: uuid.UUID, page: int = 1, page_size: int = 20
) -> list[dict[str, Any]]:
    """
    Paginated list of runs for a pipeline.
    """
    pool = get_pool()
    offset = (page - 1) * page_size
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT pr.*, e.overall_score
            FROM pipeline_runs pr
            LEFT JOIN evaluations e ON pr.id = e.run_id
            WHERE pr.pipeline_id = $1
            ORDER BY pr.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            pipeline_id,
            page_size,
            offset,
        )

        return [
            {
                "id": str(row["id"]),
                "query": row["query"],
                "latency_ms": row["latency_ms"],
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "score": row["overall_score"] or 0.0,
                "created_at": row["created_at"],
            }
            for row in rows
        ]


@router.get(
    "/{pipeline_id}/analytics",
    summary="Get pipeline analytics",
    description="Fetch aggregate deployment statistics, including P50/P95/P99 latency, cost projections, and daily usage sparklines.",
    response_description="A dictionary detailing latencies, cost approximations, quality, and usage over time."
)
@handle_errors
async def get_pipeline_analytics(pipeline_id: uuid.UUID) -> dict[str, Any]:
    """
    Aggregate statistics: p50/p95/p99 latency, cost, daily query counts.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Latency statistics
        stats = await conn.fetchrow(
            """
            SELECT 
                percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50,
                percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95,
                percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms) as p99,
                AVG(latency_ms) as avg_latency,
                SUM(input_tokens * 0.00000015 + output_tokens * 0.0000006) as total_cost_usd,
                AVG(overall_score) as avg_score
            FROM pipeline_runs pr
            LEFT JOIN evaluations e ON pr.id = e.run_id
            WHERE pr.pipeline_id = $1
            """,
            pipeline_id,
        )

        # Queries per day (last 30 days)
        sparkline = await conn.fetch(
            """
            SELECT 
                date_trunc('day', created_at) as day,
                COUNT(*) as count
            FROM pipeline_runs
            WHERE pipeline_id = $1 AND created_at > NOW() - INTERVAL '30 days'
            GROUP BY 1
            ORDER BY 1 ASC
            """,
            pipeline_id,
        )

        return {
            "latency": {
                "p50": stats["p50"] or 0,
                "p95": stats["p95"] or 0,
                "p99": stats["p99"] or 0,
                "avg": stats["avg_latency"] or 0,
            },
            "cost": {
                "total_usd": stats["total_cost_usd"] or 0,
                "avg_per_query": (
                    stats["total_cost_usd"]
                    / (
                        await conn.fetchval(
                            "SELECT COUNT(*) FROM pipeline_runs WHERE pipeline_id = $1", pipeline_id
                        )
                        or 1
                    )
                )
                or 0,
            },
            "quality": {"avg_score": stats["avg_score"] or 0},
            "daily_queries": [
                {"day": row["day"].strftime("%Y-%m-%d"), "count": row["count"]} for row in sparkline
            ],
        }


@router.get(
    "/{pipeline_id}/suggestions",
    summary="Get pipeline architecture suggestions",
    description="Analyze recent performance metrics and execute a rule-based inference engine to propose architectural optimizations.",
    response_description="A list of actionable optimization suggestions with specific component targets and rationales."
)
@handle_errors
async def get_pipeline_suggestions(pipeline_id: uuid.UUID) -> dict[str, Any]:
    """
    Get rule-based config improvements based on recent runs.
    """
    from backend.services.pipeline_optimizer import PipelineOptimizer

    pool = get_pool()
    async with pool.acquire() as conn:
        stats = await conn.fetchrow(
            """
            SELECT 
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95,
                AVG(faithfulness) as faithfulness,
                AVG(answer_relevance) as relevance,
                AVG(context_precision) as precision,
                AVG(context_recall) as recall
            FROM pipeline_runs pr
            LEFT JOIN evaluations e ON pr.id = e.run_id
            WHERE pr.pipeline_id = $1
            """,
            pipeline_id,
        )

        if not stats:
            return {"suggestions": []}

        metrics = {
            "latency_p95": stats["p95"] or 0,
            "faithfulness": stats["faithfulness"] or 1.0,
            "relevance": stats["relevance"] or 1.0,
            "precision": stats["precision"] or 1.0,
            "recall": stats["recall"] or 1.0,
        }

        return {"suggestions": PipelineOptimizer.get_suggestions(metrics)}
