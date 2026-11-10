"""
Cross-cutting configuration.

One source of truth for tunables. Nothing here imports domain code.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

# Project root (backend/) — config.py lives at backend/app/core/config.py
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """
    Application settings loaded from environment.

    Sources, in order of priority:
    1. Environment variables.
    2. backend/.env file.
    3. Defaults declared below.
    """

    database_url: str

    alpha: float = 1.0                  # LinUCB exploration
    linucb_ridge: float = 0.01          # keeps A positive definite
    reward_click: float = 1.0
    reward_inspect: float = 1.0
    reward_purchase: float = 10.0
    purchase_attribution_days: int = 7
    retrieval_k: int = 50
    feature_version: str = "v1"
    embedding_model: str = "all-MiniLM-L6-v2"
    model_dir: str = "artifacts"

    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Return application settings (cached per process)."""
    return Settings()