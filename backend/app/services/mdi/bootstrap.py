"""Register the concrete MDI extractors + promoters at app startup.

Called once from the documents route module import (which loads during app
construction). Kept out of the package ``__init__`` to avoid an import cycle
(promoters import the medication service, which imports models/db). Idempotent —
re-registration simply overwrites the registry entry.
"""

from __future__ import annotations

from app.models.medical_document import (
    CANDIDATE_DIAGNOSIS,
    CANDIDATE_FINDING,
    CANDIDATE_FOLLOW_UP,
    CANDIDATE_LAB_RESULT,
    CANDIDATE_MEDICATION,
    CANDIDATE_PROCEDURE,
    CANDIDATE_RECOMMENDATION,
)

from .classifier import DOC_GENERAL, DOC_LAB_REPORT, DOC_PRESCRIPTION
from .extractors import register_extractor
from .extractors_general import GeneralReportExtractor
from .extractors_lab import LabExtractor
from .extractors_prescription import PrescriptionExtractor
from .promoter import register_promoter
from .promoters import LabPromoter, MedicationPromoter, RecordOnlyPromoter

# General-report candidate types with no separate canonical table (§1.9).
_RECORD_ONLY_TYPES = (
    CANDIDATE_DIAGNOSIS,
    CANDIDATE_PROCEDURE,
    CANDIDATE_FINDING,
    CANDIDATE_RECOMMENDATION,
    CANDIDATE_FOLLOW_UP,
)


def register_defaults() -> None:
    register_extractor(DOC_PRESCRIPTION, PrescriptionExtractor())
    register_extractor(DOC_LAB_REPORT, LabExtractor())
    register_extractor(DOC_GENERAL, GeneralReportExtractor())
    register_promoter(CANDIDATE_MEDICATION, MedicationPromoter())
    register_promoter(CANDIDATE_LAB_RESULT, LabPromoter())
    _record_only = RecordOnlyPromoter()
    for _ctype in _RECORD_ONLY_TYPES:
        register_promoter(_ctype, _record_only)
