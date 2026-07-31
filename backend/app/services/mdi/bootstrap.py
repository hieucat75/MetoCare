"""Register the concrete MDI extractors + promoters at app startup.

Called once from the documents route module import (which loads during app
construction). Kept out of the package ``__init__`` to avoid an import cycle
(promoters import the medication service, which imports models/db). Idempotent —
re-registration simply overwrites the registry entry.
"""

from __future__ import annotations

from app.models.medical_document import CANDIDATE_MEDICATION

from .classifier import DOC_PRESCRIPTION
from .extractors import register_extractor
from .extractors_prescription import PrescriptionExtractor
from .promoter import register_promoter
from .promoters import MedicationPromoter


def register_defaults() -> None:
    register_extractor(DOC_PRESCRIPTION, PrescriptionExtractor())
    register_promoter(CANDIDATE_MEDICATION, MedicationPromoter())
