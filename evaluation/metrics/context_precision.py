import logging
from backend.providers.client import NeuroFlowClient
from backend.providers.base import ChatMessage
from backend.providers.router import RoutingCriteria

logger = logging.getLogger(__name__)

async def evaluate_context_precision(query: str, chunks: list[str], answer: str, llm_client: NeuroFlowClient) -> float:
    """
    Context Precision — Were the retrieved chunks actually useful?
    
    Algorithm:
    1. For each retrieved chunk, ask LLM: "Was this passage useful in generating the answer? yes/no"
    2. Compute: proportion of useful chunks among retrieved chunks, weighted by rank.
    Score: sum(useful[i] * (1/i) for i in ranks) / sum(1/i for i in ranks)
    """
    if not chunks:
        return 0.0

    # Step 1: Batch the utility check
    prompt = (
        "Instructions: Given the query and the generated answer, determine if each of the following "
        "context passages was useful in formulating the answer. For each passage, respond with "
        "EXACTLY 'yes' or 'no', one per line. DO NOT include numbers or any other text.\n\n"
        f"Query: {query}\n"
        f"Answer: {answer}\n\n"
        "Passages:\n"
    )
    for i, chunk in enumerate(chunks):
        # Truncate chunk if too long to save context
        truncated_chunk = chunk[:1000] + "..." if len(chunk) > 1000 else chunk
        prompt += f"Passage {i+1}: {truncated_chunk}\n\n"
        
    try:
        result = await llm_client.chat(
            messages=[ChatMessage(role="user", content=prompt)],
            routing_criteria=RoutingCriteria(task_type="evaluation")
        )
        
        # Parse lines and extract yes/no
        lines = result.content.strip().split('\n')
        final_results = []
        for line in lines:
            line_clean = line.lower().strip()
            if 'yes' in line_clean and 'no' not in line_clean:
                final_results.append(1)
            elif 'no' in line_clean:
                final_results.append(0)
            # If line is ambiguous, skip it (will be padded later)
            
    except Exception as e:
        logger.error(f"Error evaluating context precision: {e}")
        final_results = []

    # Ensure results match chunks count
    if len(final_results) < len(chunks):
        final_results.extend([0] * (len(chunks) - len(final_results)))
    final_results = final_results[:len(chunks)]

    # Step 2: Weighted precision calculation
    # Score: sum(useful[i] * (1/i) for i in ranks) / sum(1/i for i in ranks)
    numerator = 0.0
    denominator = 0.0
    for i, useful in enumerate(final_results):
        rank = i + 1
        weight = 1.0 / rank
        numerator += useful * weight
        denominator += weight
        
    return numerator / denominator if denominator > 0 else 0.0
