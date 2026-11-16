"""The stage-4 serving implementation will provide this trusted boundary."""
from typing import Protocol

from app.schemas.events import TrustedActor
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse


class RecommendationProvider(Protocol):
    def recommend(self, actor: TrustedActor, request: RecommendationRequest) -> RecommendationResponse:
        """Persist the issued decision and enforce (actor, request_key) idempotency.

        Return the previously persisted response for an identical retry; reject a
        changed payload with RequestConflict. Never mark an issued item as visible.
        """
        ...


class RequestConflict(Exception):
    """The same actor/request key was reused for a different payload."""


class ProviderUnavailable(Exception):
    """The real provider cannot safely issue and persist a decision."""
