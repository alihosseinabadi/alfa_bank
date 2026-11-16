"""
FastAPI application factory, lifespan and health check.
"""

from collections.abc import AsyncIterator
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from urllib.parse import urlsplit

from app.core.config import get_settings
from sqlalchemy import text

from app.database import engine

from app.api import users, courses, interactions, recommendations


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the optional ML serving resources once; fail closed on errors."""
    provider = None
    if get_settings().recommendations_enabled:
        app.state.recommendation_provider = None
        try:
            from app.services.ml_recommendation_provider import MLRecommendationProvider
            provider = MLRecommendationProvider.load(get_settings())
            app.state.recommendation_provider = provider
        except Exception as exc:
            # Paths, query text, credentials and database errors are not logged.
            logging.getLogger(__name__).error('Recommendation provider unavailable (%s)', type(exc).__name__)
    try:
        yield
    finally:
        if provider is not None:
            provider.close()
        engine.dispose()


def create_app() -> FastAPI:
    """App factory: build and configure the FastAPI application."""
    app = FastAPI(
        title="Alfa-Kurs API",
        lifespan=lifespan,
    )

    origins = [origin.strip() for origin in get_settings().api_cors_origins.split(',') if origin.strip()]
    for origin in origins:
        parsed = urlsplit(origin)
        if (parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or '*' in origin):
            raise ValueError('API_CORS_ORIGINS must contain explicit HTTP(S) origins')
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                       allow_methods=['GET', 'POST', 'OPTIONS'],
                       allow_headers=['Content-Type', 'X-CSRF-Token'])

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request, exc):
        # Pydantic errors can include the submitted goal or profile in "input".
        errors = [{'loc': error['loc'], 'msg': error['msg'], 'type': error['type']}
                  for error in exc.errors()]
        return JSONResponse(status_code=422, content={'detail': errors}, headers={'Cache-Control': 'no-store'})

    app.include_router(users.router, prefix="/api/v1")
    app.include_router(courses.router, prefix="/api/v1")
    app.include_router(interactions.router, prefix="/api/v1")
    app.include_router(recommendations.router, prefix="/api/v1")

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