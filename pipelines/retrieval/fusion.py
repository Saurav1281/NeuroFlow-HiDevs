from dataclasses import dataclass
from typing import Any

@dataclass
class RetrievalResult:
    chunk_id: str
    content: str
    metadata: dict[str, Any]
    score: float
    document_name: str = ""
    page_number: int | None = None

def reciprocal_rank_fusion(
    result_lists: list[list[RetrievalResult]],
    k: int = 60
) -> list[RetrievalResult]:
    """Combines multiple ranked retrieval results using Reciprocal Rank Fusion.
    
    Formula: score = sum(1 / (k + rank)) for each chunk across all lists.
    """
    fused_scores = {}  # chunk_id -> float (fused score)
    chunk_map = {}     # chunk_id -> RetrievalResult (representative)

    for result_list in result_lists:
        for rank, result in enumerate(result_list):
            chunk_id = result.chunk_id
            if chunk_id not in fused_scores:
                fused_scores[chunk_id] = 0.0
                chunk_map[chunk_id] = result
            
            # Formula: 1 / (k + rank + 1) -> +1 because rank is 0-indexed
            fused_scores[chunk_id] += 1.0 / (k + rank + 1)

    # Sort by fused score descending
    sorted_chunk_ids = sorted(fused_scores.keys(), key=lambda x: fused_scores[x], reverse=True)
    
    final_results = []
    for chunk_id in sorted_chunk_ids:
        res = chunk_map[chunk_id]
        res.score = fused_scores[chunk_id] # Update score to the fused one
        final_results.append(res)
        
    return final_results
