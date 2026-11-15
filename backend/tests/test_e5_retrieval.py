"""Contract checks for public E5 retrieval without downloading a model."""
import numpy as np
import pytest
from app.ml.e5_retriever import E5Retriever
from test_retrieval_stage5 import material, chunk, context

class FakeEncoder:
    def encode(self, texts, kind, batch_size=8):
        return np.asarray([[1.0, 0.0] if kind == "query" or "НДС" in text else [0.0, 1.0] for text in texts], dtype=np.float32).reshape((-1, 2))

def test_e5_material_pooling_and_eligibility():
    a, b = material("a"), material("b").model_copy(update={"access_type": "По подписке"})
    rows = [chunk("a", "a1", "НДС налог"), chunk("a", "a2", "НДС расчет"), chunk("b", "b1", "НДС")]
    index = E5Retriever(FakeEncoder()).fit([a, b], rows)
    assert [row[0] for row in index.query(context())] == ["a", "b"]
    assert [row[0] for row in index.query(context(budget_preference="free_only"))] == ["a"]
    assert index.query(context("")) == []
    with pytest.raises(ValueError):
        index.query(context(), True)

def test_e5_rejects_paid_body():
    paid = material().model_copy(update={"access_type":"По подписке"})
    with pytest.raises(ValueError, match="Paid body"):
        E5Retriever(FakeEncoder()).fit([paid], [chunk(content_kind="body")])
def test_e5_rejects_incompatible_context():
    idx = E5Retriever(FakeEncoder()).fit([material()], [chunk()])
    with pytest.raises(ValueError, match="context"):
        idx.query(context().model_copy(update={"schema_version":"incompatible"}))