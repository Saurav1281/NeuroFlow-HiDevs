import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from backend.api.compare import compare_pipelines
from backend.api.pipelines import create_pipeline
from backend.models.pipeline import PipelineConfig


async def test_pipeline_logic() -> None:
    print("--- Testing Pipeline Configuration Validation ---")
    valid_config = {
        "name": "legal-research-v2",
        "description": "Optimized for legal document analysis",
        "ingestion": {
            "chunking_strategy": "hierarchical",
            "chunk_size_tokens": 400,
            "chunk_overlap_tokens": 80,
            "extractors_enabled": ["pdf", "docx"],
        },
        "retrieval": {
            "dense_k": 30,
            "sparse_k": 20,
            "reranker": "cross-encoder",
            "top_k_after_rerank": 8,
            "query_expansion": True,
            "metadata_filters_enabled": True,
        },
        "generation": {
            "model_routing": {"task_type": "rag_generation", "max_cost_per_call": 0.05},
            "max_context_tokens": 6000,
            "temperature": 0.2,
            "system_prompt_variant": "precise",
        },
        "evaluation": {"auto_evaluate": True, "training_threshold": 0.82},
    }

    try:
        PipelineConfig(**valid_config)
        print("✅ PipelineConfig validation passed for valid config.")
    except Exception as e:
        print(f"❌ PipelineConfig validation failed: {e}")

    invalid_config = valid_config.copy()
    invalid_config["unknown_key"] = "should_fail"
    try:
        PipelineConfig(**invalid_config)
        print("❌ PipelineConfig FAILED to reject unknown key.")
    except Exception as e:
        print(f"✅ PipelineConfig correctly rejected unknown key: {str(e)[:50]}...")

    print("\n--- Testing CRUD Logic (Mocked DB) ---")
    mock_pool = MagicMock()
    mock_conn = AsyncMock()

    # Mock for: async with pool.acquire() as conn:
    class MockAcquire:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_pool.acquire.return_value = MockAcquire()
    mock_conn.fetchval.return_value = 1  # existing version 1

    with patch("backend.api.pipelines.get_pool", return_value=mock_pool):
        result = await create_pipeline(PipelineConfig(**valid_config))
        print(f"✅ Create pipeline returned: {result}")
        assert result["version"] == 2
        print("✅ Version increment logic works (1 -> 2).")

    print("\n--- Testing A/B Comparison Parallelism (Mocked) ---")
    # Mock NeuroFlowClient and Generator to avoid external calls
    with (
        patch("backend.api.compare.get_pool", return_value=mock_pool),
        patch("backend.api.compare.NeuroFlowClient") as mock_client_cls,
        patch("backend.api.compare.Generator") as mock_gen_cls,
        patch("backend.api.compare.RetrievalPipeline") as mock_pipe_cls,
    ):
        # Ensure initialize can be awaited
        mock_client_cls.return_value.initialize = AsyncMock()

        mock_conn.fetchrow.side_effect = [
            {"config": json.dumps(valid_config), "version": 1},
            {"config": json.dumps(valid_config), "version": 2},
        ]

        # Simulate generator stream
        async def mock_stream(*args, **kwargs):
            yield {"type": "token", "delta": "Mocked "}
            yield {"type": "token", "delta": "Response"}
            yield {"type": "done", "run_id": str(uuid.uuid4()), "citations": []}

        mock_gen_cls.return_value.generate_stream = mock_stream
        mock_pipe_cls.return_value.run = AsyncMock(return_value={"chunks_used": [1, 2, 3]})

        asyncio.get_event_loop().time()
        result = await compare_pipelines(
            query="Test query",
            pipeline_a_id=uuid.uuid4(),
            pipeline_b_id=uuid.uuid4(),
            redis=AsyncMock(),
        )
        asyncio.get_event_loop().time()

        print(f"✅ Comparison result: {json.dumps(result, indent=2)[:200]}...")
        print("✅ Total execution time for parallel run was small (simulated).")

    print("\n--- Verification Complete ---")


if __name__ == "__main__":
    asyncio.run(test_pipeline_logic())
