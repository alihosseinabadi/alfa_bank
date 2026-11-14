"""BM25 shares access filtering and deterministic material-level results."""
import pytest
from app.ml.bm25_retriever import BM25Retriever
from test_retrieval_stage5 import material, chunk, context


def test_bm25_ranks_and_respects_filters():
    a = material("a")
    b = material("b").model_copy(update={"access_type": "По подписке"})
    index = BM25Retriever().fit([a, b], [chunk("a", "a1", "НДС налог"), chunk("b", "b1", "НДС НДС налог")])
    assert {x[0] for x in index.query(context())} == {"a", "b"}
    assert [x[0] for x in index.query(context(budget_preference="free_only"))] == ["a"]
    assert index.query(context("отсутствующийтермин")) == []


def test_bm25_pools_unique_materials_and_refit():
    a, b = material("a"), material("b")
    rows = [chunk("a", "a1", "налог ндс"), chunk("a", "a2", "ндс налог"), chunk("b", "b1", "ндс налог")]
    index = BM25Retriever().fit([a, b], rows)
    first = [(key, score, row.chunk_id) for key, score, row in index.query(context())]
    assert [x[0] for x in first] == ["a", "b"]
    index.fit([a, b], rows)
    assert first == [(key, score, row.chunk_id) for key, score, row in index.query(context())]
    for k in (0, True, -1):
        with pytest.raises(ValueError):
            index.query(context(), k)


def test_bm25_rejects_paid_body():
    paid = material().model_copy(update={"access_type": "По подписке"})
    with pytest.raises(ValueError, match="Paid body"):
        BM25Retriever().fit([paid], [chunk(content_kind="body")])
def test_bm25_rejects_incompatible_context():
    idx = BM25Retriever().fit([material()], [chunk()])
    with pytest.raises(ValueError, match="context"):
        idx.query(context().model_copy(update={"schema_version":"incompatible"}))
def test_rejects_nonfinite_parameters():
    with pytest.raises(ValueError): BM25Retriever(k1=float("nan"))
    with pytest.raises(ValueError): BM25Retriever(b=float("inf"))
def test_bm25_rejects_insufficient_lexical_coverage():
    idx=BM25Retriever().fit([material()], [chunk(text="НДС налог")])
    assert idx.query(context("НДС несуществующее1 несуществующее2 несуществующее3")) == []
    assert idx.query(context("НДС"))
def test_bm25_rejects_weak_match_despite_full_corpus_coverage():
    materials=[material(str(i)) for i in range(4)]
    words=["ндс","кадры","кредит","логистика"]
    idx=BM25Retriever().fit(materials,[chunk(str(i),str(i),word) for i,word in enumerate(words)])
    assert idx.query(context("ндс кадры кредит логистика")) == []