"""Unit tests for A1b: references.py (structured reference find-or-create).

Runs against the shared SQLite test DB via the existing `db` fixture
(tests/conftest.py). Synthetic fixtures only.
"""

from __future__ import annotations

import uuid

from app.models.drug_knowledge_content import DrugSideEffect
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.models.drug_knowledge_references import DrugReference, KnowledgeReferenceLink
from app.services.knowledge_repository import add_draft, build_draft
from app.services.medication_knowledge_import.references import (
    find_existing_reference,
    find_or_create_reference,
    link_reference_to_row,
)
from app.services.medication_knowledge_import.schema import ReferenceEntry


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


def _make_row(db, ingredient_id) -> DrugSideEffect:
    row = build_draft(
        DrugSideEffect,
        authored_by="tester",
        artifact_hash="a" * 64,
        drug_ingredient_id=ingredient_id,
        concept_code=f"code-{uuid.uuid4().hex[:8]}",
        label="Label",
        frequency="common",
        action_level="self_monitor",
        description="desc",
    )
    add_draft(db, row)
    return row


def _ref(**overrides) -> ReferenceEntry:
    """Defaults include a random suffix — the `db` fixture (conftest.py)
    shares one persistent SQLite database across the WHOLE test session
    (no per-test rollback), so a literal, non-unique publisher/title would
    collide with rows other tests already committed."""
    suffix = uuid.uuid4().hex[:8]
    data = {
        "publisher": f"Test Publisher {suffix}",
        "title": f"Test Title {suffix}",
        "source_type": "formulary",
        "url": f"https://example.invalid/{suffix}",
        "publication_date": "2024-01-01",
        "source_version": "1.0",
        "accessed_at": "2026-01-01",
    }
    data.update(overrides)
    return ReferenceEntry.model_validate(data)


class TestFindOrCreateReference:
    def test_creates_new_reference(self, db) -> None:
        ref_id = find_or_create_reference(db, _ref(), batch_cache={})
        db.commit()
        assert db.query(DrugReference).filter_by(id=ref_id).one_or_none() is not None

    def test_reuses_via_batch_cache_without_db_query(self, db) -> None:
        cache: dict = {}
        ref = _ref()
        id1 = find_or_create_reference(db, ref, batch_cache=cache)
        db.flush()
        id2 = find_or_create_reference(db, ref, batch_cache=cache)
        db.commit()
        assert id1 == id2
        assert db.query(DrugReference).filter_by(publisher=ref.publisher).count() == 1

    def test_reuses_via_db_across_fresh_cache(self, db) -> None:
        ref = _ref()
        id1 = find_or_create_reference(db, ref, batch_cache={})
        db.commit()
        # fresh cache — must find via DB query, not fail to reuse
        id2 = find_or_create_reference(db, ref, batch_cache={})
        db.commit()
        assert id1 == id2
        assert db.query(DrugReference).filter_by(publisher=ref.publisher).count() == 1

    def test_different_access_date_creates_new_row(self, db) -> None:
        suffix = uuid.uuid4().hex[:8]
        shared_publisher, shared_title = f"Publisher {suffix}", f"Title {suffix}"
        id1 = find_or_create_reference(
            db,
            _ref(publisher=shared_publisher, title=shared_title, accessed_at="2026-01-01"),
            batch_cache={},
        )
        id2 = find_or_create_reference(
            db,
            _ref(publisher=shared_publisher, title=shared_title, accessed_at="2026-06-01"),
            batch_cache={},
        )
        db.commit()
        assert id1 != id2
        assert (
            db.query(DrugReference)
            .filter_by(publisher=shared_publisher, title=shared_title)
            .count()
            == 2
        )

    def test_document_identifier_preferred_over_title(self, db) -> None:
        """Same document_identifier, different publisher/title -> same row."""
        doc_id = f"ISBN-{uuid.uuid4().hex[:8]}"
        id1 = find_or_create_reference(
            db,
            _ref(document_identifier=doc_id, publisher="A", title="Title A"),
            batch_cache={},
        )
        db.flush()
        id2 = find_or_create_reference(
            db,
            _ref(document_identifier=doc_id, publisher="B", title="Title B"),
            batch_cache={},
        )
        db.commit()
        assert id1 == id2
        assert db.query(DrugReference).filter_by(document_identifier=doc_id).count() == 1

    def test_no_document_identifier_never_matches_row_that_has_one(self, db) -> None:
        """A reference with document_identifier set must not be matched by
        a lookup for a reference with no document_identifier, even if
        publisher/title/publication_date/source_version/accessed_at all
        coincide."""
        shared = f"Same-{uuid.uuid4().hex[:8]}"
        id_with_doc = find_or_create_reference(
            db,
            _ref(publisher=shared, title=shared, document_identifier="ISBN-999"),
            batch_cache={},
        )
        db.commit()
        id_without_doc = find_or_create_reference(
            db,
            _ref(publisher=shared, title=shared, document_identifier=None),
            batch_cache={},
        )
        db.commit()
        assert id_with_doc != id_without_doc
        assert db.query(DrugReference).filter_by(publisher=shared, title=shared).count() == 2


class TestFindExistingReference:
    def test_returns_none_when_absent(self, db) -> None:
        assert find_existing_reference(db, _ref()) is None

    def test_returns_row_when_present(self, db) -> None:
        ref = _ref()
        ref_id = find_or_create_reference(db, ref, batch_cache={})
        db.commit()
        found = find_existing_reference(db, ref)
        assert found is not None
        assert found.id == ref_id

    def test_read_only_never_inserts(self, db) -> None:
        before = db.query(DrugReference).count()
        find_existing_reference(db, _ref())
        assert db.query(DrugReference).count() == before


class TestLinkReferenceToRow:
    def test_creates_link(self, db) -> None:
        ingredient = _make_ingredient(db)
        row = _make_row(db, ingredient.id)
        ref_id = find_or_create_reference(db, _ref(), batch_cache={})
        link_reference_to_row(db, row, ref_id)
        db.commit()
        assert db.query(KnowledgeReferenceLink).filter_by(knowledge_row_id=row.id).count() == 1

    def test_idempotent_link_creation(self, db) -> None:
        """Calling twice for the same (row, reference) must not create a
        second link — proves link_reference_to_row's own find-or-create,
        not reliance on A1a's file-level duplicate validator."""
        ingredient = _make_ingredient(db)
        row = _make_row(db, ingredient.id)
        ref_id = find_or_create_reference(db, _ref(), batch_cache={})
        link_reference_to_row(db, row, ref_id)
        link_reference_to_row(db, row, ref_id)
        db.commit()
        assert db.query(KnowledgeReferenceLink).filter_by(knowledge_row_id=row.id).count() == 1

    def test_duplicate_reference_within_file_creates_one_link(self, db) -> None:
        """Two references in the same file sharing a document_identifier
        but different publisher/title resolve to the SAME DrugReference
        row (per document-identifier-first identity) -- both linking to
        the same row must still produce exactly one link, not a duplicate
        insert attempt against uq_krl_no_duplicate_link."""
        ingredient = _make_ingredient(db)
        row = _make_row(db, ingredient.id)
        doc_id = f"ISBN-{uuid.uuid4().hex[:8]}"
        cache: dict = {}
        ref_a = _ref(document_identifier=doc_id, publisher="A", title="Title A")
        ref_b = _ref(document_identifier=doc_id, publisher="B", title="Title B")
        ref_id_a = find_or_create_reference(db, ref_a, batch_cache=cache)
        ref_id_b = find_or_create_reference(db, ref_b, batch_cache=cache)
        assert ref_id_a == ref_id_b
        link_reference_to_row(db, row, ref_id_a)
        link_reference_to_row(db, row, ref_id_b)
        db.commit()
        assert db.query(DrugReference).filter_by(document_identifier=doc_id).count() == 1
        assert db.query(KnowledgeReferenceLink).filter_by(knowledge_row_id=row.id).count() == 1
