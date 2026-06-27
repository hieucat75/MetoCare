"""
Claude Sonnet client for MetoCare.
- Backend only — API key never exposed to frontend.
- Used ONLY for natural language explanation from canonical clinical JSON.
- Never used for classification, diagnosis, or clinical decisions.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")


def get_client():
    """Return Anthropic client. Raises if not configured."""
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "anthropic package not installed — run: pip install anthropic"
        ) from exc

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")

    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def hash_clinical_input(clinical_input: dict) -> str:
    """Deterministic hash of clinical input for cache key."""
    canonical = json.dumps(clinical_input, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
