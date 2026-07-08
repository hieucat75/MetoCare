"""Shared feature-flag gate for the Clinic SaaS Phase C0 router surface.

Mounted as a router-level dependency (`APIRouter(dependencies=[...])`) on
every new `/clinics/...` router so the whole module fails closed behind
`FeatureFlag.CLINIC_SAAS` (default OFF), the same precedent as
`CLINICAL_COPILOT`/`AI_SESSION_ENABLED`.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.core.feature_flags import FeatureFlag, is_enabled

_FEATURE_UNAVAILABLE_DETAIL = "Tính năng quản lý phòng khám hiện chưa khả dụng."


def require_clinic_saas_enabled() -> None:
    if not is_enabled(FeatureFlag.CLINIC_SAAS):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_FEATURE_UNAVAILABLE_DETAIL,
        )
