from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from app.models.interaction import Interaction
from app.models.recommendation import RecommendationImpression
from app.schemas.interaction import InteractionCreate
from app.core.config import get_settings

settings = get_settings()

# Maps event type to reward weight from config
REWARDS = {
    "click": settings.reward_click,
    "inspect": settings.reward_inspect,
    "purchase": settings.reward_purchase,
}

def create_interaction(db: Session, data: InteractionCreate) -> Interaction:
    """Record a user interaction with idempotency and attribution checks."""
    # 1. Verify impression exists
    impression = db.query(RecommendationImpression).filter(
        RecommendationImpression.id == data.impression_id
    ).first()
    if not impression:
        raise HTTPException(status_code=404, detail="Impression not found")

    # 2. Check attribution window for purchases
    if data.event_type == "purchase":
        now = datetime.now(timezone.utc)
        attribution_limit = impression.shown_at + timedelta(days=settings.purchase_attribution_days)
        if now > attribution_limit:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Purchase attribution window expired"
            )

    # 3. Create interaction (denormalizing user_id and course_id)
    reward = Decimal(str(REWARDS[data.event_type]))
    interaction = Interaction(
        impression_id=data.impression_id,
        user_id=impression.user_id,
        course_id=impression.course_id,
        event_type=data.event_type,
        reward=reward,
    )

    db.add(interaction)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Unique constraint (impression_id, event_type) or partial unique purchase
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Interaction already exists or duplicate purchase"
        )

    db.refresh(interaction)
    return interaction