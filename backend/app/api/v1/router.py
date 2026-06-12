"""Aggregate v1 API router."""

from __future__ import annotations

from fastapi import APIRouter

from .routes import admin, ai, auth, consent, health, lab, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(lab.router)
api_router.include_router(ai.router)
api_router.include_router(consent.router)
api_router.include_router(admin.router)
