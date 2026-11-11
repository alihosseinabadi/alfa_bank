"""
Canonical recommendation log and bandit state.

`recommendation_impressions` is the single canonical record of a course
shown to a user. There is no separate recommendations table and no separate
impressions table. `bandit_state` holds the shared, versioned model state.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class RecommendationImpression(Base):
    """
    One row = one course at one position in one slate.

    Written at recommendation time (Phase 4). Both scores are stored
    separately so we can compare retrieval vs. bandit decisions later.
    """

    __tablename__ = "recommendation_impressions"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )

    slate_id = Column(String(64), nullable=False)
    position = Column(Integer, nullable=False)

    retrieval_score = Column(Numeric(10, 6), nullable=False)
    bandit_score = Column(Numeric(10, 6), nullable=False)

    algorithm = Column(String(50), nullable=False)
    model_version = Column(String(50), nullable=False)

    shown_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- Relationships ---
    user = relationship("User", back_populates="impressions")
    course = relationship("Course", back_populates="impressions")
    interactions = relationship(
        "Interaction",
        back_populates="impression",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("slate_id", "position", name="slate_position"),
        UniqueConstraint("slate_id", "course_id", name="slate_course"),
    )


class BanditState(Base):
    """
    Shared, versioned LinUCB state.

    One row per model_version. `feature_version` guards against loading
    state incompatible with the current feature layout.
    """

    __tablename__ = "bandit_state"

    id = Column(Integer, primary_key=True)

    model_version = Column(String(50), nullable=False, unique=True)
    feature_version = Column(String(50), nullable=False)

    params = Column(JSONB, nullable=False)

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )