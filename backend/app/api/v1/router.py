"""Aggregate v1 API router."""

from __future__ import annotations

from fastapi import APIRouter

from .routes import ai, consent, health, lab, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(health.router)
api_router.include_router(lab.router)
api_router.include_router(ai.router)
api_router.include_router(consent.router)
