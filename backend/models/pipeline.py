from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestionConfig(BaseModel):
    chunking_strategy: str = Field(
        ..., description="Strategy for chunking: hierarchical, semantic, etc."
    )
    chunk_size_tokens: int = Field(..., description="Target token count per chunk")
    chunk_overlap_tokens: int = Field(..., description="Token overlap between chunks")
    extractors_enabled: list[str] = Field(
        ..., description="List of file extractors: pdf, docx, etc."
    )


class RetrievalConfig(BaseModel):
    dense_k: int = Field(..., description="Number of chunks to fetch from vector search")
    sparse_k: int = Field(..., description="Number of chunks to fetch from keyword search")
    reranker: str = Field(..., description="Reranker model type: cross-encoder, colbert, etc.")
    top_k_after_rerank: int = Field(..., description="Final number of chunks passed to LLM")
    query_expansion: bool = Field(default=True)
    metadata_filters_enabled: bool = Field(default=True)


class GenerationConfig(BaseModel):
    model_routing: dict[str, Any] = Field(
        ..., description="Routing params: task_type, max_cost_per_call"
    )
    max_context_tokens: int = Field(..., description="Cap on total context tokens")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    system_prompt_variant: str = Field(
        ..., description="Named prompt variant: precise, creative, etc."
    )


class EvaluationConfig(BaseModel):
    auto_evaluate: bool = Field(default=True)
    training_threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    ingestion: IngestionConfig
    retrieval: RetrievalConfig
    generation: GenerationConfig
    evaluation: EvaluationConfig
