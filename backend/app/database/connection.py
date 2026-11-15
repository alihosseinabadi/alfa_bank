"""Product events DB only; never fall back to the organizer database."""
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

def events_engine(url=None,**kwargs):
    url=url or os.environ.get("ALFA_EVENTS_DATABASE_URL")
    if not url:raise ValueError("Set ALFA_EVENTS_DATABASE_URL for the product events database")
    parsed=make_url(url)
    if parsed.drivername!="postgresql+psycopg":
        raise ValueError("Stage-7 storage requires PostgreSQL with psycopg")
    if parsed.database not in {"alfa_events","alfa_events_test"}:
        raise ValueError("Use a separate alfa_events or alfa_events_test database")
    return create_engine(parsed,pool_pre_ping=True,hide_parameters=True,**kwargs)

def events_sessions(engine):
    return sessionmaker(bind=engine,expire_on_commit=False)
