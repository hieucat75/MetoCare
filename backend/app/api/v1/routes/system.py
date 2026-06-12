"""System / health-check routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/info")
def info() -> dict:
    s = get_settings()
    return {
        "app": s.app_name,
        "env": s.env,
        "ai_mode": s.ai_mode,
        "ocr_mode": s.ocr_mode,
        "storage_mode": s.storage_mode,
    }
