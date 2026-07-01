"""FastAPI application factory for the Metabolic Care Platform (modular monolith).

Wires structured logging, the observability middleware (request id + access log
+ metrics), the v1 API, a consent-error handler, and /metrics.

Schema management: Alembic only. create_all() is never called at runtime.
Run `alembic upgrade head` in CI/CD before every container restart.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
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

        # Schema management: Alembic only.
        # create_all() is NEVER called at runtime — not in dev, not in prod.
        # CI/CD runs `alembic upgrade head` before every container restart.
        # This ensures schema is always migration-tracked and reproducible.
        logger.info("Startup: schema managed by Alembic — no runtime create_all()")

        # Initialize Meto AI provider registry from environment settings.
        # Must run after settings are validated so API keys are available.
        from app.ai.registry import init_registry_from_settings
        init_registry_from_settings()

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

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        """Return structured 422 with field path + message so frontend can show
        actionable errors instead of a generic failure message."""
        errors = [
            {
                "field": " → ".join(str(loc) for loc in e["loc"][1:])  # noqa: E501
                if len(e["loc"]) > 1
                else str(e["loc"]),
                "message": e["msg"],
                "received": str(e.get("input", ""))[:120],  # truncate for safety
            }
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"code": "VALIDATION_ERROR", "detail": errors},
        )

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
