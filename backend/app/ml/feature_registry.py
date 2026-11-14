"""Versioned observable features; null is not encoded as a negative preference."""
from dataclasses import asdict, dataclass
import math
import numpy as np
from .profile_policy import fingerprint
from .ranking_contracts import FEATURE_VERSION

@dataclass(frozen=True)
class FeatureSpec:
    name: str
    meaning: str
    source: str
    missing: str = "null; vector value 0 with known-mask 0"
    dtype: str = "nullable float32"
    minimum: float = 0.0
    maximum: float = 1.0

FEATURE_REGISTRY = (
    FeatureSpec("retrieval_rank_score", "1/log2(retrieval rank+1); not a probability", "validated retrieval batch"),
    FeatureSpec("task_text_overlap", "Fraction of distinct task tokens found in public evidence", "explicit task + public chunks"),
    FeatureSpec("explicit_topic_match", "Fraction of explicitly selected topics in material topics", "explicit-topics context + profile preferences + catalog topics"),
    FeatureSpec("history_topic_match", "Approved positive topic mass matching material topics", "context-approved profile topics + catalog topics"),
    FeatureSpec("history_support", "Distinct supporting materials n/(n+2), heuristic", "profile topic evidence"),
    FeatureSpec("avoidance_topic_match", "Approved negative topic mass matching material topics; soft cue", "context-approved profile negative evidence + catalog topics"),
    FeatureSpec("format_match", "Exact fit of requested format; unspecified is null", "request constraints + catalog format"),
    FeatureSpec("open_access", "Open access label, independent of listed price", "catalog access_type"),
    FeatureSpec("duration_fit", "Known duration fits requested time; unspecified/unknown is null", "request time + catalog duration"),
    FeatureSpec("listed_price_scaled", "min(listed RUB price/10000,1); diagnostic only", "catalog listed_price"),
    FeatureSpec("industry_match", "Exact normalized match, only when both sides have labels", "explicit industry + source catalog industry labels"),
    FeatureSpec("stage_match", "Unsupported until reviewed material stage labels exist", "unavailable in current catalog"),
    FeatureSpec("experience_match", "Unsupported until reviewed material level labels exist", "unavailable in current catalog"),
    FeatureSpec("seen_before", "Positive evidence of recorded interaction; absence remains unknown", "profile material evidence"),
    FeatureSpec("completed", "Recorded completion state, not entitlement", "compatible learning-state snapshot"),
    FeatureSpec("progress_fraction", "Maximum recorded active-leaf completion fraction across bindings", "compatible learning-state snapshot"),
    FeatureSpec("public_evidence", "All accepted channel witnesses have public scope", "validated public chunks"),
    FeatureSpec("metadata_only", "All witnesses are card metadata", "public chunk content_kind"),
    FeatureSpec("url_reachable", "Reachable=1; temporary failure/unchecked remain unknown", "catalog url_state"),
    FeatureSpec("tfidf_similarity", "TF-IDF cosine from its own channel; diagnostic", "TF-IDF evidence score"),
    FeatureSpec("e5_similarity", "(E5 cosine+1)/2; diagnostic, not a relevance probability", "E5 evidence score"),
    FeatureSpec("bm25_saturation", "BM25 score/(1+score); diagnostic, not calibrated", "BM25 evidence score"),
)
FEATURE_NAMES = tuple(spec.name for spec in FEATURE_REGISTRY)
VECTOR_LAYOUT = ("bias",) + FEATURE_NAMES + tuple(name + "__known" for name in FEATURE_NAMES)
FEATURE_DIMENSION = len(VECTOR_LAYOUT)

def registry_document():
    return {"version": FEATURE_VERSION, "features": [asdict(s) for s in FEATURE_REGISTRY],
            "vector_layout": list(VECTOR_LAYOUT), "dimension": FEATURE_DIMENSION,
            "encoding": "bias, nullable feature values (zero-filled), then observed-value mask"}

REGISTRY_HASH = fingerprint(registry_document())

def encode_features(values):
    if set(values) != set(FEATURE_NAMES):
        raise ValueError("Feature registry mismatch")
    observed, mask = [], []
    for name in FEATURE_NAMES:
        value = values[name]
        if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
            raise ValueError("Feature outside finite unit range: " + name)
        observed.append(0.0 if value is None else value)
        mask.append(float(value is not None))
    return np.asarray([1.0] + observed + mask, dtype=np.float32).tolist()

def validate_features(features):
    if features.version != FEATURE_VERSION or features.registry_hash != REGISTRY_HASH:
        raise ValueError("Incompatible feature registry")
    if features.vector != encode_features(features.values):
        raise ValueError("Feature vector/mask mismatch")
