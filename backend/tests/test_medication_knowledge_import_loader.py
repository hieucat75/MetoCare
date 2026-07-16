"""Unit tests for Phase A / PR-A1a: loader.py.

No database involved — pure file I/O tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.services.medication_knowledge_import.loader import LoaderError, load_file


def test_loads_valid_yaml(tmp_path: Path) -> None:
    f = tmp_path / "item.yaml"
    f.write_text("a: 1\nb: two\n", encoding="utf-8")
    assert load_file(f) == {"a": 1, "b": "two"}


def test_loads_valid_json(tmp_path: Path) -> None:
    f = tmp_path / "item.json"
    f.write_text('{"a": 1, "b": "two"}', encoding="utf-8")
    assert load_file(f) == {"a": 1, "b": "two"}


def test_rejects_unsupported_extension(tmp_path: Path) -> None:
    f = tmp_path / "item.sql"
    f.write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(LoaderError, match="unsupported file type"):
        load_file(f)


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LoaderError, match="not found"):
        load_file(tmp_path / "does-not-exist.yaml")


def test_rejects_malformed_yaml(tmp_path: Path) -> None:
    f = tmp_path / "broken.yaml"
    f.write_text("a: [unterminated\n", encoding="utf-8")
    with pytest.raises(LoaderError, match="malformed"):
        load_file(f)


def test_rejects_malformed_json(tmp_path: Path) -> None:
    f = tmp_path / "broken.json"
    f.write_text('{"a": }', encoding="utf-8")
    with pytest.raises(LoaderError, match="malformed"):
        load_file(f)


def test_rejects_non_mapping_top_level(tmp_path: Path) -> None:
    f = tmp_path / "list.yaml"
    f.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(LoaderError, match="did not parse to a mapping"):
        load_file(f)


def test_rejects_non_utf8_file(tmp_path: Path) -> None:
    """Regression test: a file with invalid UTF-8 bytes must be wrapped as
    LoaderError, not leak a raw UnicodeDecodeError past this module's own
    documented "never raise a raw parser exception" contract."""
    f = tmp_path / "bad-encoding.yaml"
    f.write_bytes(b"a: \xff\xfe invalid utf-8 bytes\n")
    with pytest.raises(LoaderError, match="malformed"):
        load_file(f)
