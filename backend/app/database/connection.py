"""Connections for separate product and ML-event PostgreSQL databases."""
import os
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


def _checked_engine(url, **kwargs):
    """Reject database aliases that resolve to an unexpected PostgreSQL DB."""
    expected = make_url(url).database
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True, **kwargs)

    @event.listens_for(engine, "connect")
    def check_database(dbapi_connection, _connection_record):
        try:
            with dbapi_connection.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                actual = cursor.fetchone()[0]
        finally:
            dbapi_connection.rollback()
        if actual != expected:
            raise ValueError("Database connection resolved to an unexpected PostgreSQL database")

    return engine


def events_engine(url=None, **kwargs):
    """Connect only to the explicitly named, isolated events database."""
    url = url or os.environ.get("ALFA_EVENTS_DATABASE_URL")
    if not url:
        raise ValueError("Set ALFA_EVENTS_DATABASE_URL for the product events database")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("Stage-7 storage requires PostgreSQL with psycopg")
    if parsed.database not in {"alfa_events", "alfa_events_test"}:
        raise ValueError("Use a separate alfa_events or alfa_events_test database")
    return _checked_engine(parsed, **kwargs)


def events_sessions(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@lru_cache
def product_engine():
    """Build the legacy product engine only when the HTTP app needs it."""
    from app.core.config import get_settings
    url = make_url(get_settings().database_url)
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Product storage requires PostgreSQL with psycopg")
    if url.database in {"alfa_events", "alfa_events_test"}:
        raise ValueError("DATABASE_URL must not target the ML events database")
    return _checked_engine(url)


@lru_cache
def product_sessions():
    return sessionmaker(bind=product_engine(), autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    with product_sessions()() as db:
        yield db
