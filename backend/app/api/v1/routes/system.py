"""System / health-check routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import environment_lock as env_lock
from app.core.config import get_settings
from app.core.database import get_session
from app.core.feature_flags import FeatureFlag, is_enabled

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_session)) -> JSONResponse:
    """Health check endpoint.

    Returns HTTP 200 when healthy so load balancers mark instance ready.
    Returns HTTP 503 when DB is unreachable so load balancers stop routing traffic.
    """
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    overall = "ok" if db_status == "ok" else "degraded"
    body = {"status": overall, "db": db_status}

    if db_status != "ok":
        return JSONResponse(status_code=503, content=body)
    return JSONResponse(status_code=200, content=body)


@router.get("/info")
def info(db: Session = Depends(get_session)) -> dict:
    """System info endpoint.

    Exposes app metadata, current Alembic migration version, and feature flags.
    Public endpoint — no auth required.
    """
    s = get_settings()

    # --- Migration version (P1-FIX-02) ---
    try:
        result = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        row = result.fetchone()
        migration_version: str = row[0] if row else "unknown"
    except Exception:
        migration_version = "unknown"

    # --- Feature flags (P1-FIX-02) ---
    feature_flags: dict[str, bool] = {flag.value: is_enabled(flag) for flag in FeatureFlag}

    return {
        "app": s.app_name,
        # Containment state, so an operator (and the UI banner) can see at a
        # glance whether this environment still accepts real identities.
        "synthetic_only_mode": env_lock.is_locked(),
        "environment_banner": env_lock.banner(),
        "env": s.env,
        "ai_mode": s.ai_mode,
        "ocr_mode": s.ocr_mode,
        "storage_mode": s.storage_mode,
        "migration_version": migration_version,
        # Build identity — additive. Empty when not baked (local/dev), never null,
        # so a consumer can always read the key.
        "build_sha": s.build_sha,
        "build_time": s.build_time,
        "expected_host": s.expected_host,
        "feature_flags": feature_flags,
    }
