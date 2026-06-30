"""Pydantic schemas for the drug catalog / medication suggest API."""

from __future__ import annotations

from pydantic import BaseModel, Field

SAFETY_NOTICE = (
    "Thông tin thuốc chỉ để nhận diện tên thuốc. "
    "Không tự ý dùng, ngừng hoặc đổi liều nếu chưa có chỉ định của bác sĩ."
)


class DrugSuggestItem(BaseModel):
    id: str
    display_name: str
    generic_name: str
    matched_name: str
    brand_names: list[str]
    drug_class: str
    metric_groups: list[str]
    prescription_required: bool
    caution_flags: list[str]
    confidence_score: float = Field(ge=0.0, le=100.0)
    safety_notice: str = SAFETY_NOTICE


class DrugSuggestResponse(BaseModel):
    query: str
    metric_group: str | None
    results: list[DrugSuggestItem]
    total: int


class MedicationMatch(BaseModel):
    drug_id: str | None
    parsed_name: str
    dosage_text: str | None
    confidence: float = Field(ge=0.0, le=100.0)
    ambiguous_matches: list[DrugSuggestItem]
    safety_notice: str = SAFETY_NOTICE
