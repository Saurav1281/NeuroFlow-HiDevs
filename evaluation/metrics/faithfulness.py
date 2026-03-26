import json
import logging
import re
from backend.providers.client import NeuroFlowClient
from backend.providers.base import ChatMessage
from backend.providers.router import RoutingCriteria

logger = logging.getLogger(__name__)

async def evaluate_faithfulness(query: str, answer: str, context: str, llm_client: NeuroFlowClient) -> float:
    """
    Faithfulness — Are all claims in the answer grounded in the retrieved context?
    
    Algorithm:
    1. Extract claims from the answer: prompt LLM to list all factual statements as JSON array
    2. For each claim, prompt LLM: "Is this claim supported by the context? Answer yes/no/partial"
    3. Score: supported_claims / total_claims. partial counts as 0.5.
    4. Return 0.0 if answer makes claims but context is empty
    """
    if not answer or answer.strip() == "":
        return 1.0
    
    # Step 1: Extract claims
    extract_prompt = (
        "Instructions: Extract all factual statements from the following answer as a JSON array of strings. "
        "Each statement should be a single standalone claim. DO NOT include any other text, only the JSON array.\n\n"
        f"Answer: {answer}"
    )
    
    try:
        extraction_result = await llm_client.chat(
            messages=[ChatMessage(role="user", content=extract_prompt)],
            routing_criteria=RoutingCriteria(task_type="evaluation")
        )
        
        # Robust JSON parsing
        content = extraction_result.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            claims = json.loads(match.group())
        else:
            claims = []
            
        if not isinstance(claims, list):
            claims = []
    except Exception as e:
        logger.error(f"Error extracting claims: {e}")
        claims = []

    if not claims:
        return 1.0

    if not context or context.strip() == "":
        return 0.0

    # Step 2: Verify claims (Batched for efficiency)
    verify_prompt = (
        "Instructions: Given the following context, determine if each claim is supported. "
        "Answer with a JSON array of strings where each element is strictly one of 'yes', 'no', or 'partial'. "
        "DO NOT include any other text.\n\n"
        f"Context: {context}\n\n"
        "Claims:\n"
    )
    for i, claim in enumerate(claims):
        verify_prompt += f"{i+1}. {claim}\n"
    
    try:
        verification_result = await llm_client.chat(
            messages=[ChatMessage(role="user", content=verify_prompt)],
            routing_criteria=RoutingCriteria(task_type="evaluation")
        )
        
        content = verification_result.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            results = json.loads(match.group())
        else:
            results = []
            
        if not isinstance(results, list):
            results = []
    except Exception as e:
        logger.error(f"Error verifying claims: {e}")
        results = []

    if not results:
        # If extraction worked but verification failed, we can't score. Fallback or retry.
        # For now, return 0.0 to be safe.
        return 0.0

    # Ensure results length matches claims length (padding if necessary)
    if len(results) < len(claims):
        results.extend(["no"] * (len(claims) - len(results)))
    results = results[:len(claims)]

    supported_count = 0.0
    for res in results:
        res_cleaned = str(res).lower()
        if 'yes' in res_cleaned:
            supported_count += 1.0
        elif 'partial' in res_cleaned:
            supported_count += 0.5
            
    return supported_count / len(claims)
