import pytest
from pydantic import ValidationError
from backend.models.pipeline import (
    PipelineConfig, IngestionConfig, RetrievalConfig, 
    GenerationConfig, EvaluationConfig
)

def test_pipeline_config_valid():
    valid_data = {
        "name": "Test Pipeline",
        "ingestion": {
            "chunking_strategy": "hierarchical",
            "chunk_size_tokens": 512,
            "chunk_overlap_tokens": 50,
            "extractors_enabled": ["pdf", "docx"]
        },
        "retrieval": {
            "dense_k": 5,
            "sparse_k": 5,
            "reranker": "cross-encoder",
            "top_k_after_rerank": 3
        },
        "generation": {
            "model_routing": {"task": "factual"},
            "max_context_tokens": 2048,
            "temperature": 0.5,
            "system_prompt_variant": "precise"
        },
        "evaluation": {
            "auto_evaluate": True,
            "training_threshold": 0.85
        }
    }
    config = PipelineConfig(**valid_data)
    assert config.name == "Test Pipeline"
    assert config.generation.temperature == 0.5

def test_pipeline_config_missing_field():
    incomplete_data = {
        "name": "Test Pipeline",
        "ingestion": {
            "chunking_strategy": "hierarchical",
            # chunk_size_tokens is missing
            "chunk_overlap_tokens": 50,
            "extractors_enabled": ["pdf"]
        }
        # missing retrieval, generation, evaluation
    }
    with pytest.raises(ValidationError):
        PipelineConfig(**incomplete_data)

def test_pipeline_config_invalid_types():
    bad_data = {
        "name": "Test Pipeline",
        "ingestion": {
            "chunking_strategy": "hierarchical",
            "chunk_size_tokens": "not-an-int", # Error here
            "chunk_overlap_tokens": 50,
            "extractors_enabled": "not-a-list" # Error here
        }
    }
    with pytest.raises(ValidationError):
        IngestionConfig(**bad_data["ingestion"])

def test_pipeline_config_extra_fields():
    extra_field_data = {
        "name": "Test Pipeline",
        "unknown_field": "some-value",
        "ingestion": {
            "chunking_strategy": "hierarchical",
            "chunk_size_tokens": 512,
            "chunk_overlap_tokens": 50,
            "extractors_enabled": ["pdf"]
        },
        "retrieval": {"dense_k": 5, "sparse_k": 5, "reranker": "none", "top_k_after_rerank": 3},
        "generation": {"model_routing": {}, "max_context_tokens": 100, "system_prompt_variant": "v1"},
        "evaluation": {}
    }
    # model_config = ConfigDict(extra="forbid")
    with pytest.raises(ValidationError):
        PipelineConfig(**extra_field_data)

def test_pipeline_config_range_validation():
    # temperature MUST be between 0 and 2
    with pytest.raises(ValidationError):
        GenerationConfig(
            model_routing={}, 
            max_context_tokens=100, 
            temperature=3.0, # Out of range
            system_prompt_variant="v1"
        )
    
    # training_threshold MUST be between 0 and 1
    with pytest.raises(ValidationError):
        EvaluationConfig(training_threshold=1.5) # Out of range
