"""Durable reward observations. Each revision is append-only."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base

class RewardObservation(Base):
    __tablename__ = 'reward_observations'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    impression_id: Mapped[UUID] = mapped_column(ForeignKey('recommendation_impressions.id'))
    model_key: Mapped[str] = mapped_column(String(80))
    registry_hash: Mapped[str] = mapped_column(String(64))
    policy_hash: Mapped[str] = mapped_column(String(64))
    features: Mapped[list] = mapped_column(JSONB)
    reward: Mapped[float] = mapped_column(Float)
    revision: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('model_key','impression_id'), CheckConstraint('reward >= 0 AND reward <= 1'), CheckConstraint('revision >= 1'))

class RewardRevision(Base):
    __tablename__ = 'reward_revisions'
    observation_id: Mapped[UUID] = mapped_column(ForeignKey('reward_observations.id'), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    old_reward: Mapped[float | None] = mapped_column(Float)
    new_reward: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    projection_version: Mapped[str] = mapped_column(String(40), default='verified-free-v2', server_default='legacy-v1')
    reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    __table_args__ = (CheckConstraint('revision >= 1'), CheckConstraint('new_reward >= 0 AND new_reward <= 1'), CheckConstraint('old_reward IS NULL OR (old_reward >= 0 AND old_reward <= 1)'))

class SlateRandomSeed(Base):
    __tablename__ = 'slate_random_seeds'
    actor_id: Mapped[UUID] = mapped_column(ForeignKey('event_actors.id'), primary_key=True)
    request_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    seed: Mapped[int] = mapped_column(__import__('sqlalchemy').BigInteger)
    request_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (CheckConstraint('seed >= 0'),)
