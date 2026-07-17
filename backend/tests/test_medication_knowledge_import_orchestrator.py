"""Unit tests for A1b: orchestrator.py (import_batch, the batch entrypoint).

Runs against the shared SQLite test DB via the existing `db`-fixture-style
SessionLocal() (tests/conftest.py sets up the schema at session scope).
import_batch requires a *fresh* Session per call (this is itself an
invariant under test), so these tests open their own SessionLocal()
instances rather than using the shared `db` fixture directly for the
import_batch call itself.

Synthetic fixtures only — never real clinical content.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
import yaml
from app.core.database import SessionLocal
from app.models.drug_knowledge_content import DrugSideEffect
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.models.drug_knowledge_governance import ClinicalSpecialty
from app.models.drug_knowledge_references import DrugReference, KnowledgeReferenceLink
from app.services.medication_knowledge_import.orchestrator import import_batch


@pytest.fixture
def ingredient_name() -> str:
    return f"test-ingredient-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _seed_ingredient(db, ingredient_name) -> None:
    drug_class = DrugClass(name=f"test-class-{uuid.uuid4().hex[:8]}", required_specialties=[])
    db.add(drug_class)
    db.flush()
    ingredient = DrugIngredient(name_inn=ingredient_name, drug_class_id=drug_class.id)
    db.add(ingredient)
    db.commit()


def _write_file(
    tmp_path: Path,
    ingredient_name: str,
    *,
    concept_code: str,
    version: str = "1.0.0",
    title: str = "Test Title",
    url: str | None = None,
    reviewed_at: str = "2026-01-01",
    specialty_codes: list[str] | None = None,
) -> Path:
    # A random per-call default (unless the caller pins one explicitly) —
    # since artifact_hash now covers url (PTH round-1 P1 fix), two calls
    # that want to produce a genuinely IDENTICAL artifact must pass the
    # SAME explicit url; otherwise each file is a distinct new artifact.
    resolved_url = url if url is not None else f"https://example.invalid/{uuid.uuid4().hex[:8]}"
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
        "references": [
            {
                "publisher": "Test Publisher",
                "title": title,
                "source_type": "formulary",
                "url": resolved_url,
                "publication_date": "2024-01-01",
                "source_version": "1.0",
                "accessed_at": "2026-01-01",
            }
        ],
        "review_metadata": {
            "source": "Test Source",
            "version": version,
            "evidence_level": "moderate",
            "reviewed_at": reviewed_at,
            "authored_by": "test-author",
            "ai_generated": False,
            "specialty_codes": specialty_codes or [],
        },
        "disclaimer": {"acknowledged": True},
    }
    path = tmp_path / f"{concept_code}-{uuid.uuid4().hex[:8]}.yaml"
    path.write_text(yaml.dump(data))
    return path


class TestBasicImport:
    def test_valid_file_creates_one_draft(self, db, tmp_path, ingredient_name) -> None:
        path = _write_file(tmp_path, ingredient_name, concept_code="nausea")
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path])
        fresh_db.close()
        assert result.success, result.errors
        assert len(result.written) == 1

        row = db.query(DrugSideEffect).filter_by(id=result.written[0].row_id).one()
        assert row.status == "draft"
        assert row.artifact_hash is not None
        assert len(row.artifact_hash) == 64

    def test_reference_is_persisted_and_linked(self, db, tmp_path, ingredient_name) -> None:
        path = _write_file(tmp_path, ingredient_name, concept_code="dizziness")
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path])
        fresh_db.close()
        assert result.success, result.errors

        row_id = result.written[0].row_id
        links = db.query(KnowledgeReferenceLink).filter_by(knowledge_row_id=row_id).all()
        assert len(links) == 1
        assert (
            db.query(DrugReference).filter_by(id=links[0].drug_reference_id).one_or_none()
            is not None
        )


class TestIdempotency:
    def test_reimporting_identical_file_is_no_op(self, db, tmp_path, ingredient_name) -> None:
        path = _write_file(tmp_path, ingredient_name, concept_code="fatigue")
        db1 = SessionLocal()
        result1 = import_batch(db1, [path])
        db1.close()
        assert result1.success

        db2 = SessionLocal()
        result2 = import_batch(db2, [path])
        db2.close()
        assert result2.success
        assert len(result2.written) == 0, "NO_OP must not write a new row"

        count = db.query(DrugSideEffect).filter_by(concept_code="fatigue").count()
        assert count == 1

    def test_reference_change_under_same_version_is_rejected(
        self, db, tmp_path, ingredient_name
    ) -> None:
        """The original PTH-reported bug: changing a reference while
        keeping version+content the same must be REJECT_VERSION_CONFLICT,
        not NO_OP."""
        path1 = _write_file(
            tmp_path, ingredient_name, concept_code="headache", title="Original Title"
        )
        db1 = SessionLocal()
        result1 = import_batch(db1, [path1])
        db1.close()
        assert result1.success

        path2 = _write_file(
            tmp_path, ingredient_name, concept_code="headache", title="Changed Title"
        )
        db2 = SessionLocal()
        result2 = import_batch(db2, [path2])
        db2.close()
        assert not result2.success
        assert "conflict" in result2.errors[0].message.lower()

        count = db.query(DrugSideEffect).filter_by(concept_code="headache").count()
        assert count == 1, "the rejected import must not have written anything"

    def test_provenance_change_under_same_version_is_rejected(
        self, db, tmp_path, ingredient_name
    ) -> None:
        path1 = _write_file(
            tmp_path, ingredient_name, concept_code="tremor", reviewed_at="2026-01-01"
        )
        db1 = SessionLocal()
        assert import_batch(db1, [path1]).success
        db1.close()

        path2 = _write_file(
            tmp_path, ingredient_name, concept_code="tremor", reviewed_at="2026-06-01"
        )
        db2 = SessionLocal()
        result2 = import_batch(db2, [path2])
        db2.close()
        assert not result2.success
        assert "conflict" in result2.errors[0].message.lower()

    def test_new_version_same_content_new_reference_persists(
        self, db, tmp_path, ingredient_name
    ) -> None:
        path1 = _write_file(
            tmp_path, ingredient_name, concept_code="rash", version="1.0.0", title="Ref A"
        )
        db1 = SessionLocal()
        assert import_batch(db1, [path1]).success
        db1.close()

        path2 = _write_file(
            tmp_path, ingredient_name, concept_code="rash", version="2.0.0", title="Ref B"
        )
        db2 = SessionLocal()
        result2 = import_batch(db2, [path2])
        db2.close()
        assert result2.success, result2.errors
        assert len(result2.written) == 1

        rows = db.query(DrugSideEffect).filter_by(concept_code="rash").all()
        assert len(rows) == 2
        new_row = next(r for r in rows if r.version == "2.0.0")
        links = db.query(KnowledgeReferenceLink).filter_by(knowledge_row_id=new_row.id).all()
        assert len(links) == 1


class TestBatchLocalResolution:
    def test_two_files_same_new_business_key_identical_no_op(
        self, db, tmp_path, ingredient_name
    ) -> None:
        # Same explicit url on both — a truly identical artifact, not just
        # a matching title (url is now part of the hash, PTH round-1 P1 fix).
        shared_url = f"https://example.invalid/{uuid.uuid4().hex[:8]}"
        path1 = _write_file(
            tmp_path, ingredient_name, concept_code="itch", title="Same Ref", url=shared_url
        )
        path2 = _write_file(
            tmp_path, ingredient_name, concept_code="itch", title="Same Ref", url=shared_url
        )
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path1, path2])
        fresh_db.close()
        assert result.success, result.errors
        assert (
            len(result.written) == 1
        ), "second identical file must resolve NO_OP against the first"

    def test_two_files_same_new_business_key_conflicting_rejects_whole_batch(
        self, db, tmp_path, ingredient_name
    ) -> None:
        path1 = _write_file(tmp_path, ingredient_name, concept_code="swelling", title="Ref A")
        path2 = _write_file(tmp_path, ingredient_name, concept_code="swelling", title="Ref B")
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path1, path2])
        fresh_db.close()
        assert not result.success
        count = db.query(DrugSideEffect).filter_by(concept_code="swelling").count()
        assert count == 0, "whole batch must roll back, including file 1"


class TestFreshSessionPrecondition:
    def test_session_with_pending_new_raises(self, db, tmp_path, ingredient_name) -> None:
        path = _write_file(tmp_path, ingredient_name, concept_code="bruising")
        fresh_db = SessionLocal()
        fresh_db.add(DrugClass(name="pending-not-flushed", required_specialties=[]))
        with pytest.raises(ValueError, match="fresh Session"):
            import_batch(fresh_db, [path])
        fresh_db.rollback()
        fresh_db.close()

    def test_session_with_bare_read_only_transaction_raises(
        self, db, tmp_path, ingredient_name
    ) -> None:
        """Distinguishes the tightened db.in_transaction() check from a
        weaker db.new/db.dirty check — a session that has only executed a
        read has no pending ORM changes but IS in a transaction."""
        path = _write_file(tmp_path, ingredient_name, concept_code="swelling2")
        fresh_db = SessionLocal()
        fresh_db.execute(sa.text("SELECT 1"))
        assert fresh_db.in_transaction()
        with pytest.raises(ValueError, match="fresh Session"):
            import_batch(fresh_db, [path])
        fresh_db.rollback()
        fresh_db.close()


class TestDryRun:
    def test_dry_run_writes_nothing(self, db, tmp_path, ingredient_name) -> None:
        path = _write_file(tmp_path, ingredient_name, concept_code="numbness")
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path], dry_run=True)
        fresh_db.close()
        assert result.success
        assert result.dry_run
        assert result.planned is not None
        assert len(result.planned) == 1
        count = db.query(DrugSideEffect).filter_by(concept_code="numbness").count()
        assert count == 0

    def test_real_run_after_dry_run_still_succeeds(self, db, tmp_path, ingredient_name) -> None:
        path = _write_file(tmp_path, ingredient_name, concept_code="cramping")
        db1 = SessionLocal()
        import_batch(db1, [path], dry_run=True)
        db1.close()

        db2 = SessionLocal()
        result = import_batch(db2, [path])
        db2.close()
        assert result.success
        assert len(result.written) == 1

    def test_dry_run_reference_cache_matches_real_run(
        self, db, tmp_path, ingredient_name
    ) -> None:
        shared_title = f"Shared {uuid.uuid4().hex[:8]}"
        path1 = _write_file(
            tmp_path, ingredient_name, concept_code="chills_a", title=shared_title
        )
        path2 = _write_file(
            tmp_path, ingredient_name, concept_code="chills_b", title=shared_title
        )

        db1 = SessionLocal()
        dry_result = import_batch(db1, [path1, path2], dry_run=True)
        db1.close()
        assert dry_result.success
        assert dry_result.planned is not None
        assert len(dry_result.planned) == 2
        planned_by_path = {p.path: p for p in dry_result.planned}
        first, second = planned_by_path[path1], planned_by_path[path2]
        assert (first.references_created, first.references_reused) == (1, 0), (
            "the first file to cite a brand-new reference must report it as created"
        )
        assert (second.references_created, second.references_reused) == (0, 1), (
            "the second file citing the SAME new reference must report reuse, "
            "not a second create"
        )

        db2 = SessionLocal()
        real_result = import_batch(db2, [path1, path2])
        db2.close()
        assert real_result.success
        assert len(real_result.written) == 2
        refs = db.query(DrugReference).filter_by(title=shared_title).all()
        assert len(refs) == 1, (
            "both files cite the same new reference — only one row, real run "
            "must match dry-run's plan"
        )

    def test_dry_run_reports_zero_created_when_reference_already_committed(
        self, db, tmp_path, ingredient_name
    ) -> None:
        shared_title = f"Existing {uuid.uuid4().hex[:8]}"
        path1 = _write_file(tmp_path, ingredient_name, concept_code="dryrun_a", title=shared_title)
        db1 = SessionLocal()
        assert import_batch(db1, [path1]).success
        db1.close()

        path2 = _write_file(tmp_path, ingredient_name, concept_code="dryrun_b", title=shared_title)
        db2 = SessionLocal()
        dry_result = import_batch(db2, [path2], dry_run=True)
        db2.close()
        assert dry_result.success
        assert dry_result.planned[0].references_created == 0
        assert dry_result.planned[0].references_reused == 1


class TestWholeBatchRollback:
    def test_malformed_file_rolls_back_valid_sibling(
        self, db, tmp_path, ingredient_name
    ) -> None:
        valid_path = _write_file(tmp_path, ingredient_name, concept_code="valid_effect")
        invalid_path = tmp_path / "broken.yaml"
        invalid_path.write_text("not: [valid, yaml: structure")

        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [valid_path, invalid_path])
        fresh_db.close()
        assert not result.success
        count = db.query(DrugSideEffect).filter_by(concept_code="valid_effect").count()
        assert count == 0

    def test_unknown_specialty_code_rejects_batch(self, db, tmp_path, ingredient_name) -> None:
        path = _write_file(
            tmp_path,
            ingredient_name,
            concept_code="specialty_test",
            specialty_codes=["not-a-real-specialty"],
        )
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path])
        fresh_db.close()
        assert not result.success
        assert "specialty" in result.errors[0].message.lower()

    def test_unknown_medication_identity_rejects_batch(self, db, tmp_path) -> None:
        path = _write_file(tmp_path, "does-not-exist-ingredient", concept_code="ghost_effect")
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path])
        fresh_db.close()
        assert not result.success


class TestMultiRowSameVersionResolution:
    def test_two_existing_rows_same_version_different_hash_always_rejects(
        self, db, tmp_path, ingredient_name
    ) -> None:
        """No unique constraint prevents two draft rows sharing the same
        business key + version (append-only schema; a real concurrent
        import race can produce this). resolve_version_action must reject
        regardless of DB query ordering — never silently NO_OP just
        because one of the two conflicting rows happens to be read first."""
        from app.services.knowledge_repository import add_draft, build_draft

        ingredient = db.query(DrugIngredient).filter_by(name_inn=ingredient_name).one()
        for hash_value in ("a" * 64, "b" * 64):
            row = build_draft(
                DrugSideEffect,
                authored_by="tester",
                artifact_hash=hash_value,
                drug_ingredient_id=ingredient.id,
                concept_code="dup_version_effect",
                label="Label",
                frequency="common",
                action_level="self_monitor",
                description="desc",
                version="1.0.0",
            )
            add_draft(db, row)
        db.commit()

        path = _write_file(
            tmp_path, ingredient_name, concept_code="dup_version_effect", version="1.0.0"
        )
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path])
        fresh_db.close()
        assert not result.success
        assert "conflict" in result.errors[0].message.lower()

        count = (
            db.query(DrugSideEffect).filter_by(concept_code="dup_version_effect").count()
        )
        assert count == 2, "the pre-existing conflicting pair must be untouched, no 3rd row added"


class TestZeroApprovedRows:
    @pytest.mark.parametrize(
        "model_cls_name",
        [
            "DrugUsage",
            "DrugPatientEducation",
            "DrugSideEffect",
            "DrugMonitoring",
            "DrugContraindication",
        ],
    )
    def test_zero_approved_rows_exist_anywhere(self, db, model_cls_name) -> None:
        import app.models.drug_knowledge_content as content_models

        model_cls = getattr(content_models, model_cls_name)
        assert db.query(model_cls).filter_by(status="approved").count() == 0


class TestSpecialtyValidationFromDB:
    """Specialty codes go through two gates: validators.py's fixed
    ALLOWED_SPECIALTY_CODES allowlist (file-structure check, Phase 1, no DB)
    THEN provenance.check_specialty_exists (DB-existence + is_active check).
    A code must clear both — these tests use "cardiology" (in the fixed
    allowlist) so they isolate the DB-existence gate specifically."""

    def test_active_specialty_code_accepted(self, db, tmp_path, ingredient_name) -> None:
        code = "cardiology"
        existing = db.query(ClinicalSpecialty).filter_by(code=code).one_or_none()
        if existing is None:
            db.add(
                ClinicalSpecialty(
                    code=code, display_name_vi="x", display_name_en="x", is_active=True
                )
            )
        else:
            existing.is_active = True
        db.commit()
        path = _write_file(
            tmp_path, ingredient_name, concept_code="specialty_ok", specialty_codes=[code]
        )
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path])
        fresh_db.close()
        assert result.success, result.errors

    def test_inactive_specialty_code_rejected_at_db_level(
        self, db, tmp_path, ingredient_name
    ) -> None:
        code = "nephrology"
        existing = db.query(ClinicalSpecialty).filter_by(code=code).one_or_none()
        if existing is None:
            db.add(
                ClinicalSpecialty(
                    code=code, display_name_vi="x", display_name_en="x", is_active=False
                )
            )
        else:
            existing.is_active = False
        db.commit()
        path = _write_file(
            tmp_path, ingredient_name, concept_code="specialty_inactive", specialty_codes=[code]
        )
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path])
        fresh_db.close()
        assert not result.success


class TestLegacyArtifactHashFailsClosed:
    def test_legacy_null_hash_non_retired_row_blocks_batch(
        self, db, tmp_path, ingredient_name
    ) -> None:
        from app.services.knowledge_repository import add_draft, build_draft

        ingredient = db.query(DrugIngredient).filter_by(name_inn=ingredient_name).one()
        legacy_row = build_draft(
            DrugSideEffect,
            authored_by="legacy-caller",
            drug_ingredient_id=ingredient.id,
            concept_code="legacy_effect",
            label="Label",
            frequency="common",
            action_level="self_monitor",
            description="desc",
            version="1.0.0",
        )
        add_draft(db, legacy_row)
        db.commit()
        assert legacy_row.artifact_hash is None

        path = _write_file(
            tmp_path, ingredient_name, concept_code="legacy_effect", version="2.0.0"
        )
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path])
        fresh_db.close()
        assert not result.success
        assert "LEGACY_ARTIFACT_HASH_UNAVAILABLE" in result.errors[0].message

    def test_legacy_null_hash_retired_row_does_not_block(
        self, db, tmp_path, ingredient_name
    ) -> None:
        from app.services.knowledge_repository import add_draft, build_draft

        ingredient = db.query(DrugIngredient).filter_by(name_inn=ingredient_name).one()
        legacy_row = build_draft(
            DrugSideEffect,
            authored_by="legacy-caller",
            drug_ingredient_id=ingredient.id,
            concept_code="legacy_effect_retired",
            label="Label",
            frequency="common",
            action_level="self_monitor",
            description="desc",
            version="1.0.0",
        )
        legacy_row.status = "retired"
        add_draft(db, legacy_row)
        db.commit()

        path = _write_file(
            tmp_path, ingredient_name, concept_code="legacy_effect_retired", version="2.0.0"
        )
        fresh_db = SessionLocal()
        result = import_batch(fresh_db, [path])
        fresh_db.close()
        assert result.success, result.errors
