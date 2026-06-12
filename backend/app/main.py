"""FastAPI application factory for the Metabolic Care Platform (modular monolith).

Wires structured logging, the observability middleware (request id + access log
+ metrics), the v1 API, a consent-error handler, /metrics, and dev-time table
creation (SQLite only; Postgres uses Alembic migrations).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import create_all
from app.core.logging import setup_logging
from app.core.metrics import registry
from app.core.middleware import MfaEnrollmentMiddleware, ObservabilityMiddleware
from app.services.consent import ConsentError

logger = logging.getLogger("mcp")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

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

    # Added first = inner; Observability is added last so it wraps (and logs) the
    # enrollment block too.
    app.add_middleware(MfaEnrollmentMiddleware)
    app.add_middleware(ObservabilityMiddleware)

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

    @app.get("/metrics", tags=["system"], include_in_schema=False)
    def metrics() -> Response:
        if not settings.metrics_enabled:
            return PlainTextResponse("metrics disabled", status_code=404)
        return PlainTextResponse(registry.render(), media_type="text/plain; version=0.0.4")

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
