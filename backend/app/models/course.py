"""
Course model.

Catalogue of learning materials with attributes and provenance (`source`).
Models describe storage, not rules — no ranking or reward logic here.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Course(Base):
    """
    Learning material (article, template, lesson, course).

    `source` records provenance: where the course came from
    (synthetic / real / imported).
    """

    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    # article | template | lesson | course
    type = Column(String(50), nullable=False, index=True)

    # Money — Numeric(10, 2), never Float.
    price = Column(Numeric(10, 2), nullable=False, default=0)
    is_free = Column(Boolean, nullable=False, default=True)

    # Duration must be strictly positive (CHECK below).
    duration_minutes = Column(Integer, nullable=False)

    category = Column(String(100), nullable=False, index=True)
    difficulty = Column(String(50), nullable=False)

    # Provenance: synthetic | real | imported.
    source = Column(String(20), nullable=False, index=True)

    # --- Relationships ---
    impressions = relationship(
        "RecommendationImpression",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint(
            "duration_minutes > 0",
            name="duration_minutes_positive",
        ),
        CheckConstraint(
            "(is_free = true AND price = 0) OR (is_free = false AND price > 0)",
            name="price_is_free_consistent",
        ),
    )