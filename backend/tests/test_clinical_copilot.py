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

    from tests.consultation_factories import create_doctor, create_patient

    _enable_flag(monkeypatch)
    doctor = create_doctor(db)
    _u1, profile_a = create_patient(db)
    _u2, profile_b = create_patient(db)
    consultation = consult_svc.create_consultation(
        db, patient_id=profile_a.id, doctor_id=doctor.id, data_consent_accepted=True
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

    from tests.consultation_factories import create_doctor, create_patient

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
    db.add(
        HealthMetric(
            patient_id=profile.id,
            metric_type="weight",
            value=70.0,
            unit="kg",
            measured_at=metric_date,
            source="manual",
            status="normal",
        )
    )

    lab_date = dt.date(2026, 1, 10)
    lab_row = LabResult(
        patient_id=profile.id,
        test_name="HbA1c",
        canonical_name="hba1c",
        value=7.0,
        unit="%",
        test_date=lab_date,
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

    consultation = consult_svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
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
    assert source_map["metric:weight"].date == metric_date.isoformat()
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

    from tests.consultation_factories import create_doctor, create_patient

    _enable_flag(monkeypatch)
    doctor = create_doctor(db)
    _user, profile = create_patient(db)
    consultation = consult_svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
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
