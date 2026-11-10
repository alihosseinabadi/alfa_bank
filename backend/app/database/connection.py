"""
Database connectivity: engine, session factory, FastAPI dependency.

No business logic. One session per request.
Transactions are owned by services, not by routes.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency: one session per request.

    Does not commit — services own transaction boundaries.
    Always closes the session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()