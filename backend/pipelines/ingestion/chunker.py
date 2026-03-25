import re
import math
import logging
import numpy as np
import tiktoken
from dataclasses import dataclass, field
from typing import List, Tuple

from providers.client import NeuroFlowClient
from .extractors.base import ExtractedPage

logger = logging.getLogger(__name__)

@dataclass
class Chunk:
    content: str
    metadata: dict
    token_count: int

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

class Chunker:
    """Documents chunking strategies and auto-selection logic."""
    
    def __init__(self, model_for_tokens: str = "gpt-4o-mini"):
        try:
            self.encoding = tiktoken.encoding_for_model(model_for_tokens)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")
            
    def count_tokens(self, text: str) -> int:
        return len(self.encoding.encode(text))
        
    def _split_into_sentences(self, text: str) -> list[str]:
        """Simple regex-based sentence splitter."""
        # Split on sentence boundaries (., !, ?) followed by whitespace
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    async def auto_chunk(self, pages: list[ExtractedPage], document_source: str = "unknown") -> list[Chunk]:
        """Selects the best chunking strategy automatically."""
        if not pages:
            return []
            
        # Strategy selection
        # 1. Table content -> always fixed_size
        has_table = any(p.content_type == "table" for p in pages)
        # 2. DOCX with headings -> hierarchical
        has_hierarchy = any(bool(p.metadata.get("h1") or p.metadata.get("h2")) for p in pages)
        # 3. PDF > 50 pages -> semantic
        is_long_pdf = document_source == "pdf" and len(pages) > 50
        
        if has_table:
            # We chunk tables using fixed size if they are huge, but typically each table should be a chunk.
            # But prompt says "table content type -> always fixed_size".
            logger.info("Selected fixed_size chunking (contains tables)")
            return await self.fixed_size(pages)
        elif has_hierarchy:
            logger.info("Selected hierarchical chunking (found headings)")
            return await self.hierarchical(pages)
        elif is_long_pdf:
            logger.info("Selected semantic chunking (PDF > 50 pages)")
            return await self.semantic(pages)
        else:
            logger.info("Selected default fixed_size chunking")
            return await self.fixed_size(pages)

    async def fixed_size(self, pages: list[ExtractedPage]) -> list[Chunk]:
        """Fixed size: 512 tokens, 64-token overlap. Snaps to sentence boundary within 10%."""
        target_size = 512
        overlap = 64
        margin = int(target_size * 0.10) # 51 tokens
        
        chunks = []
        full_text = "\n\n".join(p.content for p in pages if p.content.strip())
        sentences = self._split_into_sentences(full_text)
        
        if not sentences:
            return []
            
        current_chunk_sentences = []
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = self.count_tokens(sentence)
            
            # If a single sentence is huge, we might have to force split it, but sticking to "Never split mid-sentence" as strictly as possible.
            if current_tokens + sentence_tokens > target_size + margin:
                # Issue the current chunk
                if current_chunk_sentences:
                    chunk_text = " ".join(current_chunk_sentences)
                    chunks.append(Chunk(
                        content=chunk_text,
                        metadata={"strategy": "fixed_size"},
                        token_count=self.count_tokens(chunk_text)
                    ))
                    
                    # Compute overlap (keep the last few sentences roughly equal to 'overlap' tokens)
                    overlap_sentences = []
                    overlap_tokens = 0
                    for s in reversed(current_chunk_sentences):
                        t_count = self.count_tokens(s)
                        if overlap_tokens + t_count > overlap and overlap_sentences:
                            break
                        overlap_sentences.insert(0, s)
                        overlap_tokens += t_count
                        
                    current_chunk_sentences = overlap_sentences
                    current_tokens = sum(self.count_tokens(s) for s in current_chunk_sentences)
                    
            current_chunk_sentences.append(sentence)
            current_tokens += sentence_tokens
            
        # Add remaining
        if current_chunk_sentences:
            chunk_text = " ".join(current_chunk_sentences)
            chunks.append(Chunk(
                content=chunk_text,
                metadata={"strategy": "fixed_size"},
                token_count=self.count_tokens(chunk_text)
            ))
            
        return chunks

    async def semantic(self, pages: list[ExtractedPage]) -> list[Chunk]:
        """Semantic: Split where cosine similarity between adjacent sentences drops below 0.7."""
        full_text = "\n\n".join(p.content for p in pages if p.content.strip())
        sentences = self._split_into_sentences(full_text)
        
        if not sentences:
            return []
            
        if len(sentences) == 1:
            chunk_text = sentences[0]
            return [Chunk(content=chunk_text, metadata={"strategy": "semantic"}, token_count=self.count_tokens(chunk_text))]
            
        # Get embeddings for all sentences
        client = NeuroFlowClient()
        try:
            embeddings = await client.embed(sentences)
        except Exception as e:
            logger.error(f"Semantic chunking failed to embed sentences: {e}, falling back to fixed_size.")
            return await self.fixed_size(pages)
            
        chunks = []
        current_chunk_sentences = [sentences[0]]
        
        for i in range(1, len(sentences)):
            sim = cosine_similarity(embeddings[i-1], embeddings[i])
            if sim < 0.7:
                # Topic shift detected
                chunk_text = " ".join(current_chunk_sentences)
                chunks.append(Chunk(
                    content=chunk_text,
                    metadata={"strategy": "semantic"},
                    token_count=self.count_tokens(chunk_text)
                ))
                current_chunk_sentences = [sentences[i]]
            else:
                current_chunk_sentences.append(sentences[i])
                
        if current_chunk_sentences:
            chunk_text = " ".join(current_chunk_sentences)
            chunks.append(Chunk(
                content=chunk_text,
                metadata={"strategy": "semantic"},
                token_count=self.count_tokens(chunk_text)
            ))
            
        return chunks

    async def hierarchical(self, pages: list[ExtractedPage]) -> list[Chunk]:
        """Hierarchical: Group by parent-child sections.
        
        Uses ExtractedPage metadata to group sections.
        """
        chunks = []
        
        # We group pages by their h1 and h2
        # As we iterate, if we hit a new h1 or h2, we create a chunk.
        current_section_content = []
        current_metadata = {}
        
        def commit_chunk():
            if current_section_content:
                chunk_text = "\n\n".join(current_section_content)
                meta = {"strategy": "hierarchical"}
                meta.update(current_metadata)
                
                # If chunk is too large, we might still want to sub-chunk it,
                # but instruction says "Each top-level section becomes a parent chunk..."
                # We'll just save it as one chunk for now.
                chunks.append(Chunk(
                    content=chunk_text,
                    metadata=meta,
                    token_count=self.count_tokens(chunk_text)
                ))
                current_section_content.clear()
        
        for page in pages:
            h1 = page.metadata.get("h1")
            h2 = page.metadata.get("h2")
            h3 = page.metadata.get("h3")
            
            # Detect section boundary
            if h1 != current_metadata.get("h1") or h2 != current_metadata.get("h2"):
                commit_chunk()
                current_metadata = {"h1": h1, "h2": h2, "h3": h3}
                # Parent-child modeling:
                if h1:
                    current_metadata["parent_section"] = h1
                if h2:
                    current_metadata["section"] = h2
                    
            current_section_content.append(page.content)
            
        commit_chunk()
        return chunks
