"""Separate SQLAlchemy metadata for legacy product and ML event storage.

The two databases contain incompatible recommendation_impressions tables.
ML's Base retains its existing import path and migration contract.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Stage 7–9 event and learning models."""


class ProductBase(DeclarativeBase):
    """Legacy product users/courses and dormant legacy models."""
