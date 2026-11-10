"""
Declarative base for all ORM models.

Kept in a separate module to avoid import cycles between `models`
and `connection`. Models import Base from here; connection imports
nothing from models.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()