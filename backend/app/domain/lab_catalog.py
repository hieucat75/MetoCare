"""Lab reference catalog loader.

Serves the authoritative, PHI-free biomarker catalog (categories → biomarkers →
units + reference ranges) that drives the patient manual-entry cascade dropdowns
and the auto-classified status. Biomarker keys are the SAME canonical keys used by
``lab_interpreter`` / OCR, so manual entries and OCR promotion stay consistent.

The catalog is a static JSON file loaded once (lru_cache); it ships in the image.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

_CATALOG_PATH = Path(__file__).resolve().parent / "lab_reference.json"


@functools.lru_cache(maxsize=1)
def get_catalog() -> dict:
    """Return the full lab-reference catalog (cached)."""
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def biomarker_keys() -> set[str]:
    return set(get_catalog()["biomarkers"].keys())
