from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.schemas.course import CourseResponse, CourseBase
from app.services import course_s

router = APIRouter(prefix="/courses", tags=["courses"])

@router.get("/", response_model=List[CourseResponse])
def read_courses(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get a paginated list of available courses."""
    return course_s.get_courses(db, skip=skip, limit=limit)

@router.get("/{course_id}", response_model=CourseResponse)
def read_course(course_id: int, db: Session = Depends(get_db)):
    """Get detailed information about a specific course."""
    return course_s.get_course(db, course_id)

@router.post("/", response_model=CourseResponse, status_code=201)
def create_course(course: CourseBase, db: Session = Depends(get_db)):
    """Add a new course (admin/seeding use)."""
    return course_s.create_course(db, course)