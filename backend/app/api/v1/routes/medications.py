"""Drug catalog / medication name autocomplete endpoint.

GET /api/v1/medications/suggest — fuzzy-search the drug reference catalog.

This endpoint is for NAME LOOKUP ONLY.  It never returns dosing, prescribing,
or treatment advice.  A fixed safety_notice is embedded in every result item.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.models.user import UserRole
from app.schemas.drug_catalog import DrugSuggestResponse
from app.services.drug_catalog import suggest_drugs

router = APIRouter(tags=["medications"])


@router.get(
    "/medications/suggest",
    response_model=DrugSuggestResponse,
    summary="Autocomplete drug names from the reference catalog",
)
def suggest_medications(
    q: str = Query(..., min_length=1, max_length=200, description="Free-text drug name query"),
    metric_group: str | None = Query(
        None,
        description="Optional metric group key to boost/filter results (e.g. 'diabetes', 'lipid')",
    ),
    limit: int = Query(10, ge=1, le=25, description="Max results to return"),
    strict: bool = Query(
        False,
        description="If true, restrict results to drugs in the given metric_group only",
    ),
    db: Session = Depends(get_session),
    _user: CurrentUser = Depends(
        require_roles(UserRole.PATIENT, UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)
    ),
) -> DrugSuggestResponse:
    results = suggest_drugs(db, q=q, metric_group=metric_group, limit=limit, strict=strict)
    return DrugSuggestResponse(
        query=q,
        metric_group=metric_group,
        results=results,
        total=len(results),
    )
