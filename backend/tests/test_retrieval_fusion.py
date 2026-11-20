import pytest
from app.ml.retrieval_fusion import normalized_score_fusion, reciprocal_rank_fusion
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


def test_normalised_fusion_combines_scaled_channels_and_keeps_raw_evidence():
    a, b, c = chunk("a", "a"), chunk("b", "b"), chunk("c", "c")
    channels = {"bm25": [("a", 10., a), ("b", 5., b)], "dense": [("b", .9, b), ("c", .45, c)]}
    result = normalized_score_fusion(channels, weights={"bm25": .6, "dense": .4})
    assert [row[0] for row in result] == ["b", "a", "c"]
    assert result[0][1] == pytest.approx(.6 * .5 + .4 * 1.)
    assert result[0][2]["bm25"]["score"] == 5.
    assert result[0][2]["dense"]["score"] == .9


def test_normalised_fusion_is_scale_invariant_per_channel():
    a, b = chunk("a", "a"), chunk("b", "b")
    base = {"bm25": [("a", 2., a), ("b", 1., b)], "dense": [("b", .8, b), ("a", .4, a)]}
    scaled = {"bm25": [("a", 200., a), ("b", 100., b)], "dense": [("b", .08, b), ("a", .04, a)]}
    weights = {"bm25": .6, "dense": .4}
    assert [row[0] for row in normalized_score_fusion(base, weights=weights)] == [
        row[0] for row in normalized_score_fusion(scaled, weights=weights)]


def test_normalised_fusion_rejects_duplicates_and_wrong_evidence():
    a, b = chunk("a", "a"), chunk("b", "b")
    with pytest.raises(ValueError, match="Duplicate"):
        normalized_score_fusion({"x": [("a", 1., a), ("a", 2., a)]})
    with pytest.raises(ValueError, match="evidence"):
        normalized_score_fusion({"x": [("a", 1., b)]})