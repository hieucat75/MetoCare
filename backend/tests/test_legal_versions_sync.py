"""Drift guard: backend legal versions must match the canonical root JSON.

Backend and frontend live in separate Docker build contexts, so they can't
import a single runtime file. ``legal-versions.json`` at the repo root is the
canonical source; this test (run in the full checkout) fails if the backend
constants diverge from it. The frontend has a mirror guard test.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core import legal


def test_backend_versions_match_canonical_json():
    root = Path(__file__).resolve().parents[2] / "legal-versions.json"
    data = json.loads(root.read_text(encoding="utf-8"))
    assert legal.CURRENT_TERMS_VERSION == data["terms_version"]
    assert legal.CURRENT_PRIVACY_VERSION == data["privacy_version"]
