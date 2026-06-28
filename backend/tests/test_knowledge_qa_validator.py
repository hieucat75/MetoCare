"""Tests for CKP QA Validator."""
from __future__ import annotations

from pathlib import Path

from app.knowledge.qa_validator import QAIssue, QAReport, validate_registry
from app.knowledge.schema import KnowledgeCard, KnowledgeSections


def _make_valid_card(
    knowledge_id: str = "test_card",
    status: str = "internal_review",
    related_cards: list[str] | None = None,
    confidence: float = 0.80,
    future_review_due: str = "2027-06-28",
    display_name_vi: str = "Test Card",
) -> KnowledgeCard:
    return KnowledgeCard(
        knowledge_id=knowledge_id,
        knowledge_type="biomarker",
        version="1.0",
        language="vi",
        status=status,
        last_reviewed="2026-06-28",
        reviewer="test",
        medical_specialty="general",
        evidence_level="moderate",
        confidence=confidence,
        future_review_due=future_review_due,
        display_name_vi=display_name_vi,
        short_summary_vi="Short summary.",
        tags=[knowledge_id],
        related_cards=related_cards or [],
        sections=KnowledgeSections(
            definition="Definition text.",
            normal_physiology="Normal physiology text.",
            causes_of_abnormality="Causes text.",
            clinical_significance="Clinical significance text.",
            patient_explanation="Patient explanation text.",
            lifestyle_relevance="Lifestyle relevance text.",
        ),
    )


def test_valid_card_passes():
    """Well-formed card → QAReport.passed=True."""
    card = _make_valid_card()
    report = validate_registry([card])
    assert report.passed
    assert report.error_count == 0


def test_missing_definition_fails():
    """Card without definition → error."""
    card = _make_valid_card()
    card.sections.definition = ""
    report = validate_registry([card])
    assert not report.passed
    assert any("definition" in i.field for i in report.issues if i.severity == "error")


def test_missing_display_name_fails():
    """Missing display_name_vi → error."""
    card = _make_valid_card(display_name_vi="")
    report = validate_registry([card])
    assert not report.passed
    assert any(i.field == "display_name_vi" for i in report.issues if i.severity == "error")


def test_duplicate_id_fails():
    """Two cards with same knowledge_id → error."""
    card1 = _make_valid_card("dup_card")
    card2 = _make_valid_card("dup_card")
    report = validate_registry([card1, card2])
    assert not report.passed
    dup_errors = [i for i in report.issues if i.field == "knowledge_id" and i.severity == "error"]
    assert len(dup_errors) >= 1


def test_broken_related_card():
    """related_cards refs nonexistent id → error."""
    card = _make_valid_card("test_card", related_cards=["nonexistent_card"])
    report = validate_registry([card])
    assert not report.passed
    broken_refs = [
        i for i in report.issues
        if "Broken reference" in i.message and i.severity == "error"
    ]
    assert len(broken_refs) == 1


def test_deprecated_referenced_warning():
    """Active card refs deprecated card → warning only, not error."""
    deprecated = _make_valid_card("old_card", status="deprecated")
    active = _make_valid_card("active_card", related_cards=["old_card"])
    report = validate_registry([deprecated, active])
    warnings = [
        i for i in report.issues
        if "deprecated" in i.message.lower() and i.severity == "warning"
    ]
    assert len(warnings) >= 1
    # Deprecated reference alone should not block (no error for it)
    assert report.passed  # No errors for this pattern alone (only warnings)


def test_invalid_confidence_fails():
    """confidence=1.5 → error from QA check."""
    card = _make_valid_card(confidence=1.5)
    report = validate_registry([card])
    assert not report.passed
    conf_errors = [
        i for i in report.issues
        if i.field == "confidence" and i.severity == "error"
    ]
    assert len(conf_errors) == 1


def test_overdue_review_warning():
    """future_review_due in past → warning."""
    card = _make_valid_card(future_review_due="2020-01-01")
    report = validate_registry([card])
    overdue = [
        i for i in report.issues
        if i.field == "future_review_due" and i.severity == "warning"
    ]
    assert len(overdue) == 1


def test_print_report_no_issues(capsys):
    """Passed report prints 'All cards passed'."""
    report = QAReport(issues=[], cards_checked=1)
    report.print_report()
    captured = capsys.readouterr()
    assert "All cards passed" in captured.out


def test_print_report_with_issues(capsys):
    """Failed report prints errors."""
    report = QAReport(
        issues=[QAIssue("error", "test_card", "definition", "Required section missing")],
        cards_checked=1,
    )
    report.print_report()
    captured = capsys.readouterr()
    assert "❌" in captured.out or "error" in captured.out.lower()
    assert "test_card" in captured.out


def test_all_9_yaml_cards_pass_qa():
    """Load actual 9 YAML cards from cards/ dir → QAReport.passed=True."""
    from app.knowledge.registry import KnowledgeRegistry, reset_registry

    reset_registry()
    cards_path = Path(__file__).parent.parent / "app" / "knowledge" / "cards"
    reg = KnowledgeRegistry(cards_path)
    cards = reg.all_cards()

    assert len(cards) == 9, f"Expected 9 cards, got {len(cards)}: {[c.knowledge_id for c in cards]}"

    report = validate_registry(cards)
    if not report.passed:
        report.print_report()
    assert report.passed, f"{report.error_count} QA errors found in YAML cards"
