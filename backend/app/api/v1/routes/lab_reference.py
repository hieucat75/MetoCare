"""Lab reference catalog endpoint (patient manual-entry cascade dropdowns).

`GET /api/v1/lab-reference` returns the static, PHI-free biomarker catalog so the
frontend can build the loại → chỉ số → đơn vị cascade + show reference ranges and
auto-classify status. Cacheable aggressively (no PHI); auth required (patient-facing).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentUser, require_roles
from app.domain.lab_catalog import get_catalog
from app.models.user import UserRole

router = APIRouter(tags=["lab"])


@router.get("/lab-reference", summary="Biomarker catalog for manual lab entry")
def lab_reference(
    response: Response,
    _user: CurrentUser = Depends(
        require_roles(UserRole.PATIENT, UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)
    ),
) -> dict:
    # Static, non-PHI reference data — let the browser cache it for a day.
    response.headers["Cache-Control"] = "private, max-age=86400"
    return get_catalog()
