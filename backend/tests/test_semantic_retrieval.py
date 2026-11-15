"""Behavioural tests for the material-level semantic channel and ``light-hybrid-search-v2``.

Same philosophy as ``test_light_retrieval.py``: assert properties that must hold,
not tuned scores. The one numeric assertion (fewer components than documents) is a
structural requirement of LSA, not a benchmark number.
"""
from pathlib import Path

import pytest

from app.data_preparation.light_index import build_light_index, load_light_index, save_light_index
from app.ml.light_hybrid import LightHybridRetriever, LightHybridRetrieverV2
from app.ml.profile_contracts import ExplicitConstraints, ExplicitPreferences
from app.ml.profile_policy import fingerprint
from app.ml.request_context import build_request_context
from app.ml.retrieval_contracts import (
    LIGHT_RETRIEVAL_VERSION,
    LIGHT_RETRIEVAL_VERSION_V2,
    LightRetrievalPolicyV2,
    PublicSearchChunk,
    SearchMaterial,
)
from app.ml.semantic_retriever import SemanticRetriever
from app.ml.synonyms import SynonymDictionary, SynonymGroup
from app.ml.user_profile import build_user_profile

MATERIALS = [
    ("cs", "Клиентский сервис и удержание", ["Клиентский сервис"], ["удержание"],
     "Открытый", None, 45, "podcast"),
    ("discounts", "Скидки и промо", ["Маркетинг"], ["скидки"], "Открытый", None, 60, "article"),
    ("unit", "Юнит-экономика: LTV и CAC", ["Финансы"], ["ltv", "cac"],
     "По подписке", 4900, 120, "course"),
    ("hiring", "Найм первых сотрудников", ["Найм"], ["найм"],
     "По подписке", 3900, 90, "course"),
    ("legal", "Регистрация ИП и налоги", ["Право"], ["ип"], "Открытый", None, 30, "document"),
    ("cash", "Кассовый разрыв", ["Финансы"], ["денежный поток"], "Открытый", None, 75, "webinar"),
]

TEXTS = {
    "cs": "Клиенты возвращаются, если сервис отвечает быстро. Удержание клиента дешевле привлечения.",
    "discounts": "Скидки и акции возвращают покупателей и повышают повторные продажи.",
    "unit": "Считаем LTV, CAC, маржу и прибыль с клиента.",
    "hiring": "Как нанимать первых сотрудников и проводить собеседование.",
    "legal": "Регистрация ИП, НДС и выбор налогового режима.",
    "cash": "Кассовый разрыв: как планировать денежный поток.",
}

EXTRA_CHUNKS = {
    "cs": ["Как отвечать на жалобы клиентов и не терять выручку."],
}


def _material(row):
    key, title, topics, tags, access, price, duration, item_type = row
    return SearchMaterial(
        material_key=key,
        title=title,
        item_type=item_type,
        url=f"https://example.test/{key}",
        topics=topics,
        tags=tags,
        access_type=access,
        listed_price=price,
        duration_minutes=duration,
        is_discoverable=True,
        url_state="reachable",
    )


@pytest.fixture
def corpus():
    materials = [_material(row) for row in MATERIALS]
    rows = {row[0]: row for row in MATERIALS}
    chunks = []
    for key in TEXTS:
        _, title, topics, tags, *_ = rows[key]
        header = f"{title}. Тема: {topics[0]}. Теги: {', '.join(tags)}."
        chunks.append(PublicSearchChunk(
            chunk_id=f"{key}-meta",
            material_key=key,
            text=header,
            source_block_ids=[f"block-{key}-meta"],
            content_kind="metadata",
        ))
        if key not in {"unit", "hiring"}:
            chunks.append(PublicSearchChunk(
                chunk_id=f"{key}-body-0",
                material_key=key,
                text=TEXTS[key],
                source_block_ids=[f"block-{key}-body-0"],
                content_kind="body",
            ))
    for key, texts in EXTRA_CHUNKS.items():
        for index, text in enumerate(texts):
            chunks.append(PublicSearchChunk(
                chunk_id=f"{key}-body-{index + 1}",
                material_key=key,
                text=text,
                source_block_ids=[f"block-{key}-body-{index + 1}"],
                content_kind="body",
            ))
    return materials, chunks


def context(task="", **constraints):
    profile = build_user_profile("synthetic:semantic-test", [], [], ExplicitPreferences())
    return build_request_context(profile, task, ExplicitConstraints(**constraints))


def keys(result):
    return [candidate.material_key for candidate in result.candidates]


@pytest.fixture
def semantic(corpus):
    materials, chunks = corpus
    return SemanticRetriever(LightRetrievalPolicyV2()).fit(materials, chunks)


@pytest.fixture
def index_v2(corpus):
    materials, chunks = corpus
    return build_light_index(materials, chunks, LightRetrievalPolicyV2())


def test_semantic_channel_has_one_row_per_material(semantic):
    assert semantic.documents is not None
    assert len(semantic.keys) == len(semantic.documents) == len(MATERIALS)
    assert len(semantic.rows) > len(semantic.keys)  # several chunks per material


def test_components_are_fewer_than_documents(semantic):
    assert semantic.components == min(40, len(MATERIALS) - 1)
    assert semantic.components < len(semantic.keys)


def test_components_are_capped_by_the_policy(corpus):
    materials, chunks = corpus
    retriever = SemanticRetriever(LightRetrievalPolicyV2(semantic_components=3)).fit(materials, chunks)
    assert retriever.components == 3


def test_evidence_chunk_is_deterministic(semantic):
    for key in semantic.keys:
        assert semantic.evidence[key].material_key == key
    assert semantic.evidence["cs"].chunk_id == "cs-meta"


def test_v2_reports_its_own_version(index_v2):
    result = index_v2.query(context("как удержать клиента"), 5)
    assert result.status == "matched"
    assert result.version == LIGHT_RETRIEVAL_VERSION_V2
    assert all(row.retrieval_version == LIGHT_RETRIEVAL_VERSION_V2 for row in result.candidates)


def test_v2_identity_includes_the_semantic_bundle(index_v2):
    assert index_v2.semantic.bundle_id is not None
    assert index_v2.identity is not None


def test_v2_is_deterministic(corpus):
    materials, chunks = corpus
    first = build_light_index(materials, chunks, LightRetrievalPolicyV2())
    second = build_light_index(materials, chunks, LightRetrievalPolicyV2())
    assert first.identity == second.identity


def test_v1_is_untouched(corpus):
    materials, chunks = corpus
    index = build_light_index(materials, chunks)
    assert isinstance(index, LightHybridRetriever)
    assert not isinstance(index, LightHybridRetrieverV2)
    result = index.query(context("как удержать клиента"), 5)
    assert result.version == LIGHT_RETRIEVAL_VERSION


def test_v2_respects_budget_filter(index_v2):
    result = index_v2.query(context("прибыль с клиента", budget_preference="free_only"), 10)
    assert result.status == "matched"
    assert result.candidates
    assert "unit" not in keys(result)


@pytest.mark.parametrize(
    "task",
    ["посадка лунохода", "синтез химического элемента", "рецепт борща"],
)
def test_v2_refuses_out_of_domain(index_v2, task):
    result = index_v2.query(context(task), 5)
    assert result.status == "no_eligible"
    assert result.reason_codes == ["query_out_of_domain"]
    assert result.candidates == []


@pytest.mark.parametrize(
    "task,target",
    [("удерживать клиентов", "cs"), ("удержать клиента", "cs"), ("скидок", "discounts")],
)
def test_v2_survives_word_forms(index_v2, task, target):
    result = index_v2.query(context(task), 5)
    assert target in keys(result)[:3], (task, keys(result))


def test_synonym_expansion_changes_the_query_vector(corpus):
    """The semantic query vector must actually include curated expansion terms."""
    materials, chunks = corpus
    dictionary = SynonymDictionary(
        version="test-synonyms",
        groups=(SynonymGroup("keep", ("клиент", "покупатель")),),
        canonical_map={},
        expansion_map={
            "клиент": frozenset({"покупател"}),
            "покупател": frozenset({"клиент"}),
        },
        identity=fingerprint({"version": "test-synonyms"}),
    )
    policy = LightRetrievalPolicyV2(semantic_synonym_weight=0.5)
    expanded = SemanticRetriever(policy, dictionary).fit(materials, chunks)
    plain = SemanticRetriever(
        LightRetrievalPolicyV2(semantic_synonym_weight=0.0), dictionary
    ).fit(materials, chunks)
    assert expanded._query_vector("клиент").nnz > plain._query_vector("клиент").nnz


def test_unsupported_policy_version_is_rejected(corpus):
    materials, chunks = corpus
    with pytest.raises(ValueError):
        build_light_index(materials, chunks, LightRetrievalPolicyV2(version="light-hybrid-search-v0"))


def test_v2_index_roundtrip(corpus, tmp_path):
    materials, chunks = corpus
    index = build_light_index(materials, chunks, LightRetrievalPolicyV2())
    root = Path(__file__).resolve().parents[2]
    path = save_light_index(index, tmp_path / "light", root, catalog_bundle_id="catalog-test")
    loaded, manifest = load_light_index(path)
    assert manifest["retrieval_version"] == LIGHT_RETRIEVAL_VERSION_V2
    assert manifest["audit"]["semantic_components"] == index.semantic.components
    assert loaded.identity == index.identity
    result = loaded.query(context("как удержать клиента"), 5)
    assert keys(result) == keys(index.query(context("как удержать клиента"), 5))
