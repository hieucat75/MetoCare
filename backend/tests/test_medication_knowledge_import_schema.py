"""Unit tests for Phase A / PR-A1a: schema.py.

No database involved — pure Pydantic structural validation over synthetic
dicts (never real clinical content, per Phase A's scope lock).
"""

from __future__ import annotations

import copy

import pytest
from app.services.medication_knowledge_import.schema import KnowledgeFile
from pydantic import ValidationError


def _valid_file_dict() -> dict:
    return {
        "metadata": {
            "knowledge_type": "patient_education",
            "medication_identity": {"name_inn": "test-ingredient-synthetic"},
            "locale": "vi",
            "audience": "patient",
        },
        "content": {
            "theme": "test-theme",
            "body": "synthetic test content — never staged/production",
        },
        "references": [
            {
                "publisher": "Test Publisher",
                "title": "Synthetic Test Reference",
                "source_type": "formulary",
                "url": "https://example.invalid/ref",
                "document_identifier": None,
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


def test_valid_file_parses() -> None:
    knowledge_file = KnowledgeFile.model_validate(_valid_file_dict())
    assert knowledge_file.metadata.knowledge_type == "patient_education"
    assert knowledge_file.typed_content().theme == "test-theme"


@pytest.mark.parametrize(
    "field_path",
    [
        ("review_metadata", "source"),
        ("review_metadata", "version"),
        ("review_metadata", "reviewed_at"),
        ("review_metadata", "authored_by"),
    ],
)
def test_missing_required_provenance_field_rejected(field_path: tuple[str, str]) -> None:
    data = _valid_file_dict()
    section, key = field_path
    del data[section][key]
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_missing_disclaimer_acknowledgment_rejected() -> None:
    data = _valid_file_dict()
    del data["disclaimer"]["acknowledged"]
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_disclaimer_false_rejected() -> None:
    data = _valid_file_dict()
    data["disclaimer"]["acknowledged"] = False
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_ai_generated_true_rejected() -> None:
    data = _valid_file_dict()
    data["review_metadata"]["ai_generated"] = True
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_empty_references_rejected() -> None:
    data = _valid_file_dict()
    data["references"] = []
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_reference_without_url_or_document_identifier_rejected() -> None:
    data = _valid_file_dict()
    data["references"][0]["url"] = None
    data["references"][0]["document_identifier"] = None
    with pytest.raises(ValidationError, match="url or a document_identifier"):
        KnowledgeFile.model_validate(data)


def test_reference_with_document_identifier_instead_of_url_accepted() -> None:
    data = _valid_file_dict()
    data["references"][0]["url"] = None
    data["references"][0]["document_identifier"] = "ISBN-0000000000"
    KnowledgeFile.model_validate(data)  # does not raise


def test_unsupported_locale_rejected() -> None:
    data = _valid_file_dict()
    data["metadata"]["locale"] = "en"
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_unsupported_source_type_rejected() -> None:
    data = _valid_file_dict()
    data["references"][0]["source_type"] = "rumor"
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_prohibited_status_field_rejected() -> None:
    """The schema has no `status` field — extra="forbid" means an authoring
    file that tries to set one is a hard validation error, not a silently
    ignored no-op (Codex review P2: unknown fields were previously accepted
    silently)."""
    data = _valid_file_dict()
    data["status"] = "approved"  # extraneous — KnowledgeFile has no such field
    with pytest.raises(ValidationError, match="status"):
        KnowledgeFile.model_validate(data)


def test_unknown_field_in_review_metadata_rejected() -> None:
    data = _valid_file_dict()
    data["review_metadata"]["reviewer_notes"] = "not a real field"
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_unknown_field_in_content_rejected() -> None:
    data = _valid_file_dict()
    data["content"]["extra_unexpected_field"] = "x"
    with pytest.raises(ValidationError, match="content does not match the shape"):
        KnowledgeFile.model_validate(data)


def test_whitespace_only_source_rejected() -> None:
    data = _valid_file_dict()
    data["review_metadata"]["source"] = "   "
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_whitespace_only_document_identifier_rejected() -> None:
    data = _valid_file_dict()
    data["references"][0]["url"] = None
    data["references"][0]["document_identifier"] = "   "
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_malformed_url_rejected() -> None:
    data = _valid_file_dict()
    data["references"][0]["url"] = "not a url"
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_version_over_32_chars_rejected() -> None:
    """review_metadata.version maps directly to KnowledgeLifecycleMixin.version,
    a VARCHAR(32) — a longer value would pass A1a and fail A1b's DB write."""
    data = _valid_file_dict()
    data["review_metadata"]["version"] = "v" * 33
    with pytest.raises(ValidationError):
        KnowledgeFile.model_validate(data)


def test_non_normalized_concept_code_rejected() -> None:
    data = _valid_file_dict()
    data["metadata"]["knowledge_type"] = "side_effect"
    data["content"] = {
        "level": "common",
        "concept_code": "Not Normalized!",
        "description": "synthetic test description",
    }
    with pytest.raises(ValidationError, match="content does not match the shape"):
        KnowledgeFile.model_validate(data)


def test_non_normalized_condition_key_rejected() -> None:
    data = _valid_file_dict()
    data["metadata"]["knowledge_type"] = "contraindication"
    data["content"] = {
        "condition_type": "renal",
        "condition_key": "Bad Key With Spaces",
        "condition_detail": "synthetic test detail",
    }
    with pytest.raises(ValidationError, match="content does not match the shape"):
        KnowledgeFile.model_validate(data)


@pytest.mark.parametrize(
    "knowledge_type,bad_content",
    [
        ("usage", {"wrong_field": "x"}),
        ("side_effect", {"level": "common"}),  # missing concept_code/description
        ("monitoring", {"parameter": "eGFR"}),  # missing patient_context/guidance
        ("contraindication", {"condition_type": "renal"}),  # missing condition_key/detail
    ],
)
def test_content_shape_mismatch_rejected(knowledge_type: str, bad_content: dict) -> None:
    data = _valid_file_dict()
    data["metadata"]["knowledge_type"] = knowledge_type
    data["content"] = bad_content
    with pytest.raises(ValidationError, match="content does not match the shape"):
        KnowledgeFile.model_validate(data)


def test_side_effect_content_valid_shape_accepted() -> None:
    data = _valid_file_dict()
    data["metadata"]["knowledge_type"] = "side_effect"
    data["content"] = {
        "level": "common",
        "concept_code": "nausea",
        "description": "synthetic test description",
    }
    knowledge_file = KnowledgeFile.model_validate(data)
    assert knowledge_file.typed_content().concept_code == "nausea"


def test_usage_content_valid_shape_accepted() -> None:
    data = _valid_file_dict()
    data["metadata"]["knowledge_type"] = "usage"
    data["content"] = {"body": "synthetic test usage narrative"}
    knowledge_file = KnowledgeFile.model_validate(data)
    assert knowledge_file.typed_content().body == "synthetic test usage narrative"


def test_monitoring_content_valid_shape_accepted() -> None:
    data = _valid_file_dict()
    data["metadata"]["knowledge_type"] = "monitoring"
    data["content"] = {
        "parameter": "eGFR",
        "patient_context": "baseline",
        "guidance": "synthetic test monitoring guidance",
    }
    knowledge_file = KnowledgeFile.model_validate(data)
    assert knowledge_file.typed_content().parameter == "eGFR"


def test_contraindication_content_valid_shape_accepted() -> None:
    data = _valid_file_dict()
    data["metadata"]["knowledge_type"] = "contraindication"
    data["content"] = {
        "condition_type": "renal",
        "condition_key": "egfr_lt_30",
        "condition_detail": "synthetic test contraindication detail",
    }
    knowledge_file = KnowledgeFile.model_validate(data)
    assert knowledge_file.typed_content().condition_key == "egfr_lt_30"


def test_source_does_not_mutate_input_dict() -> None:
    """Guard against accidental in-place mutation (project immutability rule)."""
    data = _valid_file_dict()
    snapshot = copy.deepcopy(data)
    KnowledgeFile.model_validate(data)
    assert data == snapshot
