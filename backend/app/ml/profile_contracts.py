"""Pure profile and request DTOs; no serving, database or ETL imports."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

PROFILE_SCHEMA_VERSION = "profiles-v1"
CONTEXT_VERSION = "request-context-v1"
MaterialFormat = Literal["course","article","document","webinar","podcast","glossary","calculator"]

class ProfileRecord(BaseModel):
    model_config = ConfigDict(extra="forbid",allow_inf_nan=False)

class ExplicitPreferences(ProfileRecord):
    business_stage: str | None = None
    industry: str | None = None
    experience: str | None = None
    budget_preference: Literal["free_only","paid_allowed"] | None = None
    available_time_minutes: int | None = Field(default=None,gt=0)
    formats: list[MaterialFormat] = Field(default_factory=list)
    selected_topics: list[str] = Field(default_factory=list)
    reset_inferred: bool = False

    @field_validator("business_stage","industry","experience",mode="before")
    @classmethod
    def clean_optional_text(cls,value):
        return value.strip() or None if isinstance(value,str) else value

    @field_validator("formats","selected_topics")
    @classmethod
    def unique_values(cls,value):
        return list(dict.fromkeys(x.strip() for x in value if x.strip()))

class MaterialEvidence(ProfileRecord):
    material_key: str
    implicit_strength: float = Field(ge=0,le=1)
    explicit_positive: float = Field(ge=0,le=1)
    explicit_negative: float = Field(ge=0,le=1)
    positive_strength: float = Field(ge=0,le=1)
    negative_strength: float = Field(ge=0,le=1)
    net_strength: float = Field(ge=0,le=1)
    source_kinds: list[str]
    observation_ids: list[str]

class TopicEvidence(ProfileRecord):
    topic: str
    positive_strength: float = Field(ge=0)
    negative_strength: float = Field(ge=0)
    net_strength: float = Field(ge=0)
    supporting_material_keys: list[str]
    negative_material_keys: list[str]
    support_count: int = Field(ge=0)
    confidence: float = Field(ge=0,le=1)

class TitleFallback(ProfileRecord):
    material_key: str
    title: str
    evidence_strength: float = Field(gt=0,le=1)
    source: Literal["observed_material_title"] = "observed_material_title"

class UserProfile(ProfileRecord):
    schema_version: str = PROFILE_SCHEMA_VERSION
    user_key: str
    profile_version: str
    policy_version: str
    policy_hash: str
    history_bundle_id: str
    catalog_bundle_id: str
    mode: Literal["current","historical"]
    cutoff_month: str | None = None
    context_topic_limit: int = Field(default=3,ge=1,le=10)
    explicit_preferences: ExplicitPreferences
    topic_weights: dict[str,float]
    avoidance_weights: dict[str,float]
    topic_evidence: list[TopicEvidence]
    material_evidence: list[MaterialEvidence]
    title_fallbacks: list[TitleFallback]
    observed_format_counts: dict[str,int]
    support_material_count: int = Field(ge=0)
    cold_start: bool
    cold_start_reason: str | None
    quality_flags: list[str]
    skipped_observations: dict[str,int]
    confidence_is_calibrated: bool = False
    learning_state_reference: str | None = None

class ExplicitConstraints(ProfileRecord):
    # None means inherit; [] explicitly clears a previous format restriction.
    formats: list[MaterialFormat] | None = None
    available_time_minutes: int | None = Field(default=None,gt=0)
    budget_preference: Literal["free_only","paid_allowed"] | None = None

class ContinuationCandidate(ProfileRecord):
    material_key: str
    course_user_binding_id: str
    candidate_lesson_ids: list[str]
    requires_access_check: Literal[True] = True
    requires_progression_check: Literal[True] = True
    entitlement_granted: Literal[False] = False
    source: Literal["learning_state_snapshot"] = "learning_state_snapshot"

class RequestContext(ProfileRecord):
    schema_version: str = CONTEXT_VERSION
    context_id: str
    profile_version: str
    user_key: str
    task_text: str
    query_text: str
    query_source: Literal["explicit_task","explicit_topics","inferred_topics","material_titles","cold_start"]
    query_strategy: Literal["task_first","explicit_topics_first","profile_fallback","starter_required"]
    supporting_interests: list[str]
    avoidance_topics: list[str]
    avoidance_is_hard_filter: Literal[False] = False
    history_weight: float = Field(ge=0,le=1)
    formats: list[MaterialFormat]
    available_time_minutes: int | None = Field(default=None,gt=0)
    budget_preference: Literal["free_only","paid_allowed"] | None
    business_stage: str | None
    industry: str | None
    experience: str | None
    cold_start: bool
    fallback_required: bool
    clarification: str | None
    reason_codes: list[str]
    continuation_candidates: list[ContinuationCandidate]
    mode: Literal["current","historical"]
    cutoff_month: str | None
