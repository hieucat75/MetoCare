"""Tests for KnowledgeRegistry."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml
from app.knowledge.registry import KnowledgeRegistry, get_registry, reset_registry


def _write_card(directory: Path, filename: str, data: dict) -> None:
    """Write a YAML card to a directory."""
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def _make_card_dict(
    knowledge_id: str = "test_card",
    status: str = "internal_review",
    related_cards: list[str] | None = None,
    tags: list[str] | None = None,
    display_name_vi: str = "Test Card",
) -> dict:
    return {
        "knowledge_id": knowledge_id,
        "knowledge_type": "biomarker",
        "version": "1.0",
        "language": "vi",
        "status": status,
        "last_reviewed": "2026-06-28",
        "reviewer": "test",
        "medical_specialty": "general",
        "evidence_level": "moderate",
        "confidence": 0.80,
        "future_review_due": "2027-06-28",
        "display_name_vi": display_name_vi,
        "short_summary_vi": f"Summary for {knowledge_id}.",
        "tags": tags or [knowledge_id],
        "related_cards": related_cards or [],
        "sections": {
            "definition": f"Definition of {knowledge_id}.",
            "normal_physiology": "Normal physiology.",
            "causes_of_abnormality": "Causes.",
            "clinical_significance": "Clinical significance.",
            "patient_explanation": "Patient explanation.",
            "lifestyle_relevance": "Lifestyle relevance.",
        },
    }


@pytest.fixture(autouse=True)
def reset_singleton():
    """Always reset the registry singleton before each test."""
    reset_registry()
    yield
    reset_registry()


def test_registry_loads_cards():
    """Registry with test dir loads YAML → cards in _cards dict."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cards_dir = Path(tmpdir)
        _write_card(cards_dir, "ldl_elevated.yaml", _make_card_dict("ldl_elevated"))
        _write_card(cards_dir, "hdl_low.yaml", _make_card_dict("hdl_low"))

        reg = KnowledgeRegistry(cards_dir)
        cards = reg.all_cards()
        assert len(cards) == 2
        ids = {c.knowledge_id for c in cards}
        assert "ldl_elevated" in ids
        assert "hdl_low" in ids


def test_lookup_existing():
    """lookup('ldl_elevated') returns KnowledgeCard."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cards_dir = Path(tmpdir)
        _write_card(cards_dir, "ldl_elevated.yaml", _make_card_dict("ldl_elevated"))
        reg = KnowledgeRegistry(cards_dir)
        card = reg.lookup("ldl_elevated")
        assert card is not None
        assert card.knowledge_id == "ldl_elevated"


def test_lookup_nonexistent():
    """lookup('nonexistent') returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cards_dir = Path(tmpdir)
        _write_card(cards_dir, "test.yaml", _make_card_dict("test_card"))
        reg = KnowledgeRegistry(cards_dir)
        result = reg.lookup("nonexistent")
        assert result is None


def test_lookup_deprecated_returns_none():
    """Deprecated card → lookup returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cards_dir = Path(tmpdir)
        _write_card(
            cards_dir, "old.yaml", _make_card_dict("old_card", status="deprecated")
        )
        reg = KnowledgeRegistry(cards_dir)
        result = reg.lookup("old_card")
        assert result is None


def test_search_by_tag():
    """search('tim_mach') returns cards with that tag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cards_dir = Path(tmpdir)
        _write_card(
            cards_dir,
            "ldl.yaml",
            _make_card_dict("ldl_elevated", tags=["tim_mach", "lipid"]),
        )
        _write_card(
            cards_dir,
            "glucose.yaml",
            _make_card_dict("glucose_elevated", tags=["duong_huyet"]),
        )
        reg = KnowledgeRegistry(cards_dir)
        results = reg.search("tim_mach")
        assert len(results) == 1
        assert results[0].knowledge_id == "ldl_elevated"


def test_search_by_name():
    """search('cholesterol') matches display_name_vi."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cards_dir = Path(tmpdir)
        _write_card(
            cards_dir,
            "ldl.yaml",
            _make_card_dict("ldl_elevated", display_name_vi="Cholesterol LDL (xấu)"),
        )
        _write_card(
            cards_dir,
            "glucose.yaml",
            _make_card_dict("glucose_elevated", display_name_vi="Đường huyết"),
        )
        reg = KnowledgeRegistry(cards_dir)
        results = reg.search("cholesterol")
        assert len(results) == 1
        assert results[0].knowledge_id == "ldl_elevated"


def test_related_cards():
    """related_cards('ldl_elevated') returns [hdl_low, triglyceride_elevated, ...]."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cards_dir = Path(tmpdir)
        _write_card(
            cards_dir,
            "ldl.yaml",
            _make_card_dict(
                "ldl_elevated", related_cards=["hdl_low", "triglyceride_elevated"]
            ),
        )
        _write_card(cards_dir, "hdl.yaml", _make_card_dict("hdl_low"))
        _write_card(cards_dir, "tg.yaml", _make_card_dict("triglyceride_elevated"))

        reg = KnowledgeRegistry(cards_dir)
        related = reg.related_cards("ldl_elevated")
        related_ids = {c.knowledge_id for c in related}
        assert "hdl_low" in related_ids
        assert "triglyceride_elevated" in related_ids


def test_cards_for_insight():
    """cards_for_insight('ldl_elevated') returns at most 3 cards."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cards_dir = Path(tmpdir)
        _write_card(cards_dir, "ldl.yaml", _make_card_dict("ldl_elevated"))
        reg = KnowledgeRegistry(cards_dir)
        result = reg.cards_for_insight("ldl_elevated")
        assert len(result) <= 3
        assert result[0].knowledge_id == "ldl_elevated"


def test_cards_for_patient_report():
    """Mock report with 2 insight card_ids → 2 cards returned."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cards_dir = Path(tmpdir)
        _write_card(cards_dir, "ldl.yaml", _make_card_dict("ldl_elevated"))
        _write_card(cards_dir, "hdl.yaml", _make_card_dict("hdl_low"))

        report = {
            "insights": [
                {"card_id": "ldl_elevated", "title_vi": "LDL cao"},
                {"card_id": "hdl_low", "title_vi": "HDL thấp"},
            ]
        }
        reg = KnowledgeRegistry(cards_dir)
        cards = reg.cards_for_patient_report(report)
        assert len(cards) == 2
        ids = {c.knowledge_id for c in cards}
        assert "ldl_elevated" in ids
        assert "hdl_low" in ids


def test_registry_singleton():
    """get_registry() twice returns same object."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cards_dir = Path(tmpdir)
        os.environ["KNOWLEDGE_BASE_PATH"] = str(cards_dir)
        try:
            r1 = get_registry()
            r2 = get_registry()
            assert r1 is r2
        finally:
            del os.environ["KNOWLEDGE_BASE_PATH"]


def test_reset_registry():
    """reset_registry() + get_registry() = new instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["KNOWLEDGE_BASE_PATH"] = str(tmpdir)
        try:
            r1 = get_registry()
            reset_registry()
            r2 = get_registry()
            assert r1 is not r2
        finally:
            del os.environ["KNOWLEDGE_BASE_PATH"]


def test_registry_max_5_cards():
    """Report with 10 insight types → max 5 cards returned."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cards_dir = Path(tmpdir)
        # Create 10 cards
        for i in range(10):
            cid = f"card_{i}"
            _write_card(cards_dir, f"{cid}.yaml", _make_card_dict(cid))

        report = {
            "insights": [{"card_id": f"card_{i}"} for i in range(10)]
        }
        reg = KnowledgeRegistry(cards_dir)
        cards = reg.cards_for_patient_report(report)
        assert len(cards) <= 5
