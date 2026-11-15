"""
Public API for the models layer.

Importing every model here registers it in Base.metadata.
Alembic autogenerate sees only models imported via this module,
so any new model must be added to the imports and to __all__.
"""

from app.models.user import User
from app.models.course import Course
from app.models.recommendation import BanditState, RecommendationImpression
from app.models.interaction import Interaction

__all__ = [
    "User",
    "Course",
    "RecommendationImpression",
    "BanditState",
    "Interaction",
]