"""Engineering gates for stage 6; these tests do not measure recommendation quality."""
import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app.ml.profile_contracts import ExplicitPreferences, ExplicitConstraints, TopicEvidence
from app.ml.user_profile import build_user_profile
from app.ml.request_context import build_request_context
from app.ml.profile_policy import fingerprint
from app.ml.ranking_contracts import RankingMaterial, ProgressSnapshot, ProgressEvidence
from app.ml.retrieval_contracts import PublicSearchChunk
from app.ml.tfidf_retriever import TfidfRetriever
from app.ml.bm25_retriever import BM25Retriever
from app.ml.e5_retriever import E5Retriever
from app.ml.hybrid_retriever import HybridRetriever
from app.ml.ranking_inputs import from_search_result, from_channel, from_hybrid
from app.ml.feature_registry import FEATURE_NAMES, VECTOR_LAYOUT, FEATURE_DIMENSION, encode_features, validate_features
from app.ml.feature_engineering import build_pair_features
from app.ml.prior_ranking import PriorPolicy, rank_candidates
from app.data_preparation.ranking_bundle import project_progress, save_ranking
from app.data_preparation.history_io import resolve_bundle, verify_files

ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = {"index_bundle_id":"index", "catalog_bundle_id":"catalog", "retrieval_policy_id":"retrieval-policy"}

def material(key="a", **changes):
    values = dict(material_key=key, title="НДС для бизнеса", item_type="article",
        url="https://example.invalid/"+key, topics=["Финансы"], tags=[], access_type="Открытый",
        is_discoverable=True, url_state="temporary_failure")
    return RankingMaterial(**dict(values, **changes))

def chunk(key="a", **changes):
    return PublicSearchChunk(**dict(dict(chunk_id="chunk:"+key, material_key=key, text="НДС налог учет Финансы",
        source_block_ids=["source:"+key]), **changes))

def profile(*, positive=True, negative=False, prefs=None):
    p = build_user_profile("synthetic:ranking", [], [], prefs or ExplicitPreferences(),
        history_bundle_id="history", catalog_bundle_id="catalog")
    evidence = TopicEvidence(topic="Финансы", positive_strength=1 if positive else 0,
        negative_strength=1 if negative else 0, net_strength=1 if positive else 0,
        supporting_material_keys=["synthetic:course"] if positive else [],
        negative_material_keys=["synthetic:other"] if negative else [],
        support_count=2 if positive and negative else 1, confidence=.3)
    fields = {"topic_weights":{"Финансы":1.0} if positive else {},
        "avoidance_weights":{"Финансы":1.0} if negative else {},
        "topic_evidence":[evidence], "cold_start":not positive, "cold_start_reason":None if positive else "no_usable_history"}
    return p.model_copy(update=dict(fields, profile_version=fingerprint(p.model_copy(update=fields).model_dump())))

def setup(task="НДС", *, p=None, materials=None, constraints=None):
    p = p or profile(positive=False)
    materials = materials or [material()]
    ctx = build_request_context(p, task, constraints)
    idx = TfidfRetriever().fit(materials, [chunk(m.material_key) for m in materials])
    batch = from_search_result(idx.query(ctx, 50), {c.chunk_id:c for c in idx.rows}, ctx, **PROVENANCE)
    return p, ctx, materials, batch

def test_cold_start_task_has_public_reason_and_versioned_features():
    p, ctx, mats, batch = setup()
    result = rank_candidates(batch, mats, ctx, profile=p)
    card = result.candidates[0]
    assert result.status == "matched" and card.next_step.url == mats[0].url
    assert card.features.profile_version == p.profile_version
    assert card.features.index_bundle_id == "index"
    assert card.features.retrieval_policy_id == "retrieval-policy"
    assert any(r.feature == "task_text_overlap" for r in card.reasons)
    assert card.citations[0].excerpt in batch.hits[0].evidence[0].chunk.text
    assert not card.requires_access_check
    assert "live_url_not_confirmed" in card.quality_flags

def test_vector_layout_and_unknown_mask_distinguish_zero_from_missing():
    _, ctx, mats, batch = setup(materials=[material(listed_price=0, access_type="По подписке")])
    features = build_pair_features(batch.hits[0], mats[0], batch, ctx)
    validate_features(features)
    assert FEATURE_DIMENSION == 45 == len(features.vector) == len(VECTOR_LAYOUT)
    assert set(features.values) == set(FEATURE_NAMES)
    assert all(math.isfinite(v) and 0 <= v <= 1 for v in features.vector)
    assert features.values["listed_price_scaled"] == 0
    assert features.values["open_access"] == 0
    assert features.values["duration_fit"] is None
    assert features.vector[VECTOR_LAYOUT.index("listed_price_scaled__known")] == 1
    assert features.vector[VECTOR_LAYOUT.index("duration_fit__known")] == 0
    broken = features.model_copy(update={"vector":features.vector[:-1]})
    with pytest.raises(ValueError, match="vector"): validate_features(broken)

@pytest.mark.parametrize("field", ["stage_match", "experience_match", "industry_match", "seen_before", "completed", "url_reachable"])
def test_unsupported_or_unobserved_fields_remain_unknown(field):
    p, ctx, mats, batch = setup()
    f = build_pair_features(batch.hits[0], mats[0], batch, ctx, p)
    assert f.values[field] is None

def test_industry_uses_both_explicit_and_source_labels():
    p = profile(positive=False, prefs=ExplicitPreferences(industry="Розница"))
    p, ctx, mats, batch = setup(p=p, materials=[material(industry_labels=["РОЗНИЦА"])])
    f = build_pair_features(batch.hits[0], mats[0], batch, ctx, p)
    assert f.values["industry_match"] == 1

def test_explicit_topics_are_observed_preferences_not_inferred_history():
    p = profile(positive=False, prefs=ExplicitPreferences(selected_topics=["Финансы"]))
    p, ctx, mats, batch = setup("", p=p)
    card = rank_candidates(batch, mats, ctx, profile=p).candidates[0]
    assert card.features.values["explicit_topic_match"] == 1
    assert card.score_components["history_topic_match"] == 0
    assert card.features.matched_explicit_topics == ["финансы"]

def test_positive_history_requires_support_and_is_capped_by_distinct_materials():
    p, ctx, mats, batch = setup("", p=profile())
    card = rank_candidates(batch, mats, ctx, profile=p).candidates[0]
    assert card.features.values["history_topic_match"] == 1
    assert card.features.values["history_support"] == pytest.approx(1/3)
    assert card.score_components["history_topic_match"] == pytest.approx(.05)
    unsupported = p.model_copy(update={"topic_evidence":[]})
    no = rank_candidates(batch, mats, ctx, profile=unsupported).candidates[0]
    assert no.features.values["history_topic_match"] is None

def test_explicit_task_disables_positive_negative_and_completion_scoring():
    p, ctx, mats, batch = setup(p=profile(positive=True, negative=True))
    progress = ProgressSnapshot(user_key=p.user_key, history_bundle_id=p.history_bundle_id, mode="current",
        entries=[ProgressEvidence(material_key="a", completed=True, progress_fraction=1)])
    card = rank_candidates(batch, mats, ctx, profile=p, progress=progress).candidates[0]
    for name in ("history_topic_match", "avoidance_topic_match", "completed"):
        assert card.score_components[name] == 0
    assert card.features.values["completed"] == 1
    assert card.features.values["history_topic_match"] is None

def test_negative_history_is_soft_not_exclusion():
    p, ctx, mats, batch = setup("", p=profile(positive=True, negative=True))
    card = rank_candidates(batch, mats, ctx, profile=p).candidates[0]
    assert card.score_components["avoidance_topic_match"] < 0
    assert any(r.feature == "avoidance_topic_match" for r in card.reasons)

@pytest.mark.parametrize("changes", [
    {"access_type":"По подписке", "listed_price":0},
    {"duration_minutes":60},
    {"item_type":"course"},
    {"is_discoverable":False},
    {"url":"javascript:alert(1)"},
    {"url_state":"unavailable"},
])
def test_ranker_rechecks_hard_eligibility(changes):
    p, ctx, mats, batch = setup(constraints=ExplicitConstraints(formats=["article"], budget_preference="free_only", available_time_minutes=10))
    changed = mats[0].model_copy(update=changes)
    result = rank_candidates(batch, [changed], ctx, profile=p)
    assert not result.candidates and result.status == "no_eligible"
    assert result.excluded_counts["explicit_constraints_or_catalog_eligibility"] == 1

def test_platform_blocks_and_unknown_duration():
    p, ctx, mats, batch = setup(constraints=ExplicitConstraints(available_time_minutes=10))
    card = rank_candidates(batch, mats, ctx, profile=p).candidates[0]
    assert card.duration_fit == "unknown" and card.score_components["duration_fit"] == 0
    assert not rank_candidates(batch, mats, ctx, profile=p, blocked_material_keys=["a"]).candidates

def test_paid_card_requires_access_and_body_cannot_be_ranked():
    p, ctx, mats, batch = setup(materials=[material(access_type="По подписке", listed_price=0)])
    card = rank_candidates(batch, mats, ctx, profile=p).candidates[0]
    assert card.requires_access_check and "card_metadata_only" in card.quality_flags
    bad_hit = batch.hits[0].model_copy(deep=True)
    bad_hit.evidence[0].chunk.content_kind = "body"
    bad = batch.model_copy(update={"hits":[bad_hit]})
    with pytest.raises(ValueError, match="paid body"): rank_candidates(bad, mats, ctx, profile=p)
    bad_hit.evidence[0].chunk.access_scope = "entitled"
    with pytest.raises(ValueError, match="public"): rank_candidates(bad, mats, ctx, profile=p)

def test_version_catalog_user_and_progress_mismatch_fail():
    p, ctx, mats, batch = setup()
    for changed in [p.model_copy(update={"catalog_bundle_id":"other"}), p.model_copy(update={"user_key":"other"}),
                    p.model_copy(update={"profile_version":"future"})]:
        with pytest.raises(ValueError, match="profile"): rank_candidates(batch, mats, ctx, profile=changed)
    with pytest.raises(ValueError, match="context"):
        rank_candidates(batch.model_copy(update={"context_id":"other"}), mats, ctx, profile=p)
    progress = ProgressSnapshot(user_key=p.user_key, history_bundle_id="wrong", mode="current")
    with pytest.raises(ValueError, match="progress"): rank_candidates(batch, mats, ctx, profile=p, progress=progress)
    with pytest.raises(ValueError, match="policy"):
        rank_candidates(batch, mats, ctx, policy=PriorPolicy(version="future"))

def test_historical_progress_cannot_use_current_snapshot():
    p = profile().model_copy(update={"mode":"historical", "cutoff_month":"2026-06"})
    with pytest.raises(ValueError, match="Historical"):
        project_progress(p, [SimpleNamespace()])
    with pytest.raises(ValidationError):
        ProgressSnapshot(user_key=p.user_key, history_bundle_id="history", mode="historical",
            entries=[ProgressEvidence(material_key="a", completed=True)])

def test_progress_multiple_bindings_has_explicit_reduction():
    p = profile()
    states = [SimpleNamespace(user_key=p.user_key, material_key="a", is_completed=False,
        completed_lesson_ids=["1","1"], active_leaf_lesson_count=4),
        SimpleNamespace(user_key=p.user_key, material_key="a", is_completed=True,
        completed_lesson_ids=["1","2","3","4"], active_leaf_lesson_count=4)]
    snap = project_progress(p, states)
    assert snap.entries[0].completed is True and snap.entries[0].progress_fraction == 1

def test_no_query_never_generates_new_candidates():
    p, ctx, mats, batch = setup("")
    result = rank_candidates(batch, mats, ctx, profile=p)
    assert not result.candidates and result.clarification and result.status == "needs_clarification"

def test_all_channels_share_boundary_and_raw_scores_are_not_added():
    p, ctx, mats, batch = setup()
    lexical = BM25Retriever().fit(mats, [chunk()])
    bm = from_channel(lexical.query(ctx), ctx, method="bm25", **PROVENANCE)
    class Encoder:
        def encode(self, texts, kind, batch_size=8):
            import numpy as np
            return np.tile([1., 0.], (len(texts), 1))
    semantic = E5Retriever(Encoder()).fit(mats, [chunk()])
    e5 = from_channel(semantic.query(ctx), ctx, method="e5", **PROVENANCE)
    hybrid = from_hybrid(HybridRetriever(semantic, lexical, semantic_threshold=.5).query(ctx), ctx, **PROVENANCE)
    policy = PriorPolicy(task_overlap_weight=0, industry_weight=0, duration_weight=0)
    scores = [rank_candidates(b, mats, ctx, profile=p, policy=policy).candidates[0].prior_score for b in (batch, bm, e5, hybrid)]
    assert scores == [1,1,1,1]
    assert {e.channel for e in hybrid.hits[0].evidence} == {"e5","bm25"}

def test_inputs_not_mutated_and_ties_are_canonical():
    p, ctx, mats, batch = setup(materials=[material("b"), material("a")])
    before = copy.deepcopy((p, ctx, mats, batch))
    # A documented task bonus exactly compensates the rank-score gap.
    tied = from_channel([("b", .9, chunk("b", text="Прочее")),
                         ("a", .8, chunk("a", text="НДС"))], ctx, method="e5", **PROVENANCE)
    policy = PriorPolicy(task_overlap_weight=1-1/math.log2(3))
    result = rank_candidates(tied, list(reversed(mats)), ctx, profile=p, policy=policy)
    assert [c.material_key for c in result.candidates] == ["a","b"]
    assert (p, ctx, mats, batch) == before

def test_feature_schema_and_saved_artifact_are_deterministic(tmp_path):
    p, ctx, mats, batch = setup()
    policy = PriorPolicy()
    result = rank_candidates(batch, mats, ctx, profile=p)
    first = save_ranking(result, policy, tmp_path, ROOT)
    second = save_ranking(result, policy, tmp_path, ROOT)
    assert first == second == resolve_bundle(tmp_path)
    manifest = json.loads((first/"manifest.json").read_text())
    verify_files(first, manifest)
    assert json.loads((first/"feature_registry.json").read_text())["dimension"] == 45
    assert json.loads((first/"ranking.json").read_text()) == result.model_dump()
