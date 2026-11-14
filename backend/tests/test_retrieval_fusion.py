import pytest
from app.ml.retrieval_fusion import reciprocal_rank_fusion
from test_retrieval_stage5 import chunk

def test_fusion_rewards_consistent_rank_and_keeps_evidence():
    a, b, c = chunk("a", "a"), chunk("b", "b"), chunk("c", "c")
    channels = {"semantic": [("a", .9, a), ("b", .8, b)], "lexical": [("b", 3., b), ("c", 1., c)]}
    result = reciprocal_rank_fusion(channels)
    assert result[0][0] == "b"
    assert set(result[0][2]) == {"semantic", "lexical"}
    assert [r[0] for r in reciprocal_rank_fusion(channels, weights={"semantic": 0, "lexical": 1})] == ["b", "c"]

def test_fusion_rejects_duplicates_and_wrong_evidence():
    a, b = chunk("a", "a"), chunk("b", "b")
    with pytest.raises(ValueError, match="Duplicate"):
        reciprocal_rank_fusion({"x": [("a", 1., a), ("a", 2., a)]})
    with pytest.raises(ValueError, match="evidence"):
        reciprocal_rank_fusion({"x": [("a", 1., b)]})
def test_fusion_rejects_nonfinite_rank_constant():
    with pytest.raises(ValueError): reciprocal_rank_fusion({}, rank_constant=float("nan"))