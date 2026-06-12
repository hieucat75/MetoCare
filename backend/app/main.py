"""FastAPI application factory for the Metabolic Care Platform (modular monolith).

Wires the v1 API, a consent-error handler, and dev-time table creation. Real
migrations (Alembic) and RBAC/JWT middleware are P1.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import create_all
from app.services.consent import ConsentError

logger = logging.getLogger("mcp")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # SQLite dev/test convenience: create tables directly so the app runs
        # with zero setup. PostgreSQL/TimescaleDB MUST use Alembic migrations
        # (create_all would make plain tables without the hypertable/CAGG).
        if not settings.is_prod and settings.database_url.startswith("sqlite"):
            create_all()
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Metabolic Care Platform — Sprint 0 foundation (modular monolith).",
        lifespan=lifespan,
    )

    for warning in settings.warn_if_insecure():
        logger.warning("INSECURE CONFIG: %s", warning)

    @app.exception_handler(ConsentError)
    async def _consent_error_handler(_: Request, exc: ConsentError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"code": "consent_denied", "message": str(exc)},
        )

    @app.get("/health", tags=["system"])
    def root_health() -> dict:
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
