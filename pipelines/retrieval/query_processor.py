import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from opentelemetry import trace

from backend.providers.client import NeuroFlowClient
from backend.providers.router import RoutingCriteria
from backend.providers.base import ChatMessage

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("neuroflow.retrieval")

@dataclass
class ProcessedQuery:
    original_query: str
    expanded_queries: list[str]
    metadata_filters: dict[str, Any]
    query_type: str  # factual, analytical, comparative, procedural

class QueryProcessor:
    """Processes raw user queries for optimized retrieval."""
    
    def __init__(self, llm_client: NeuroFlowClient):
        self.client = llm_client

    async def process(self, query: str) -> ProcessedQuery:
        """Process a raw query into a structured ProcessedQuery object."""
        with tracer.start_as_current_span("query_processor.process") as span:
            span.set_attribute("query", query)
            
            # 1. Generate expansions, filters, and classification
            prompt = f"""Analyze the following user query for a RAG system.
Query: "{query}"

Tasks:
1. Query Expansion: Generate 2-3 alternative phrasings that capture the same intent but use different terminology.
2. Metadata Extraction: Identify any implicit filters (e.g., year, topic, document type). Return as a flat JSON dictionary.
3. Classification: Classify the query as 'factual', 'analytical', 'comparative', or 'procedural'.

Return the result in EXACTLY this JSON format:
{{
  "expanded_queries": ["query 1", "query 2"],
  "metadata_filters": {{"key": "value"}},
  "query_type": "factual"
}}
"""
            try:
                result = await self.client.chat(
                    messages=[ChatMessage(role="user", content=prompt)],
                    routing_criteria=RoutingCriteria(task_type="classification")
                )
                
                content = result.content
                # Robust JSON extraction
                json_match = re.search(r"(\{.*\})", content, re.DOTALL)
                if json_match:
                    content = json_match.group(1)
                
                data = json.loads(content)
                
                processed = ProcessedQuery(
                    original_query=query,
                    expanded_queries=data.get("expanded_queries", []),
                    metadata_filters=data.get("metadata_filters", {}),
                    query_type=data.get("query_type", "factual")
                )
                
                span.set_attribute("query_type", processed.query_type)
                span.set_attribute("num_expansions", len(processed.expanded_queries))
                return processed
                
            except Exception as e:
                logger.error(f"Query processing failed for '{query}': {e}")
                span.record_exception(e)
                # Fallback to defaults
                return ProcessedQuery(
                    original_query=query,
                    expanded_queries=[],
                    metadata_filters={},
                    query_type="factual"
                )
