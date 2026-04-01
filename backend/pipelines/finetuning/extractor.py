import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class TrainingDataExtractor:
    """Extracts and prepares high-quality training pairs for fine-tuning."""
    
    def __init__(self, storage_path: str = "training_data"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def extract_from_logs(self, logs: List[Dict[str, Any]], min_score: float = 0.82) -> List[Dict[str, Any]]:
        """Filters logs for high-quality pairs and formats for OpenAI."""
        training_pairs = []
        
        for entry in logs:
            quality_score = entry.get("quality_score", 0.0)
            if quality_score < min_score:
                continue
                
            # Basic PII Scrubbing (placeholder for regex-based scrubber)
            query = self._scrub_pii(entry.get("query", ""))
            response = self._scrub_pii(entry.get("response", ""))
            
            if not query or not response:
                continue
                
            # Format according to OpenAI chat completions fine-tuning
            pair = {
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant for NeuroFlow RAG system."},
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": response}
                ]
            }
            training_pairs.append(pair)
            
        return training_pairs

    def save_to_jsonl(self, data: List[Dict[str, Any]], filename: str = None) -> str:
        """Saves formatted pairs to a JSONL file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"finetune_data_{timestamp}.jsonl"
            
        file_path = self.storage_path / filename
        
        with open(file_path, "w", encoding="utf-8") as f:
            for entry in data:
                f.write(json.dumps(entry) + "\n")
                
        logger.info(f"Saved {len(data)} training pairs to {file_path}")
        return str(file_path)

    def _scrub_pii(self, text: str) -> str:
        """Heuristic-based PII scrubbing (emails, phone numbers)."""
        # Simple email mask
        import re
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
        # Simple phone mask
        text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', text)
        return text
