from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, ConfigDict, Field

# Жесткая привязка к словам из UI
BusinessStatus = Literal["Запускаю бизнес", "Действующий бизнес", "Масштабируюсь"]
BusinessSphere = Literal["Услуги", "Торговля", "Производство", "IT", "Другая"]
BusinessGoal = Literal["Найти клиентов", "Разобраться с финансами", "Нанять сотрудника"]
ExperienceLevel = Literal["Есть опыт", "Нет опыта"]
BudgetSensitivity = Literal["low", "medium", "high"]

class UserCreate(BaseModel):
    """Payload for user registration (onboarding is optional)."""
    email: EmailStr = Field(description="Уникальный email пользователя")
    business_status: Optional[BusinessStatus] = None
    business_sphere: Optional[BusinessSphere] = None
    current_goal: Optional[BusinessGoal] = None
    experience: Optional[ExperienceLevel] = None
    budget_sensitivity: Optional[BudgetSensitivity] = None

class UserUpdate(BaseModel):
    """Payload for partial profile update."""
    business_status: Optional[BusinessStatus] = None
    business_sphere: Optional[BusinessSphere] = None
    current_goal: Optional[BusinessGoal] = None
    experience: Optional[ExperienceLevel] = None
    budget_sensitivity: Optional[BudgetSensitivity] = None

class UserResponse(BaseModel):
    """User profile returned by the API."""
    id: int
    email: EmailStr
    business_status: Optional[str] = None
    business_sphere: Optional[str] = None
    current_goal: Optional[str] = None
    experience: Optional[str] = None
    budget_sensitivity: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)