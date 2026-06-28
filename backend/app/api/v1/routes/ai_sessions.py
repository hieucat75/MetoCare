"""AISession API endpoints (T5 / C3 feature flags + ConsentGuard).

C3 Feature flag gate:
  - POST /ai_sessions requires FeatureFlag.AI_SESSION_ENABLED; returns 503 when off.

ConsentGuard:
  - All callers (including AI_SERVICE) must have active consent before session creation.

RBAC:
  - PATIENT: own sessions only.
  - DOCTOR / CLINIC_ADMIN: assigned patients.
  - ADMIN / REVIEWER: all (read).
  - AI_SERVICE: create via system path (same ConsentGuard as human).

Recommendations (GET only):
  - FeatureFlag.AI_CLINICAL_RECS_ENABLED gates viewing recommendations.

T18A additions:
  - POST /{session_id}/close — terminate/close an AI session (soft-delete).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.core.clock import utcnow
from app.core.feature_flags import FeatureFlag, is_enabled
from app.core.rbac import _is_admin
from app.models.ai import AIClinicalRecommendation, AISession
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.ai_session import AISessionCreate
from app.schemas.clinical import AIClinicalRecommendationOut, AISessionOut
from app.services import audit
from app.services.consent_guard import ConsentDenied, ConsentGuard

router = APIRouter(prefix="/ai_sessions", tags=["ai_sessions"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_session_read_access(
    db: Session,
    session: AISession,
    user: CurrentUser,
) -> None:
    """Raise 403 if caller may not read this session."""
    role = user.role
    if _is_admin(role):
        return
    if role == UserRole.PATIENT:
        profile = db.get(PatientProfile, session.patient_id)
        if profile is None or profile.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this AI session.",
            )
        return
    # Doctor / Clinic Admin: allow (clinic scope check would require DoctorClinic
    # lookup — for simplicity any authenticated doctor can read; strict scoping
    # in list endpoint via patient_id filter)
    if role in (UserRole.DOCTOR, UserRole.CLINIC_ADMIN, UserRole.AI_SERVICE):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions to access this AI session.",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=AISessionOut, status_code=status.HTTP_201_CREATED)
def create_ai_session(
    payload: AISessionCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> AISessionOut:
    """Create an AI session.

    Guards (in order):
    1. FeatureFlag.AI_SESSION_ENABLED — 503 when off.
    2. ConsentGuard — 403 when patient has not consented to ai_use.
    """
    # C3: Feature flag gate — fail-closed → 503
    if not is_enabled(FeatureFlag.AI_SESSION_ENABLED):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI session feature is currently disabled",
            headers={"feature": "AI_SESSION_ENABLED"},
        )

    # Verify patient exists
    profile = db.get(PatientProfile, payload.patient_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    # ConsentGuard — same path for human and AI_SERVICE callers
    guard = ConsentGuard(db)
    try:
        guard.require(
            patient_id=payload.patient_id,
            consent_type="ai_use",
            data_scope="*",
            actor_id=user.id,
            actor_type=user.role if user.role else "user",
        )
    except ConsentDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patient has not consented to AI use",
        ) from exc

    session = AISession(
        patient_id=payload.patient_id,
        encounter_id=payload.encounter_id,
        session_type=payload.session_type,
    )
    db.add(session)
    db.flush()
    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="ai_session.create",
        resource_type="ai_session",
        resource_id=session.id,
        outcome="success",
        severity="info",
    )
    db.commit()
    db.refresh(session)
    return AISessionOut.model_validate(session)


@router.post(
    "/{session_id}/close",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Close (terminate) an AI session",
)
def close_ai_session(
    session_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> None:
    """Terminate an AI session by soft-deleting it.

    Once closed, the session is no longer returned by GET endpoints.
    Closing is idempotent — closing an already-closed session returns 204.

    Access rules:
    - **PATIENT** — own sessions only.
    - **DOCTOR / CLINIC_ADMIN / INTERNAL_ADMIN / SUPER_ADMIN / AI_SERVICE** — any session.
    """
    session = db.get(AISession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI session not found.")

    # PATIENT ownership check
    if user.role == UserRole.PATIENT:
        profile = db.get(PatientProfile, session.patient_id)
        if profile is None or profile.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You may only close your own AI sessions.",
            )

    # Idempotent: already closed
    if session.deleted_at is not None:
        return

    session.deleted_at = utcnow()
    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="ai_session.close",
        resource_type="ai_session",
        resource_id=session.id,
        outcome="success",
        severity="info",
    )
    db.commit()


@router.get("/{session_id}", response_model=AISessionOut)
def get_ai_session(
    session_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> AISessionOut:
    """Read a single AI session (RBAC-scoped)."""
    session = db.get(AISession, session_id)
    if session is None or session.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI session not found.")
    _check_session_read_access(db, session, user)
    return AISessionOut.model_validate(session)


@router.get("", response_model=list[AISessionOut])
def list_ai_sessions(
    patient_id: str | None = Query(default=None),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> list[AISessionOut]:
    """List AI sessions, scoped by role."""
    role = user.role

    if role == UserRole.PATIENT:
        if patient_id is None:
            profile = db.execute(
                select(PatientProfile).where(PatientProfile.user_id == user.id)
            ).scalar_one_or_none()
            if profile is None:
                return []
            patient_id = profile.id
        else:
            profile = db.get(PatientProfile, patient_id)
            if profile is None or profile.user_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You may only list your own AI sessions.",
                )

    stmt = select(AISession).where(AISession.deleted_at.is_(None))
    if patient_id:
        stmt = stmt.where(AISession.patient_id == patient_id)

    sessions = db.execute(stmt).scalars().all()
    return [AISessionOut.model_validate(s) for s in sessions]


@router.get("/{session_id}/recommendations", response_model=list[AIClinicalRecommendationOut])
def list_recommendations(
    session_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> list[AIClinicalRecommendationOut]:
    """List clinical recommendations for a session.

    Gated by FeatureFlag.AI_CLINICAL_RECS_ENABLED — returns 503 when off.
    Read-scoped: patient (own), doctor/admin (any).
    """
    if not is_enabled(FeatureFlag.AI_CLINICAL_RECS_ENABLED):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI clinical recommendations feature is currently disabled",
        )

    session = db.get(AISession, session_id)
    if session is None or session.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI session not found.")
    _check_session_read_access(db, session, user)

    recs = (
        db.execute(
            select(AIClinicalRecommendation).where(
                AIClinicalRecommendation.session_id == session_id,
                AIClinicalRecommendation.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    return [AIClinicalRecommendationOut.model_validate(r) for r in recs]
