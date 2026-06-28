"""Narrative cache for full PatientInsightReport narratives.

File-based (same pattern as explanation_cache.py) at NARRATIVE_CACHE_DIR.
Cache key includes: patient_id, batch_id, engine_version, prompt_version, provider, model, language.
Auto-invalidated when any of these change.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

NARRATIVE_CACHE_DIR: str = os.getenv("NARRATIVE_CACHE_DIR", "/tmp/metocare_narratives")


def _make_cache_key(
    patient_id: str,
    batch_id: str | None,
    engine_version: str,
    prompt_version: str,
    provider: str,
    model: str,
    language: str,
) -> str:
    parts = f"{patient_id}|{batch_id or 'none'}|{engine_version}|{prompt_version}|{provider}|{model}|{language}"
    return hashlib.sha256(parts.encode()).hexdigest()[:24]


def _cache_path(key: str) -> str:
    return os.path.join(NARRATIVE_CACHE_DIR, f"{key}.json")


def get_cached_narrative(key: str) -> dict | None:
    """Return cached narrative dict or None if not found."""
    path = _cache_path(key)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save_narrative(key: str, data: dict) -> None:
    """Persist narrative to cache. Errors are non-fatal."""
    os.makedirs(NARRATIVE_CACHE_DIR, exist_ok=True)
    payload = {**data, "cached_at": datetime.utcnow().isoformat()}
    try:
        with open(_cache_path(key), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # Cache write failures are non-fatal


def invalidate_narrative(key: str) -> bool:
    """Delete a cached narrative entry. Returns True if deleted, False if not found."""
    path = _cache_path(key)
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError:
            pass
    return False


def make_narrative_key(
    patient_id: str,
    batch_id: str | None,
    engine_version: str,
    prompt_version: str,
    provider: str,
    model: str,
    language: str,
) -> str:
    return _make_cache_key(patient_id, batch_id, engine_version, prompt_version, provider, model, language)
