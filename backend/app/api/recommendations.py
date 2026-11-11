from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.recommendation import FeedResponse
from app.services import recommendation_s

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

@router.get("/{user_id}", response_model=FeedResponse)
def get_feed(user_id: int, db: Session = Depends(get_db)):
    """
    Get a personalized feed for the user.
    Logs impressions in the database at the time of retrieval.
    """
    return recommendation_s.get_personalized_feed(db, user_id)