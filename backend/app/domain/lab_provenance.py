"""Lab Provenance Layer — pure dataclasses representing the audit chain.

Per the Lab Intelligence Engine spec:
- Raw OCR data preserved forever (never overwritten)
- ocr_confidence is for audit/provenance only, never used clinically
- is_clinically_usable = True ONLY when verified_by_user or verified_by_doctor

No DB models here — these are domain-layer immutable value objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RawOcrProvenance:
    """Snapshot of original OCR-extracted values — never mutated after creation."""

    original_test_name: str
    original_value: float | None
    original_unit: str | None
    original_reference_range: str | None
    ocr_confidence: float | None  # for audit only; NEVER used in clinical computation
    hospital_detected: str | None
    parser_version: str | None


@dataclass(frozen=True)
class CorrectionEvent:
    """An immutable record of one correction applied by patient or doctor."""

    field: str          # "value" | "unit" | "test_name"
    old_value: str
    new_value: str
    corrected_by: str   # "patient" | "doctor"
    corrected_at: datetime


@dataclass
class LabRecordProvenance:
    """Full provenance chain for one LabResult record.

    ``is_clinically_usable`` is the single gate for the clinical engine:
    it must be True (verified_by_user OR verified_by_doctor) before any
    clinical computation runs on this record.
    """

    lab_result_id: str
    source_type: str               # "ocr_upload" | "manual_entry" | "device_sync"
    verification_status: str       # "unverified" | "patient_verified" | "doctor_verified"
    raw_ocr: RawOcrProvenance | None  # None for manual_entry / device_sync
    corrections: list[CorrectionEvent] = field(default_factory=list)
    is_clinically_usable: bool = False  # True ONLY when verified_by_user or verified_by_doctor

    @classmethod
    def from_lab_result(cls, row: object) -> "LabRecordProvenance":
        """Build provenance from a LabResult ORM row (duck-typed to avoid circular imports)."""
        verified_by_user = getattr(row, "verified_by_user", False) or False
        verified_by_doctor = getattr(row, "verified_by_doctor", False) or False

        if verified_by_doctor:
            verification_status = "doctor_verified"
        elif verified_by_user:
            verification_status = "patient_verified"
        else:
            verification_status = "unverified"

        is_clinically_usable = verified_by_user or verified_by_doctor

        # Build RawOcrProvenance only when OCR was involved.
        source_type = getattr(row, "source_type", "manual_entry") or "manual_entry"
        raw_ocr: RawOcrProvenance | None = None
        if source_type == "ocr_upload":
            raw_ocr = RawOcrProvenance(
                original_test_name=getattr(row, "original_test_name", "") or "",
                original_value=getattr(row, "original_value", None),
                original_unit=getattr(row, "original_unit", None),
                original_reference_range=getattr(row, "original_reference_range", None),
                ocr_confidence=getattr(row, "ocr_confidence", None),
                hospital_detected=None,   # stored on LabDocument, not LabResult
                parser_version=None,
            )

        # Correction history — stored as JSON array in correction_history_json column.
        import json as _json
        corrections: list[CorrectionEvent] = []
        raw_history = getattr(row, "correction_history_json", None)
        if raw_history:
            try:
                events = _json.loads(raw_history)
                for evt in events:
                    corrections.append(
                        CorrectionEvent(
                            field=evt.get("field", ""),
                            old_value=str(evt.get("old_value", "")),
                            new_value=str(evt.get("new_value", "")),
                            corrected_by=evt.get("corrected_by", "patient"),
                            corrected_at=datetime.fromisoformat(
                                evt.get("corrected_at", datetime.utcnow().isoformat())
                            ),
                        )
                    )
            except (ValueError, TypeError, KeyError):
                pass  # malformed JSON is an audit warning, not a blocking error

        return cls(
            lab_result_id=str(getattr(row, "id", "")),
            source_type=source_type,
            verification_status=verification_status,
            raw_ocr=raw_ocr,
            corrections=corrections,
            is_clinically_usable=is_clinically_usable,
        )
