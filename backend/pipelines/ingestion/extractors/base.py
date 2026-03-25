from dataclasses import dataclass, field
from typing import Any, Protocol, List

@dataclass
class ExtractedPage:
    """Represents a single extracted chunk of content from a document (e.g., a PDF page, a PPTX slide, a CSV row chunk)."""
    page_number: int
    content: str
    content_type: str  # "text" | "table" | "image_description"
    metadata: dict[str, Any] = field(default_factory=dict)

class BaseExtractor(Protocol):
    """Protocol for all document extractors."""
    
    async def extract(self, file_path_or_bytes: str | bytes, **kwargs) -> list[ExtractedPage]:
        """Extract pages from the given file.
        
        Args:
            file_path_or_bytes: Path to the file or the raw bytes.
            **kwargs: Additional parameters (e.g., for routing or processing).
            
        Returns:
            A list of ExtractedPage objects.
        """
        ...
