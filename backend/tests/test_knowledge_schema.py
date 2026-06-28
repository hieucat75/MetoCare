"""Tests for KnowledgeCard schema."""
from __future__ import annotations

from app.knowledge.schema import KnowledgeCard, KnowledgeSections


def _minimal_card_dict() -> dict:
    return {
        "knowledge_id": "test_biomarker",
        "knowledge_type": "biomarker",
        "version": "1.0",
        "language": "vi",
        "status": "internal_review",
        "last_reviewed": "2026-06-28",
        "reviewer": "test",
        "medical_specialty": "general",
        "evidence_level": "moderate",
        "confidence": 0.80,
        "future_review_due": "2027-06-28",
        "display_name_vi": "Test Biomarker",
        "short_summary_vi": "Short summary.",
        "tags": ["test"],
        "related_cards": [],
        "sections": {
            "definition": "Test definition.",
            "normal_physiology": "Normal physiology.",
            "causes_of_abnormality": "Causes.",
            "clinical_significance": "Clinical significance.",
            "patient_explanation": "Patient explanation.",
            "lifestyle_relevance": "Lifestyle relevance.",
        },
    }


def test_card_from_dict():
    """Test loading a minimal valid dict into KnowledgeCard."""
    data = _minimal_card_dict()
    card = KnowledgeCard.from_dict(data)
    assert card.knowledge_id == "test_biomarker"
    assert card.knowledge_type == "biomarker"
    assert card.version == "1.0"
    assert card.language == "vi"
    assert card.status == "internal_review"
    assert card.confidence == 0.80
    assert card.display_name_vi == "Test Biomarker"


def test_card_from_dict_nested_sections():
    """Sections dict properly parsed into KnowledgeSections."""
    data = _minimal_card_dict()
    data["sections"]["patient_explanation"] = "Patient friendly explanation."
    data["sections"]["common_questions"] = ["Q1?", "Q2?"]
    data["sections"]["doctor_discussion_topics"] = ["Topic 1"]
    data["sections"]["references"] = ["Ref 1"]
    card = KnowledgeCard.from_dict(data)
    assert isinstance(card.sections, KnowledgeSections)
    assert card.sections.definition == "Test definition."
    assert card.sections.patient_explanation == "Patient friendly explanation."
    assert card.sections.common_questions == ["Q1?", "Q2?"]
    assert card.sections.doctor_discussion_topics == ["Topic 1"]
    assert card.sections.references == ["Ref 1"]


def test_card_from_dict_missing_section_defaults():
    """Missing optional sections default to empty string / list."""
    data = _minimal_card_dict()
    # Remove optional sections
    data["sections"].pop("doctor_discussion_topics", None)
    data["sections"].pop("guideline_notes", None)
    data["sections"].pop("references", None)
    card = KnowledgeCard.from_dict(data)
    assert card.sections.doctor_discussion_topics == []
    assert card.sections.guideline_notes == ""
    assert card.sections.references == []


def test_card_status_values():
    """All valid status values are accepted (schema does not raise)."""
    valid_statuses = ["draft", "internal_review", "medical_review", "approved", "deprecated"]
    for status in valid_statuses:
        data = _minimal_card_dict()
        data["status"] = status
        card = KnowledgeCard.from_dict(data)
        assert card.status == status


def test_card_invalid_confidence_not_validated_at_schema_level():
    """Confidence outside 0-1 is NOT validated at schema level — QA catches it."""
    data = _minimal_card_dict()
    data["confidence"] = 1.5
    # Schema doesn't raise — QA validator does
    card = KnowledgeCard.from_dict(data)
    assert card.confidence == 1.5  # Schema stores it; QA rejects it
