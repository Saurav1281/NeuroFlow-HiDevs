import logging

logger = logging.getLogger(__name__)


class Chunker:
    def __init__(
        self, strategy: str = "hierarchical", chunk_size: int = 500, chunk_overlap: int = 50
    ) -> None:
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str) -> list[str]:
        """
        Chunks text based on the selected strategy.
        """
        if not text:
            return []

        if self.strategy == "hierarchical":
            return self._hierarchical_chunking(text)
        elif self.strategy == "semantic":
            return self._semantic_chunking(text)
        else:
            return self._fixed_size_chunking(text)

    def _fixed_size_chunking(self, text: str) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start += self.chunk_size - self.chunk_overlap
            if start >= len(text):
                break
        return chunks

    def _hierarchical_chunking(self, text: str) -> list[str]:
        # Simple simulation of hierarchical chunking (e.g. by paragraphs then sentences)
        paragraphs = text.split("\n\n")
        chunks = []
        for p in paragraphs:
            if len(p) > self.chunk_size:
                chunks.extend(self._fixed_size_chunking(p))
            else:
                chunks.append(p)
        return chunks

    def _semantic_chunking(self, text: str) -> list[str]:
        # Simple simulation of semantic chunking (e.g. splitting by sentences)
        import re

        sentences = re.split(r"(?<=[.!?]) +", text)
        chunks = []
        current_chunk = ""
        for s in sentences:
            if len(current_chunk) + len(s) <= self.chunk_size:
                current_chunk += s + " "
            else:
                chunks.append(current_chunk.strip())
                current_chunk = s + " "
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks
