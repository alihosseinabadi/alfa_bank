"""Legacy endpoint is unavailable until the ML HTTP contract is integrated."""
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/{user_id}")
def get_feed(user_id: int):
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Recommendation service is not integrated yet")
