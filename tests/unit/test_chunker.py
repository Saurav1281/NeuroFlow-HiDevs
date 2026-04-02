import pytest
from backend.services.chunking import Chunker

def test_fixed_size_chunking():
    chunker = Chunker(strategy="fixed", chunk_size=10, chunk_overlap=0)
    text = "abcdefghijk"
    chunks = chunker.chunk_text(text)
    assert chunks == ["abcdefghij", "k"]

def test_chunk_overlap():
    chunker = Chunker(strategy="fixed", chunk_size=10, chunk_overlap=2)
    text = "abcdefghijkl"
    # abcdefghij (start 0, end 10)
    # next start = 10 - 2 = 8
    # ijkl (8:12)
    chunks = chunker.chunk_text(text)
    assert chunks == ["abcdefghij", "ijkl"]

def test_hierarchical_chunking():
    chunker = Chunker(strategy="hierarchical", chunk_size=20, chunk_overlap=0)
    text = "Paragraph 1\n\nParagraph 2 is longer than twenty chars"
    chunks = chunker.chunk_text(text)
    assert "Paragraph 1" in chunks
    assert any("Paragraph 2" in c for c in chunks)
    assert len(chunks) >= 2

def test_semantic_chunking():
    chunker = Chunker(strategy="semantic", chunk_size=50, chunk_overlap=0)
    text = "First sentence. Second sentence. Third sentence is quite a bit longer."
    chunks = chunker.chunk_text(text)
    assert len(chunks) >= 1
    assert "First sentence." in chunks[0]

def test_empty_text():
    chunker = Chunker()
    assert chunker.chunk_text("") == []
    assert chunker.chunk_text(None) == []
