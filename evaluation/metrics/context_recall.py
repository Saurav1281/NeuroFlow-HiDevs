import re
import logging
from backend.providers.client import NeuroFlowClient
from backend.providers.base import ChatMessage
from backend.providers.router import RoutingCriteria

logger = logging.getLogger(__name__)

async def evaluate_context_recall(query: str, chunks: list[str], answer: str, llm_client: NeuroFlowClient) -> float:
    """
    Context Recall — Were the relevant sources retrieved?
    
    Algorithm:
    1. Break the answer into sentences.
    2. For each sentence, ask LLM: "Can this sentence be attributed to the provided context?"
    3. Score: attributable_sentences / total_sentences
    """
    if not answer or answer.strip() == "":
        return 0.0
    
    context = "\n\n".join(chunks)
    if not context.strip():
        return 0.0

    # Step 1: Split into sentences (simple regex-based sentence splitter)
    sentences = re.split(r'(?<=[.!?])\s+', answer)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    
    if not sentences:
        return 0.0

    # Step 2: Batch attribution check
    prompt = (
        "Instructions: Determine if each of the following sentences can be fully attributed to the "
        "provided context. For each sentence, respond with EXACTLY 'yes' or 'no' on a new line. "
        "DO NOT include numbers or any other text.\n\n"
        f"Context: {context}\n\n"
        "Sentences:\n"
    )
    for i, sentence in enumerate(sentences):
        prompt += f"{i+1}. {sentence}\n"

    try:
        result = await llm_client.chat(
            messages=[ChatMessage(role="user", content=prompt)],
            routing_criteria=RoutingCriteria(task_type="evaluation")
        )
        
        lines = result.content.strip().split('\n')
        attributable_count = 0
        
        # Match lines to sentences
        for line in lines:
            line_clean = line.lower().strip()
            if 'yes' in line_clean and 'no' not in line_clean:
                attributable_count += 1
            # 'no' or ambiguous lines count as 0
            
        # Cap attributable_count to len(sentences) just in case
        attributable_count = min(attributable_count, len(sentences))
        
        return attributable_count / len(sentences)
        
    except Exception as e:
        logger.error(f"Error evaluating context recall: {e}")
        return 0.0
