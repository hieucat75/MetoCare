"""Read a knowledge authoring file (.yaml/.yml/.json) into a raw dict.

No validation, no database access — that's schema.py/validators.py/
provenance.py's job. This module's only responsibility is "parse the bytes
on disk into a Python dict, or fail with a clear error."
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

_SUPPORTED_SUFFIXES = {".yaml", ".yml", ".json"}


class LoaderError(ValueError):
    """Raised when a knowledge file cannot be read or parsed."""


def load_file(path: Path) -> dict:
    """Load one knowledge authoring file into a raw dict.

    Raises LoaderError for: unsupported extension, missing file, or a
    syntactically broken YAML/JSON body. Never raises a raw parser
    exception (PyYAML's YAMLError, json.JSONDecodeError) to the caller —
    those are wrapped so orchestrator.py can collect batch-wide errors
    uniformly (see MEDICATION_PHASE_A_PR_A1_IMPLEMENTATION_PLAN.md Section 4).
    """
    if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise LoaderError(
            f"unsupported file type {path.suffix!r} for {path} — "
            f"only {sorted(_SUPPORTED_SUFFIXES)} are accepted, never manual SQL"
        )
    if not path.is_file():
        raise LoaderError(f"knowledge file not found: {path}")

    text = path.read_text(encoding="utf-8")

    try:
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            data = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise LoaderError(f"malformed {path.suffix} in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise LoaderError(
            f"{path} did not parse to a mapping (got {type(data).__name__}) — "
            "a knowledge file must be a single object, not a list or scalar"
        )
    return data
