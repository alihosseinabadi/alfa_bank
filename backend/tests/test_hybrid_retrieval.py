import pytest
from app.ml.hybrid_retriever import HybridRetriever
from test_retrieval_stage5 import chunk, context

class Channel:
    def __init__(self, results):
        self.results = results
        self.rows = []
        self.materials = {}
        self.postings = {"ндс": []}
    def query(self, ctx, k): return self.results[:k]

def test_threshold_and_fusion():
    a, b = chunk("a", "a"), chunk("b", "b")
    model = HybridRetriever(Channel([("a", .8, a), ("b", .4, b)]), Channel([("b", 2., b)]), semantic_threshold=.7)
    result = model.query(context())
    assert [row[0] for row in result] == ["a", "b"]
    assert set(result[0][2]) == {"semantic"}
    assert model.query(context("")) == []
    with pytest.raises(ValueError): model.query(context(), 0)

def test_semantic_threshold_is_explicit_and_finite():
    with pytest.raises(ValueError): HybridRetriever(Channel([]), Channel([]), semantic_threshold=float("nan"))
def test_hybrid_rejects_incompatible_corpora():
    left, right = Channel([]), Channel([])
    right.materials = {"unshared": object()}
    with pytest.raises(ValueError, match="same public corpus"):
        HybridRetriever(left, right, semantic_threshold=.7)
def test_oov_returns_no_semantic_cards():
    a=chunk("a","a")
    model=HybridRetriever(Channel([("a",.99,a)]),Channel([]),semantic_threshold=.7)
    assert model.query(context("несуществующееслово")) == []
    assert model.query(context("НДС"))