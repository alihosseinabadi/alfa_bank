from typing import List
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.course import Course
from app.schemas.course import CourseBase

def get_courses(db: Session, skip: int = 0, limit: int = 100) -> List[Course]:
    """Retrieve a paginated list of courses."""
    return db.query(Course).offset(skip).limit(limit).all()

def get_course(db: Session, course_id: int) -> Course:
    """Retrieve a course by ID. Raises 404 if not found."""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course

def create_course(db: Session, data: CourseBase) -> Course:
    """Create a new course (used for seeding/admin)."""
    course = Course(**data.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course