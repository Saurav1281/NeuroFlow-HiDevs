import numpy as np
import logging
from backend.providers.client import NeuroFlowClient
from backend.providers.base import ChatMessage
from backend.providers.router import RoutingCriteria

logger = logging.getLogger(__name__)

async def evaluate_answer_relevance(query: str, answer: str, llm_client: NeuroFlowClient) -> float:
    """
    Answer Relevance — Does the answer address what was asked?
    
    Algorithm:
    1. Generate 3-5 questions that the answer could be a response to.
    2. Embed the original query and all generated questions.
    3. Score: mean cosine similarity between the original query embedding and generated question embeddings.
    """
    if not answer or answer.strip() == "":
        return 0.0

    # Step 1: Generate 3-5 questions
    prompt = (
        "Instructions: Based on the provided answer, generate 3 to 5 diverse questions that this answer "
        "would be a perfect response to. Return ONLY the questions, one per line, without numbers or bullets.\n\n"
        f"Answer: {answer}"
    )
    
    try:
        gen_result = await llm_client.chat(
            messages=[ChatMessage(role="user", content=prompt)],
            routing_criteria=RoutingCriteria(task_type="evaluation")
        )
        gen_questions = [q.strip() for q in gen_result.content.split('\n') if q.strip()]
        # Filter out anything that isn't a question (basic check)
        gen_questions = [q for q in gen_questions if len(q) > 5]
    except Exception as e:
        logger.error(f"Error generating questions for relevance: {e}")
        return 0.0

    if not gen_questions:
        return 0.0

    # Step 2: Embed and calculate similarity
    try:
        all_qs = [query] + gen_questions
        embeddings = await llm_client.embed(all_qs)
        
        query_emb = np.array(embeddings[0])
        gen_embs = [np.array(e) for e in embeddings[1:]]
        
        similarities = []
        for gen_emb in gen_embs:
            norm_q = np.linalg.norm(query_emb)
            norm_g = np.linalg.norm(gen_emb)
            if norm_q > 0 and norm_g > 0:
                sim = np.dot(query_emb, gen_emb) / (norm_q * norm_g)
                # Cosine similarity can be slightly > 1 or < -1 due to float precision
                sim = max(0.0, min(1.0, sim))
                similarities.append(sim)
            else:
                similarities.append(0.0)
                
        return float(np.mean(similarities)) if similarities else 0.0
    except Exception as e:
        logger.error(f"Error calculating embedding similarity for relevance: {e}")
        return 0.0
