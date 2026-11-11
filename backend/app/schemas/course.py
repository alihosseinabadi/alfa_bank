from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

CourseType = Literal["article", "template", "lesson", "course"]
Difficulty = Literal["базовый", "средний", "продвинутый"]
Source = Literal["synthetic", "real", "imported"]


class CourseBase(BaseModel):
    """Base course attributes with strict validation."""
    title: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=256)
    type: CourseType
    price: Decimal = Field(ge=0, decimal_places=2, max_digits=10)
    is_free: bool
    duration_minutes: int = Field(gt=0)
    category: str = Field(min_length=1, max_length=64)
    difficulty: Difficulty
    source: Source

    model_config = ConfigDict(str_strip_whitespace=True)


class CourseResponse(CourseBase):
    """Course data returned by the API."""
    id: int
    model_config = ConfigDict(from_attributes=True)