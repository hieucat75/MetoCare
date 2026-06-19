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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import create_all
from app.core.logging import setup_logging
from app.core.metrics import registry
from app.core.middleware import MfaEnrollmentMiddleware, ObservabilityMiddleware
from app.services.consent import ConsentError
from app.services.consent_guard import ConsentDenied
from app.services.doctor_review import PermissionDenied

logger = logging.getLogger("mcp")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # P1-FIX-03: Validate required env vars at startup — fail fast, never
        # silently start a broken server.
        settings.validate_required_env_vars()

        # SQLite dev/test convenience: create tables directly so the app runs
        # with zero setup. PostgreSQL MUST use Alembic migrations — create_all
        # is intentionally skipped in prod (schema managed by `alembic upgrade head`
        # which runs in CI/CD before container restart).
        # NOTE: create_all() is never called in production (is_prod=True) or when
        # MCP_DATABASE_URL points to PostgreSQL. This block is SQLite-only.
        if not settings.is_prod and settings.database_url.startswith("sqlite"):
            # P1-FIX-04: Gunicorn multi-worker race condition — multiple workers
            # may call create_all simultaneously on the same SQLite file.
            # Wrap with try/except to handle "table already exists" gracefully.
            try:
                create_all()
            except Exception as exc:  # noqa: BLE001
                logger.warning("create_all skipped (tables may already exist): %s", exc)
        elif settings.is_prod:
            # Production path: schema is managed by Alembic migrations.
            # create_all() is NOT called here. CI/CD runs `alembic upgrade head`
            # before container restart to ensure schema is up-to-date.
            logger.info("Production mode: skipping create_all() — Alembic manages schema.")
        # Start the async OCR worker (built-in asyncio queue; no Celery/Redis).
        worker = None
        if settings.ocr_worker_enabled:
            from app.services.lab_pipeline import get_worker

            worker = get_worker()
            worker.start()
        try:
            yield
        finally:
            if worker is not None:
                await worker.stop()

    # Interactive docs are convenient for dev/manual testing but must never be
    # exposed in production (force off there regardless of the flag).
    docs_on = settings.enable_docs and not settings.is_prod
    app = FastAPI(
        title=settings.app_name,
        version="0.3.0",
        description=(
            "Metabolic Care Platform — modular monolith API (P2 foundation). "
            "AI is guardrailed and runs in mock mode; no real LLM/OCR is called."
        ),
        lifespan=lifespan,
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
        openapi_tags=[
            {"name": "auth", "description": "Đăng ký / đăng nhập / refresh / MFA enroll+verify."},
            {"name": "health-tracking", "description": "Ghi nhận + xem xu hướng chỉ số sức khỏe."},
            {"name": "lab", "description": "Upload tài liệu xét nghiệm + pipeline OCR/interpret."},
            {"name": "ai", "description": "AI chat (guardrailed) / triage / metabolic score."},
            {"name": "consent", "description": "Cấp / thu hồi đồng ý chia sẻ dữ liệu."},
            {"name": "admin", "description": "Audit log + unlock account (role+MFA gated)."},
            {"name": "system", "description": "Health check / system."},
        ],
    )

    # CORSMiddleware must be outermost so OPTIONS preflight is answered before
    # any auth/business middleware runs. Without it every preflight returns 405.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Inner middleware (MFA then Observability wraps both).
    app.add_middleware(MfaEnrollmentMiddleware)
    app.add_middleware(ObservabilityMiddleware)

    for warning in settings.warn_if_insecure():
        logger.warning("INSECURE CONFIG: %s", warning)

    @app.exception_handler(ConsentDenied)
    async def _consent_denied_handler(_: Request, exc: ConsentDenied) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"code": "CONSENT_DENIED", "message": str(exc)},
        )

    @app.exception_handler(PermissionDenied)
    async def _permission_denied_handler(_: Request, exc: PermissionDenied) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"code": "PERMISSION_DENIED", "message": str(exc)},
        )

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
