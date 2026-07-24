"""PostgreSQL integration tests for K2 Slice 1 (read-only medication
knowledge retrieval) against a REAL PostgreSQL instance, exercised through
the full FastAPI HTTP stack (TestClient) — not just the service layer.

Why this file exists separately from the SQLite route tests
(tests/test_medication_knowledge_routes.py, 50 tests): this is a targeted
subset proving the same guarantees hold under a real Postgres engine and
against the actual migration history (`alembic upgrade head`), not a
SQLite-approximated schema. Gate 3 of the K2 Slice 1 pre-merge checklist.

Runs only when POSTGRES_TEST_URL is set — same convention as
tests/integration/test_medication_k1_6_knowledge_retrieval_postgres.py.

IMPORTANT: `tests/conftest.py` is always loaded by pytest before any test
file, even when this file is targeted directly, and it unconditionally
points `MCP_DATABASE_URL` at a throwaway SQLite file before importing
`app.main` — so `app.core.database`'s module-level engine is permanently
SQLite-bound before this file's own code ever runs. Rebinding that global
is not attempted here. Instead, the FastAPI `get_session` dependency is
overridden directly (`app.dependency_overrides`, the standard pattern for
swapping test databases) so `TestClient(app)` talks to Postgres while every
other test file in the suite keeps using SQLite, independent of import
order. The `POSTGRES_TEST_URL`/`MCP_DATABASE_URL` lines below still matter
for Alembic (which reads `MCP_DATABASE_URL` via `get_settings()` inside
`alembic/env.py`), just not for the app's own request-time DB session.

All rows synthetic test fixtures — never real clinical content.
"""

from __future__ import annotations

import os

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")

if POSTGRES_TEST_URL:
    os.environ["MCP_DATABASE_URL"] = POSTGRES_TEST_URL

import datetime as dt
import uuid
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if not POSTGRES_TEST_URL:
        pytest.skip(
            "POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests. "
            "Set POSTGRES_TEST_URL to a throw-away Postgres database to run these tests."
        )


def _make_alembic_config(db_url: str) -> Config:
    # alembic/env.py:25 overwrites its own sqlalchemy.url with
    # get_settings().database_url — it does NOT read the value set on this
    # Config object below. get_settings() is lru_cache'd and tests/conftest.py
    # (always loaded first) already called it once with MCP_DATABASE_URL
    # pointed at SQLite, so the cache must be cleared after re-pointing the
    # env var, or env.py would silently run migrations against SQLite —
    # same pattern as test_medication_k1_6_knowledge_retrieval_postgres.py's
    # own _make_alembic_config.
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
    """Upgrades to head (no new migration from K2 Slice 1 — head is
    unchanged) and downgrades back to the same pre-K1.6 baseline the
    existing K1.6 Postgres test leaves the shared `mcp_test` DB at, so this
    file and that one are safely re-runnable against each other."""
    db_url = pg_engine.url.render_as_string(hide_password=False)
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, "head")
    yield pg_engine
    command.downgrade(cfg, "k1_a1b_f2_specialty_seed")


# ---------------------------------------------------------------------------
# app.* imports below this line only — MCP_DATABASE_URL is already set above.
# ---------------------------------------------------------------------------

from app.api.deps import get_session  # noqa: E402
from app.core.ratelimit import get_rate_limiter  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402
from app.models.care import Doctor  # noqa: E402
from app.models.clinical import Medication  # noqa: E402
from app.models.consultation import DoctorVerificationStatus  # noqa: E402
from app.models.drug_knowledge_content import DrugSideEffect  # noqa: E402
from app.models.drug_knowledge_core import (  # noqa: E402
    DrugClass,
    DrugIngredient,
    DrugProduct,
    DrugProductIngredient,
)
from app.models.drug_knowledge_references import DrugReference, KnowledgeReferenceLink  # noqa: E402
from app.models.governance import AuditLog  # noqa: E402
from app.models.patient import PatientProfile  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services import knowledge_repository as repo  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

# `tests/conftest.py` (always loaded first by pytest, even when this file is
# targeted directly) unconditionally sets MCP_DATABASE_URL to a throwaway
# SQLite file and imports app.main before this module's own top-of-file
# MCP_DATABASE_URL override ever runs — so `app.core.database.engine` is
# permanently bound to SQLite by the time we get here, regardless of the
# module-level override above. Rebinding that global is not an option.
# Instead, override the `get_session` FastAPI dependency directly — the
# standard, documented pattern for swapping a test database
# (https://fastapi.tiangolo.com/advanced/testing-database/) — so
# `TestClient(app)` reads/writes Postgres while every other test file in
# this suite keeps using SQLite, completely independent of import order.


@pytest.fixture(scope="module")
def pg_sessionmaker(migrated_schema) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_schema, autoflush=False, autocommit=False, future=True)


@pytest.fixture(scope="module", autouse=True)
def _override_get_session(pg_sessionmaker: sessionmaker[Session]) -> Generator[None, None, None]:
    def _pg_get_session() -> Generator[Session, None, None]:
        session = pg_sessionmaker()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _pg_get_session
    yield
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture()
def db(pg_sessionmaker: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = pg_sessionmaker()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _enable_flag(monkeypatch):
    monkeypatch.setenv("FEATURE_MEDICATION_KNOWLEDGE_RETRIEVAL", "true")


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    get_rate_limiter().reset()
    yield
    get_rate_limiter().reset()


def _mint(user_id: str, role: str) -> dict[str, str]:
    token = create_access_token(subject=user_id, role=role)
    return {"Authorization": f"Bearer {token}"}


def _make_ingredient(db) -> DrugIngredient:
    suffix = uuid.uuid4().hex[:8]
    drug_class = DrugClass(name=f"k2-pg-class-{suffix}", required_specialties=[])
    db.add(drug_class)
    db.flush()
    ingredient = DrugIngredient(name_inn=f"k2-pg-ingredient-{suffix}", drug_class_id=drug_class.id)
    db.add(ingredient)
    db.commit()
    db.refresh(ingredient)
    return ingredient


def _approval_provenance_fields(**overrides) -> dict[str, object]:
    # evidence_level default is "expert_consensus" (16 chars), NOT
    # "clinical_guideline" (18 chars) — deliberately. Postgres genuinely
    # enforces `evidence_level VARCHAR(16)` (SQLite does not enforce
    # VARCHAR length at all, which is why 50/50 SQLite tests and the
    # earlier code review never caught this): "clinical_guideline" (18
    # chars) and "peer_reviewed_literature" (24 chars) — both locked,
    # valid ADR-15 §D vocabulary values — cannot be persisted in the
    # current schema on Postgres. This is a pre-existing K1/ADR-13 schema
    # defect (`KnowledgeLifecycleMixin.evidence_level`, column predates
    # ADR-15's vocabulary lock), not a K2 Slice 1 bug, and is explicitly
    # NOT fixed here — fixing it requires a migration, out of Slice 1's
    # authorized scope. Reported in the Gate 3 findings instead. Every
    # value below is a genuinely valid, ADR-15-locked value that also
    # happens to fit the current column width, so these tests still prove
    # Slice 1's own read-path logic (fail-soft, provenance, exclusion)
    # under real Postgres — they do not, and are not meant to, validate
    # the vocabulary/column-width mismatch itself.
    fields = dict(
        source="Synthetic Test Source",
        version="1.0",
        evidence_level="expert_consensus",
        reviewed_by="reviewer-1",
        last_reviewed_at=dt.datetime.now(dt.UTC),
    )
    fields.update(overrides)
    return fields


def _approved_side_effect(db, ingredient_id: str, **overrides) -> DrugSideEffect:
    fields = dict(
        drug_ingredient_id=ingredient_id,
        concept_code="nausea",
        label="Nausea",
        frequency="common",
        action_level="self_monitor",
        description="synthetic test description — never staged/production",
        **_approval_provenance_fields(),
    )
    fields.update(overrides)
    row = repo.create_draft(db, DrugSideEffect, authored_by="author-1", **fields)
    repo.submit_for_review(db, row, actor_user_id="author-1")
    return repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role="internal_admin")


def _seed_patient(db) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"k2-pg-patient-{suffix}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Test Patient",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Test Patient")
    db.add(profile)
    db.commit()
    return {"user_id": user.id, "patient_id": profile.id}


def _seed_doctor(
    db, *, verification_status: str = DoctorVerificationStatus.VERIFIED, is_active: bool = True
) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"k2-pg-doctor-{suffix}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Test Doctor",
    )
    db.add(user)
    db.flush()
    doctor = Doctor(
        user_id=user.id,
        full_name="Test Doctor",
        verification_status=verification_status,
        is_active=is_active,
    )
    db.add(doctor)
    db.commit()
    return {"user_id": user.id, "doctor_id": doctor.id}


def _seed_product(db, ingredient_id: str) -> DrugProduct:
    product = DrugProduct(display_name=f"K2 PG Test Product {uuid.uuid4().hex[:6]}")
    db.add(product)
    db.flush()
    db.add(
        DrugProductIngredient(
            drug_product_id=product.id, drug_ingredient_id=ingredient_id, is_primary=True
        )
    )
    db.commit()
    return product


def _seed_medication(db, patient_id: str, drug_product_id: str | None) -> Medication:
    medication = Medication(patient_id=patient_id, name="K2 PG Test Med", drug_product_id=drug_product_id)
    db.add(medication)
    db.commit()
    return medication


def _knowledge_row_count(db) -> int:
    return db.query(DrugSideEffect).count()


class TestPostgresPatientSuccess:
    def test_patient_owned_medication_returns_200(self, db, client):
        ingredient = _make_ingredient(db)
        _approved_side_effect(db, ingredient.id)
        product = _seed_product(db, ingredient.id)
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], product.id)

        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.status_code == 200
        assert len(resp.json()["side_effects"]) == 1


class TestPostgresAntiEnumeration:
    def test_not_owned_medication_returns_404(self, db, client):
        owner = _seed_patient(db)
        other = _seed_patient(db)
        med = _seed_medication(db, owner["patient_id"], None)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(other["user_id"], "patient"),
        )
        assert resp.status_code == 404

    def test_nonexistent_medication_returns_404(self, db, client):
        patient = _seed_patient(db)
        resp = client.get(
            f"/api/v1/patient/medications/{uuid.uuid4()}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.status_code == 404

    def test_soft_deleted_medication_returns_404(self, db, client):
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        med.deleted_at = dt.datetime.now(dt.UTC)
        db.commit()
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.status_code == 404


class TestPostgresDoctorVerification:
    def test_verified_and_active_doctor_returns_200(self, db, client):
        ingredient = _make_ingredient(db)
        doctor = _seed_doctor(db, verification_status=DoctorVerificationStatus.VERIFIED, is_active=True)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert resp.status_code == 200

    def test_verified_but_inactive_doctor_returns_403(self, db, client):
        """Hardened 2026-07-23 — require_verified_doctor now also checks
        is_active, matching consultation.py/consultation_access.py."""
        ingredient = _make_ingredient(db)
        doctor = _seed_doctor(
            db, verification_status=DoctorVerificationStatus.VERIFIED, is_active=False
        )
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert resp.status_code == 403

    def test_pending_verification_doctor_returns_403(self, db, client):
        ingredient = _make_ingredient(db)
        doctor = _seed_doctor(db, verification_status=DoctorVerificationStatus.PENDING_VERIFICATION)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert resp.status_code == 403

    def test_doctor_role_with_no_linked_doctor_row_returns_403(self, db, client):
        ingredient = _make_ingredient(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(str(uuid.uuid4()), "doctor"),
        )
        assert resp.status_code == 403


class TestPostgresProvenance:
    def test_reference_loading(self, db, client):
        ingredient = _make_ingredient(db)
        row = _approved_side_effect(db, ingredient.id)
        ref = DrugReference(
            publisher="VIDAL Vietnam",
            title="Metformin",
            source_type="product_label",
            document_identifier=f"K2PG-{uuid.uuid4().hex[:8]}",
            publication_date=dt.date(2026, 1, 15),
            source_version="2026.1",
            accessed_at=dt.date(2026, 1, 20),
        )
        db.add(ref)
        db.flush()
        db.add(
            KnowledgeReferenceLink(
                knowledge_table="drug_side_effects", knowledge_row_id=row.id, drug_reference_id=ref.id
            )
        )
        db.commit()
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        references = resp.json()["side_effects"][0]["references"]
        assert len(references) == 1
        assert references[0]["publisher"] == "VIDAL Vietnam"


class TestPostgresVocabularyFailSoft:
    def test_invalid_evidence_level_omitted(self, db, client):
        ingredient = _make_ingredient(db)
        # "bad_value" (9 chars) — deliberately NOT one of ADR-15's 6 locked
        # values, but short enough to fit VARCHAR(16) so this test exercises
        # fail-soft omission specifically, not the separate column-width
        # defect documented in TestPostgresSchemaDefectEvidenceLevelColumnWidth.
        _approved_side_effect(db, ingredient.id, evidence_level="bad_value")
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        item = resp.json()["side_effects"][0]
        assert "evidence_level" not in item
        assert resp.status_code == 200

    def test_invalid_theme_omitted(self, db, client):
        from app.models.drug_knowledge_content import DrugPatientEducation

        ingredient = _make_ingredient(db)
        fields = dict(
            drug_ingredient_id=ingredient.id,
            theme="not_a_locked_theme",
            locale="vi",
            audience="doctor",
            content="synthetic test content",
            **_approval_provenance_fields(),
        )
        row = repo.create_draft(db, DrugPatientEducation, authored_by="author-1", **fields)
        repo.submit_for_review(db, row, actor_user_id="author-1")
        repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role="internal_admin")
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        item = resp.json()["patient_education"][0]
        assert "theme" not in item


class TestPostgresFieldExclusion:
    def test_patient_context_and_condition_type_excluded_from_patient_contract(self, db, client):
        from app.models.drug_knowledge_content import DrugContraindication, DrugMonitoring

        ingredient = _make_ingredient(db)
        for model_cls, fields in (
            (
                DrugMonitoring,
                dict(parameter="renal_function", patient_context="baseline", guidance="monitor"),
            ),
            (
                DrugContraindication,
                dict(condition_type="disease", condition_key="ckd", condition_detail="detail"),
            ),
        ):
            row_fields = dict(
                drug_ingredient_id=ingredient.id, **fields, **_approval_provenance_fields()
            )
            row = repo.create_draft(db, model_cls, authored_by="author-1", **row_fields)
            repo.submit_for_review(db, row, actor_user_id="author-1")
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role="internal_admin")
        product = _seed_product(db, ingredient.id)
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], product.id)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        raw = resp.text
        assert '"patient_context"' not in raw
        assert '"condition_type"' not in raw


class TestPostgresRateLimiting:
    def test_rate_limit_eventually_returns_429(self, db, client):
        ingredient = _make_ingredient(db)
        doctor = _seed_doctor(db)
        headers = _mint(doctor["user_id"], "doctor")
        statuses = []
        for _ in range(60):
            resp = client.get(
                f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge", headers=headers
            )
            statuses.append(resp.status_code)
            if resp.status_code == 429:
                break
        assert 429 in statuses, f"never rate-limited across 60 requests: {statuses}"


class TestPostgresAuditAndNoWritePath:
    def test_patient_endpoint_creates_one_audit_row(self, db, client):
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        before = db.query(AuditLog).count()
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.status_code == 200
        after = db.query(AuditLog).count()
        assert after == before + 1
        latest = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()
        assert latest.action == "read_medication_knowledge"
        assert latest.resource_id == med.id

    def test_zero_medication_knowledge_row_mutation(self, db, client):
        ingredient = _make_ingredient(db)
        _approved_side_effect(db, ingredient.id)
        product = _seed_product(db, ingredient.id)
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], product.id)
        doctor = _seed_doctor(db)

        before = _knowledge_row_count(db)
        client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert _knowledge_row_count(db) == before


# A prior revision of this file had a
# TestPostgresSchemaDefectEvidenceLevelColumnWidth class here, documenting
# that evidence_level VARCHAR(16) could not hold ADR-15 §D's
# "clinical_guideline"/"peer_reviewed_literature" values. That defect is
# now FIXED by migration k2_s1_widen_evidence_level (VARCHAR(16) ->
# VARCHAR(32)) — keeping a test asserting the old narrow-column rejection
# would now be actively wrong (the insert succeeds post-migration). The
# migration itself, its upgrade/downgrade safety, and both long canonical
# values round-tripping through the real approval path are now covered by
# tests/integration/test_medication_k2_widen_evidence_level_migration.py,
# which supersedes this class entirely.
