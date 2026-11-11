from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict

EventType = Literal["click", "inspect", "purchase"]

class InteractionCreate(BaseModel):
    """Payload for recording a user action on an impression."""
    impression_id: int
    event_type: EventType

class InteractionResponse(BaseModel):
    """Result of recording an interaction."""
    id: int
    impression_id: int
    event_type: str
    reward: Decimal
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)