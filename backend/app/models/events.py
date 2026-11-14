"""Issued decisions are separate from client-confirmed visible impressions."""
from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import String,DateTime,ForeignKey,UniqueConstraint,CheckConstraint,Float,Integer,Boolean,Numeric,func
from sqlalchemy.dialects.postgresql import UUID as PGUUID,JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.database.base import Base

class Actor(Base):
    __tablename__="event_actors"
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True)
    kind:Mapped[str]=mapped_column(String(16))
    anonymous_session_id:Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(CheckConstraint("kind IN ('anonymous','authenticated')"),
        CheckConstraint("(kind='anonymous' AND anonymous_session_id IS NOT NULL) OR (kind='authenticated' AND anonymous_session_id IS NULL)"),)

class Decision(Base):
    __tablename__="recommendation_decisions"
    protocol_version:Mapped[str]=mapped_column(String(24),default="events-v1",server_default="events-v1")
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    actor_id:Mapped[UUID]=mapped_column(ForeignKey("event_actors.id"),index=True)
    session_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    request_key:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    payload_hash:Mapped[str]=mapped_column(String(64))
    snapshot:Mapped[dict]=mapped_column(JSONB)
    simulated:Mapped[bool]=mapped_column(Boolean)
    issued_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(UniqueConstraint("actor_id","request_key"),)

class DecisionItem(Base):
    __tablename__="recommendation_items"
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    decision_id:Mapped[UUID]=mapped_column(ForeignKey("recommendation_decisions.id"),index=True)
    material_key:Mapped[str]=mapped_column(String(160))
    position:Mapped[int]=mapped_column(Integer)
    access_type:Mapped[str]=mapped_column(String(32))
    snapshot:Mapped[dict]=mapped_column(JSONB)
    __table_args__=(UniqueConstraint("decision_id","position"),UniqueConstraint("decision_id","material_key"),
        CheckConstraint("position BETWEEN 1 AND 50"),)

class Impression(Base):
    __tablename__="recommendation_impressions"
    protocol_version:Mapped[str]=mapped_column(String(24),default="events-v1",server_default="events-v1")
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    item_id:Mapped[UUID]=mapped_column(ForeignKey("recommendation_items.id"),unique=True)
    client_time:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    visible_ms:Mapped[int]=mapped_column(Integer)
    visible_fraction:Mapped[float]=mapped_column(Float)
    source:Mapped[str]=mapped_column(String(32),default="client_visibility_ack")
    confirmed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(CheckConstraint("visible_ms BETWEEN 1000 AND 86400000"),
        CheckConstraint("visible_fraction BETWEEN 0.5 AND 1"),CheckConstraint("source='client_visibility_ack'"),)

class Interaction(Base):
    __tablename__="interaction_events"
    protocol_version:Mapped[str]=mapped_column(String(24),default="events-v1",server_default="events-v1")
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    actor_id:Mapped[UUID]=mapped_column(ForeignKey("event_actors.id"),index=True)
    session_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    item_id:Mapped[UUID]=mapped_column(ForeignKey("recommendation_items.id"))
    impression_id:Mapped[UUID]=mapped_column(ForeignKey("recommendation_impressions.id"),index=True)
    kind:Mapped[str]=mapped_column(String(32),index=True)
    source:Mapped[str]=mapped_column(String(32))
    trust:Mapped[str]=mapped_column(String(32))
    simulated:Mapped[bool]=mapped_column(Boolean)
    is_free_open:Mapped[bool]=mapped_column(Boolean,default=False)
    qualified_use:Mapped[bool]=mapped_column(Boolean,default=False)
    client_time:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    ingested_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    provider:Mapped[str|None]=mapped_column(String(32))
    payment_environment:Mapped[str|None]=mapped_column(String(16))
    transaction_key:Mapped[str|None]=mapped_column(String(128))
    amount:Mapped[float|None]=mapped_column(Numeric(12,2))
    currency:Mapped[str|None]=mapped_column(String(3))
    payment_hash:Mapped[str|None]=mapped_column(String(64))
    __table_args__=(UniqueConstraint("provider","payment_environment","transaction_key"),
        CheckConstraint("kind IN ('click','material_open','purchase_intent','purchase_confirmed')"),
        CheckConstraint("(kind='purchase_confirmed' AND source='payment_server' AND trust='server_verified' AND provider IS NOT NULL AND payment_environment IS NOT NULL AND payment_environment IN ('test','production') AND transaction_key IS NOT NULL AND amount IS NOT NULL AND amount>0 AND currency IS NOT NULL AND payment_hash IS NOT NULL) OR (kind!='purchase_confirmed' AND source='client' AND trust='client_reported' AND provider IS NULL AND payment_environment IS NULL AND transaction_key IS NULL AND amount IS NULL AND currency IS NULL AND payment_hash IS NULL)"),
        CheckConstraint("qualified_use=false"),
        CheckConstraint("is_free_open=false OR kind='material_open'"),)

class MessageReceipt(Base):
    __tablename__="event_receipts"
    protocol_version:Mapped[str]=mapped_column(String(24),default="events-v1",server_default="events-v1")
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    actor_id:Mapped[UUID]=mapped_column(ForeignKey("event_actors.id"))
    event_key:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    message_type:Mapped[str]=mapped_column(String(32))
    payload_hash:Mapped[str]=mapped_column(String(64))
    impression_id:Mapped[UUID|None]=mapped_column(ForeignKey("recommendation_impressions.id"))
    interaction_id:Mapped[UUID|None]=mapped_column(ForeignKey("interaction_events.id"))
    ingested_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(UniqueConstraint("actor_id","event_key"),
        CheckConstraint("(message_type='visibility' AND impression_id IS NOT NULL AND interaction_id IS NULL) OR (message_type IN ('click','material_open','purchase_intent','purchase_confirmed') AND impression_id IS NULL AND interaction_id IS NOT NULL)"),)
