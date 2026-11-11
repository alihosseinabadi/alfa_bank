from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict

class UserCreate(BaseModel):
    """Payload for user registration (onboarding is optional)."""
    email: EmailStr
    business_status: Optional[str] = None
    business_sphere: Optional[str] = None
    current_goal: Optional[str] = None
    budget_sensitivity: Optional[str] = None

class UserUpdate(BaseModel):
    """Payload for partial profile update."""
    business_status: Optional[str] = None
    business_sphere: Optional[str] = None
    current_goal: Optional[str] = None
    budget_sensitivity: Optional[str] = None

class UserResponse(BaseModel):
    """User profile returned by the API."""
    id: int
    email: EmailStr
    business_status: Optional[str]
    business_sphere: Optional[str]
    current_goal: Optional[str]
    budget_sensitivity: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)