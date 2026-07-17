"""Unit tests for A1b: versioning.py (business key, artifact hash,
version-action resolution).

Runs against the shared SQLite test DB via the existing `db` fixture
(tests/conftest.py), matching K1-S3's own convention. Synthetic fixtures
only — never real clinical content.
"""

from __future__ import annotations

import copy
import uuid

import pytest
from app.models.drug_knowledge_content import DrugSideEffect
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.services.knowledge_repository import add_draft, build_draft
from app.services.medication_knowledge_import import versioning as v
from app.services.medication_knowledge_import.schema import KnowledgeFile


def _make_ingredient(db) -> DrugIngredient:
    suffix = uuid.uuid4().hex[:8]
    drug_class = DrugClass(name=f"test-class-{suffix}", required_specialties=[])
    db.add(drug_class)
    db.flush()
    ingredient = DrugIngredient(name_inn=f"test-ingredient-{suffix}", drug_class_id=drug_class.id)
    db.add(ingredient)
    db.commit()
    db.refresh(ingredient)
    return ingredient


def _side_effect_file(
    *,
    concept_code="nausea",
    version="1.0.0",
    title="Test Title",
    publisher="Test Publisher",
    source_type="formulary",
    url="https://example.invalid/x",
    document_identifier=None,
    publication_date="2024-01-01",
    reviewed_at="2026-01-01",
    evidence_level="moderate",
    specialty_codes=None,
) -> dict:
    reference: dict = {
        "publisher": publisher,
        "title": title,
        "source_type": source_type,
        "url": url,
        "publication_date": publication_date,
        "source_version": "1.0",
        "accessed_at": "2026-01-01",
    }
    if document_identifier is not None:
        reference["document_identifier"] = document_identifier
    return {
        "metadata": {
            "knowledge_type": "side_effect",
            "medication_identity": {"name_inn": "test-ingredient-synthetic"},
            "locale": "vi",
            "audience": "patient",
        },
        "content": {
            "frequency": "common",
            "action_level": "self_monitor",
            "concept_code": concept_code,
            "label": "Label",
            "description": "synthetic test description",
        },
        "references": [reference],
        "review_metadata": {
            "source": "Test Source",
            "version": version,
            "evidence_level": evidence_level,
            "reviewed_at": reviewed_at,
            "authored_by": "test-author",
            "ai_generated": False,
            "specialty_codes": specialty_codes or [],
        },
        "disclaimer": {"acknowledged": True},
    }


def _kf(**kwargs) -> KnowledgeFile:
    return KnowledgeFile.model_validate(_side_effect_file(**kwargs))


class TestBusinessKeyFor:
    def test_side_effect_key_is_ingredient_and_concept_code_only(self) -> None:
        kf = _kf()
        assert v.business_key_for(kf, "ing-1") == ("ing-1", "nausea")

    def test_usage_key_includes_locale_and_audience(self) -> None:
        data = {
            "metadata": {
                "knowledge_type": "usage",
                "medication_identity": {"name_inn": "x"},
                "locale": "vi",
                "audience": "patient",
            },
            "content": {"body": "synthetic body"},
            "references": [
                {
                    "publisher": "p",
                    "title": "t",
                    "source_type": "formulary",
                    "url": "https://example.invalid/x",
                    "publication_date": "2024-01-01",
                    "source_version": "1.0",
                    "accessed_at": "2026-01-01",
                }
            ],
            "review_metadata": {
                "source": "s",
                "version": "1.0.0",
                "evidence_level": "moderate",
                "reviewed_at": "2026-01-01",
                "authored_by": "a",
                "ai_generated": False,
                "specialty_codes": [],
            },
            "disclaimer": {"acknowledged": True},
        }
        kf = KnowledgeFile.model_validate(data)
        assert v.business_key_for(kf, "ing-1") == ("ing-1", "vi", "patient")


class TestArtifactHash:
    def test_identical_file_hashes_identically(self) -> None:
        kf1 = _kf()
        kf2 = _kf()
        assert v.artifact_hash(kf1) == v.artifact_hash(kf2)

    def test_hash_is_64_char_hex(self) -> None:
        h = v.artifact_hash(_kf())
        assert len(h) == 64
        int(h, 16)  # raises ValueError if not valid hex

    def test_reference_change_changes_hash(self) -> None:
        """The original bug report: changing a reference must NOT be
        invisible to the hash."""
        h1 = v.artifact_hash(_kf(title="Original Title"))
        h2 = v.artifact_hash(_kf(title="Different Title"))
        assert h1 != h2

    def test_provenance_change_changes_hash(self) -> None:
        h1 = v.artifact_hash(_kf(reviewed_at="2026-01-01"))
        h2 = v.artifact_hash(_kf(reviewed_at="2026-06-01"))
        assert h1 != h2

    def test_evidence_level_change_changes_hash(self) -> None:
        h1 = v.artifact_hash(_kf(evidence_level="moderate"))
        h2 = v.artifact_hash(_kf(evidence_level="strong"))
        assert h1 != h2

    def test_specialty_codes_reorder_is_no_op(self) -> None:
        h1 = v.artifact_hash(_kf(specialty_codes=["a", "b"]))
        h2 = v.artifact_hash(_kf(specialty_codes=["b", "a"]))
        assert h1 == h2

    def test_specialty_codes_change_changes_hash(self) -> None:
        h1 = v.artifact_hash(_kf(specialty_codes=["a"]))
        h2 = v.artifact_hash(_kf(specialty_codes=["a", "b"]))
        assert h1 != h2

    def test_reference_reorder_is_no_op(self) -> None:
        data = _side_effect_file()
        data["references"] = [
            {
                "publisher": "p1",
                "title": "t1",
                "source_type": "formulary",
                "url": "https://example.invalid/1",
                "publication_date": "2024-01-01",
                "source_version": "1.0",
                "accessed_at": "2026-01-01",
            },
            {
                "publisher": "p2",
                "title": "t2",
                "source_type": "formulary",
                "url": "https://example.invalid/2",
                "publication_date": "2024-01-01",
                "source_version": "1.0",
                "accessed_at": "2026-01-01",
            },
        ]
        kf_a = KnowledgeFile.model_validate(data)
        reordered = copy.deepcopy(data)
        reordered["references"] = list(reversed(reordered["references"]))
        kf_b = KnowledgeFile.model_validate(reordered)
        assert v.artifact_hash(kf_a) == v.artifact_hash(kf_b)

    def test_reference_reorder_is_no_op_with_mixed_document_identifier(self) -> None:
        """Codex round-1 P2: the reorder test above uses two references
        that both have `document_identifier=None` — this proves
        `_reference_sort_key`'s `(is_none, value)` design is genuinely
        total-order-safe for a MIXED pair (one None, one string-valued),
        not just when both share the same None-ness, and that no
        TypeError is raised from a direct None-vs-str comparison."""
        data = _side_effect_file()
        data["references"] = [
            {
                "publisher": "p1",
                "title": "t1",
                "source_type": "formulary",
                "url": "https://example.invalid/1",
                "publication_date": "2024-01-01",
                "source_version": "1.0",
                "accessed_at": "2026-01-01",
            },
            {
                "publisher": "p2",
                "title": "t2",
                "source_type": "peer_reviewed",
                "document_identifier": "ISBN-mixed",
                "publication_date": "2024-01-01",
                "source_version": "1.0",
                "accessed_at": "2026-01-01",
            },
        ]
        kf_a = KnowledgeFile.model_validate(data)
        reordered = copy.deepcopy(data)
        reordered["references"] = list(reversed(reordered["references"]))
        kf_b = KnowledgeFile.model_validate(reordered)
        assert v.artifact_hash(kf_a) == v.artifact_hash(kf_b)

    def test_content_change_changes_hash(self) -> None:
        h1 = v.artifact_hash(_kf(concept_code="nausea"))
        h2 = v.artifact_hash(_kf(concept_code="dizziness"))
        assert h1 != h2

    def test_reference_url_change_changes_hash(self) -> None:
        """PTH round-1 P1 fix: url is persisted on DrugReference but was
        NOT part of the old identity-only hash — changing it under an
        unchanged version must not be silently NO_OP."""
        h1 = v.artifact_hash(_kf(url="https://example.invalid/original"))
        h2 = v.artifact_hash(_kf(url="https://example.invalid/changed"))
        assert h1 != h2

    def test_reference_source_type_change_changes_hash(self) -> None:
        h1 = v.artifact_hash(_kf(source_type="formulary"))
        h2 = v.artifact_hash(_kf(source_type="peer_reviewed"))
        assert h1 != h2

    def test_reference_publisher_change_with_document_identifier_changes_hash(self) -> None:
        """On the document-identifier branch, F1's citation identity does
        NOT include publisher/title/publication_date — those fields must
        still be part of the artifact hash even though they're not part of
        the DB-dedup identity."""
        h1 = v.artifact_hash(_kf(document_identifier="ISBN-1", publisher="Publisher A"))
        h2 = v.artifact_hash(_kf(document_identifier="ISBN-1", publisher="Publisher B"))
        assert h1 != h2

    def test_reference_title_change_with_document_identifier_changes_hash(self) -> None:
        h1 = v.artifact_hash(_kf(document_identifier="ISBN-1", title="Title A"))
        h2 = v.artifact_hash(_kf(document_identifier="ISBN-1", title="Title B"))
        assert h1 != h2

    def test_reference_publication_date_change_with_document_identifier_changes_hash(
        self,
    ) -> None:
        h1 = v.artifact_hash(_kf(document_identifier="ISBN-1", publication_date="2024-01-01"))
        h2 = v.artifact_hash(_kf(document_identifier="ISBN-1", publication_date="2024-06-01"))
        assert h1 != h2


class TestResolveVersionAction:
    def test_new_business_key_is_new_draft(self) -> None:
        assert v.resolve_version_action([], "1.0.0", "hash-a") == v.VersionAction.NEW_DRAFT

    def test_same_version_same_hash_is_no_op(self) -> None:
        known = [("1.0.0", "hash-a")]
        assert (
            v.resolve_version_action(known, "1.0.0", "hash-a")
            == v.VersionAction.NO_OP_ALREADY_IMPORTED
        )

    def test_same_version_different_hash_is_reject(self) -> None:
        known = [("1.0.0", "hash-a")]
        assert (
            v.resolve_version_action(known, "1.0.0", "hash-b")
            == v.VersionAction.REJECT_VERSION_CONFLICT
        )

    def test_new_version_matching_older_hash_is_warn_proceed(self) -> None:
        known = [("1.0.0", "hash-a")]
        assert (
            v.resolve_version_action(known, "2.0.0", "hash-a")
            == v.VersionAction.WARN_PROCEED_REPEATED_ARTIFACT
        )

    def test_new_version_new_hash_is_new_draft(self) -> None:
        known = [("1.0.0", "hash-a")]
        assert v.resolve_version_action(known, "2.0.0", "hash-b") == v.VersionAction.NEW_DRAFT

    def test_matches_older_non_latest_version_not_just_most_recent(self) -> None:
        """v1 and v2 exist; re-importing v1's exact hash under a new v3
        string must resolve WARN_PROCEED, proving the full history is
        checked, not just the most recent row."""
        known = [("1.0.0", "hash-v1"), ("2.0.0", "hash-v2")]
        assert (
            v.resolve_version_action(known, "3.0.0", "hash-v1")
            == v.VersionAction.WARN_PROCEED_REPEATED_ARTIFACT
        )

    def test_two_rows_same_version_same_hash_is_no_op(self) -> None:
        """PTH round-1 P1 fix: no unique constraint prevents two rows
        sharing (business_key, version) — a real concurrent-import race
        can leave duplicates. If both share the incoming hash, NO_OP."""
        known = [("1.0.0", "hash-a"), ("1.0.0", "hash-a")]
        assert (
            v.resolve_version_action(known, "1.0.0", "hash-a")
            == v.VersionAction.NO_OP_ALREADY_IMPORTED
        )

    def test_two_rows_same_version_different_hash_always_rejects(self) -> None:
        """Two existing rows under the same version already disagree with
        each other — a real artifact conflict exists regardless of what
        the incoming file's hash is. Must always reject, never NO_OP just
        because the incoming hash happens to match ONE of the two."""
        known = [("1.0.0", "hash-a"), ("1.0.0", "hash-b")]
        assert (
            v.resolve_version_action(known, "1.0.0", "hash-a")
            == v.VersionAction.REJECT_VERSION_CONFLICT
        )
        assert (
            v.resolve_version_action(known, "1.0.0", "hash-b")
            == v.VersionAction.REJECT_VERSION_CONFLICT
        )
        assert (
            v.resolve_version_action(known, "1.0.0", "hash-c")
            == v.VersionAction.REJECT_VERSION_CONFLICT
        )

    def test_matching_and_conflicting_hash_both_present_rejects(self) -> None:
        """Incoming hash matches one of two existing same-version rows,
        but a second, conflicting row also exists under that version — the
        old first-match-only logic could resolve NO_OP here depending on
        query order; the fixed logic must always reject."""
        known = [("1.0.0", "hash-a"), ("1.0.0", "hash-b")]
        assert (
            v.resolve_version_action(known, "1.0.0", "hash-a")
            == v.VersionAction.REJECT_VERSION_CONFLICT
        )

    def test_same_version_conflict_result_is_order_independent(self) -> None:
        """The old bug made NO_OP-vs-REJECT depend on unspecified DB query
        ordering. The fix must give the identical result regardless of the
        order `known_versions` happens to arrive in."""
        known_order_a = [("1.0.0", "hash-a"), ("1.0.0", "hash-b")]
        known_order_b = [("1.0.0", "hash-b"), ("1.0.0", "hash-a")]
        assert (
            v.resolve_version_action(known_order_a, "1.0.0", "hash-a")
            == v.resolve_version_action(known_order_b, "1.0.0", "hash-a")
            == v.VersionAction.REJECT_VERSION_CONFLICT
        )


class TestKnownVersionsFor:
    def _insert_side_effect(
        self, db, ingredient_id, *, concept_code, version, artifact_hash, status="draft"
    ):
        row = build_draft(
            DrugSideEffect,
            authored_by="tester",
            artifact_hash=artifact_hash,
            drug_ingredient_id=ingredient_id,
            concept_code=concept_code,
            label="Label",
            frequency="common",
            action_level="self_monitor",
            description="desc",
            version=version,
        )
        row.status = status
        add_draft(db, row)
        db.commit()
        return row

    def test_returns_full_non_retired_history(self, db) -> None:
        ingredient = _make_ingredient(db)
        self._insert_side_effect(
            db, ingredient.id, concept_code="x", version="1.0.0", artifact_hash="h1"
        )
        self._insert_side_effect(
            db, ingredient.id, concept_code="x", version="2.0.0", artifact_hash="h2"
        )
        known = v.known_versions_for(db, "side_effect", (ingredient.id, "x"))
        assert set(known) == {("1.0.0", "h1"), ("2.0.0", "h2")}

    def test_excludes_retired_rows(self, db) -> None:
        ingredient = _make_ingredient(db)
        self._insert_side_effect(
            db,
            ingredient.id,
            concept_code="y",
            version="1.0.0",
            artifact_hash="h1",
            status="retired",
        )
        known = v.known_versions_for(db, "side_effect", (ingredient.id, "y"))
        assert known == []

    def test_fails_closed_on_non_retired_null_hash(self, db) -> None:
        ingredient = _make_ingredient(db)
        self._insert_side_effect(
            db, ingredient.id, concept_code="z", version="1.0.0", artifact_hash=None, status="draft"
        )
        with pytest.raises(
            v.LegacyArtifactHashUnavailableError, match="LEGACY_ARTIFACT_HASH_UNAVAILABLE"
        ):
            v.known_versions_for(db, "side_effect", (ingredient.id, "z"))

    def test_retired_null_hash_row_does_not_block(self, db) -> None:
        ingredient = _make_ingredient(db)
        self._insert_side_effect(
            db,
            ingredient.id,
            concept_code="w",
            version="1.0.0",
            artifact_hash=None,
            status="retired",
        )
        # must not raise — retired rows are excluded from the query entirely
        known = v.known_versions_for(db, "side_effect", (ingredient.id, "w"))
        assert known == []

    def test_empty_for_unknown_business_key(self, db) -> None:
        ingredient = _make_ingredient(db)
        known = v.known_versions_for(db, "side_effect", (ingredient.id, "never-imported"))
        assert known == []
