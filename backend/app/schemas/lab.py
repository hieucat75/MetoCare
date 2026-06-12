"""Lab schemas."""

from __future__ import annotations

from pydantic import BaseModel


class LabDocumentCreate(BaseModel):
    storage_key: str
    file_type: str | None = None
    lab_name: str | None = None


class LabDocumentOut(BaseModel):
    id: str
    patient_id: str
    ocr_status: str
    status: str = "uploaded"

    model_config = {"from_attributes": True}


class LabDocumentStatusOut(BaseModel):
    id: str
    status: str
    ocr_status: str
    enqueued: bool = False


class InterpretedBiomarkerOut(BaseModel):
    canonical: str
    value: float
    unit: str
    status: str
    reference_range: str
    needs_verification: bool
    patient_note: str


class InterpretationOut(BaseModel):
    biomarkers: list[InterpretedBiomarkerOut]
    abnormal: list[str]
    critical: list[str]
    needs_verification: bool
    patient_explanation: str
    doctor_summary: str
