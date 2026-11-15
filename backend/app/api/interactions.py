"""Legacy integer event API is disabled pending the ML event contract."""
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/interactions", tags=["interactions"])


@router.post("/")
def record_interaction():
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Interaction service is not integrated yet")
