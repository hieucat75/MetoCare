"""Current legal document versions.

The canonical source is the repo-root ``legal-versions.json`` (shared with the
frontend). Backend and frontend live in separate Docker build contexts, so the
file cannot be imported at runtime by both — instead each side mirrors it and a
drift-guard test (``tests/test_legal_versions_sync.py`` /
``legalVersions.sync.test.ts``) fails if any copy diverges.

Bump the version in ``legal-versions.json`` when the Terms change to force
re-acceptance (a new ``terms_consents`` row is written per version).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Fallbacks used inside the backend container (root JSON not in the image).
_FALLBACK_TERMS = "1.0"
_FALLBACK_PRIVACY = "1.0"


def _load_versions() -> tuple[str, str]:
    """Read the canonical root JSON when available (dev/CI), else fall back."""
    # backend/app/core/legal.py → repo root is three parents up.
    root = Path(__file__).resolve().parents[3] / "legal-versions.json"
    try:
        data = json.loads(root.read_text(encoding="utf-8"))
        return str(data["terms_version"]), str(data["privacy_version"])
    except (OSError, KeyError, ValueError):
        return _FALLBACK_TERMS, _FALLBACK_PRIVACY


CURRENT_TERMS_VERSION, CURRENT_PRIVACY_VERSION = _load_versions()
# App build version, overridable at deploy time.
CURRENT_APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
