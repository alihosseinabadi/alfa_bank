import uuid
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.user import User
from app.models.course import Course
from app.models.recommendation import RecommendationImpression
from app.schemas.recommendation import FeedResponse, FeedItemResponse
from app.schemas.course import CourseResponse
from app.core.config import get_settings
from app.database.mongo import get_mongo_db

settings = get_settings()


def fetch_ml_recommendations_from_mongo(user_id: int) -> list[dict] | None:
    """
    STUB FOR FUTURE USE.
    This will query MongoDB to get the ranked course IDs from the ML module.
    
    Currently returns None: "No ML data, use the fallback".
    """
    # Future implementation:
    # db = get_mongo_db()
    # response = db.ml_responses.find_one({"user_id": user_id})
    # if response:
    #     return response["items"]
    
    return None 


def get_personalized_feed(db: Session, user_id: int) -> FeedResponse:
    """Generate a feed for the user and log impressions."""
    
    # 1. Check if the user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Try to fetch data from the ML module
    ml_recommendations = fetch_ml_recommendations_from_mongo(user_id)

    # If ML data is available (in the future)
    if ml_recommendations:
        # TODO: When ML is ready, fetch courses by ID from PostgreSQL
        # and use the scores from MongoDB.
        pass
    
    # If no ML data is available (current fallback)
    else:
        # Get 10 courses from PostgreSQL (stub)
        courses = db.query(Course).limit(10).all()
        if not courses:
            raise HTTPException(status_code=404, detail="No courses available in catalogue")

    # 3. Generate a unique slate ID
    slate_id = f"slate_{uuid.uuid4().hex[:12]}"
    algorithm = "linucb_stub"
    model_version = settings.feature_version

    feed_items = []

    # 4. Write impressions to the DB and build the response for the frontend
    for position, course in enumerate(courses, start=1):
        impression = RecommendationImpression(
            user_id=user.id,
            course_id=course.id,
            slate_id=slate_id,
            position=position,
            retrieval_score=0.9,  # Stub
            bandit_score=0.8,     # Stub
            algorithm=algorithm,
            model_version=model_version
        )
        db.add(impression)
        db.flush() # Get the impression ID before committing

        feed_items.append(
            FeedItemResponse(
                impression_id=impression.id,
                slate_id=slate_id,
                position=position,
                course=CourseResponse.model_validate(course),
                reason="Recommended based on your interests" # Stub for now
            )
        )

    # 5. Commit the transaction
    db.commit()

    return FeedResponse(
        slate_id=slate_id,
        algorithm=algorithm,
        model_version=model_version,
        items=feed_items
    )