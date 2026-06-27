"""
Cache Claude explanations by (lab_result_id, clinical_input_hash).

Uses a simple file-based JSON cache (interim solution).
If a DB explanation table is added later, swap the backend here.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

CACHE_DIR: str = os.getenv(
    "EXPLANATION_CACHE_DIR", "/tmp/metocare_explanations"
)


def get_cached_explanation(lab_result_id: str, input_hash: str) -> dict | None:
    """Return cached explanation dict or None if not found."""
    path = _cache_path(lab_result_id, input_hash)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save_cached_explanation(
    lab_result_id: str, input_hash: str, data: dict
) -> None:
    """Persist explanation to cache (fire-and-forget; errors are logged but not raised)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload = {**data, "cached_at": datetime.utcnow().isoformat()}
    try:
        with open(_cache_path(lab_result_id, input_hash), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # Cache write failures are non-fatal


def invalidate_cached_explanation(lab_result_id: str, input_hash: str) -> bool:
    """Delete a cached entry. Returns True if deleted, False if not found."""
    path = _cache_path(lab_result_id, input_hash)
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError:
            pass
    return False


def _cache_path(lab_result_id: str, input_hash: str) -> str:
    return os.path.join(CACHE_DIR, f"{lab_result_id}_{input_hash}.json")
