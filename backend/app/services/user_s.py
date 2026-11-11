from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.user import User
from app.schemas.user import UserCreate

def create_user(db: Session, data: UserCreate) -> User:
    """Create a new user. Raises 409 if email already exists."""
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists"
        )
    
    user = User(
        email=data.email,
        business_status=data.business_status,
        business_sphere=data.business_sphere,
        current_goal=data.current_goal,
        budget_sensitivity=data.budget_sensitivity,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def get_user(db: Session, user_id: int) -> User:
    """Retrieve a user by ID. Raises 404 if not found."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user