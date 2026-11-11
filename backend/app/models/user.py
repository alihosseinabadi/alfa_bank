"""
User model.

Represents an entrepreneur profile: onboarding answers used as context
for retrieval and LinUCB. No secrets — auth is out of MVP scope.
"""

from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """
    Entrepreneur profile.

    Onboarding fields (business_status, business_sphere, current_goal,
    budget_sensitivity) correspond to the "What do you want to learn?"
    screen on the mockups.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    # Natural login key.
    email = Column(String(255), unique=True, index=True, nullable=False)

    # --- Onboarding profile ---
    business_status = Column(String(50), nullable=True)
    business_sphere = Column(String(100), nullable=True)
    current_goal = Column(String(100), nullable=False, index=True)
    budget_sensitivity = Column(String(20), nullable=True)
    experience = Column(String(50), nullable=True)

    # --- Service fields ---
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --- Relationships ---
    impressions = relationship(
        "RecommendationImpression",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )