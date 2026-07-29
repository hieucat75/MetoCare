"""K2 Slice 1 route tests (MEDICATION_K2_KNOWLEDGE_API_IMPLEMENTATION_PLAN.md §13).

  GET /api/v1/patient/medications/{medication_id}/knowledge
  GET /api/v1/doctor/ingredients/{drug_ingredient_id}/knowledge

Covers: feature-flag gate, authorization/BOLA, product->ingredient
resolution, locale/audience filter, ADR-15 vocabulary fail-soft, provenance
(never-fabricated citations, source_type disambiguation), field exclusion
(frequency/action_level/governance metadata/patient_context/condition_type
on the patient contract), caching header, audit, and no-write-path.

Reuses `tests/test_knowledge_retrieval.py`'s fixture helpers (same
convention as `tests/consultation_factories.py` being imported across
multiple test files) rather than re-deriving K1.5/K1.6 fixture plumbing.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.care import Doctor
from app.models.clinical import Medication
from app.models.consultation import DoctorVerificationStatus
from app.models.drug_knowledge_content import (
    DrugContraindication,
    DrugMonitoring,
    DrugPatientEducation,
    DrugSideEffect,
    DrugUsage,
)
from app.models.drug_knowledge_core import DrugProduct, DrugProductIngredient
from app.models.drug_knowledge_references import DrugReference, KnowledgeReferenceLink
from app.models.governance import AuditLog
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from fastapi.testclient import TestClient

from tests.test_knowledge_retrieval import _approved_row, _make_ingredient

client = TestClient(app)

_ALL_KNOWLEDGE_MODELS = [
    DrugUsage,
    DrugPatientEducation,
    DrugSideEffect,
    DrugMonitoring,
    DrugContraindication,
]


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _enable_flag(monkeypatch):
    monkeypatch.setenv("FEATURE_MEDICATION_KNOWLEDGE_RETRIEVAL", "true")
    # Slice 0: MEDICATION_EXPERIMENTAL_VOCABULARY now gates evidence_level/
    # theme exposure and defaults OFF. This file's pre-existing ADR-15
    # fail-soft/provenance/field-exclusion tests were all written to
    # exercise the vocabulary-value validity logic itself (valid vs.
    # out-of-vocabulary), not this new flag — turned on here, file-wide,
    # so those tests keep testing exactly what they always tested.
    # TestExperimentalVocabularyFlagOff below explicitly tests the new
    # default (flag unset/false) behavior on its own.
    monkeypatch.setenv("FEATURE_MEDICATION_EXPERIMENTAL_VOCABULARY", "true")


@pytest.fixture(autouse=True)
def _cleanup_all_knowledge_rows(db):
    """Same rationale as test_knowledge_retrieval.py's own cleanup fixture
    — the `db` session here has no per-test rollback, and every test in
    this module writes real 'approved' rows through the real K1.5 write
    path."""
    existing_ids = {m: {row.id for row in db.query(m.id).all()} for m in _ALL_KNOWLEDGE_MODELS}
    existing_reference_ids = {row.id for row in db.query(DrugReference.id).all()}
    existing_link_ids = {row.id for row in db.query(KnowledgeReferenceLink.id).all()}
    yield
    db.rollback()
    for row in db.query(KnowledgeReferenceLink).filter(
        ~KnowledgeReferenceLink.id.in_(existing_link_ids)
    ).all():
        db.delete(row)
    for row in db.query(DrugReference).filter(~DrugReference.id.in_(existing_reference_ids)).all():
        db.delete(row)
    for m in _ALL_KNOWLEDGE_MODELS:
        for row in db.query(m).filter(~m.id.in_(existing_ids[m])).all():
            db.delete(row)
    db.commit()


def _mint(user_id: str, role: str) -> dict[str, str]:
    token = create_access_token(subject=user_id, role=role)
    return {"Authorization": f"Bearer {token}"}


def _seed_patient(db) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"k2-patient-{suffix}@example.com",
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
        email=f"k2-doctor-{suffix}@example.com",
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


def _seed_product(db, *ingredient_ids: str, primary_id: str | None = None) -> DrugProduct:
    product = DrugProduct(display_name=f"Test Product {uuid.uuid4().hex[:6]}")
    db.add(product)
    db.flush()
    for ingredient_id in ingredient_ids:
        db.add(
            DrugProductIngredient(
                drug_product_id=product.id,
                drug_ingredient_id=ingredient_id,
                is_primary=(ingredient_id == primary_id) if primary_id else True,
            )
        )
    db.commit()
    return product


def _seed_medication(db, patient_id: str, drug_product_id: str | None) -> Medication:
    medication = Medication(patient_id=patient_id, name="Test Med", drug_product_id=drug_product_id)
    db.add(medication)
    db.commit()
    return medication


def _knowledge_row_counts(db) -> dict[str, int]:
    return {m.__tablename__: db.query(m).count() for m in _ALL_KNOWLEDGE_MODELS}


# ---------------------------------------------------------------------------
# Feature-flag gate
# ---------------------------------------------------------------------------


class TestFeatureFlagGate:
    def test_patient_endpoint_503_when_flag_off(self, db, monkeypatch):
        monkeypatch.setenv("FEATURE_MEDICATION_KNOWLEDGE_RETRIEVAL", "false")
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.status_code == 503

    def test_doctor_endpoint_503_when_flag_off(self, db, monkeypatch):
        monkeypatch.setenv("FEATURE_MEDICATION_KNOWLEDGE_RETRIEVAL", "false")
        doctor = _seed_doctor(db)
        ingredient = _make_ingredient(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert resp.status_code == 503

    def test_flag_off_writes_zero_rows(self, db, monkeypatch):
        monkeypatch.setenv("FEATURE_MEDICATION_KNOWLEDGE_RETRIEVAL", "false")
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        before = db.query(AuditLog).count()
        client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert db.query(AuditLog).count() == before


# ---------------------------------------------------------------------------
# Authorization / BOLA — endpoint #1
# ---------------------------------------------------------------------------


class TestPatientEndpointAuthorization:
    def test_owner_gets_200(self, db):
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.status_code == 200

    def test_other_patients_medication_gets_404_not_403(self, db):
        owner = _seed_patient(db)
        other = _seed_patient(db)
        med = _seed_medication(db, owner["patient_id"], None)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(other["user_id"], "patient"),
        )
        assert resp.status_code == 404

    def test_nonexistent_medication_gets_404_indistinguishable(self, db):
        patient = _seed_patient(db)
        resp = client.get(
            f"/api/v1/patient/medications/{uuid.uuid4()}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.status_code == 404

    def test_soft_deleted_medication_gets_404(self, db):
        import datetime as dt

        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        med.deleted_at = dt.datetime.now(dt.UTC)
        db.commit()
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.status_code == 404

    @pytest.mark.parametrize(
        "role",
        ["doctor", "clinic_admin", "internal_admin", "super_admin", "ai_service", "medical_reviewer"],
    )
    def test_non_patient_roles_get_403(self, db, role):
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        other_user_id = str(uuid.uuid4())
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(other_user_id, role),
        )
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, db):
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        resp = client.get(f"/api/v1/patient/medications/{med.id}/knowledge")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Authorization — endpoint #2
# ---------------------------------------------------------------------------


class TestDoctorEndpointAuthorization:
    def test_verified_and_active_doctor_gets_200(self, db):
        doctor = _seed_doctor(
            db, verification_status=DoctorVerificationStatus.VERIFIED, is_active=True
        )
        ingredient = _make_ingredient(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert resp.status_code == 200

    def test_verified_but_inactive_doctor_gets_403(self, db):
        """Hardened 2026-07-23 — require_verified_doctor now also checks
        is_active, matching consultation.py/consultation_access.py's
        established defense-in-depth pattern."""
        doctor = _seed_doctor(
            db, verification_status=DoctorVerificationStatus.VERIFIED, is_active=False
        )
        ingredient = _make_ingredient(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert resp.status_code == 403

    def test_pending_verification_doctor_gets_403(self, db):
        doctor = _seed_doctor(db, verification_status=DoctorVerificationStatus.PENDING_VERIFICATION)
        ingredient = _make_ingredient(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert resp.status_code == 403

    def test_doctor_role_with_no_linked_doctor_row_gets_403(self, db):
        """DOCTOR-role JWT for a user_id with no Doctor row at all (e.g. an
        account created without ever completing doctor onboarding) —
        distinct from PENDING_VERIFICATION, which has a Doctor row."""
        resp = client.get(
            f"/api/v1/doctor/ingredients/{_make_ingredient(db).id}/knowledge",
            headers=_mint(str(uuid.uuid4()), "doctor"),
        )
        assert resp.status_code == 403

    @pytest.mark.parametrize(
        "role", ["patient", "clinic_admin", "internal_admin", "super_admin", "ai_service", "medical_reviewer"]
    )
    def test_non_doctor_roles_get_403(self, db, role):
        ingredient = _make_ingredient(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(str(uuid.uuid4()), role),
        )
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, db):
        ingredient = _make_ingredient(db)
        resp = client.get(f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge")
        assert resp.status_code == 401

    def test_no_audit_log_written(self, db):
        doctor = _seed_doctor(db)
        ingredient = _make_ingredient(db)
        before = db.query(AuditLog).count()
        client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert db.query(AuditLog).count() == before


# ---------------------------------------------------------------------------
# Product -> ingredient resolution, locale/audience filter, merge rules
# ---------------------------------------------------------------------------


class TestProductIngredientResolution:
    def test_null_drug_product_id_returns_empty_categories(self, db):
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["usage"] is None
        assert body["side_effects"] == []
        assert body["monitoring"] == []
        assert body["contraindications"] == []

    def test_unmatched_drug_product_id_returns_empty_not_404(self, db):
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], str(uuid.uuid4()))
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.status_code == 200
        assert resp.json()["side_effects"] == []

    def test_combination_product_merges_side_effects_across_ingredients(self, db):
        ing_a = _make_ingredient(db)
        ing_b = _make_ingredient(db)
        _approved_row(db, DrugSideEffect, ing_a.id, variant="a", evidence_level="clinical_guideline")
        _approved_row(db, DrugSideEffect, ing_b.id, variant="b", evidence_level="clinical_guideline")
        product = _seed_product(db, ing_a.id, ing_b.id, primary_id=ing_a.id)
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], product.id)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        body = resp.json()
        assert resp.status_code == 200
        assert len(body["side_effects"]) == 2

    def test_combination_product_usage_prefers_primary_ingredient(self, db):
        ing_primary = _make_ingredient(db)
        ing_secondary = _make_ingredient(db)
        _approved_row(
            db, DrugUsage, ing_primary.id, variant="primary", evidence_level="clinical_guideline",
            content="primary-content",
        )
        _approved_row(
            db, DrugUsage, ing_secondary.id, variant="secondary", evidence_level="clinical_guideline",
            content="secondary-content",
        )
        product = _seed_product(db, ing_secondary.id, ing_primary.id, primary_id=ing_primary.id)
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], product.id)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        body = resp.json()
        assert body["usage"]["content"] == "primary-content"


class TestLocaleAudienceFilter:
    """`locale`/`audience` only exist on `DrugUsage`/`DrugPatientEducation`
    (verified against `app/models/drug_knowledge_content.py` — a live-schema
    correction to K2 plan §1.3 fact 4, which claims all 5 tables carry both
    fields). `DrugSideEffect`/`DrugMonitoring`/`DrugContraindication` have
    neither column, so there is no audience/locale duplicate to filter for
    them — see `TestVocabularyFailSoft`/`TestProvenance` below, which
    intentionally do not pass `audience=` to those 3 models."""

    def test_patient_endpoint_excludes_doctor_audience_row(self, db):
        ingredient = _make_ingredient(db)
        _approved_row(
            db, DrugPatientEducation, ingredient.id, audience="doctor",
            evidence_level="clinical_guideline",
        )
        product = _seed_product(db, ingredient.id)
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], product.id)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.json()["patient_education"] == []

    def test_doctor_endpoint_excludes_patient_audience_row(self, db):
        ingredient = _make_ingredient(db)
        _approved_row(
            db, DrugPatientEducation, ingredient.id, audience="patient",
            evidence_level="clinical_guideline",
        )
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert resp.json()["patient_education"] == []

    def test_doctor_endpoint_returns_doctor_audience_row(self, db):
        ingredient = _make_ingredient(db)
        _approved_row(
            db, DrugPatientEducation, ingredient.id, audience="doctor",
            evidence_level="clinical_guideline",
        )
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert len(resp.json()["patient_education"]) == 1


# ---------------------------------------------------------------------------
# ADR-15 vocabulary fail-soft
# ---------------------------------------------------------------------------


class TestVocabularyFailSoft:
    def test_valid_evidence_level_present_in_response(self, db):
        ingredient = _make_ingredient(db)
        _approved_row(
            db, DrugSideEffect, ingredient.id, evidence_level="clinical_guideline"
        )
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        item = resp.json()["side_effects"][0]
        assert item["evidence_level"] == "clinical_guideline"

    def test_invalid_evidence_level_key_absent_not_null(self, db):
        """ADR-15 §G: field genuinely ABSENT from JSON, not present as null."""
        ingredient = _make_ingredient(db)
        _approved_row(
            db, DrugSideEffect, ingredient.id, evidence_level="not_a_locked_value"
        )
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        item = resp.json()["side_effects"][0]
        assert "evidence_level" not in item
        assert resp.status_code == 200  # invariant 4: never fails the whole request

    def test_invalid_theme_key_absent_item_survives(self, db):
        ingredient = _make_ingredient(db)
        row = _approved_row(
            db, DrugPatientEducation, ingredient.id, audience="doctor",
            evidence_level="clinical_guideline",
        )
        # theme is not one of ADR-15's 6 locked values by construction
        # (_model_fields uses "general") — assert it, don't re-seed.
        assert row.theme == "general"
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        item = resp.json()["patient_education"][0]
        assert "theme" not in item
        assert item["content"] == row.content  # rest of the item unaffected

    # No test seeds an out-of-vocabulary `DrugReference.source_type` — unlike
    # `evidence_level`/`theme`, `source_type` is already DB CHECK-enforced
    # (`ck_drug_references_source_type`, verified directly: attempting the
    # insert raises `IntegrityError` before this module's own fail-soft code
    # would ever run). `_references_out`'s `_SOURCE_TYPE_VALUES` filter is
    # kept as defense-in-depth (ADR-15 §G's general principle), but the
    # scenario it guards against is structurally unreachable today.


class TestExperimentalVocabularyFlagOff:
    """Slice 0: MEDICATION_EXPERIMENTAL_VOCABULARY's actual default
    (unset/false) — overrides this file's own autouse `_enable_flag`
    fixture, which turns it ON for every OTHER test in this file so the
    pre-existing ADR-15 fail-soft tests above keep testing vocabulary-value
    validity, not this flag."""

    def test_evidence_level_omitted_when_flag_off(self, db, monkeypatch):
        monkeypatch.setenv("FEATURE_MEDICATION_EXPERIMENTAL_VOCABULARY", "false")
        ingredient = _make_ingredient(db)
        row = _approved_row(
            db, DrugSideEffect, ingredient.id, evidence_level="clinical_guideline"
        )
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        item = resp.json()["side_effects"][0]
        assert "evidence_level" not in item
        # never present as null either — genuinely absent
        assert "evidence_level" not in resp.json()["side_effects"][0].keys()
        # rest of the item, and the stored value itself, unaffected
        assert item["description"] == row.description
        assert row.evidence_level == "clinical_guideline"

    def test_theme_omitted_when_flag_off(self, db, monkeypatch):
        monkeypatch.setenv("FEATURE_MEDICATION_EXPERIMENTAL_VOCABULARY", "false")
        ingredient = _make_ingredient(db)
        row = _approved_row(
            db,
            DrugPatientEducation,
            ingredient.id,
            audience="doctor",
            evidence_level="clinical_guideline",
            theme="why_this_matters",
        )
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        item = resp.json()["patient_education"][0]
        assert "theme" not in item
        assert item["content"] == row.content
        assert row.theme == "why_this_matters"  # stored value never mutated

    def test_evidence_level_omitted_by_default_with_no_env_var_set(self, db, monkeypatch):
        """Proves OFF is the actual default, not just an explicit 'false'
        override — deletes the env var entirely rather than setting it."""
        monkeypatch.delenv("FEATURE_MEDICATION_EXPERIMENTAL_VOCABULARY", raising=False)
        monkeypatch.delenv("MCP_FEATURE_MEDICATION_EXPERIMENTAL_VOCABULARY", raising=False)
        ingredient = _make_ingredient(db)
        _approved_row(db, DrugSideEffect, ingredient.id, evidence_level="clinical_guideline")
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert "evidence_level" not in resp.json()["side_effects"][0]

    def test_patient_contract_also_omits_evidence_level_when_flag_off(self, db, monkeypatch):
        monkeypatch.setenv("FEATURE_MEDICATION_EXPERIMENTAL_VOCABULARY", "false")
        ingredient = _make_ingredient(db)
        row = _approved_row(
            db, DrugSideEffect, ingredient.id, evidence_level="clinical_guideline"
        )
        product = _seed_product(db, ingredient.id)
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], product.id)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        item = resp.json()["side_effects"][0]
        assert "evidence_level" not in item
        assert item["description"] == row.description


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_valid_reference_returned_with_all_fields(self, db):
        ingredient = _make_ingredient(db)
        row = _approved_row(
            db, DrugSideEffect, ingredient.id, evidence_level="clinical_guideline"
        )
        ref = DrugReference(
            publisher="VIDAL Vietnam",
            title="Metformin",
            source_type="product_label",
            url="https://example.invalid/metformin",
            document_identifier=f"VIDAL-{uuid.uuid4().hex[:8]}",
            publication_date=__import__("datetime").date(2026, 1, 15),
            source_version="2026.1",
            accessed_at=__import__("datetime").date(2026, 1, 20),
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
        reference_out = resp.json()["side_effects"][0]["references"][0]
        assert reference_out["publisher"] == "VIDAL Vietnam"
        assert reference_out["source_type"] == "product_label"
        assert reference_out["document_identifier"] == ref.document_identifier

    def test_no_citation_link_returns_empty_list_never_fabricated(self, db):
        ingredient = _make_ingredient(db)
        _approved_row(
            db, DrugSideEffect, ingredient.id, evidence_level="clinical_guideline"
        )
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert resp.json()["side_effects"][0]["references"] == []

    def test_patient_contract_has_no_references_field_at_all(self, db):
        ingredient = _make_ingredient(db)
        _approved_row(
            db, DrugSideEffect, ingredient.id, evidence_level="clinical_guideline"
        )
        product = _seed_product(db, ingredient.id)
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], product.id)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        item = resp.json()["side_effects"][0]
        assert "references" not in item


# ---------------------------------------------------------------------------
# Field exclusion (schema-introspection)
# ---------------------------------------------------------------------------


class TestFieldExclusion:
    def _full_payload(self, db):
        """`locale`/`audience` only exist on `DrugUsage`/`DrugPatientEducation`
        — the other 3 models get one unfiltered approved row each (see
        `TestLocaleAudienceFilter`'s docstring)."""
        ingredient = _make_ingredient(db)
        for model_cls in (DrugUsage, DrugPatientEducation):
            for audience in ("patient", "doctor"):
                _approved_row(
                    db, model_cls, ingredient.id, variant=audience, audience=audience,
                    evidence_level="clinical_guideline",
                )
        for model_cls in (DrugSideEffect, DrugMonitoring, DrugContraindication):
            _approved_row(db, model_cls, ingredient.id, evidence_level="clinical_guideline")
        return ingredient

    def test_patient_contract_never_has_frequency_or_action_level(self, db):
        ingredient = self._full_payload(db)
        product = _seed_product(db, ingredient.id)
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], product.id)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        raw = resp.text
        assert '"frequency"' not in raw
        assert '"action_level"' not in raw

    def test_doctor_contract_never_has_frequency_or_action_level(self, db):
        ingredient = self._full_payload(db)
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        raw = resp.text
        assert '"frequency"' not in raw
        assert '"action_level"' not in raw

    def test_no_contract_ever_has_governance_fields(self, db):
        ingredient = self._full_payload(db)
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        raw = resp.text
        for field in ("authored_by", "status_changed_by", "artifact_hash"):
            assert field not in raw

    def test_patient_contract_never_has_patient_context_or_condition_type(self, db):
        ingredient = self._full_payload(db)
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

    def test_doctor_contract_exposes_patient_context_and_condition_type(self, db):
        ingredient = self._full_payload(db)
        doctor = _seed_doctor(db)
        resp = client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        body = resp.json()
        assert body["monitoring"][0]["patient_context"] == "baseline"
        assert body["contraindications"][0]["condition_type"] == "disease"


# ---------------------------------------------------------------------------
# Caching, envelope, no-write-path
# ---------------------------------------------------------------------------


class TestCachingAndEnvelope:
    def test_patient_endpoint_sets_private_no_store(self, db):
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.headers.get("cache-control") == "private, no-store"

    def test_envelope_has_knowledge_vocabulary_version(self, db):
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        resp = client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert resp.json()["knowledge_vocabulary_version"] == "1.0"


class TestNoWritePath:
    def test_patient_endpoint_never_changes_knowledge_row_counts(self, db):
        ingredient = _make_ingredient(db)
        _approved_row(
            db, DrugSideEffect, ingredient.id, evidence_level="clinical_guideline"
        )
        product = _seed_product(db, ingredient.id)
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], product.id)
        before = _knowledge_row_counts(db)
        client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        assert _knowledge_row_counts(db) == before

    def test_doctor_endpoint_never_changes_knowledge_row_counts(self, db):
        ingredient = _make_ingredient(db)
        _approved_row(
            db, DrugSideEffect, ingredient.id, evidence_level="clinical_guideline"
        )
        doctor = _seed_doctor(db)
        before = _knowledge_row_counts(db)
        client.get(
            f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
            headers=_mint(doctor["user_id"], "doctor"),
        )
        assert _knowledge_row_counts(db) == before

    def test_patient_endpoint_produces_one_audit_row(self, db):
        patient = _seed_patient(db)
        med = _seed_medication(db, patient["patient_id"], None)
        before = db.query(AuditLog).count()
        client.get(
            f"/api/v1/patient/medications/{med.id}/knowledge",
            headers=_mint(patient["user_id"], "patient"),
        )
        after = db.query(AuditLog).count()
        assert after == before + 1
        latest = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()
        assert latest.action == "read_medication_knowledge"
        assert latest.resource_id == med.id


class TestNoAiFrontendRegression:
    def test_five_knowledge_tables_absent_from_ai_and_frontend(self):
        import pathlib

        backend_dir = pathlib.Path(__file__).resolve().parents[1]
        repo_root = backend_dir.parent
        table_names = [m.__tablename__ for m in _ALL_KNOWLEDGE_MODELS]
        search_dirs = [backend_dir / "app" / "ai", repo_root / "frontend" / "src"]
        hits = []
        for directory in search_dirs:
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file() and any(name in path.read_text(errors="ignore") for name in table_names):
                    hits.append(str(path))
        assert hits == [], f"K2 scope violated — found references in: {hits}"


class TestReferenceQueryCountDoesNotScaleWithRowCount:
    """Regression test for the N+1 fix (2026-07-23) — the doctor endpoint
    must issue ONE reference query per category (side_effects/monitoring/
    contraindications), not one per approved row. Instruments the actual
    SQL statements issued during a live request via a `before_cursor_
    execute` event listener on the app's real engine — proof by
    observation, not by reading the code and assuming it's right."""

    def test_five_side_effect_rows_produce_one_reference_query_not_five(self, db):
        from app.core.database import engine as app_engine
        from sqlalchemy import event

        ingredient = _make_ingredient(db)
        expected_document_identifier_by_concept_code: dict[str, str] = {}
        for i in range(5):
            row = _approved_row(
                db, DrugSideEffect, ingredient.id, variant=f"v{i}",
                evidence_level="clinical_guideline", concept_code=f"concept-{i}",
            )
            document_identifier = f"DOC-{uuid.uuid4().hex[:8]}"
            ref = DrugReference(
                publisher=f"Publisher {i}",
                title=f"Title {i}",
                source_type="product_label",
                document_identifier=document_identifier,
                publication_date=__import__("datetime").date(2026, 1, 1),
                source_version="1.0",
                accessed_at=__import__("datetime").date(2026, 1, 2),
            )
            db.add(ref)
            db.flush()
            db.add(
                KnowledgeReferenceLink(
                    knowledge_table="drug_side_effects", knowledge_row_id=row.id, drug_reference_id=ref.id
                )
            )
            expected_document_identifier_by_concept_code[f"concept-{i}"] = document_identifier
        db.commit()
        doctor = _seed_doctor(db)

        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(app_engine, "before_cursor_execute", _capture)
        try:
            resp = client.get(
                f"/api/v1/doctor/ingredients/{ingredient.id}/knowledge",
                headers=_mint(doctor["user_id"], "doctor"),
            )
        finally:
            event.remove(app_engine, "before_cursor_execute", _capture)

        assert resp.status_code == 200
        side_effects = resp.json()["side_effects"]
        assert len(side_effects) == 5
        for item in side_effects:
            assert len(item["references"]) == 1
            expected_document_identifier = expected_document_identifier_by_concept_code[
                item["concept_code"]
            ]
            assert item["references"][0]["document_identifier"] == expected_document_identifier, (
                f"row {item['concept_code']} received a reference belonging to a different "
                f"row — batch-loading must map references back to their own knowledge row, "
                f"not just the right count"
            )

        reference_queries = [
            s for s in statements if "drug_references" in s or "knowledge_reference_links" in s
        ]
        assert len(reference_queries) == 1, (
            f"expected exactly 1 batched reference query for 5 approved rows "
            f"(1 per category, not 1 per row), got {len(reference_queries)}: {reference_queries}"
        )
