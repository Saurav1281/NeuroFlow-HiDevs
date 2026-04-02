from typing import Any, List, Optional, Dict
from pydantic import BaseModel, Field

class Document(BaseModel):
    id: str
    message: Optional[str] = None
    url: Optional[str] = None

class QueryResult(BaseModel):
    run_id: str
    response: Optional[str] = None
    citations: List[Any] = Field(default_factory=list)
    sources: List[Any] = Field(default_factory=list)

class EvaluationResult(BaseModel):
    id: str
    run_id: str
    overall_score: Optional[float] = None
    faithfulness_score: Optional[float] = None
    relevance_score: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
