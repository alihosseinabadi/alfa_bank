"""Behavioural tests for the stemmed light hybrid retrieval path.

These tests assert *properties*, not tuned scores: word-form equivalence,
out-of-domain refusal, filter inheritance, determinism, caps, uniqueness and
artifact provenance. They run on a small hand-written Russian corpus so that a
failure points at one specific behaviour.
"""
import json
from pathlib import Path

import pytest

from app.data_preparation.light_index import build_light_index, load_light_index, save_light_index
from app.ml.light_hybrid import LightHybridRetriever
from app.ml.lsa_retriever import LsaRetriever
from app.ml.profile_contracts import ExplicitConstraints, ExplicitPreferences
from app.ml.request_context import build_request_context
from app.ml.retrieval_contracts import (
    LIGHT_RETRIEVAL_VERSION,
    LightRetrievalPolicy,
    PublicSearchChunk,
    SearchMaterial,
)
from app.ml.user_profile import build_user_profile

ROOT = Path(__file__).resolve().parents[2]

CUSTOMER_SERVICE = (
    "Клиентский сервис решает, вернётся ли покупатель. Чтобы удержать клиента, "
    "нужно отвечать быстро, а скидками компенсировать сбой. Повторные покупки "
    "дешевле привлечения нового покупателя."
)
MATERIALS = [
    ("cs_podcast", "Клиентский сервис и удержание", ["Клиентский сервис"],
     ["удержание", "сервис"], "Открытый", None, 45, "podcast"),
    ("discounts", "Скидки и промо для повторных продаж", ["Маркетинг"],
     ["скидки", "промо"], "Открытый", None, 60, "article"),
    ("unit_econ", "Юнит-экономика: LTV и CAC", ["Финансы"],
     ["юнит-экономика", "ltv", "cac"], "По подписке", 4900, 120, "course"),
    ("hiring", "Найм первых сотрудников", ["Найм"],
     ["найм", "собеседование"], "По подписке", 3900, 90, "course"),
    ("legal", "Регистрация ИП и налоговый режим", ["Право"],
     ["ип", "налоги"], "Открытый", None, 30, "document"),
    ("cashflow", "Кассовый разрыв и денежный поток", ["Финансы"],
     ["денежный поток"], "Открытый", None, 75, "webinar"),
]
TEXTS = {
    "cs_podcast": CUSTOMER_SERVICE,
    "discounts": "Скидки и акции возвращают покупателя и повышают повторные продажи.",
    "unit_econ": "Считаем LTV, CAC, маржу и прибыль с клиента.",
    "hiring": "Как проводить собеседование и нанимать первых сотрудников.",
    "legal": "Регистрация ИП, НДС и выбор налогового режима.",
    "cashflow": "Кассовый разрыв: как планировать денежный поток.",
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
    chunks = [
        PublicSearchChunk(
            chunk_id=f"chunk-{key}",
            material_key=key,
            text=text,
            source_block_ids=[f"block-{key}"],
            content_kind="metadata" if key in {"unit_econ", "hiring"} else "body",
        )
        for key, text in TEXTS.items()
    ]
    return materials, chunks


@pytest.fixture
def index(corpus):
    materials, chunks = corpus
    return build_light_index(materials, chunks)


def context(task="", **constraints):
    profile = build_user_profile("synthetic:light-test", [], [], ExplicitPreferences())
    return build_request_context(profile, task, ExplicitConstraints(**constraints))


def keys(result):
    return [candidate.material_key for candidate in result.candidates]


WORD_FORM_PAIRS = [
    ("клиентском сервисе", "клиентский сервис", "cs_podcast"),
    ("удерживать клиентов", "удержать клиента", "cs_podcast"),
    ("покупателей", "покупателя", "cs_podcast"),
    ("скидок", "скидками", "discounts"),
]


@pytest.mark.parametrize("variant,canonical,target", WORD_FORM_PAIRS)
def test_word_forms_retrieve_the_same_material(index, variant, canonical, target):
    """Both word forms must surface the target material in the top-3.

    Identical ordering is *not* asserted for the hybrid: the char n-gram channel
    is surface based by design, so it may reorder neighbours. The stemmed channel
    is asserted separately below.
    """
    for task in (variant, canonical):
        result = index.query(context(task), 5)
        assert result.status == "matched"
        assert target in keys(result)[:3], (task, target, keys(result))


@pytest.mark.parametrize("variant,canonical,target", WORD_FORM_PAIRS)
def test_stemmed_channel_order_is_form_invariant(index, variant, canonical, target):
    first = [row[0] for row in index.bm25.query(context(variant), 10)]
    second = [row[0] for row in index.bm25.query(context(canonical), 10)]
    assert first == second, (variant, canonical, first, second)


@pytest.mark.parametrize(
    "task",
    ["посадка лунохода", "синтез химического элемента", "рецепт борща"],
)
def test_out_of_domain_queries_refuse_precisely(index, task):
    result = index.query(context(task), 5)
    assert result.status == "no_eligible"
    assert result.candidates == []
    assert result.reason_codes == ["query_out_of_domain"]
    assert result.query_has_vocabulary is False
    assert result.clarification and "Альфа-Курса" in result.clarification


def test_partial_coverage_asks_for_clarification(index):
    task = "марсоход телескоп орбита вулкан клиентский"
    result = index.query(context(task), 5)
    assert result.status == "no_eligible"
    assert result.reason_codes == ["insufficient_query_coverage"]
    assert result.candidates == []
    assert result.query_has_vocabulary is True


def test_empty_query_asks_for_clarification(index):
    result = index.query(context(""), 5)
    assert result.status == "needs_clarification"
    assert result.reason_codes == ["empty_query"]


def test_free_only_and_format_filters_are_inherited(index):
    paid_only = index.query(context("найм сотрудников"), 10)
    assert keys(paid_only)[0] == "hiring"

    free_only = index.query(context("найм сотрудников", budget_preference="free_only"), 10)
    assert all(candidate["access_type"] == "Открытый"
               for candidate in [c.model_dump() for c in free_only.candidates])
    assert "hiring" not in keys(free_only)

    articles = index.query(context("скидки покупателя", formats=["article"]), 10)
    assert "discounts" in keys(articles)
    assert {c.item_type for c in articles.candidates} == {"article"}

    short = index.query(context("клиентский сервис", available_time_minutes=30), 10)
    assert "cs_podcast" not in keys(short)
    assert all(
        index.materials[key].duration_minutes is None
        or index.materials[key].duration_minutes <= 30
        for key in keys(short)
    )


def test_cap_uniqueness_and_determinism(corpus, index):
    result = index.query(context("покупатель клиент скидки найм налоги деньги"), 50)
    assert len(result.candidates) <= 50
    assert len(keys(result)) == len(set(keys(result)))
    assert all(0.0 <= candidate.retrieval_score <= 1.0 for candidate in result.candidates)
    materials, chunks = corpus
    second = build_light_index(materials, chunks)
    assert second.identity == index.identity
    assert [c.material_key for c in second.query(context("покупатель клиент"), 10).candidates] == [
        c.material_key for c in index.query(context("покупатель клиент"), 10).candidates
    ]


def test_returns_light_version(index):
    result = index.query(context("клиентский сервис"), 5)
    assert result.version == LIGHT_RETRIEVAL_VERSION
    assert result.algorithm == "light_hybrid"
    assert result.candidates[0].retrieval_version == LIGHT_RETRIEVAL_VERSION


def test_paid_material_body_cannot_enter_the_public_index(corpus):
    materials, chunks = corpus
    leaked = PublicSearchChunk(
        chunk_id="leak",
        material_key="unit_econ",
        text="Закрытый текст платного урока",
        source_block_ids=["block-unit_econ"],
        content_kind="body",
    )
    with pytest.raises(ValueError):
        build_light_index(materials, chunks + [leaked])


def test_invalid_inputs_are_rejected(index):
    with pytest.raises(ValueError):
        index.query(context("клиент"), 0)
    with pytest.raises(ValueError):
        LightHybridRetriever(policy=LightRetrievalPolicy(version="light-hybrid-search-v0"))
    with pytest.raises(ValueError):
        index.query(context("клиент"), True)


def test_lsa_artifact_roundtrip_and_tamper_detection(corpus, tmp_path):
    materials, chunks = corpus
    policy = LightRetrievalPolicy(lsa_components=4)
    retriever = LsaRetriever(policy).fit(materials, chunks)
    path = retriever.save(tmp_path / "lsa")
    loaded = LsaRetriever.load(path, policy=policy)
    first = retriever.query(context("юнит-экономика"), 5)
    second = loaded.query(context("юнит-экономика"), 5)
    assert [row[0] for row in first] == [row[0] for row in second]
    for row, other in zip(first, second):
        assert row[1] == pytest.approx(other[1])
    (path / "documents.npz").write_bytes(b"tampered")
    with pytest.raises(ValueError):
        LsaRetriever.load(path, policy=policy)


def test_index_artifact_roundtrip_and_tamper_detection(corpus, index, tmp_path):
    materials, chunks = corpus
    bundle = save_light_index(index, tmp_path, ROOT, catalog_bundle_id="catalog-test",
                              catalog_files={"materials.csv": "deadbeef"})
    loaded, manifest = load_light_index(bundle, catalog_bundle_id="catalog-test")
    assert manifest["bundle_id"]
    assert loaded.identity == index.identity
    assert [c.material_key for c in loaded.query(context("клиентский сервис"), 5).candidates] == [
        c.material_key for c in index.query(context("клиентский сервис"), 5).candidates
    ]
    with pytest.raises(ValueError):
        load_light_index(bundle, catalog_bundle_id="other-catalog")
    rows = bundle / "rows.jsonl"
    rows.write_text(rows.read_text(encoding="utf-8").replace("покупатель", "клиент"), encoding="utf-8")
    with pytest.raises(ValueError):
        load_light_index(bundle, catalog_bundle_id="catalog-test")
