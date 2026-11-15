"""Stage-7 DTOs. Actor/payment principals are supplied by trusted server code."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,AwareDatetime

class EventDTO(BaseModel):
    model_config=ConfigDict(extra="forbid",allow_inf_nan=False,frozen=True)

class TrustedActor(EventDTO):
    actor_id: UUID
    session_id: UUID
    kind: Literal["anonymous","authenticated"]

class PaymentPrincipal(EventDTO):
    provider: str=Field(pattern=r"^[a-zA-Z0-9_-]{1,32}$")
    environment: Literal["test","production"]="test"

class VisibilityAck(EventDTO):
    event_key: UUID
    item_id: UUID
    material_key: str=Field(min_length=1,max_length=160)
    client_time: AwareDatetime|None=None
    visible_ms: int=Field(ge=1000,le=86400000)
    visible_fraction: float=Field(ge=.5,le=1)

class ClientAction(EventDTO):
    event_key: UUID
    item_id: UUID
    material_key: str=Field(min_length=1,max_length=160)
    impression_id: UUID|None=None
    kind: Literal["click","material_open","purchase_intent"]
    client_time: AwareDatetime|None=None

class PaymentNotice(EventDTO):
    event_key: UUID
    item_id: UUID
    material_key: str=Field(min_length=1,max_length=160)
    impression_id: UUID|None=None
    transaction_key: str=Field(pattern=r"^[a-zA-Z0-9_.:-]{1,128}$")
    amount: Decimal=Field(gt=0,max_digits=12,decimal_places=2)
    currency: str=Field(pattern=r"^[A-Z]{3}$")
    occurred_at: AwareDatetime|None=None
