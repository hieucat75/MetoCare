"""Register the concrete MDI extractors + promoters at app startup.

Called once from the documents route module import (which loads during app
construction). Kept out of the package ``__init__`` to avoid an import cycle
(promoters import the medication service, which imports models/db). Idempotent —
re-registration simply overwrites the registry entry.
"""

from __future__ import annotations

from app.models.medical_document import CANDIDATE_LAB_RESULT, CANDIDATE_MEDICATION

from .classifier import DOC_LAB_REPORT, DOC_PRESCRIPTION
from .extractors import register_extractor
from .extractors_lab import LabExtractor
from .extractors_prescription import PrescriptionExtractor
from .promoter import register_promoter
from .promoters import LabPromoter, MedicationPromoter


def register_defaults() -> None:
    register_extractor(DOC_PRESCRIPTION, PrescriptionExtractor())
    register_extractor(DOC_LAB_REPORT, LabExtractor())
    register_promoter(CANDIDATE_MEDICATION, MedicationPromoter())
    register_promoter(CANDIDATE_LAB_RESULT, LabPromoter())
