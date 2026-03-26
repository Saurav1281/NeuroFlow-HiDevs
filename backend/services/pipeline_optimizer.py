from typing import List, Dict

class PipelineOptimizer:
    @staticmethod
    def get_suggestions(metrics: Dict[str, float]) -> List[Dict[str, str]]:
        """
        Rule-based suggestions based on RAG evaluation metrics.
        """
        suggestions = []
        
        # 1. Context Precision Low
        if metrics.get("precision", 1.0) < 0.7:
            suggestions.append({
                "metric": "context_precision",
                "suggestion": "Reduce top_k_after_rerank or increase reranker threshold.",
                "rationale": "Low precision indicates the reranker is letting too much noise through to the LLM."
            })
            
        # 2. Context Recall Low
        if metrics.get("recall", 1.0) < 0.7:
            suggestions.append({
                "metric": "context_recall",
                "suggestion": "Increase dense_k and sparse_k in retrieval config.",
                "rationale": "Low recall suggests the initial retrieval stage is missing relevant chunks."
            })
            
        # 3. Faithfulness Low
        if metrics.get("faithfulness", 1.0) < 0.8:
            suggestions.append({
                "metric": "faithfulness",
                "suggestion": "Adjust system_prompt_variant to 'precise' or reduce temperature.",
                "rationale": "Low faithfulness indicates hallucinations; stricter prompting or lower temperature can help."
            })
            
        # 4. Latency High
        if metrics.get("latency_p95", 0) > 3000:
            suggestions.append({
                "metric": "latency",
                "suggestion": "Disable query_expansion or use a faster reranker model.",
                "rationale": "P95 latency exceeding 3s impacts UX; look into optimizing the retrieval chain."
            })
            
        return suggestions
