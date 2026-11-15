"""
MongoDB connection for ML communication.

Used as a bridge to send contexts to the ML module and receive ranked course IDs.
"""

from pymongo import MongoClient
from pymongo.database import Database
from app.core.config import get_settings

settings = get_settings()

# Global server (makes once for process)
_client = MongoClient(settings.mongo_url)

def get_mongo_db() -> Database:
    """Return the MongoDB database instance."""
    return _client[settings.mongo_db_name]