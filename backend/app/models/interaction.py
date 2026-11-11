"""
Interaction model.

Every user action is one row. Idempotency is enforced by unique constraints,
not by application code.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Interaction(Base):
    """
    One user event on one impression.

    `user_id` and `course_id` are denormalized from the impression
    so we can enforce "one purchase per (user, course)" cheaply.
    """

    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True)

    impression_id = Column(
        Integer,
        ForeignKey("recommendation_impressions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Denormalized from impression — required for unique purchase constraint.
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

    event_type = Column(String(20), nullable=False)

    reward = Column(Numeric(10, 6), nullable=False, default=0)

    timestamp = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- Relationships ---
    impression = relationship(
        "RecommendationImpression",
        back_populates="interactions",
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('click', 'inspect', 'purchase')",
            name="event_type_valid",
        ),
        UniqueConstraint(
            "impression_id",
            "event_type",
            name="impression_event_type",
        ),
        Index(
            "unique_purchase_per_user_course",
            "user_id",
            "course_id",
            unique=True,
            postgresql_where=text("event_type = 'purchase'"),
        ),
    )