"""Lab document + interpretation routes (mock OCR in dev/test)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_user_id, get_session
from app.schemas.lab import (
    InterpretationOut,
    LabDocumentCreate,
    LabDocumentOut,
)
from app.services import lab

router = APIRouter(tags=["lab"])


@router.post("/patients/{patient_id}/lab-documents", response_model=LabDocumentOut, status_code=201)
def register_document(
    patient_id: str,
    payload: LabDocumentCreate,
    requester_id: str = Depends(current_user_id),
    db: Session = Depends(get_session),
) -> LabDocumentOut:
    doc = lab.register_document(
        db,
        patient_id=patient_id,
        requester_id=requester_id,
        storage_key=payload.storage_key,
        file_type=payload.file_type,
        lab_name=payload.lab_name,
    )
    return LabDocumentOut.model_validate(doc)


@router.post("/lab-documents/{document_id}/interpret", response_model=InterpretationOut)
def interpret_document(
    document_id: str,
    requester_id: str = Depends(current_user_id),
    db: Session = Depends(get_session),
) -> InterpretationOut:
    try:
        result = lab.interpret_document(db, document_id=document_id, requester_id=requester_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return InterpretationOut(
        biomarkers=[
            {
                "canonical": b.canonical,
                "value": b.value,
                "unit": b.unit,
                "status": b.status.value,
                "reference_range": b.reference_range,
                "needs_verification": b.needs_verification,
                "patient_note": b.patient_note,
            }
            for b in result.biomarkers
        ],
        abnormal=result.abnormal,
        critical=result.critical,
        needs_verification=result.needs_verification,
        patient_explanation=result.patient_explanation,
        doctor_summary=result.doctor_summary,
    )
