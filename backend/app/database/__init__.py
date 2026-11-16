"""Legacy product ORM exports without initializing the HTTP database for ML."""
from app.database.base import ProductBase as Base
from app.database.connection import get_db, product_engine, product_sessions


def __getattr__(name):
    if name == "engine":
        return product_engine()
    if name == "SessionLocal":
        return product_sessions()
    raise AttributeError(name)


__all__ = ["Base", "SessionLocal", "engine", "get_db"]
