"""Legacy Mongo/fake-score recommendation service is disabled."""
from fastapi import HTTPException, status


def get_personalized_feed(db, user_id):
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Recommendation service is not integrated yet")
