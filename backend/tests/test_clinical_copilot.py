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
    '"contradictions_or_gaps": [], "differentials_to_exclude": []}'
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
    assert resp.status_code == 200
    body = resp.json()
    # The raw garbage must never be passed through verbatim as a finding.
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
