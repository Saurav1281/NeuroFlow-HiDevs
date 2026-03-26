import logging
from typing import Optional

logger = logging.getLogger(__name__)

class PromptBuilder:
    """Builds dynamic prompts for RAG generation based on query type."""
    
    BASE_SYSTEM_PROMPT = """You are a precise research assistant. Answer the user's question using ONLY the provided context.
If the context does not contain enough information to answer fully, say so explicitly.
For every factual claim, include a citation in the format [Source N].
Do not introduce information not present in the context.
"""

    QUERY_TYPE_PROMPTS = {
        "factual": "Provide a direct, concise answer. If multiple sources agree, cite all of them.",
        "analytical": "Analyze and synthesize across the provided sources. Identify agreements and contradictions.",
        "comparative": "Organize your response as a structured comparison. Use a table if appropriate.",
        "procedural": "Provide numbered steps. Each step must be cited."
    }

    COT_PROMPT = "Before providing your final answer, perform a hidden reasoning step. Think through the synthesis process within <think> tags. This thinking section will be removed before the user sees it, so use it freely to organize your thoughts."

    def build_system_prompt(self, query_type: str) -> str:
        """Assembles the system prompt based on query type and reasoning needs."""
        prompt = self.BASE_SYSTEM_PROMPT
        
        # Add query-specific instructions
        type_instruction = self.QUERY_TYPE_PROMPTS.get(query_type, self.QUERY_TYPE_PROMPTS["factual"])
        prompt += f"\n{type_instruction}\n"
        
        # Add Chain-of-Thought for complex queries
        if query_type in ["analytical", "comparative"]:
            prompt += f"\n{self.COT_PROMPT}\n"
            
        return prompt.strip()

    def build_user_prompt(self, query: str, context_string: str) -> str:
        """Formats the context and query into a user message."""
        return f"<context>\n{context_string}\n</context>\n\nQuery: {query}"

    def assemble_messages(self, query: str, context_string: str, query_type: str) -> list[dict[str, str]]:
        """Assembles the full message list for the LLM."""
        return [
            {"role": "system", "content": self.build_system_prompt(query_type)},
            {"role": "user", "content": self.build_user_prompt(query, context_string)}
        ]
