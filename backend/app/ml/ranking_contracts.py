"""Typed boundary between retrieval, prior ranking and future exposure logging."""
from typing import Literal
from pydantic import Field, model_validator
from .profile_contracts import ProfileRecord, MaterialFormat, ContinuationCandidate
from .retrieval_contracts import SearchMaterial, PublicSearchChunk, NextStep

RANKING_INPUT_VERSION = "ranking-input-v1"
FEATURE_VERSION = "pair-features-v1"
RANKING_VERSION = "prior-ranking-v1"
Channel = Literal["tfidf", "topic_baseline", "bm25", "e5"]

class RankingMaterial(SearchMaterial):
    industry_labels: list[str] = Field(default_factory=list)

class ChannelEvidence(ProfileRecord):
    channel: Channel
    raw_score: float
    channel_rank: int = Field(ge=1, le=50)
    chunk: PublicSearchChunk

class RetrievalHit(ProfileRecord):
    material_key: str
    retrieval_rank: int = Field(ge=1, le=50)
    raw_score: float
    evidence: list[ChannelEvidence] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence(self):
        channels = [e.channel for e in self.evidence]
        if len(channels) != len(set(channels)):
            raise ValueError("Duplicate evidence channel")
        if any(e.chunk.material_key != self.material_key or e.chunk.access_scope != "public" for e in self.evidence):
            raise ValueError("Evidence must be public and belong to the candidate")
        return self

class RetrievalBatch(ProfileRecord):
    schema_version: Literal["ranking-input-v1"] = RANKING_INPUT_VERSION
    context_id: str
    index_bundle_id: str = Field(min_length=1)
    catalog_bundle_id: str = Field(min_length=1)
    retrieval_policy_id: str = Field(min_length=1)
    retrieval_parameters: dict[str, str | float] = Field(default_factory=dict)
    method: Literal["tfidf", "topic_baseline", "bm25", "e5", "hybrid"]
    status: Literal["matched", "starter", "needs_clarification", "no_eligible"]
    clarification: str | None = None
    hits: list[RetrievalHit] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_hits(self):
        if len({h.material_key for h in self.hits}) != len(self.hits):
            raise ValueError("Duplicate canonical candidate")
        if [h.retrieval_rank for h in self.hits] != list(range(1, len(self.hits) + 1)):
            raise ValueError("Candidate ranks must be consecutive and ordered")
        if bool(self.hits) != (self.status in {"matched", "starter"}):
            raise ValueError("Inconsistent retrieval status")
        return self

class ProgressEvidence(ProfileRecord):
    material_key: str
    completed: bool | None = None
    progress_fraction: float | None = Field(default=None, ge=0, le=1)
    source: Literal["learning_state_snapshot"] = "learning_state_snapshot"

class ProgressSnapshot(ProfileRecord):
    user_key: str
    history_bundle_id: str
    mode: Literal["current", "historical"]
    cutoff_month: str | None = None
    entries: list[ProgressEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_entries(self):
        if len({e.material_key for e in self.entries}) != len(self.entries):
            raise ValueError("Duplicate progress material")
        if self.mode == "historical" and self.entries:
            raise ValueError("Current progress cannot enter a historical context")
        return self

class PairFeatures(ProfileRecord):
    version: Literal["pair-features-v1"] = FEATURE_VERSION
    registry_hash: str
    context_id: str
    profile_version: str
    catalog_bundle_id: str
    index_bundle_id: str
    retrieval_policy_id: str
    material_key: str
    values: dict[str, float | None]
    vector: list[float]
    matched_history_topics: list[str] = Field(default_factory=list)
    matched_explicit_topics: list[str] = Field(default_factory=list)

class Citation(ProfileRecord):
    channel: Channel
    chunk_id: str
    source_block_ids: list[str]
    excerpt: str
    raw_score: float
    channel_rank: int

class RankingReason(ProfileRecord):
    feature: str
    value: float
    source: str
    text: str

class RankedMaterial(ProfileRecord):
    material_key: str
    title: str
    item_type: MaterialFormat
    url: str
    access_type: str
    listed_price: float | None
    duration_minutes: float | None
    duration_fit: Literal["fits", "unknown", "not_requested"]
    url_state: str
    quality_flags: list[str]
    retrieval_rank: int
    rank: int
    prior_score: float
    score_components: dict[str, float]
    features: PairFeatures
    reasons: list[RankingReason]
    citations: list[Citation]
    next_step: NextStep
    # Public discovery of a paid card does not grant the right to its body.
    requires_access_check: bool

class RankingResult(ProfileRecord):
    version: Literal["prior-ranking-v1"] = RANKING_VERSION
    context_id: str
    profile_version: str
    index_bundle_id: str
    catalog_bundle_id: str
    retrieval_policy_id: str
    feature_registry_hash: str
    policy_id: str
    retrieval_method: str
    retrieval_parameters: dict[str, str | float]
    status: Literal["matched", "starter", "needs_clarification", "no_eligible"]
    clarification: str | None = None
    candidates: list[RankedMaterial]
    excluded_counts: dict[str, int]
    continuation_candidates: list[ContinuationCandidate]
    quality_flags: list[str]
