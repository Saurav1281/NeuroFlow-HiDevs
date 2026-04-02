from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestionConfig(BaseModel):
    chunking_strategy: str = Field(
        ..., description="Strategy for chunking: hierarchical, semantic, etc.", example="hierarchical"
    )
    chunk_size_tokens: int = Field(..., description="Target token count per chunk", example=512)
    chunk_overlap_tokens: int = Field(..., description="Token overlap between chunks", example=50)
    extractors_enabled: list[str] = Field(
        ..., description="List of file extractors: pdf, docx, etc.", example=["pdf", "txt"]
    )


class RetrievalConfig(BaseModel):
    dense_k: int = Field(..., description="Number of chunks to fetch from vector search", example=10)
    sparse_k: int = Field(..., description="Number of chunks to fetch from keyword search", example=5)
    reranker: str = Field(..., description="Reranker model type: cross-encoder, colbert, etc.", example="cross-encoder")
    top_k_after_rerank: int = Field(..., description="Final number of chunks passed to LLM", example=3)
    query_expansion: bool = Field(default=True, description="Whether to expand queries via LLM", example=True)
    metadata_filters_enabled: bool = Field(default=True, description="Filter vectors by properties", example=True)


class GenerationConfig(BaseModel):
    model_routing: dict[str, Any] = Field(
        ..., description="Routing params: task_type, max_cost_per_call", example={"provider": "openai", "model": "gpt-4o"}
    )
    max_context_tokens: int = Field(..., description="Cap on total context tokens", example=8000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0, description="Sampling temp", example=0.2)
    system_prompt_variant: str = Field(
        ..., description="Named prompt variant: precise, creative, etc.", example="precise"
    )


class EvaluationConfig(BaseModel):
    auto_evaluate: bool = Field(default=True, description="Run automated evaluation hooks", example=True)
    training_threshold: float = Field(default=0.8, ge=0.0, le=1.0, description="Quality bar to use for training", example=0.85)


class PipelineConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "production-rag-v1",
                "description": "Standard document query pipeline",
                "ingestion": {
                    "chunking_strategy": "hierarchical",
                    "chunk_size_tokens": 512,
                    "chunk_overlap_tokens": 50,
                    "extractors_enabled": ["pdf", "text"]
                },
                "retrieval": {
                    "dense_k": 20,
                    "sparse_k": 10,
                    "reranker": "cross-encoder",
                    "top_k_after_rerank": 5,
                    "query_expansion": True,
                    "metadata_filters_enabled": True
                },
                "generation": {
                    "model_routing": {"provider": "openai", "fallback": "anthropic"},
                    "max_context_tokens": 4000,
                    "temperature": 0.1,
                    "system_prompt_variant": "factual_concise"
                },
                "evaluation": {
                    "auto_evaluate": True,
                    "training_threshold": 0.8
                }
            }
        }
    )

    name: str = Field(..., description="Unique label for the pipeline.", example="production-rag-v1")
    description: str | None = Field(None, description="Detailed explanation.", example="Standard doc query routing")
    ingestion: IngestionConfig = Field(..., description="Document indexing parameters")
    retrieval: RetrievalConfig = Field(..., description="Vector search and ranking settings")
    generation: GenerationConfig = Field(..., description="LLM prompt and sampling parameters")
    evaluation: EvaluationConfig = Field(..., description="Asynchronous quality metrics setup")
