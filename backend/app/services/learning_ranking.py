"""Service boundary for database availability and safe prior fallback."""
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.ml.ucb_ranking import rank_with_fallback

def rank_with_learning_service(prior, loader):
    try:
        return rank_with_fallback(prior, loader)
    except (OperationalError, DisconnectionError):
        return prior, 'database_unavailable'
