"""Versioned public HTTP contract; ML implementation details stay private."""
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

MaterialFormat = Literal['course', 'article', 'document', 'webinar', 'podcast', 'glossary', 'calculator']


class PublicModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True, revalidate_instances='always')


class RecommendationProfile(PublicModel):
    business_stage: str | None = Field(default=None, min_length=1, max_length=100)
    industry: str | None = Field(default=None, min_length=1, max_length=100)
    experience: str | None = Field(default=None, min_length=1, max_length=100)


class RecommendationConstraints(PublicModel):
    formats: list[MaterialFormat] = Field(default_factory=list, max_length=7)
    budget_preference: Literal['free_only', 'paid_allowed'] | None = None
    available_time_minutes: int | None = Field(default=None, gt=0, le=10080, strict=True)

    @field_validator('formats')
    @classmethod
    def distinct_formats(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('formats must be unique')
        return values


class RecommendationRequest(PublicModel):
    request_key: UUID
    task: str = Field(min_length=1, max_length=300)
    profile: RecommendationProfile = Field(default_factory=RecommendationProfile)
    constraints: RecommendationConstraints = Field(default_factory=RecommendationConstraints)
    limit: int = Field(default=6, ge=1, le=6, strict=True)
    # Reserved for a future authenticated principal; never trusted as authentication.
    user_id: int | None = Field(default=None, gt=0, strict=True)


class RecommendationCard(PublicModel):
    item_id: UUID
    material_key: str = Field(min_length=1, max_length=160)
    position: int = Field(ge=1, le=6, strict=True)
    title: str = Field(min_length=1, max_length=500)
    format: MaterialFormat
    url: HttpUrl
    link_status: Literal['reachable', 'unknown']
    access_type: str | None = Field(default=None, min_length=1, max_length=100)
    requires_access_check: bool
    listed_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    duration_minutes: float | None = Field(default=None, gt=0)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def validate_access_and_url(self):
        if self.access_type != 'Открытый' and not self.requires_access_check:
            raise ValueError('unknown or restricted access requires verification')
        if self.url.username or self.url.password:
            raise ValueError('URL credentials are not allowed')
        return self


class RecommendationResponse(PublicModel):
    learning_mode: Literal['standard', 'test_fast'] = 'standard'
    status: Literal['matched', 'starter', 'needs_clarification', 'no_eligible']
    decision_id: UUID
    items: list[RecommendationCard] = Field(max_length=6)
    message: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode='after')
    def validate_result(self):
        if bool(self.items) != (self.status in {'matched', 'starter'}):
            raise ValueError('status and items disagree')
        if not self.items and not self.message:
            raise ValueError('empty results require a user-facing message')
        if [x.position for x in self.items] != list(range(1, len(self.items) + 1)):
            raise ValueError('items must be in consecutive displayed order')
        if len({x.item_id for x in self.items}) != len(self.items):
            raise ValueError('item IDs must be unique')
        if len({x.material_key for x in self.items}) != len(self.items):
            raise ValueError('materials must be unique')
        return self


class SessionResponse(PublicModel):
    csrf_token: str
