from decimal import Decimal
from pydantic import BaseModel, ConfigDict

class CourseBase(BaseModel):
    """Base course attributes."""
    title: str
    description: str
    type: str
    price: Decimal
    is_free: bool
    duration_minutes: int
    category: str
    difficulty: str
    source: str

class CourseResponse(CourseBase):
    """Course data returned by the API."""
    id: int
    model_config = ConfigDict(from_attributes=True)