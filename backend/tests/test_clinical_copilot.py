"""Meto Clinical Copilot API tests.

Covers:
- POST /doctor/patients/{id}/ai-summary    (deterministic, no LLM)
- POST /doctor/patients/{id}/ai-analysis   (deterministic priority + LLM phrasing)
- POST /doctor/patients/{id}/ai-questions  (LLM-suggested history-taking questions)
- POST /doctor/patients/{id}/ai-advice     (LLM-suggested counseling direction)

Guardrails under test: cross-doctor scope, consent gate, feature flag fail-closed,
provider-failure fail-closed, deterministic priority never overridden by the LLM,
malformed LLM output never crashes/leaks, audit trail never carries PHI, and this
surface never writes to ConsultationNote (advisory only, never the medical record).
"""

from __future__ import annotations

import datetime as dt
import json
import os

import pytest
from app.ai.providers.base import ChatResponse, ConversationProvider, ProviderHealthStatus
from app.ai.registry import ProviderRegistry
from app.models.clinical import HealthMetric
from app.models.consultation import ConsultationNote
from app.models.governance import AuditLog, Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from sqlalchemy import select

API = "/api/v1"


# ---------------------------------------------------------------------------
# Stub LLM provider — registered directly into a test-local ProviderRegistry
# so no test ever hits the network. Mirrors MockConversationProvider's shape.
# ---------------------------------------------------------------------------


class _StubProvider(ConversationProvider):
    def __init__(self, *, content: str = "", raise_exc: Exception | None = None, name: str = "claude"):
        self._content = content
        self._raise_exc = raise_exc
        self._name = name
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def model_name(self) -> str:
        return "stub-1.0"

    @property
    def max_context_tokens(self) -> int:
        return 32_000

    @property
    def supports_streaming(self) -> bool:
        return False

    @property
    def supports_tool_use(self) -> bool:
        return False

    async def chat(
        self,
        messages,
        system_prompt,
        tools=None,
        temperature=0.3,
        max_tokens=2000,
        stream=False,
    ) -> ChatResponse:
        self.call_count += 1
        if self._raise_exc is not None:
            raise self._raise_exc
        return ChatResponse(
            content=self._content,
            tool_calls=None,
            input_tokens=10,
            output_tokens=10,
            model_used=self.model_name,
            finish_reason="stop",
            latency_ms=5,
            provider=self._name,
        )

    async def chat_stream(self, messages, system_prompt, tools=None, temperature=0.3, max_tokens=2000):
        raise NotImplementedError
        yield  # pragma: no cover

    async def cancel(self, request_id: str) -> bool:
        return True

    async def estimate_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def health_check(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(provider=self._name, is_alive=True)


def _registry_with(provider: _StubProvider) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(provider)
    return registry


def _patch_registry(monkeypatch, provider: _StubProvider) -> None:
    registry = _registry_with(provider)
    monkeypatch.setattr("app.services.clinical_copilot.get_registry", lambda: registry)


def _enable_flag(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_CLINICAL_COPILOT", "true")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_doctor(db, *, name: str = "BS Test") -> dict:
    from app.models.care import Doctor

    uid = os.urandom(4).hex()
    user = User(
        email=f"dr-{uid}@clinic.vn",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name=name,
        is_active=True,
        mfa_enabled=True,
    )
    db.add(user)
    db.flush()
    doc = Doctor(user_id=user.id, full_name=name, specialty="Nội tiết", is_active=True)
    db.add(doc)
    db.commit()
    return {"user_id": user.id, "doctor_id": doc.id}


def _make_patient(db, *, name: str = "Bệnh nhân Test") -> PatientProfile:
    uid = os.urandom(4).hex()
    user = User(
        email=f"pt-{uid}@example.vn",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name=name,
        is_active=True,
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name=name)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _grant_profile_consent(db, *, patient_id: str, doctor_user_id: str) -> None:
    db.add(
        Consent(
            patient_id=patient_id,
            consent_type="doctor_access",
            data_scope="profile",
            granted_to=doctor_user_id,
        )
    )
    db.commit()


def _grant_ai_use_consent(db, *, patient_id: str, doctor_user_id: str) -> None:
    db.add(
        Consent(
            patient_id=patient_id,
            consent_type="ai_use",
            data_scope="clinical_copilot",
            granted_to=doctor_user_id,
        )
    )
    db.commit()


def _fully_authorized_doctor(db, *, name: str = "BS Test") -> dict:
    """A doctor + patient pair with BOTH profile-scope and ai_use consent granted."""
    doctor = _make_doctor(db, name=name)
    profile = _make_patient(db)
    _grant_profile_consent(db, patient_id=profile.id, doctor_user_id=doctor["user_id"])
    _grant_ai_use_consent(db, patient_id=profile.id, doctor_user_id=doctor["user_id"])
    return {**doctor, "patient_id": profile.id}


def _headers(user_id: str) -> dict:
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(subject=user_id, role='doctor', mfa=True)}"}


def _seed_critical_finding(db, *, patient_id: str) -> None:
    """Seed an HbA1c reading above the critical_high threshold (10.0%)."""
    db.add(
        HealthMetric(
            patient_id=patient_id,
            metric_type="hba1c",
            value=12.0,
            unit="%",
            measured_at=dt.datetime(2026, 1, 1, 8, 0),
            source="manual",
            status="high",
        )
    )
    db.commit()


VALID_ANALYSIS_JSON = (
    '{"key_issues": ["Tất cả đều ổn, không có vấn đề gì."], '
    '"contradictions_or_gaps": [], "differentials_to_exclude": [], '
    '"questions": [], "items": []}'
)


# ---------------------------------------------------------------------------
# 1. Cross-doctor access blocked
# ---------------------------------------------------------------------------


def test_cross_doctor_access_blocked(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    owner = _fully_authorized_doctor(db, name="BS Owner")
    stranger = _make_doctor(db, name="BS Stranger")
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    resp = client.post(
        f"{API}/doctor/patients/{owner['patient_id']}/ai-summary",
        json={},
        headers=_headers(stranger["user_id"]),
    )
    assert resp.status_code == 403
    body = resp.json()
    # Generic detail message — no patient NAME / clinical content ever leaked
    # (the existing consent-gate error format already includes the opaque
    # patient_id UUID — pre-existing codebase behavior, not PHI).
    assert "BS Owner" not in str(body)
    assert "Bệnh nhân" not in str(body)


# ---------------------------------------------------------------------------
# 2. Missing / denied ai_use consent
# ---------------------------------------------------------------------------


def test_missing_ai_use_consent_denied_and_audited(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    doctor = _make_doctor(db)
    profile = _make_patient(db)
    # Grant profile-scope (passes the timeline gate) but NOT ai_use.
    _grant_profile_consent(db, patient_id=profile.id, doctor_user_id=doctor["user_id"])
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    resp = client.post(
        f"{API}/doctor/patients/{profile.id}/ai-summary",
        json={},
        headers=_headers(doctor["user_id"]),
    )
    assert resp.status_code == 403

    denied = db.execute(
        select(AuditLog).where(
            AuditLog.action == "consent.check:ai_use",
            AuditLog.resource_id == profile.id,
            AuditLog.outcome == "denied",
        )
    ).scalars().all()
    assert len(denied) >= 1


# ---------------------------------------------------------------------------
# 3. Feature flag off — 503, provider never invoked
# ---------------------------------------------------------------------------


def test_feature_flag_off_returns_503_and_never_calls_provider(client, db, monkeypatch):
    # No _enable_flag() — default is OFF (fail-closed).
    monkeypatch.delenv("FEATURE_CLINICAL_COPILOT", raising=False)
    ctx = _fully_authorized_doctor(db)
    stub = _StubProvider(content=VALID_ANALYSIS_JSON)
    _patch_registry(monkeypatch, stub)

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 503
    assert stub.call_count == 0


# ---------------------------------------------------------------------------
# 4. Provider fails every call — 503 friendly message + audit outcome=failed
# ---------------------------------------------------------------------------


def test_provider_unavailable_returns_503_and_audits_failure(client, db, monkeypatch):
    from app.ai.exceptions import ProviderUnavailableError

    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    stub = _StubProvider(raise_exc=ProviderUnavailableError("claude", "down"))
    _patch_registry(monkeypatch, stub)

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 503
    # Never the raw exception text.
    assert "ProviderUnavailableError" not in resp.text
    assert "Traceback" not in resp.text

    failed = db.execute(
        select(AuditLog).where(
            AuditLog.action == "ai_clinical_analysis.failed",
            AuditLog.resource_id == ctx["patient_id"],
            AuditLog.outcome == "failed",
        )
    ).scalars().all()
    assert len(failed) >= 1


# ---------------------------------------------------------------------------
# 5. Critical finding → priority.level == "urgent" regardless of LLM phrasing
# ---------------------------------------------------------------------------


def test_critical_finding_forces_urgent_priority_regardless_of_llm(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _seed_critical_finding(db, patient_id=ctx["patient_id"])
    # The mocked LLM tries to claim everything is fine — must NOT change the level.
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["priority"]["level"] == "urgent"


# ---------------------------------------------------------------------------
# 6. Malformed / non-JSON LLM output does not crash
# ---------------------------------------------------------------------------


def test_malformed_llm_output_does_not_crash(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _patch_registry(monkeypatch, _StubProvider(content="Xin lỗi, mình không hiểu ý bạn."))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    # A genuinely unusable top-level structure (non-JSON) is now a controlled
    # 422 — never a 500, and never the raw model text leaked to the client.
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"] == "Meto không thể xử lý phản hồi AI cho yêu cầu này. Vui lòng thử lại."
    assert "mình không hiểu ý bạn" not in str(body)


# ---------------------------------------------------------------------------
# 7. No AuditLog row for this feature ever contains patient content — ids only
# ---------------------------------------------------------------------------


def test_audit_rows_never_contain_patient_content(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _seed_critical_finding(db, patient_id=ctx["patient_id"])
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    for path in ("ai-summary", "ai-analysis", "ai-questions", "ai-advice"):
        resp = client.post(
            f"{API}/doctor/patients/{ctx['patient_id']}/{path}",
            json={},
            headers=_headers(ctx["user_id"]),
        )
        assert resp.status_code == 200, (path, resp.text)

    rows = db.execute(
        select(AuditLog).where(
            AuditLog.action.like("ai_clinical_%"),
            AuditLog.resource_id == ctx["patient_id"],
        )
    ).scalars().all()
    assert rows, "expected at least one ai_clinical_* audit row"
    for row in rows:
        # resource_id must look like an id (the patient_id we seeded), never a
        # content/summary string, and the model must carry no content/summary column.
        assert row.resource_id == ctx["patient_id"]
        assert not hasattr(row, "content")
        assert not hasattr(row, "summary")


# ---------------------------------------------------------------------------
# 8. consultation_id whose patient_id differs from the URL's patient_id → 400
# ---------------------------------------------------------------------------


def test_consultation_id_patient_mismatch_returns_400(client, db, monkeypatch):
    from app.services import consultation as consult_svc
    from app.services import consultation_payment

    from tests.consultation_factories import CONSENT_ALL_CATEGORIES, create_doctor, create_patient

    _enable_flag(monkeypatch)
    doctor = create_doctor(db)
    _u1, profile_a = create_patient(db)
    _u2, profile_b = create_patient(db)
    consultation = consult_svc.create_consultation(
        db, patient_id=profile_a.id, doctor_id=doctor.id, data_consent_accepted=True,
        consent_categories=CONSENT_ALL_CATEGORIES
    )
    consultation_payment.pay_mock(db, consultation, patient_profile_id=profile_a.id)
    _grant_ai_use_consent(db, patient_id=profile_b.id, doctor_user_id=doctor.user_id)
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    # URL says patient_b, but consultation_id belongs to patient_a.
    resp = client.post(
        f"{API}/doctor/patients/{profile_b.id}/ai-summary",
        json={"consultation_id": consultation.id},
        headers=_headers(doctor.user_id),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 9. This feature never writes to ConsultationNote (advisory only)
# ---------------------------------------------------------------------------


def test_never_writes_consultation_note(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    before = db.execute(select(ConsultationNote)).scalars().all()
    for path in ("ai-summary", "ai-analysis", "ai-questions", "ai-advice"):
        resp = client.post(
            f"{API}/doctor/patients/{ctx['patient_id']}/{path}",
            json={},
            headers=_headers(ctx["user_id"]),
        )
        assert resp.status_code == 200
    after = db.execute(select(ConsultationNote)).scalars().all()
    assert len(after) == len(before)


# ---------------------------------------------------------------------------
# 10. No data at all -> every applicable category missing, confidence "low",
#     no claim asserted without a needs_confirmation/sourced basis
# ---------------------------------------------------------------------------


def test_no_data_analysis_missing_all_categories_low_confidence(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    content = json.dumps(
        {
            "key_issues": [{"text": "Chưa đủ dữ liệu để đưa ra nhận định.", "source_ids": []}],
            "contradictions_or_gaps": [],
            "differentials_to_exclude": [],
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["confidence"] == "low"
    assert body["confidence_note_vi"]
    missing_categories = {m["category"] for m in body["missing_data"]}
    # profile row exists (patient created via _fully_authorized_doctor) so
    # "demographics" is present; no consultation_id -> symptoms/consultation_context
    # are not applicable at all.
    assert missing_categories == {
        "allergies",
        "medications",
        "medical_history",
        "vitals_metrics",
        "labs",
    }
    for field in ("key_issues", "contradictions_or_gaps", "differentials_to_exclude"):
        for claim in body[field]:
            if claim["basis"] == "sourced":
                assert claim["sources"], claim
            else:
                assert claim["basis"] == "needs_confirmation"
                assert claim["sources"] == []


# ---------------------------------------------------------------------------
# 11. Partial data -> missing_data contains exactly the missing categories
# ---------------------------------------------------------------------------


def test_partial_data_missing_data_matches_expected_categories(client, db, monkeypatch):
    from app.models.clinical import Medication

    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    db.add(
        Medication(
            patient_id=ctx["patient_id"], name="Metformin", dose="500mg", frequency="2 lần/ngày"
        )
    )
    db.commit()
    content = json.dumps(
        {"key_issues": [], "contradictions_or_gaps": [], "differentials_to_exclude": []}
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    missing_categories = {m["category"] for m in body["missing_data"]}
    assert "medications" not in missing_categories
    assert missing_categories == {"allergies", "medical_history", "vitals_metrics", "labs"}


# ---------------------------------------------------------------------------
# 12. Stale lab finding -> real ISO date on the source + confidence downgraded
# ---------------------------------------------------------------------------


def test_stale_lab_finding_downgrades_confidence_and_has_real_date(client, db, monkeypatch):
    from app.models.clinical import LabResult

    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    stale_dt = dt.datetime.now(dt.UTC) - dt.timedelta(days=400)
    db.add(
        HealthMetric(
            patient_id=ctx["patient_id"],
            metric_type="hba1c",
            value=8.0,
            unit="%",
            measured_at=dt.datetime(stale_dt.year, stale_dt.month, stale_dt.day, 8, 0),
            source="manual",
            status="high",
        )
    )
    lab_row = LabResult(
        patient_id=ctx["patient_id"],
        test_name="HbA1c",
        canonical_name="hba1c",
        value=8.0,
        unit="%",
        test_date=stale_dt.date(),
        # The copilot reads confirmed labs only — an unverified OCR row is a
        # machine's guess, not something to cite to a doctor.
        verified_by_user=True,
    )
    db.add(lab_row)
    db.commit()
    db.refresh(lab_row)

    source_id = f"lab:{lab_row.id}"
    content = json.dumps(
        {
            "key_issues": [{"text": "HbA1c tăng, đã lâu chưa xét nghiệm lại.", "source_ids": [source_id]}],
            "contradictions_or_gaps": [],
            "differentials_to_exclude": [],
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    # Never "high" while the freshest reading is stale.
    assert body["confidence"] in ("low", "medium")
    claim = body["key_issues"][0]
    assert claim["basis"] == "sourced"
    assert claim["sources"][0]["date"] == stale_dt.date().isoformat()
    assert claim["confidence"] == "medium"


# ---------------------------------------------------------------------------
# 13. Table-driven: SourceRef.date resolves to the real underlying record date
#     for each source-producing type (lab, metric, medication, consultation,
#     profile) — direct service-level check of `_build_source_map`.
# ---------------------------------------------------------------------------


def test_source_map_dates_match_underlying_fixtures(db):
    from app.models.clinical import LabResult, Medication
    from app.services import clinical_copilot as svc
    from app.services import consultation as consult_svc
    from app.services import consultation_payment

    from tests.consultation_factories import CONSENT_ALL_CATEGORIES, create_doctor, create_patient

    doctor = create_doctor(db)
    _user, profile = create_patient(db)
    profile.known_conditions = json.dumps(["Đái tháo đường type 2"])
    profile.allergies = json.dumps(["Penicillin"])
    db.commit()
    db.refresh(profile)

    medication = Medication(
        patient_id=profile.id, name="Metformin", dose="500mg", frequency="2 lần/ngày"
    )
    db.add(medication)

    metric_date = dt.datetime(2026, 2, 1, 8, 0)
    weight_metric = HealthMetric(
        patient_id=profile.id,
        metric_type="weight",
        value=70.0,
        unit="kg",
        measured_at=metric_date,
        source="manual",
        status="normal",
    )
    db.add(weight_metric)

    lab_date = dt.date(2026, 1, 10)
    lab_row = LabResult(
        patient_id=profile.id,
        test_name="HbA1c",
        canonical_name="hba1c",
        value=7.0,
        unit="%",
        test_date=lab_date,
        verified_by_user=True,
    )
    db.add(lab_row)
    db.add(
        HealthMetric(
            patient_id=profile.id,
            metric_type="hba1c",
            value=7.0,
            unit="%",
            measured_at=dt.datetime(2026, 1, 10, 8, 0),
            source="manual",
            status="normal",
        )
    )
    db.commit()
    db.refresh(medication)
    db.refresh(lab_row)
    db.refresh(weight_metric)

    consultation = consult_svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True,
        consent_categories=CONSENT_ALL_CATEGORIES
    )
    consultation_payment.pay_mock(db, consultation, patient_profile_id=profile.id)
    db.refresh(consultation)

    findings = svc.list_insights(db, patient_id=profile.id, abnormal_only=False)
    profile_reloaded = svc._load_profile(db, profile.id)
    conditions, allergies = svc._conditions_and_allergies(profile_reloaded)
    medication_records = svc._medication_records(db, profile.id)
    lab_rows = svc._lab_rows(db, profile.id)
    metric_rows = svc._metric_rows(db, profile.id)

    source_map = svc._build_source_map(
        patient_id=profile.id,
        profile=profile_reloaded,
        conditions=conditions,
        allergies=allergies,
        medication_records=medication_records,
        findings=findings,
        lab_rows=lab_rows,
        metric_rows=metric_rows,
        consultation=consultation,
    )

    assert source_map[f"medication:{medication.id}"].date == medication.created_at.isoformat()
    assert source_map[f"metric:{weight_metric.id}"].date == metric_date.isoformat()
    assert source_map[f"lab:{lab_row.id}"].date == lab_date.isoformat()
    assert source_map[f"consultation:{consultation.id}"].date == consultation.created_at.isoformat()
    assert source_map[f"profile:{profile.id}"].date == profile_reloaded.updated_at.isoformat()


# ---------------------------------------------------------------------------
# 14. Every claim across a mixed-data scenario is either sourced or explicitly
#     needs_confirmation — never neither.
# ---------------------------------------------------------------------------


def test_all_claims_have_basis_and_consistent_sources(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _seed_critical_finding(db, patient_id=ctx["patient_id"])
    content = json.dumps(
        {
            "key_issues": [
                {"text": "HbA1c rất cao, cần đánh giá sớm.", "source_ids": ["lab:hba1c"]},
                {"text": "Chưa rõ nguyên nhân, cần thêm thông tin.", "source_ids": []},
            ],
            "contradictions_or_gaps": [
                {"text": "Chưa có thông tin dị ứng để đối chiếu.", "source_ids": ["does-not-exist"]},
            ],
            "differentials_to_exclude": [],
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    all_claims = (
        body["key_issues"] + body["contradictions_or_gaps"] + body["differentials_to_exclude"]
    )
    assert len(all_claims) == 3
    for claim in all_claims:
        if claim["basis"] == "sourced":
            assert claim["sources"], "sourced claim must carry >=1 SourceRef"
        else:
            assert claim["basis"] == "needs_confirmation"
            assert claim["sources"] == []


# ---------------------------------------------------------------------------
# 15. Invented/unknown source id -> needs_confirmation, never a crash, never a
#     fabricated source.
# ---------------------------------------------------------------------------


def test_invented_source_id_becomes_needs_confirmation(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    content = json.dumps(
        {
            "key_issues": [
                {"text": "Một phát hiện không có căn cứ rõ ràng.", "source_ids": ["lab:does-not-exist"]}
            ],
            "contradictions_or_gaps": [],
            "differentials_to_exclude": [],
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["key_issues"]) == 1
    claim = body["key_issues"][0]
    assert claim["sources"] == []
    assert claim["basis"] == "needs_confirmation"
    assert claim["confidence"] == "low"


# ---------------------------------------------------------------------------
# 16. Genuinely malformed top-level structure (wrong type, not just wrong
#     content) -> 422 with ONLY the friendly detail, never raw model text.
# ---------------------------------------------------------------------------


def test_malformed_top_level_type_returns_422(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    content = json.dumps(
        {
            "key_issues": "not a list",
            "contradictions_or_gaps": [],
            "differentials_to_exclude": [],
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"] == "Meto không thể xử lý phản hồi AI cho yêu cầu này. Vui lòng thử lại."
    assert "not a list" not in str(body)


# ---------------------------------------------------------------------------
# 17. Every endpoint's response carries a non-empty `disclaimer`.
# ---------------------------------------------------------------------------


def test_all_endpoints_include_nonempty_disclaimer(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    content = json.dumps(
        {
            "key_issues": [],
            "contradictions_or_gaps": [],
            "differentials_to_exclude": [],
            "questions": [],
            "items": [],
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    for path in ("ai-summary", "ai-analysis", "ai-questions", "ai-advice"):
        resp = client.post(
            f"{API}/doctor/patients/{ctx['patient_id']}/{path}",
            json={},
            headers=_headers(ctx["user_id"]),
        )
        assert resp.status_code == 200, (path, resp.text)
        assert resp.json()["disclaimer"], path


# ---------------------------------------------------------------------------
# 18. Regression: a consultation whose access grant has been revoked
#     (COMPLETED lifecycle) must 403 on the copilot route itself.
# ---------------------------------------------------------------------------


def test_consultation_revoked_access_returns_403(client, db, monkeypatch):
    from app.services import consultation as consult_svc
    from app.services import consultation_payment

    from tests.consultation_factories import CONSENT_ALL_CATEGORIES, create_doctor, create_patient

    _enable_flag(monkeypatch)
    doctor = create_doctor(db)
    _user, profile = create_patient(db)
    consultation = consult_svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True,
        consent_categories=CONSENT_ALL_CATEGORIES
    )
    consultation_payment.pay_mock(db, consultation, patient_profile_id=profile.id)
    _grant_ai_use_consent(db, patient_id=profile.id, doctor_user_id=doctor.user_id)
    consult_svc.complete(db, consultation.id, doctor_user_id=doctor.user_id)
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    resp = client.post(
        f"{API}/doctor/patients/{profile.id}/ai-summary",
        json={"consultation_id": consultation.id},
        headers=_headers(doctor.user_id),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Async-safety regression: get_analysis/get_questions/get_advice must never run
# blocking DB reads directly on the event loop — every DB round-trip (context
# assembly + the outcome audit write) must be dispatched through
# ``run_in_threadpool``. This guards against re-introducing a blocking call
# inline in one of these coroutines.
# ---------------------------------------------------------------------------


def test_analysis_threads_context_fetch_and_audit_write_off_event_loop(client, db, monkeypatch):
    """Wrap ``clinical_copilot.run_in_threadpool`` to record every dispatched
    callable while still executing it for real (so the request behaves
    normally). A passing test proves both that the blocking DB-context
    assembly (``_fetch_context``) and the audit write (``_record``) go through
    the threadpool — not inline in the ``async def`` body — and that exactly
    one of each happens for one successful request (no duplicate audit rows)."""
    import app.services.clinical_copilot as svc

    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    real_run_in_threadpool = svc.run_in_threadpool
    dispatched: list[str] = []

    async def _tracking_run_in_threadpool(func, *args, **kwargs):
        dispatched.append(getattr(func, "__name__", repr(func)))
        return await real_run_in_threadpool(func, *args, **kwargs)

    monkeypatch.setattr(svc, "run_in_threadpool", _tracking_run_in_threadpool)

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )

    assert resp.status_code == 200
    # The blocking context-fetch closure ran through the threadpool exactly once...
    assert dispatched.count("_fetch_context") == 1
    # ...and so did the single "generated" audit write — never inline, never twice.
    assert dispatched.count("_record") == 1


def _tracked_run_in_threadpool(svc, monkeypatch) -> list[str]:
    """Shared harness for the questions/advice threadpool-dispatch regression
    tests below — identical wiring to
    ``test_analysis_threads_context_fetch_and_audit_write_off_event_loop``."""
    real_run_in_threadpool = svc.run_in_threadpool
    dispatched: list[str] = []

    async def _tracking_run_in_threadpool(func, *args, **kwargs):
        dispatched.append(getattr(func, "__name__", repr(func)))
        return await real_run_in_threadpool(func, *args, **kwargs)

    monkeypatch.setattr(svc, "run_in_threadpool", _tracking_run_in_threadpool)
    return dispatched


def test_questions_threads_context_fetch_and_audit_write_off_event_loop(client, db, monkeypatch):
    """Same guard as the ai-analysis regression test above, for ai-questions."""
    import app.services.clinical_copilot as svc

    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))
    dispatched = _tracked_run_in_threadpool(svc, monkeypatch)

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-questions",
        json={},
        headers=_headers(ctx["user_id"]),
    )

    assert resp.status_code == 200
    assert dispatched.count("_fetch_context") == 1
    assert dispatched.count("_record") == 1


def test_advice_threads_context_fetch_and_audit_write_off_event_loop(client, db, monkeypatch):
    """Same guard as the ai-analysis regression test above, for ai-advice."""
    import app.services.clinical_copilot as svc

    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))
    dispatched = _tracked_run_in_threadpool(svc, monkeypatch)

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-advice",
        json={},
        headers=_headers(ctx["user_id"]),
    )

    assert resp.status_code == 200
    assert dispatched.count("_fetch_context") == 1
    assert dispatched.count("_record") == 1


# ---------------------------------------------------------------------------
# Fix 1 regression: metric SourceRef ids are row-scoped (per HealthMetric.id),
# never a bare category label — and track whichever row is currently freshest.
# ---------------------------------------------------------------------------


def test_metric_source_ref_id_is_row_scoped_and_tracks_freshest_row(client, db, monkeypatch):
    """Two `weight` HealthMetric rows (same metric_type, different ids/dates).
    `priority.sources`' SourceRef.id for the weight finding must be
    `metric:<HealthMetric.id>` of the SPECIFIC freshest row — never the
    type-only `metric:weight` string — and must change to track whichever row
    becomes freshest, proving it is never ambiguous between the two rows."""
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    row1 = HealthMetric(
        patient_id=ctx["patient_id"],
        metric_type="weight",
        value=68.0,
        unit="kg",
        measured_at=dt.datetime(2026, 1, 1, 8, 0),
        source="manual",
        status="high",
    )
    db.add(row1)
    db.commit()
    db.refresh(row1)

    resp1 = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp1.status_code == 200
    metric_sources1 = [s for s in resp1.json()["priority"]["sources"] if s["type"] == "metric"]
    assert len(metric_sources1) == 1
    assert metric_sources1[0]["id"] == f"metric:{row1.id}"
    assert metric_sources1[0]["id"] != "metric:weight"
    assert metric_sources1[0]["date"] == row1.measured_at.isoformat()

    row2 = HealthMetric(
        patient_id=ctx["patient_id"],
        metric_type="weight",
        value=71.0,
        unit="kg",
        measured_at=dt.datetime(2026, 2, 1, 8, 0),
        source="manual",
        status="high",
    )
    db.add(row2)
    db.commit()
    db.refresh(row2)

    resp2 = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp2.status_code == 200
    metric_sources2 = [s for s in resp2.json()["priority"]["sources"] if s["type"] == "metric"]
    assert len(metric_sources2) == 1
    # Now backed by the NEW freshest row — id changes, never the older row's id.
    assert metric_sources2[0]["id"] == f"metric:{row2.id}"
    assert metric_sources2[0]["id"] != metric_sources1[0]["id"]
    assert metric_sources2[0]["date"] == row2.measured_at.isoformat()


# ---------------------------------------------------------------------------
# Aliased-raw-type source resolution: `MetricInsight.metric_type` is the
# CANONICAL group key (`clinical_insight.canonical_metric_key`), but a
# `HealthMetric` row may be stored under a raw ALIAS type (e.g. "weight_kg"
# folds to canonical "weight"). `_metric_row_index` must key by the same
# canonical identity so the citation always resolves to the real row — never
# degrading to the dateless, type-only `metric:<canonical>` fallback merely
# because the row was indexed under a different alias.
# ---------------------------------------------------------------------------


def _metric_sources(resp) -> list[dict]:
    return [s for s in resp.json()["priority"]["sources"] if s["type"] == "metric"]


def test_aliased_raw_metric_type_resolves_to_real_row_not_type_only_fallback(
    client, db, monkeypatch
):
    """A single HealthMetric row stored under the raw alias `metric_type="weight_kg"`
    must still be cited by its own row id/date — never `metric:weight` (the
    canonical, dateless, type-only fallback)."""
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    row = HealthMetric(
        patient_id=ctx["patient_id"],
        metric_type="weight_kg",
        value=90.0,
        unit="kg",
        measured_at=dt.datetime(2026, 1, 5, 8, 0),
        source="manual",
        status="high",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    metric_sources = _metric_sources(resp)
    assert len(metric_sources) == 1
    assert metric_sources[0]["id"] == f"metric:{row.id}"
    assert metric_sources[0]["id"] != "metric:weight"
    assert metric_sources[0]["date"] == row.measured_at.isoformat()


def test_mixed_alias_freshest_row_cites_newer_row_across_aliases(client, db, monkeypatch):
    """Two rows under DIFFERENT raw aliases of the SAME canonical group
    ("weight" and "weight_kg" both fold to "weight"): the older row uses the
    bare canonical raw type, the newer row uses the alias. The citation must
    track the freshest row ACROSS both raw types, not the freshest within one
    raw type (that would be the shape of the original bug)."""
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    older = HealthMetric(
        patient_id=ctx["patient_id"],
        metric_type="weight",
        value=68.0,
        unit="kg",
        measured_at=dt.datetime(2026, 1, 1, 8, 0),
        source="manual",
        status="high",
    )
    newer = HealthMetric(
        patient_id=ctx["patient_id"],
        metric_type="weight_kg",
        value=93.0,
        unit="kg",
        measured_at=dt.datetime(2026, 2, 1, 8, 0),
        source="manual",
        status="high",
    )
    db.add_all([older, newer])
    db.commit()
    db.refresh(older)
    db.refresh(newer)

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    metric_sources = _metric_sources(resp)
    assert len(metric_sources) == 1
    assert metric_sources[0]["id"] == f"metric:{newer.id}"
    assert metric_sources[0]["id"] != f"metric:{older.id}"
    assert metric_sources[0]["date"] == newer.measured_at.isoformat()


def test_waist_alias_also_resolves_to_real_row(client, db, monkeypatch):
    """Same shape of bug/fix as the weight/weight_kg case, proven for a second
    alias pair (`waist` -> canonical `waist_cm`) to show the fix isn't
    hardcoded to the weight case specifically."""
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    row = HealthMetric(
        patient_id=ctx["patient_id"],
        metric_type="waist",
        value=105.0,
        unit="cm",
        measured_at=dt.datetime(2026, 1, 10, 8, 0),
        source="manual",
        status="high",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    metric_sources = _metric_sources(resp)
    assert len(metric_sources) == 1
    assert metric_sources[0]["id"] == f"metric:{row.id}"
    assert metric_sources[0]["id"] != "metric:waist_cm"
    assert metric_sources[0]["date"] == row.measured_at.isoformat()


def test_distinct_canonical_groups_never_collide_in_source_map(client, db, monkeypatch):
    """Two rows belonging to DIFFERENT canonical groups (weight-family vs
    waist-family) must produce two DISTINCT citations, each attributed to its
    own row — proving canonicalization only merges TRUE aliases of the same
    group and never accidentally merges unrelated groups."""
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    weight_row = HealthMetric(
        patient_id=ctx["patient_id"],
        metric_type="weight_kg",
        value=95.0,
        unit="kg",
        measured_at=dt.datetime(2026, 1, 1, 8, 0),
        source="manual",
        status="high",
    )
    waist_row = HealthMetric(
        patient_id=ctx["patient_id"],
        metric_type="waist",
        value=110.0,
        unit="cm",
        measured_at=dt.datetime(2026, 1, 2, 8, 0),
        source="manual",
        status="high",
    )
    db.add_all([weight_row, waist_row])
    db.commit()
    db.refresh(weight_row)
    db.refresh(waist_row)

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    metric_sources = {s["id"]: s for s in _metric_sources(resp)}
    assert len(metric_sources) == 2
    assert metric_sources[f"metric:{weight_row.id}"]["date"] == weight_row.measured_at.isoformat()
    assert metric_sources[f"metric:{waist_row.id}"]["date"] == waist_row.measured_at.isoformat()
    # Neither collided into a type-only fallback nor swapped dates.
    assert metric_sources[f"metric:{weight_row.id}"]["id"] != metric_sources[
        f"metric:{waist_row.id}"
    ]["id"]


# ---------------------------------------------------------------------------
# Fix 2 regression: get_questions/get_advice must never crash on a
# non-string `group`/`category` from the LLM (frozenset membership test on an
# unhashable value raises TypeError without an isinstance guard first).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_group", [["current_symptoms"], {"a": 1}, None, 5], ids=["list", "dict", "null", "int"])
def test_ai_questions_malformed_group_dropped_not_500(client, db, monkeypatch, bad_group):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    content = json.dumps(
        {
            "questions": [
                {
                    "group": bad_group,
                    "question_vi": "Triệu chứng bắt đầu khi nào?",
                    "reason_vi": "Xác định mốc thời gian khởi phát.",
                }
            ]
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-questions",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    assert resp.json()["questions"] == []


def test_ai_questions_regression_list_group_does_not_500(client, db, monkeypatch):
    """Exact case found broken during review: `group` returned as a list —
    `frozenset({'a'}).__contains__(['x'])` raises TypeError without an
    isinstance guard evaluated first."""
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    content = json.dumps(
        {"questions": [{"group": ["current_symptoms"], "question_vi": "x", "reason_vi": "y"}]}
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-questions",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    assert resp.json()["questions"] == []


@pytest.mark.parametrize("bad_category", [["home_monitoring"], {"a": 1}, None, 5], ids=["list", "dict", "null", "int"])
def test_ai_advice_malformed_category_dropped_not_500(client, db, monkeypatch, bad_category):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    content = json.dumps(
        {"items": [{"category": bad_category, "text_vi": "Theo dõi đường huyết tại nhà mỗi ngày."}]}
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-advice",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# Additional low-cost coverage.
# ---------------------------------------------------------------------------


def test_contradiction_flag_downgrades_confidence_never_high(client, db, monkeypatch):
    """A data_quality_flag='flag' lab result, with otherwise-complete data
    (completeness_ratio >= 0.75), must downgrade confidence to 'medium' —
    NEVER 'high' while a data-quality flag exists."""
    from app.models.clinical import LabResult, Medication

    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    profile = db.query(PatientProfile).filter(PatientProfile.id == ctx["patient_id"]).first()
    profile.known_conditions = json.dumps(["Đái tháo đường type 2"])
    profile.allergies = json.dumps(["Penicillin"])
    db.commit()

    db.add(
        Medication(
            patient_id=ctx["patient_id"], name="Metformin", dose="500mg", frequency="2 lần/ngày"
        )
    )
    db.add(
        HealthMetric(
            patient_id=ctx["patient_id"],
            metric_type="weight",
            value=70.0,
            unit="kg",
            measured_at=dt.datetime.now(dt.UTC),
            source="manual",
            status="normal",
        )
    )
    db.add(
        LabResult(
            patient_id=ctx["patient_id"],
            test_name="HbA1c",
            canonical_name="hba1c",
            value=6.0,
            unit="%",
            test_date=dt.date.today(),
            data_quality_flag="flag",
            verified_by_user=True,
        )
    )
    db.commit()

    content = json.dumps(
        {"key_issues": [], "contradictions_or_gaps": [], "differentials_to_exclude": []}
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    assert resp.json()["confidence"] == "medium"


def test_low_confidence_can_coexist_with_urgent_priority(client, db, monkeypatch):
    """A near-empty record (completeness_ratio < 0.34) with one critical
    finding must yield BOTH confidence == 'low' AND priority.level ==
    'urgent' in the same response — the two computations are independently
    extreme without interfering with each other."""
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    _seed_critical_finding(db, patient_id=ctx["patient_id"])
    _patch_registry(monkeypatch, _StubProvider(content=VALID_ANALYSIS_JSON))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["confidence"] == "low"
    assert body["priority"]["level"] == "urgent"


def test_key_issues_text_as_int_is_dropped(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    content = json.dumps(
        {
            "key_issues": [{"text": 123, "source_ids": []}],
            "contradictions_or_gaps": [],
            "differentials_to_exclude": [],
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    assert resp.json()["key_issues"] == []


def test_key_issues_text_as_none_is_dropped(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    content = json.dumps(
        {
            "key_issues": [{"text": None, "source_ids": []}],
            "contradictions_or_gaps": [],
            "differentials_to_exclude": [],
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    assert resp.json()["key_issues"] == []


def test_key_issues_source_ids_as_bare_string_treated_as_no_sources(client, db, monkeypatch):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    content = json.dumps(
        {
            "key_issues": [{"text": "Có nội dung hợp lệ.", "source_ids": "not-a-list"}],
            "contradictions_or_gaps": [],
            "differentials_to_exclude": [],
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["key_issues"]) == 1
    assert body["key_issues"][0]["basis"] == "needs_confirmation"
    assert body["key_issues"][0]["sources"] == []


def test_key_issues_source_ids_with_non_string_elements_treated_as_no_sources(
    client, db, monkeypatch
):
    _enable_flag(monkeypatch)
    ctx = _fully_authorized_doctor(db)
    content = json.dumps(
        {
            "key_issues": [{"text": "Có nội dung hợp lệ.", "source_ids": [1, 2, 3]}],
            "contradictions_or_gaps": [],
            "differentials_to_exclude": [],
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    resp = client.post(
        f"{API}/doctor/patients/{ctx['patient_id']}/ai-analysis",
        json={},
        headers=_headers(ctx["user_id"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["key_issues"]) == 1
    assert body["key_issues"][0]["basis"] == "needs_confirmation"
    assert body["key_issues"][0]["sources"] == []


async def test_get_analysis_drops_consultation_on_patient_id_mismatch(db, monkeypatch):
    """Bypasses the route entirely (calls the service function directly) to
    prove `get_analysis` itself never trusts a consultation whose patient_id
    doesn't match the requested patient_id — belt-and-suspenders behind the
    route's `_authorize` gate, which already 400s a genuine mismatch before
    this code path is ever reached in normal operation."""
    from app.services import clinical_copilot as svc
    from app.services import consultation as consult_svc
    from app.services import consultation_payment

    from tests.consultation_factories import CONSENT_ALL_CATEGORIES, create_doctor, create_patient

    doctor = create_doctor(db)
    _user_a, profile_a = create_patient(db)
    _user_b, profile_b = create_patient(db)
    consultation = consult_svc.create_consultation(
        db, patient_id=profile_a.id, doctor_id=doctor.id, data_consent_accepted=True,
        consent_categories=CONSENT_ALL_CATEGORIES
    )
    consultation_payment.pay_mock(db, consultation, patient_profile_id=profile_a.id)

    content = json.dumps(
        {
            "key_issues": [
                {
                    "text": "Trích dẫn bối cảnh buổi tư vấn.",
                    "source_ids": [f"consultation:{consultation.id}"],
                }
            ],
            "contradictions_or_gaps": [],
            "differentials_to_exclude": [],
        }
    )
    _patch_registry(monkeypatch, _StubProvider(content=content))

    # patient_id says profile_b, but consultation_id belongs to profile_a.
    result = await svc.get_analysis(
        db,
        doctor_user_id=doctor.user_id,
        patient_id=profile_b.id,
        consultation_id=consultation.id,
        chief_complaint="Không thuộc về patient_b.",
    )

    # The consultation source id must NOT be resolvable — the service dropped
    # the mismatched consultation, so the claim citing it degrades to
    # needs_confirmation instead of being falsely treated as sourced.
    assert result.key_issues[0].basis == "needs_confirmation"
    assert result.key_issues[0].sources == []
