"""Tests for Narrative Memory."""
from __future__ import annotations

import tempfile

import pytest
from app.knowledge.memory import (
    format_memory_context,
    load_narrative_memory,
    save_narrative_memory,
)


@pytest.fixture(autouse=True)
def use_temp_memory_dir(monkeypatch):
    """Redirect memory to a temp dir for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("NARRATIVE_MEMORY_DIR", tmpdir)
        import app.knowledge.memory as mem_module
        mem_module.NARRATIVE_MEMORY_DIR = tmpdir
        yield tmpdir


def test_load_no_memory():
    """Patient with no history → None."""
    result = load_narrative_memory("patient_99999")
    assert result is None


def test_save_and_load_memory():
    """save then load → correct fields."""
    narrative = {
        "section_1_summary": "Sức khỏe ổn định.",
        "section_6_most_important_today": "Tập thể dục mỗi ngày.",
        "section_9_doctor_questions": ["Câu hỏi 1?"],
    }
    report_summary = {
        "top_priorities": ["Kiểm soát cholesterol"],
        "overall_status": "attention",
    }
    save_narrative_memory("patient_001", narrative, report_summary)
    loaded = load_narrative_memory("patient_001")
    assert loaded is not None
    assert loaded["patient_id"] == "patient_001"
    assert loaded["last_narrative_summary"] == "Sức khỏe ổn định."
    assert loaded["previous_section6"] == "Tập thể dục mỗi ngày."
    assert loaded["previous_priorities"] == ["Kiểm soát cholesterol"]
    assert loaded["report_overall_status"] == "attention"
    assert "saved_at" in loaded


def test_format_memory_context_empty():
    """None → empty string."""
    result = format_memory_context(None)
    assert result == ""


def test_format_memory_context_with_data():
    """Returns string with 'Tóm tắt lần trước'."""
    memory = {
        "last_narrative_summary": "Tình trạng sức khỏe ổn định.",
        "previous_section6": "Uống đủ nước.",
        "report_overall_status": "attention",
    }
    result = format_memory_context(memory)
    assert "Tóm tắt lần trước" in result
    assert "NGỮ CẢNH LỊCH SỬ" in result
    assert "Việc quan trọng nhất lần trước" in result


def test_format_memory_context_truncates():
    """Long summary → truncated in output."""
    long_summary = "A" * 500
    memory = {
        "last_narrative_summary": long_summary,
        "previous_section6": "",
        "report_overall_status": "",
    }
    result = format_memory_context(memory)
    # The summary gets truncated to 200 chars
    assert "A" * 201 not in result  # Longer than 200 chars should not appear
    assert "Tóm tắt lần trước" in result
