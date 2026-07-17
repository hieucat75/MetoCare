"""Postgres integration tests for A1b: orchestrator.py against a REAL
PostgreSQL instance — partial-unique-index parity for reference dedup,
commit-ownership (a successful batch is durably visible from a separate
connection), and whole-batch rollback when a reference write hits a real
IntegrityError from the partial unique index.

SQLite unit tests (tests/test_medication_knowledge_import_orchestrator.py)
already cover the orchestrator's own logic; this file exists only for
behavior that depends on the real Postgres dialect: partial unique indexes
and genuine IntegrityError-on-flush semantics don't exist the same way on
SQLite. Runs only when POSTGRES_TEST_URL is set — same convention as
tests/integration/test_medication_k1_a1b_f1_schema_completion.py.

All rows synthetic test fixtures — never real clinical content.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
import yaml
from alembic import command
from alembic.config import Config
from app.models.drug_knowledge_content import DrugSideEffect
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.models.drug_knowledge_references import DrugReference
from app.services.medication_knowledge_import.orchestrator import import_batch
from sqlalchemy.orm import Session, sessionmaker

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if not POSTGRES_TEST_URL:
        pytest.skip(
            "POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests. "
            "Set POSTGRES_TEST_URL to a throw-away Postgres database to run these tests."
        )


def _make_alembic_config(db_url: str) -> Config:
    os.environ["MCP_DATABASE_URL"] = db_url
    from app.core.config import get_settings

    get_settings.cache_clear()

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    alembic_ini = os.path.join(backend_dir, "alembic.ini")
    cfg = Config(alembic_ini)
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    return cfg


@pytest.fixture(scope="module")
def pg_engine() -> Generator[sa.Engine, None, None]:
    _require_postgres()
    engine = sa.create_engine(POSTGRES_TEST_URL, echo=False, future=True)
    with engine.connect() as _conn:
        assert _conn.dialect.name == "postgresql"
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated_schema(pg_engine: sa.Engine) -> Generator[sa.Engine, None, None]:
    db_url = pg_engine.url.render_as_string(hide_password=False)
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, "head")
    yield pg_engine
    # Only undo this migration's own column, not the full chain — deep
    # downgrade past k1_a1b_f1_schema_complete refuses once this file's
    # synthetic drug_side_effects rows exist (F1's own dormancy guard,
    # already covered by test_medication_k1_a1b_f1_schema_completion.py).
    # This file's purpose is orchestrator.py's behavior, not migration
    # teardown depth.
    command.downgrade(cfg, "k1_a1b_f2_specialty_seed")


@pytest.fixture()
def session_factory(migrated_schema: sa.Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_schema, expire_on_commit=False)


@pytest.fixture()
def ingredient(session_factory: sessionmaker[Session]) -> dict:
    suffix = uuid.uuid4().hex[:8]
    db = session_factory()
    try:
        drug_class = DrugClass(name=f"test-class-{suffix}", required_specialties=[])
        db.add(drug_class)
        db.flush()
        name = f"test-ingredient-{suffix}"
        ingredient_row = DrugIngredient(name_inn=name, drug_class_id=drug_class.id)
        db.add(ingredient_row)
        db.commit()
        return {"id": ingredient_row.id, "name": name}
    finally:
        db.close()


def _write_file(
    tmp_path: Path,
    ingredient_name: str,
    *,
    concept_code: str,
    version: str = "1.0.0",
    title: str = "Test Title",
    url: str | None = None,
    document_identifier: str | None = None,
) -> Path:
    # PTH round-2 P1 fix: reference reuse now requires the full authored
    # artifact (including url) to match, not just F1's narrower citation
    # identity — two calls that want to share ONE reference must pass the
    # SAME explicit title AND url, not just a shared title.
    resolved_url = url if url is not None else f"https://example.invalid/{uuid.uuid4().hex[:8]}"
    reference: dict = {
        "publisher": "Test Publisher",
        "title": title,
        "source_type": "formulary",
        "url": resolved_url,
        "publication_date": "2024-01-01",
        "source_version": "1.0",
        "accessed_at": "2026-01-01",
    }
    if document_identifier is not None:
        reference["document_identifier"] = document_identifier
    data = {
        "metadata": {
            "knowledge_type": "side_effect",
            "medication_identity": {"name_inn": ingredient_name},
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
            "evidence_level": "moderate",
            "reviewed_at": "2026-01-01",
            "authored_by": "test-author",
            "ai_generated": False,
            "specialty_codes": [],
        },
        "disclaimer": {"acknowledged": True},
    }
    path = tmp_path / f"{concept_code}-{uuid.uuid4().hex[:8]}.yaml"
    path.write_text(yaml.dump(data))
    return path


class TestReferenceDedupParityOnRealIndex:
    """Proves find_or_create_reference's ORM query matches the real
    partial unique index exactly — a cross-session reuse (not just a
    batch-local cache hit) succeeds without ever tripping the constraint."""

    def test_cross_session_reuse_of_committed_reference(
        self, session_factory, ingredient, tmp_path
    ) -> None:
        shared_title = f"Shared {uuid.uuid4().hex[:8]}"
        shared_url = f"https://example.invalid/{uuid.uuid4().hex[:8]}"
        path1 = _write_file(
            tmp_path, ingredient["name"], concept_code="pg_ref_a", title=shared_title, url=shared_url
        )
        db1 = session_factory()
        result1 = import_batch(db1, [path1])
        db1.close()
        assert result1.success, result1.errors

        # Fresh session, fresh batch-local cache — must reuse via the real
        # DB query against the partial unique index, not fail or duplicate.
        path2 = _write_file(
            tmp_path, ingredient["name"], concept_code="pg_ref_b", title=shared_title, url=shared_url
        )
        db2 = session_factory()
        result2 = import_batch(db2, [path2])
        db2.close()
        assert result2.success, result2.errors

        verify_db = session_factory()
        try:
            refs = verify_db.query(DrugReference).filter_by(title=shared_title).all()
            assert len(refs) == 1, "must reuse the existing committed reference, not duplicate it"
        finally:
            verify_db.close()


class TestReferenceIdentityMetadataConflict:
    """PTH round-2 P1 fix, on the real Postgres partial unique index: a
    version bump that changes an authored reference field (url) while
    keeping the same citation identity must fail the whole batch closed,
    never silently link to the existing row's stale metadata."""

    def test_version_bump_same_document_identifier_different_url_fails_closed(
        self, session_factory, ingredient, tmp_path
    ) -> None:
        doc_id = f"ISBN-{uuid.uuid4().hex[:8]}"
        path1 = _write_file(
            tmp_path,
            ingredient["name"],
            concept_code="pg_ref_conflict",
            version="1.0.0",
            document_identifier=doc_id,
            url="https://example.invalid/original",
        )
        db1 = session_factory()
        assert import_batch(db1, [path1]).success
        db1.close()

        path2 = _write_file(
            tmp_path,
            ingredient["name"],
            concept_code="pg_ref_conflict",
            version="2.0.0",
            document_identifier=doc_id,
            url="https://example.invalid/changed",
        )
        db2 = session_factory()
        result = import_batch(db2, [path2])
        db2.close()
        assert not result.success
        assert "REFERENCE_IDENTITY_METADATA_CONFLICT" in result.errors[0].message

        verify_db = session_factory()
        try:
            rows = (
                verify_db.query(DrugSideEffect)
                .filter_by(concept_code="pg_ref_conflict")
                .all()
            )
            assert len(rows) == 1, "no 2nd draft row must survive the conflict"
            assert (
                verify_db.query(DrugReference).filter_by(document_identifier=doc_id).count() == 1
            )
        finally:
            verify_db.close()


class TestCommitOwnership:
    """A successful batch's writes must be durably committed — visible from
    a BRAND NEW connection/session, not merely visible within the same
    session's own uncommitted transaction."""

    def test_successful_batch_is_durable_across_new_connection(
        self, session_factory, ingredient, tmp_path
    ) -> None:
        path = _write_file(tmp_path, ingredient["name"], concept_code="pg_durable")
        db = session_factory()
        result = import_batch(db, [path])
        db.close()
        assert result.success, result.errors

        fresh_db = session_factory()
        try:
            row = (
                fresh_db.query(DrugSideEffect)
                .filter_by(concept_code="pg_durable")
                .one_or_none()
            )
            assert row is not None, "committed row must be visible from an entirely new connection"
            assert row.artifact_hash is not None
        finally:
            fresh_db.close()

    def test_failed_batch_leaves_zero_rows_from_new_connection(
        self, session_factory, ingredient, tmp_path
    ) -> None:
        invalid_path = tmp_path / "broken.yaml"
        invalid_path.write_text("not: [valid, yaml: structure")
        valid_path = _write_file(tmp_path, ingredient["name"], concept_code="pg_never_written")

        db = session_factory()
        result = import_batch(db, [valid_path, invalid_path])
        db.close()
        assert not result.success

        fresh_db = session_factory()
        try:
            count = (
                fresh_db.query(DrugSideEffect).filter_by(concept_code="pg_never_written").count()
            )
            assert count == 0
        finally:
            fresh_db.close()


class TestReferenceIntegrityViolationRollsBackWholeBatch:
    """Deterministically simulates the real concurrent-race scenario
    references.py's own docstring documents: a reference with this EXACT
    identity has already been committed by a separate connection, but
    find_or_create_reference's own read (a genuinely concurrent read under
    READ COMMITTED would behave identically) reports "not found" — forcing
    it down the INSERT path, where the real partial unique index rejects
    it. Proves the whole batch — including this plan's own knowledge row —
    rolls back, not just the reference write."""

    def test_reference_integrity_violation_rolls_back_whole_batch(
        self, session_factory, ingredient, tmp_path, monkeypatch
    ) -> None:
        shared_title = f"Prewritten {uuid.uuid4().hex[:8]}"
        setup_db = session_factory()
        try:
            pre_existing = DrugReference(
                publisher="Test Publisher",
                title=shared_title,
                source_type="formulary",
                url="https://example.invalid/pre-existing",
                publication_date=dt.date(2024, 1, 1),
                source_version="1.0",
                accessed_at=dt.date(2026, 1, 1),
            )
            setup_db.add(pre_existing)
            setup_db.commit()
        finally:
            setup_db.close()

        monkeypatch.setattr(
            "app.services.medication_knowledge_import.references.find_existing_reference",
            lambda db, ref: None,
        )

        path = _write_file(
            tmp_path, ingredient["name"], concept_code="pg_integrity_race", title=shared_title
        )
        db = session_factory()
        result = import_batch(db, [path])
        db.close()

        assert not result.success
        assert result.errors, "a real IntegrityError must surface as a BatchResult failure"

        verify_db = session_factory()
        try:
            row_count = (
                verify_db.query(DrugSideEffect)
                .filter_by(concept_code="pg_integrity_race")
                .count()
            )
            assert row_count == 0, (
                "the knowledge row must roll back too — whole-batch, not just the "
                "failed reference insert"
            )
            ref_count = verify_db.query(DrugReference).filter_by(title=shared_title).count()
            assert ref_count == 1, "no duplicate reference row should exist after rollback"
        finally:
            verify_db.close()
