import re
import uuid
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class Citation:
    reference: str        # "Source 1"
    chunk_id: str
    document_name: str
    page_number: Optional[int]
    content_preview: str  # first 100 chars of cited chunk
    invalid_citation: bool = False

class CitationProcessor:
    """Parses and validates citations in generated responses."""
    
    def parse_citations(self, response_text: str, context_data: dict[str, Any]) -> list[Citation]:
        """Parses [Source N] patterns and maps them to context chunks."""
        
        # 1. Find all [Source N] patterns
        pattern = r"\[Source (\d+)\]"
        matches = re.finditer(pattern, response_text)
        
        # 2. Extract unique source indices
        found_indices = sorted(list(set(int(m.group(1)) for m in matches)))
        
        citations = []
        sources = context_data.get("sources", [])
        num_sources = len(sources)
        
        # Fetching chunk content requires mapping back to retriever results which we might not have here.
        # But we can assume context_data might have more details or we can fetch them.
        # For now, let's use what's in context_data["sources"].
        
        for idx in found_indices:
            ref_str = f"Source {idx}"
            
            # Check for hallucinations (idx starts at 1)
            if idx > num_sources or idx < 1:
                citations.append(Citation(
                    reference=ref_str,
                    chunk_id="hallucination",
                    document_name="Unknown",
                    page_number=None,
                    content_preview="N/A",
                    invalid_citation=True
                ))
                continue
                
            # Map to source (idx is 1-based)
            source = sources[idx - 1]
            citations.append(Citation(
                reference=ref_str,
                chunk_id=source["chunk_id"],
                document_name=source["document_name"],
                page_number=source.get("page_number"),
                content_preview=source.get("content_preview", "Content not available")
            ))
            
        return citations

    def validate_citations(self, citations: list[Citation]) -> bool:
        """Returns True if all citations are valid."""
        return not any(c.invalid_citation for c in citations)
