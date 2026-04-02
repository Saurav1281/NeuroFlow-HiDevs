import pytest
from pipelines.retrieval.fusion import RetrievalResult, reciprocal_rank_fusion

def test_rrf_basic():
    # List 1: A (rank 0), B (rank 1)
    res_a = RetrievalResult(chunk_id="A", content="A content", metadata={}, score=1.0)
    res_b = RetrievalResult(chunk_id="B", content="B content", metadata={}, score=0.9)
    
    # List 2: B (rank 0), A (rank 1)
    res_b2 = RetrievalResult(chunk_id="B", content="B content", metadata={}, score=1.0)
    res_a2 = RetrievalResult(chunk_id="A", content="A content", metadata={}, score=0.9)
    
    results = reciprocal_rank_fusion([ [res_a, res_b], [res_b2, res_a2] ], k=60)
    
    # Both should have same fused score: 1/(60+1) + 1/(60+2)
    assert len(results) == 2
    assert results[0].chunk_id in ["A", "B"]
    assert results[0].score == results[1].score

def test_rrf_single_list():
    res_a = RetrievalResult(chunk_id="A", content="A content", metadata={}, score=1.0)
    res_b = RetrievalResult(chunk_id="B", content="B content", metadata={}, score=0.9)
    
    results = reciprocal_rank_fusion([ [res_a, res_b] ], k=60)
    assert results[0].chunk_id == "A"
    assert results[1].chunk_id == "B"

def test_rrf_no_overlap():
    res_a = RetrievalResult(chunk_id="A", content="A content", metadata={}, score=1.0)
    res_c = RetrievalResult(chunk_id="C", content="C content", metadata={}, score=1.0)
    
    results = reciprocal_rank_fusion([ [res_a], [res_c] ], k=60)
    assert len(results) == 2
    assert {r.chunk_id for r in results} == {"A", "C"}

def test_rrf_empty():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[]]) == []

def test_rrf_ranking_consistency():
    # A is rank 0 in list 1, rank 1 in list 2
    # B is rank 0 in list 1, rank 0 in list 2
    # B should be first
    res_a = RetrievalResult(chunk_id="A", content="A content", metadata={}, score=1.0)
    res_b = RetrievalResult(chunk_id="B", content="B content", metadata={}, score=1.0)
    
    list1 = [res_a, res_b] # A=0, B=1
    list2 = [res_b, res_a] # B=0, A=1
    list3 = [res_b]        # B=0
    
    results = reciprocal_rank_fusion([list1, list2, list3], k=60)
    assert results[0].chunk_id == "B"
    assert results[1].chunk_id == "A"
