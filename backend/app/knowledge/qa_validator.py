"""QA Validator for KnowledgeCards.

Validates all cards in the registry for:
- Missing required fields
- Missing required sections
- Invalid status values
- Duplicate knowledge_ids
- Broken related_cards references
- Missing references metadata
- Outdated future_review_due
- Deprecated cards still referenced by active cards

Callable as CLI: python -m app.knowledge.qa_validator [--path /path/to/cards]
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import KnowledgeCard

REQUIRED_SECTIONS = [
    "definition",
    "normal_physiology",
    "causes_of_abnormality",
    "clinical_significance",
    "patient_explanation",
    "lifestyle_relevance",
]
VALID_STATUSES = {"draft", "internal_review", "medical_review", "approved", "deprecated"}


@dataclass
class QAIssue:
    severity: str   # "error" | "warning"
    knowledge_id: str
    field: str
    message: str


@dataclass
class QAReport:
    issues: list[QAIssue] = field(default_factory=list)
    cards_checked: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def passed(self) -> bool:
        return self.error_count == 0

    def print_report(self) -> None:
        print(f"\n=== CKP QA Report — {self.cards_checked} cards ===")
        if not self.issues:
            print("✅ All cards passed QA validation.")
            return
        for issue in self.issues:
            icon = "❌" if issue.severity == "error" else "⚠️"
            print(f"{icon} [{issue.knowledge_id}] {issue.field}: {issue.message}")
        print(f"\nTotal: {self.error_count} errors, {self.warning_count} warnings")
        if self.passed:
            print("✅ No blocking errors.")
        else:
            print("❌ Blocking errors found. Fix before marking cards as approved.")


def validate_registry(cards: list[KnowledgeCard]) -> QAReport:
    """Run all QA checks against a list of KnowledgeCards."""
    report = QAReport(cards_checked=len(cards))

    # Build id set for reference checks
    all_ids = {c.knowledge_id for c in cards}
    deprecated_ids = {c.knowledge_id for c in cards if c.status == "deprecated"}

    # Duplicate check
    seen_ids: set[str] = set()
    for card in cards:
        if card.knowledge_id in seen_ids:
            report.issues.append(
                QAIssue("error", card.knowledge_id, "knowledge_id", "Duplicate knowledge_id")
            )
        seen_ids.add(card.knowledge_id)

    today = date.today().isoformat()

    for card in cards:
        kid = card.knowledge_id

        # Required fields
        if not card.display_name_vi:
            report.issues.append(
                QAIssue("error", kid, "display_name_vi", "Missing display_name_vi")
            )
        if not card.short_summary_vi:
            report.issues.append(
                QAIssue("warning", kid, "short_summary_vi", "Missing short_summary_vi")
            )
        if card.status not in VALID_STATUSES:
            report.issues.append(
                QAIssue("error", kid, "status", f"Invalid status: {card.status}")
            )
        if not card.last_reviewed:
            report.issues.append(
                QAIssue("warning", kid, "last_reviewed", "Missing last_reviewed date")
            )
        if not card.future_review_due:
            report.issues.append(
                QAIssue("warning", kid, "future_review_due", "Missing future_review_due")
            )
        elif card.future_review_due < today:
            report.issues.append(
                QAIssue(
                    "warning",
                    kid,
                    "future_review_due",
                    f"Overdue: {card.future_review_due}",
                )
            )
        if not (0.0 <= card.confidence <= 1.0):
            report.issues.append(
                QAIssue(
                    "error",
                    kid,
                    "confidence",
                    f"confidence must be 0.0–1.0, got {card.confidence}",
                )
            )

        # Required sections
        for sec in REQUIRED_SECTIONS:
            val = getattr(card.sections, sec, "")
            if not val or (isinstance(val, str) and not val.strip()):
                report.issues.append(
                    QAIssue(
                        "error",
                        kid,
                        f"sections.{sec}",
                        f"Required section '{sec}' is missing or empty",
                    )
                )

        # Broken related_cards
        for ref_id in card.related_cards:
            if ref_id not in all_ids:
                report.issues.append(
                    QAIssue(
                        "error",
                        kid,
                        "related_cards",
                        f"Broken reference: '{ref_id}' not found",
                    )
                )

        # Deprecated referenced by non-deprecated
        if card.status != "deprecated":
            for ref_id in card.related_cards:
                if ref_id in deprecated_ids:
                    report.issues.append(
                        QAIssue(
                            "warning",
                            kid,
                            "related_cards",
                            f"References deprecated card: '{ref_id}'",
                        )
                    )

        # Missing references for approved cards
        if card.status == "approved" and not card.sections.references:
            report.issues.append(
                QAIssue(
                    "warning",
                    kid,
                    "sections.references",
                    "Approved card has no references",
                )
            )

    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate MetoCare CKP knowledge cards")
    parser.add_argument("--path", type=Path, default=None, help="Path to cards directory")
    args = parser.parse_args()

    # Reset and load
    from app.knowledge.registry import KnowledgeRegistry

    reg = KnowledgeRegistry(args.path)
    cards = reg.all_cards()

    report = validate_registry(cards)
    report.print_report()
    sys.exit(0 if report.passed else 1)
