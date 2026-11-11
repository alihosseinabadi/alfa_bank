from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.interaction import InteractionCreate, InteractionResponse
from app.services import interaction_s

router = APIRouter(prefix="/interactions", tags=["interactions"])

@router.post("/", response_model=InteractionResponse, status_code=201)
def record_interaction(data: InteractionCreate, db: Session = Depends(get_db)):
    """Record a click, inspect, or purchase event."""
    return interaction_s.create_interaction(db, data)