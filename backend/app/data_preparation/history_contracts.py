"""Archive observations, not online impressions or reward events."""
from typing import Literal
from pydantic import Field, model_validator
from .contracts import Record

HISTORY_VERSION = "history-v1"
TIME_POLICY = "archive-month-v1"
RESOLUTION_VERSION = "archive-entities-v1"

class FeedbackTag(Record):
    tag_id: str
    label: str | None = None
    text: str | None = None
    status: Literal["resolved", "deleted", "unknown"]

class Observation(Record):
    observation_id: str
    source_table: Literal["CourseUserBindings", "CourseUserLessonBindings", "UserRatings"]
    source_record_id: str
    source_snapshot_id: str
    user_key: str | None = None
    source_user_id: str | None = None
    observation_kind: Literal["enrollment_state", "lesson_progress", "explicit_rating"]
    source_entity_table: str | None = None
    source_entity_id: str
    source_entity_type_id: str | None = None
    material_key: str | None = None
    lesson_id: str | None = None
    course_user_binding_id: str | None = None
    event_time: str | None = None  # YYYY-MM; never a fabricated precise timestamp
    event_time_source: str | None = None
    time_granularity: Literal["month", "unknown"] = "unknown"
    time_confidence: Literal["coarse", "uncertain", "missing"] = "missing"
    ingestion_time: str
    available_from_month: str | None = None
    evaluation_eligible: bool = False
    evaluation_exclusion_reasons: list[str] = Field(default_factory=list)
    resolution_status: Literal["accepted", "unassigned", "rejected"] = "rejected"
    resolution_rule: str = "unresolved"
    quality_flags: list[str] = Field(default_factory=list)
    raw_values: dict[str, str | None] = Field(default_factory=dict)
    raw_dates: dict[str, str | None] = Field(default_factory=dict)
    rating_value: int | None = None
    rating_group_id: str | None = None
    rating_scale_values: list[int] = Field(default_factory=list)
    rating_scale_status: Literal["not_applicable", "resolved", "unknown", "invalid_value"] = "not_applicable"
    feedback_tags: list[FeedbackTag] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_resolution(self):
        if self.resolution_status == "accepted":
            if not self.user_key or not self.source_user_id or not self.source_entity_table:
                raise ValueError("Accepted observation needs user and resolved entity")
            if not self.material_key and self.source_entity_table != "Lessons":
                raise ValueError("Only resolved lessons may have no canonical material")
        if self.evaluation_eligible and (self.resolution_status != "accepted" or
            self.time_confidence != "coarse" or not self.available_from_month):
            raise ValueError("Invalid temporal evaluation eligibility")
        if self.raw_values.keys() & {"IP", "email", "CreatedById", "ModifiedById"}:
            raise ValueError("Forbidden derived history fields")
        return self

class LearningState(Record):
    user_key: str
    course_user_binding_id: str
    material_key: str
    stream_id: str | None
    subscription_id: str | None
    is_completed: bool
    completed_lesson_ids: list[str]
    active_leaf_lesson_count: int
    source_lessons_completed: int
    candidate_lesson_ids: list[str]
    next_lesson_id: str | None = None
    access_state: Literal["blocked", "unknown"]
    requires_access_check: bool = True
    requires_progression_check: bool = True
    entitlement_granted: bool = False
    quality_flags: list[str]
    as_of: str

class RelatedMaterial(Record):
    relation_id: str
    source_record_id: str  # canonical JSON encoding of full composite PK
    source_material_key: str | None
    target_material_key: str | None
    status: Literal["resolved", "unresolved", "ambiguous", "self_relation"]
    resolution_rule: str
    order: int | None = None
    raw_course_id: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
