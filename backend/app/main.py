"""
FastAPI application factory, lifespan and health check.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text

from app.database import engine

from app.api import users, courses, interactions # add interactions


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App lifespan. Engine created at import; dispose on shutdown."""
    yield
    engine.dispose()


def create_app() -> FastAPI:
    """App factory: build and configure the FastAPI application."""
    app = FastAPI(
        title="Alfa-Kurs API",
        lifespan=lifespan,
    )

    app.include_router(users.router, prefix="/api/v1")
    app.include_router(courses.router, prefix="/api/v1")
    app.include_router(interactions.router, prefix="/api/v1")

    @app.get("/health", tags=["infra"])
    def health() -> dict[str, str]:
        """
        Health check with DB status.

        Returns 200 if the DB is reachable, 503 otherwise.
        Never returns a silent success.
        """
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database unreachable",
            )
        return {"status": "ok"}

    return app


app = create_app()