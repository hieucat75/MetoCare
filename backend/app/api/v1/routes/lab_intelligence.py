from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_roles
from app.domain.clinical_patterns import detect_patterns
from app.domain.clinical_rules import ClinicalFinding, assess_biomarker, summarize_findings
from app.domain.derived_metrics import compute_all_derived
from app.domain.longitudinal import compute_trends
from app.models.clinical import LabResult
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.services import consent

router = APIRouter(tags=["lab_intelligence"])


class LabIntelligenceRequest(BaseModel):
    lab_result_ids: list[str] | None = None
    include_trends: bool = True
    include_patterns: bool = True
    include_derived: bool = True
    age_years: int | None = None
    is_male: bool = True
    waist_cm: float | None = None


@router.post("/patients/{patient_id}/lab-intelligence")
def lab_intelligence(
    patient_id: str,
    body: LabIntelligenceRequest,
    db: Session = Depends(get_session),
    user: CurrentUser = Depends(require_roles(UserRole.PATIENT, UserRole.DOCTOR, UserRole.INTERNAL_ADMIN)),  # noqa: E501
):
    if user.role == UserRole.PATIENT.value:
        profile = db.get(PatientProfile, patient_id)
        if profile is None or profile.user_id != user.id:
            raise HTTPException(status_code=403, detail="Patients may only access their own records.")  # noqa: E501
    else:
        consent.require_access(db, patient_id=patient_id, requester_id=user.id, scope="lab")

    q = select(LabResult).where(LabResult.patient_id == patient_id, LabResult.deleted_at.is_(None))
    if body.lab_result_ids:
        q = q.where(LabResult.id.in_(body.lab_result_ids))
    rows = db.execute(q).scalars().all()
    verified = [r for r in rows if r.verified_by_user or r.verified_by_doctor]
    excluded = len(rows) - len(verified)
    if not verified:
        return {
            "patient_id": patient_id,
            "analysis_timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "records_analyzed": 0,
            "unverified_excluded": excluded,
            "biomarker_findings": [],
            "derived_metrics": [],
            "patterns": [],
            "trends": [],
            "top_priorities": [],
            "doctor_review_required": False,
            "summary_vi": "Chưa có kết quả đã xác minh để phân tích.",
            "disclaimer_vi": "Đây là công cụ tham khảo, không phải chẩn đoán y tế. Vui lòng tham khảo bác sĩ.",  # noqa: E501
            "ai_draft_contract": None,
        }

    findings: list[ClinicalFinding] = []
    raw_inputs: dict[str, float] = {}
    biomarker_findings = []
    for r in verified:
        if r.canonical_name and r.value is not None:
            raw_inputs[r.canonical_name] = r.value
            f = assess_biomarker(r.canonical_name, r.value, age_years=body.age_years, is_male=body.is_male)  # noqa: E501
            if f:
                findings.append(f)
                biomarker_findings.append(f.__dict__)

    derived = []
    if body.include_derived:
        for dr in compute_all_derived(raw_inputs, age_years=body.age_years, is_male=body.is_male, waist_cm=body.waist_cm):  # noqa: E501
            derived.append(dr.__dict__)

    derived_map = {d["canonical"]: d for d in derived}
    if body.include_patterns:
        patterns = [p.__dict__ for p in detect_patterns({"findings": {f.canonical: f.__dict__ for f in findings}, "derived": {k: v.get("value") if isinstance(v, dict) else v for k, v in derived_map.items()}})]  # noqa: E501
    else:
        patterns = []

    trends = []
    if body.include_trends:
        for c in sorted(set(r.canonical_name for r in verified if r.canonical_name)):
            trends.append(compute_trends(verified, c).__dict__)

    summary_vi, top_priorities, doctor_review = summarize_findings(findings)
    doctor_review = doctor_review or any(p.get("doctor_review_required") for p in patterns)

    return {
        "patient_id": patient_id,
        "analysis_timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "records_analyzed": len(verified),
        "unverified_excluded": excluded,
        "biomarker_findings": biomarker_findings,
        "derived_metrics": derived,
        "patterns": patterns,
        "trends": trends,
        "top_priorities": top_priorities,
        "doctor_review_required": doctor_review,
        "summary_vi": summary_vi,
        "disclaimer_vi": "Đây là công cụ tham khảo, không phải chẩn đoán y tế. Vui lòng tham khảo bác sĩ.",  # noqa: E501
        "ai_draft_contract": None,
    }
