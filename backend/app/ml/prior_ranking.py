"""Deterministic heuristic prior; weights are configuration, never trained utility."""
from collections import Counter
from pydantic import Field
from .profile_contracts import ProfileRecord
from .profile_policy import fingerprint
from .ranking_contracts import RANKING_VERSION, RankingResult, RankedMaterial, RankingReason, Citation
from .retrieval_contracts import NextStep
from .feature_registry import REGISTRY_HASH, validate_features
from .feature_engineering import build_pair_features, validate_context, historical_cues_enabled
from .tfidf_retriever import eligible_for_context, tokenize_text
from .evidence import lexical_excerpt

class PriorPolicy(ProfileRecord):
    version: str = RANKING_VERSION
    retrieval_weight: float = Field(default=1.0, gt=0, le=10)
    task_overlap_weight: float = Field(default=0.10, ge=0, le=1)
    explicit_topic_weight: float = Field(default=0.10, ge=0, le=1)
    history_topic_weight: float = Field(default=0.15, ge=0, le=1)
    avoidance_weight: float = Field(default=0.05, ge=0, le=1)
    industry_weight: float = Field(default=0.05, ge=0, le=1)
    duration_weight: float = Field(default=0.02, ge=0, le=1)
    completed_penalty: float = Field(default=0.03, ge=0, le=1)

    def identity(self):
        return fingerprint(self.model_dump())

def score_features(features, context, policy):
    validate_features(features)
    if features.context_id != context.context_id or features.profile_version != context.profile_version:
        raise ValueError("Feature/context mismatch")
    if policy.version != RANKING_VERSION:
        raise ValueError("Incompatible prior policy")
    v = features.values
    history = context.history_weight if historical_cues_enabled(context) else 0.0
    parts = {
        "retrieval_rank_score": policy.retrieval_weight * v["retrieval_rank_score"],
        "task_text_overlap": policy.task_overlap_weight * (v["task_text_overlap"] or 0.0),
        "explicit_topic_match": policy.explicit_topic_weight * (v["explicit_topic_match"] or 0.0),
        "history_topic_match": policy.history_topic_weight * history * (v["history_topic_match"] or 0.0) * (v["history_support"] or 0.0),
        "avoidance_topic_match": -policy.avoidance_weight * history * (v["avoidance_topic_match"] or 0.0),
        "industry_match": policy.industry_weight * (v["industry_match"] or 0.0),
        "duration_fit": policy.duration_weight * (v["duration_fit"] or 0.0),
        "completed": -policy.completed_penalty * history * (v["completed"] or 0.0),
    }
    return sum(parts.values()), parts

def _reasons(hit, features, components, starter):
    v = features.values
    reason = RankingReason(feature="retrieval_rank_score", value=v["retrieval_rank_score"],
        source="retrieval", text="Общая стартовая подборка; персональное совпадение не установлено." if starter else
        f"Кандидат №{hit.retrieval_rank} в исходном поиске; оценка ранжирования не является вероятностью полезности.")
    reasons = [reason]
    if components["task_text_overlap"] > 0:
        reasons.append(RankingReason(feature="task_text_overlap", value=v["task_text_overlap"],
            source="explicit_task/public_chunks", text="Часть слов вашей задачи найдена в публичном тексте материала."))
    if components["explicit_topic_match"] > 0:
        reasons.append(RankingReason(feature="explicit_topic_match", value=v["explicit_topic_match"],
            source="explicit_preferences/catalog_topics", text="Совпадает с выбранными темами: " + ", ".join(features.matched_explicit_topics) + "."))
    if components["history_topic_match"] > 0:
        reasons.append(RankingReason(feature="history_topic_match", value=v["history_topic_match"],
            source="profile_topic_evidence/catalog_topics", text="Есть подтверждённые историей тематические совпадения: " + ", ".join(features.matched_history_topics) + "."))
    if components["avoidance_topic_match"] < 0:
        reasons.append(RankingReason(feature="avoidance_topic_match", value=v["avoidance_topic_match"],
            source="profile_negative_evidence", text="Историческое отрицательное свидетельство немного снизило оценку; материал не исключён."))
    for field, text, source in [
        ("industry_match", "В каталоге указана выбранная вами отрасль.", "explicit_industry/catalog_industry"),
        ("duration_fit", "Известная длительность укладывается в указанное время.", "requested_time/catalog_duration"),
    ]:
        if components[field] > 0:
            reasons.append(RankingReason(feature=field, value=v[field], source=source, text=text))
    if v["format_match"] == 1:
        reasons.append(RankingReason(feature="format_match", value=1, source="requested_format/catalog",
                                     text="Формат соответствует вашему ограничению."))
    if components["completed"] < 0:
        reasons.append(RankingReason(feature="completed", value=1, source="learning_state_snapshot",
                                     text="Материал отмечен завершённым в доступном снимке прогресса."))
    return reasons

def rank_candidates(batch, materials, context, *, profile=None, progress=None, policy=None,
                    blocked_material_keys=(), k=6):
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError("k must be a positive integer")
    policy = policy or PriorPolicy()
    if policy.version != RANKING_VERSION:
        raise ValueError("Incompatible prior policy")
    validate_context(batch, context, profile, progress)
    owners = {m.material_key: m for m in materials}
    if len(owners) != len(materials):
        raise ValueError("Duplicate catalog material")
    blocked = set(blocked_material_keys)
    excluded, candidates = Counter(), []
    for hit in batch.hits:
        if hit.material_key not in owners:
            raise ValueError("Candidate missing from pinned catalog")
        material = owners[hit.material_key]
        if hit.material_key in blocked:
            excluded["platform_blocked"] += 1
            continue
        if not eligible_for_context(material, context):
            excluded["explicit_constraints_or_catalog_eligibility"] += 1
            continue
        features = build_pair_features(hit, material, batch, context, profile, progress)
        score, parts = score_features(features, context, policy)
        flags = []
        if material.duration_minutes is None:
            flags.append("duration_unknown")
        if material.listed_price is None:
            flags.append("listed_price_unknown")
        if material.url_state != "reachable":
            flags.append("live_url_not_confirmed")
        if material.access_type != "Открытый":
            flags.append("card_metadata_only")
        citations = [Citation(channel=e.channel, chunk_id=e.chunk.chunk_id,
            source_block_ids=list(e.chunk.source_block_ids),
            excerpt=lexical_excerpt(e.chunk.text, tokenize_text(context.query_text)) if e.channel != "e5" else e.chunk.text[:360],
            raw_score=e.raw_score, channel_rank=e.channel_rank) for e in hit.evidence]
        candidates.append(RankedMaterial(material_key=material.material_key, title=material.title,
            item_type=material.item_type, url=material.url, access_type=material.access_type,
            listed_price=material.listed_price, duration_minutes=material.duration_minutes,
            duration_fit="not_requested" if context.available_time_minutes is None else "unknown" if material.duration_minutes is None else "fits",
            url_state=material.url_state, quality_flags=flags, retrieval_rank=hit.retrieval_rank, rank=1,
            prior_score=score, score_components=parts, features=features,
            reasons=_reasons(hit, features, parts, batch.status == "starter"), citations=citations,
            next_step=NextStep(url=material.url), requires_access_check=material.access_type != "Открытый"))
    candidates.sort(key=lambda item: (-item.prior_score, item.material_key))
    candidates = [c.model_copy(update={"rank": i}) for i, c in enumerate(candidates[:min(k, 50)], 1)]
    status = batch.status if not batch.hits else "starter" if batch.status == "starter" and candidates else "matched" if candidates else "no_eligible"
    flags = ["heuristic_not_trained_utility", "quality_evaluation_deferred", "unknown_features_have_explicit_masks",
             "stage_and_experience_fit_unavailable", "continuation_requires_platform_checks"]
    if profile is None:
        flags.append("profile_snapshot_not_supplied")
    return RankingResult(context_id=context.context_id, profile_version=context.profile_version,
        index_bundle_id=batch.index_bundle_id, catalog_bundle_id=batch.catalog_bundle_id,
        retrieval_policy_id=batch.retrieval_policy_id, feature_registry_hash=REGISTRY_HASH,
        policy_id=policy.identity(), retrieval_method=batch.method,
        retrieval_parameters=dict(batch.retrieval_parameters), status=status,
        clarification=None if candidates else batch.clarification or "Нет подходящих кандидатов. Уточните задачу или ограничения.",
        candidates=candidates, excluded_counts=dict(excluded),
        continuation_candidates=list(context.continuation_candidates), quality_flags=flags)
