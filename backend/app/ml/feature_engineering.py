"""Observable pair features; no access-controlled text or fabricated user traits."""
import math
from .feature_registry import FEATURE_NAMES, REGISTRY_HASH, encode_features
from .profile_contracts import CONTEXT_VERSION, PROFILE_SCHEMA_VERSION
from .ranking_contracts import PairFeatures
from .tfidf_retriever import normalize_text, tokenize_text

def validate_context(batch, context, profile=None, progress=None):
    if context.schema_version != CONTEXT_VERSION or batch.context_id != context.context_id:
        raise ValueError("Incompatible ranking/context")
    if profile is not None:
        if (profile.schema_version != PROFILE_SCHEMA_VERSION or profile.user_key != context.user_key
                or profile.profile_version != context.profile_version or profile.mode != context.mode
                or profile.cutoff_month != context.cutoff_month
                or profile.catalog_bundle_id != batch.catalog_bundle_id):
            raise ValueError("Incompatible ranking/profile/catalog snapshot")
    if progress is not None:
        if profile is None:
            raise ValueError("A compatible profile is required for a progress snapshot")
        if (progress.user_key != context.user_key or progress.mode != context.mode
                or progress.cutoff_month != context.cutoff_month
                or (profile is not None and progress.history_bundle_id != profile.history_bundle_id)
                or (context.mode == "historical" and progress.entries)):
            raise ValueError("Incompatible progress snapshot")

def historical_cues_enabled(context):
    return context.history_weight > 0 and context.query_source in {"inferred_topics", "material_titles"}

def build_pair_features(hit, material, batch, context, profile=None, progress=None):
    validate_context(batch, context, profile, progress)
    if material.material_key != hit.material_key:
        raise ValueError("Candidate/material mismatch")
    for witness in hit.evidence:
        if (witness.chunk.access_scope != "public" or witness.chunk.material_key != hit.material_key
                or not witness.chunk.source_block_ids):
            raise ValueError("Invalid public evidence")
        if material.access_type != "Открытый" and witness.chunk.content_kind != "metadata":
            raise ValueError("Non-public paid body evidence")
    values = dict.fromkeys(FEATURE_NAMES)
    values["retrieval_rank_score"] = 1 / math.log2(hit.retrieval_rank + 1)
    query_tokens = set(tokenize_text(context.query_text))
    public_tokens = {token for e in hit.evidence for token in tokenize_text(e.chunk.text)}
    if context.query_source == "explicit_task" and query_tokens:
        values["task_text_overlap"] = len(query_tokens & public_tokens) / len(query_tokens)
    topics = {normalize_text(t) for t in material.topics}
    explicit_matches, history_matches = [], []
    if profile is not None and context.query_source == "explicit_topics":
        requested = {normalize_text(t) for t in profile.explicit_preferences.selected_topics if t.strip()}
        if requested:
            explicit_matches = sorted(requested & topics)
            values["explicit_topic_match"] = len(explicit_matches) / len(requested)
    if profile is not None and historical_cues_enabled(context):
        evidence = {e.topic: e for e in profile.topic_evidence}
        approved = {t: w for t, w in profile.topic_weights.items() if t in context.supporting_interests
                    and t in evidence and evidence[t].supporting_material_keys and evidence[t].net_strength > 0}
        if approved:
            matched = [t for t in approved if normalize_text(t) in topics]
            history_matches = sorted(matched)
            values["history_topic_match"] = sum(approved[t] for t in matched) / sum(approved.values())
            support = {key for t in matched for key in evidence[t].supporting_material_keys}
            values["history_support"] = len(support) / (len(support) + 2)
        negatives = {t: w for t, w in profile.avoidance_weights.items() if t in context.avoidance_topics
                     and t in evidence and evidence[t].negative_material_keys and evidence[t].negative_strength > 0}
        if negatives:
            values["avoidance_topic_match"] = sum(w for t, w in negatives.items() if normalize_text(t) in topics) / sum(negatives.values())
    if context.formats:
        values["format_match"] = float(material.item_type in context.formats)
    values["open_access"] = {"Открытый": 1.0, "Платный": 0.0, "По подписке": 0.0}.get(material.access_type)
    if context.available_time_minutes is not None and material.duration_minutes is not None:
        values["duration_fit"] = float(material.duration_minutes <= context.available_time_minutes)
    if material.listed_price is not None:
        values["listed_price_scaled"] = min(material.listed_price / 10000, 1.0)
    labels = getattr(material, "industry_labels", [])
    if context.industry and labels:
        values["industry_match"] = float(normalize_text(context.industry) in {normalize_text(t) for t in labels})
    if profile is not None and any(e.material_key == material.material_key for e in profile.material_evidence):
        values["seen_before"] = 1.0
    if progress is not None:
        entry = next((e for e in progress.entries if e.material_key == material.material_key), None)
        if entry is not None:
            values["completed"] = float(entry.completed) if entry.completed is not None else None
            values["progress_fraction"] = entry.progress_fraction
    values["public_evidence"] = 1.0
    values["metadata_only"] = float(all(e.chunk.content_kind == "metadata" for e in hit.evidence))
    if material.url_state == "reachable":
        values["url_reachable"] = 1.0
    for witness in hit.evidence:
        score = witness.raw_score
        if witness.channel == "tfidf":
            if not 0 <= score <= 1 + 1e-9:
                raise ValueError("Invalid TF-IDF cosine")
            values["tfidf_similarity"] = min(score, 1.0)
        elif witness.channel == "e5":
            if not -1 - 1e-6 <= score <= 1 + 1e-6:
                raise ValueError("Invalid E5 cosine")
            values["e5_similarity"] = max(0.0, min((score + 1) / 2, 1.0))
        elif witness.channel == "bm25":
            if score < 0:
                raise ValueError("Invalid BM25 score")
            values["bm25_saturation"] = score / (1 + score)
    return PairFeatures(registry_hash=REGISTRY_HASH, context_id=context.context_id,
        profile_version=context.profile_version, catalog_bundle_id=batch.catalog_bundle_id,
        index_bundle_id=batch.index_bundle_id, retrieval_policy_id=batch.retrieval_policy_id,
        material_key=material.material_key, values=values, vector=encode_features(values),
        matched_history_topics=history_matches, matched_explicit_topics=explicit_matches)
