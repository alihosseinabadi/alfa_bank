"""Versioned, framework-independent catalog contracts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

CATALOG_VERSION = "catalog-v2"
CLEANING_VERSION = "blocks-v1"
ENCODER = "intfloat/multilingual-e5-base"
ENCODER_REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"

class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

class SourceIdentity(Record):
    table: str
    record_id: str

class Material(Record):
    material_key: str
    item_type: Literal["course", "article", "document", "webinar", "podcast", "glossary", "calculator"]
    source_identities: list[SourceIdentity]
    title: str
    descriptions: list[str] = Field(default_factory=list)
    url: str = ""
    topics: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    industry_labels: list[str] = Field(default_factory=list)
    access_type: str
    listed_price: float | None = Field(default=None, ge=0)
    price_is_missing: bool = True
    price_rule: str = "unknown"
    duration_minutes: float | None = Field(default=None, gt=0)
    published_at: str | None = None
    publication_status: str
    source_entity_type_id: str | None = None
    exclusion_reasons: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    is_discoverable: bool = False
    content_coverage: Literal["metadata_only", "body", "partial_body"] = "metadata_only"
    transcript_available: bool = False
    url_state: Literal["unchecked", "reachable", "unavailable", "temporary_failure"] = "unchecked"
    snapshot_id: str
    extracted_at: str
    content_version: str = CATALOG_VERSION
    content_hash: str = ""
    raw: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_identity(self):
        if not self.material_key.startswith(self.item_type + ":") or not self.source_identities:
            raise ValueError("Invalid canonical identity")
        if self.is_discoverable and (self.exclusion_reasons or not self.title or not self.url):
            raise ValueError("Invalid discovery eligibility")
        return self

class Alias(Record):
    source_table: str
    source_record_id: str
    material_key: str
    rule: str

class ContentBlock(Record):
    block_id: str
    material_key: str
    source_table: str
    source_record_id: str
    order: int
    text: str
    access_scope: Literal["public", "entitled"]
    entitlement_key: str | None = None
    content_kind: Literal["metadata", "body"] = "body"

    @model_validator(mode="after")
    def check_access(self):
        if self.access_scope == "entitled" and not self.entitlement_key:
            raise ValueError("Protected block requires entitlement key")
        return self

class Chunk(Record):
    chunk_id: str
    material_key: str
    order: int
    text: str
    source_block_ids: list[str]
    access_scope: Literal["public", "entitled"]
    entitlement_key: str | None = None
    token_count: int = Field(gt=0, le=512)
    content_hash: str
    encoder_revision: str = ENCODER_REVISION

class ChildLink(Record):
    source_table: str = "CourseLessonBindings"
    source_record_id: str
    material_key: str
    lesson_id: str
    order: int
    is_closed: bool | None
    is_trial: bool | None
    closed_until: str | None = None
