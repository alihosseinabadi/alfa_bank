"""The shipped demo catalogue must answer the frozen synthetic query set.

This is the regression guard for the demo retrieval path: the catalogue is the
same one ``scripts/build_demo_catalog.py`` writes for Docker, and the retriever is
the BM25 + dense-vector hybrid the API serves.  Cases ``empty`` and
``out_of_vocabulary`` must stay empty; a small set of natural phrasings must
reach the material a person would expect.

The task list is tracked synthetic data, not real user evaluation, and a match
only means "some material passed retrieval coverage" - it is not a quality or
business-impact claim.
"""
import json
from pathlib import Path

import pytest

from app.data_preparation.retrieval_bundle import load_index
from app.ml.bm25_retriever import BM25Retriever
from app.ml.hybrid_retrieval import DenseHybridRetriever
from app.ml.lsa_retriever import LsaRetriever
from app.ml.profile_contracts import ExplicitConstraints, ExplicitPreferences
from app.ml.request_context import build_request_context
from app.ml.user_profile import build_user_profile

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "data/synthetic/retrieval_cases_v2.json"

EXPECTED = {
    "dev002": "document:d-processes",
    "dev009": "article:a-start",
    "dev019": "article:a-taxes",
    "dev025": "article:a-start",
    "dev037": "course:c005",
    "test002": "article:a-start",
    "test019": "article:a-taxes",
    "test023": "webinar:w-sales",
    "test024": "course:c002",
    "test025": "course:c002",
    "test030": "course:c002",
}


def context_for(case: dict):
    profile = build_user_profile("synthetic:query-regression", [], [], ExplicitPreferences())
    constraints = ExplicitConstraints(
        formats=list(case.get("formats") or []),
        budget_preference=case.get("budget_preference"),
    )
    return build_request_context(profile, case.get("task") or "", constraints)


@pytest.fixture(scope="module")
def demo_search(tmp_path_factory):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from build_demo_catalog import build

    base = tmp_path_factory.mktemp("demo-catalogue")
    build(base / "catalog", base / "retrieval", base / "embedding")
    index, _ = load_index(base / "retrieval")
    search = BM25Retriever().fit(list(index.materials.values()), index.rows)
    dense = LsaRetriever.load(base / "embedding")
    dense.attach_materials(index.materials.values())
    return DenseHybridRetriever(dense, search, dense_weight=0.4), index, dense


def test_every_empty_and_out_of_vocabulary_case_returns_nothing(demo_search):
    search, _, _ = demo_search
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    behavior = [case for case in cases if case.get("behavior") or not (case.get("task") or "").strip()]
    assert behavior
    for case in behavior:
        assert search.query(context_for(case), 3) == [], case["case_id"]


def test_expected_materials_are_retrieved_for_representative_questions(demo_search):
    search, _, _ = demo_search
    cases = {case["case_id"]: case for case in json.loads(CASES.read_text(encoding="utf-8"))}
    for case_id, material_key in EXPECTED.items():
        found = search.query(context_for(cases[case_id]), 3)
        assert found, case_id
        assert found[0][0] == material_key, (case_id, [item[0] for item in found])


def test_the_frozen_set_has_no_vocabulary_dead_ends(demo_search):
    search, index, _ = demo_search
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    available_formats = {material.item_type for material in index.materials.values()}
    missing = []
    for case in cases:
        if case.get("behavior") or not (case.get("task") or "").strip():
            continue
        requested = set(case.get("formats") or [])
        if requested and not requested & available_formats:
            continue
        if not search.query(context_for(case), 3):
            missing.append(case["case_id"])
    assert not missing, missing


def test_hybrid_keeps_bm25_and_dense_evidence(demo_search):
    search, _, _ = demo_search
    found = search.query(context_for({"task": "Хочу стабильный поток клиентов"}), 5)
    assert found
    channels = found[0][2]
    assert "bm25" in channels and "dense" in channels
    assert -1.0 <= channels["dense"]["score"] <= 1.0


def test_hybrid_top_result_does_not_depend_on_page_size(demo_search):
    search, _, _ = demo_search
    context = context_for({"task": "Как рассчитать себестоимость поставки товара?"})
    small = search.query(context, 3)
    large = search.query(context, 20)
    assert small[0][0] == large[0][0]
    assert [row[0] for row in small] == [row[0] for row in large[:3]]


def test_dense_dataset_is_complete_and_finite(demo_search):
    _, index, dense = demo_search
    assert dense.rows == index.rows
    assert dense.vectors is not None and dense.vectors.ndim == 2
    assert dense.vectors.shape[0] == len(index.rows)
    assert dense.vectors.shape[1] >= 2
    assert dense.matrix.shape == (len(index.rows), len(dense.vectorizer.vocabulary_))
    assert dense.vectors.dtype.name == "float32"


def test_dense_channel_rejects_nonsense_query(demo_search):
    _, _, dense = demo_search
    assert dense.query(context_for({"task": "абракадабра про марсианские корабли"}), 3) == []
