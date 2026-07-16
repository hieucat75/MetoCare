"""Unit tests for Phase A / PR-A1a: validators.py.

No database involved — validators.py's checks are pure Python-level
allowlist/structural checks by design (see
docs/medication-management/MEDICATION_PHASE_A_BLOCKING_FINDINGS.md
Finding 2 for why the specialty check has no DB dependency at this layer).
"""

from __future__ import annotations

from app.services.medication_knowledge_import.schema import KnowledgeFile
from app.services.medication_knowledge_import.validators import (
    ALLOWED_SPECIALTY_CODES,
    validate_business_rules,
)


def _valid_file_dict() -> dict:
    return {
        "metadata": {
            "knowledge_type": "usage",
            "medication_identity": {"name_inn": "test-ingredient-synthetic"},
            "locale": "vi",
            "audience": "patient",
        },
        "content": {"body": "synthetic test content"},
        "references": [
            {
                "publisher": "Test Publisher",
                "title": "Synthetic Test Reference",
                "source_type": "formulary",
                "url": "https://example.invalid/ref",
                "publication_date": "2024-01-01",
                "source_version": "1.0",
                "accessed_at": "2026-07-01",
            }
        ],
        "review_metadata": {
            "source": "Test Source",
            "version": "1.0.0",
            "evidence_level": "moderate",
            "reviewed_at": "2026-07-01",
            "authored_by": "test-author",
            "ai_generated": False,
            "specialty_codes": [],
        },
        "disclaimer": {"acknowledged": True},
    }


def test_no_errors_for_valid_file_with_no_specialties() -> None:
    knowledge_file = KnowledgeFile.model_validate(_valid_file_dict())
    assert validate_business_rules(knowledge_file) == []


def test_allowed_specialty_code_passes() -> None:
    data = _valid_file_dict()
    code = next(iter(ALLOWED_SPECIALTY_CODES))
    data["review_metadata"]["specialty_codes"] = [code]
    knowledge_file = KnowledgeFile.model_validate(data)
    assert validate_business_rules(knowledge_file) == []


def test_invalid_specialty_code_rejected() -> None:
    data = _valid_file_dict()
    data["review_metadata"]["specialty_codes"] = ["neurosurgery"]
    knowledge_file = KnowledgeFile.model_validate(data)
    errors = validate_business_rules(knowledge_file)
    assert len(errors) == 1
    assert "neurosurgery" in errors[0]


def test_duplicate_reference_in_same_file_rejected() -> None:
    data = _valid_file_dict()
    data["references"] = [data["references"][0], dict(data["references"][0])]
    knowledge_file = KnowledgeFile.model_validate(data)
    errors = validate_business_rules(knowledge_file)
    assert any("duplicate reference" in e for e in errors)


def test_multiple_violations_all_reported_at_once() -> None:
    """Batch validation: one call surfaces every problem, not just the first."""
    data = _valid_file_dict()
    data["review_metadata"]["specialty_codes"] = ["neurosurgery"]
    data["references"] = [data["references"][0], dict(data["references"][0])]
    knowledge_file = KnowledgeFile.model_validate(data)
    errors = validate_business_rules(knowledge_file)
    assert len(errors) == 2
