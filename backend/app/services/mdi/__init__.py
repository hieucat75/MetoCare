"""Medical Document Intelligence (MDI) service package (Master Plan §1.3–§1.9).

Owns document artifacts, the secure ingestion pipeline (§1.7), the staged OCR
pipeline (§1.4), the one-to-many candidate model (§1.5), and promotion of
confirmed candidates into the canonical Lab/Medication/Diagnosis contexts. MDI
never owns canonical clinical data.
"""

from __future__ import annotations
