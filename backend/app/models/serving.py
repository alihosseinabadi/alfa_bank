"""Durable public response for actor-scoped HTTP idempotency."""
from uuid import UUID
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ServingRequest(Base):
    __tablename__ = 'serving_requests'
    actor_id: Mapped[UUID] = mapped_column(ForeignKey('event_actors.id'), primary_key=True)
    request_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_id: Mapped[UUID] = mapped_column(ForeignKey('recommendation_decisions.id'), nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint('decision_id'),)
