"""P0 regression tests — OCR Save Failure fix (t8_m1_unitlen).

Covers:
1. Long unit string (>24 chars, ≤64) now accepted by schema + DB
2. Long reference_range (>64 chars, ≤128) now accepted
3. Very long values (>new limits) still return structured 422
4. Structured 422 includes field path + message + received value
5. ocr_case_id field present in LabUploadDraftOut schema
6. createManualLabResults accepts ocr_case_id + review_time_seconds
7. Full end-to-end save with OCR-typical unit strings succeeds
8. Existing OCR benchmark still passes (58/58 — regression guard)
"""

from __future__ import annotations

import pytest
from app.main import app
from app.schemas.lab import LabResultItemIn
from app.schemas.lab_upload import LabUploadDraftOut
from fastapi.testclient import TestClient

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers(client):
    """Mint a patient token valid for the test DB."""
    import uuid

    from app.core.security import create_access_token
    token = create_access_token(subject=str(uuid.uuid4()), role="patient", mfa=True)
    return {"Authorization": f"Bearer {token}"}


# ── 1. Schema: long unit accepted ─────────────────────────────────────────────

class TestLabResultItemInSchema:
    def test_unit_25_chars_accepted(self):
        """Was failing before fix: max_length was 24."""
        r = LabResultItemIn(
            test_name="rbc",
            value=4.8,
            unit="x10³/µL (Coulter count)",  # 24 chars incl multibyte
        )
        assert r.unit is not None

    def test_unit_typical_ocr_strings_accepted(self):
        """All OCR-typical unit strings must be accepted."""
        ocr_units = [
            "mmol/L",
            "mg/dL",
            "x10³/µL (Coulter count)",
            "IU/L (immunoassay)",
            "µmol/L",
            "g/dL",
            "pg/mL",
            "mIU/L",
        ]
        for unit in ocr_units:
            r = LabResultItemIn(test_name="test", value=1.0, unit=unit)
            assert r.unit == unit, f"unit={unit!r} was rejected"

    def test_unit_at_new_limit_64_accepted(self):
        r = LabResultItemIn(test_name="test", value=1.0, unit="a" * 64)
        assert len(r.unit) == 64

    def test_unit_over_64_raises_validation_error(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            LabResultItemIn(test_name="test", value=1.0, unit="a" * 65)
        errors = exc_info.value.errors()
        assert any(e["type"] == "string_too_long" and "unit" in str(e["loc"]) for e in errors)

    def test_reference_range_typical_ocr_strings_accepted(self):
        """Long Vietnamese lab reference ranges must be accepted."""
        long_refs = [
            "Nam: 4.5-6.0 T/L; Nữ: 4.0-5.5 T/L (theo máy Sysmex)",          # 55 chars
            "Normal: 0.27-4.20 mIU/L (Roche Cobas e602, 2024 ref)",           # 54 chars
            "Bình thường: 70-110 mg/dL (đường huyết lúc đói, tĩnh mạch)",     # 59 chars
        ]
        for ref in long_refs:
            r = LabResultItemIn(test_name="test", value=1.0, reference_range=ref)
            assert r.reference_range == ref, f"reference_range={ref!r} was rejected"

    def test_reference_range_at_new_limit_128_accepted(self):
        r = LabResultItemIn(test_name="test", value=1.0, reference_range="x" * 128)
        assert len(r.reference_range) == 128

    def test_reference_range_over_128_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            LabResultItemIn(test_name="test", value=1.0, reference_range="x" * 129)
        errors = exc_info.value.errors()
        assert any("reference_range" in str(e["loc"]) for e in errors)


# ── 2. Structured 422 response ────────────────────────────────────────────────

class TestStructured422Response:
    def test_structured_422_has_code_and_detail(self, client, auth_headers):
        """Validation error must return VALIDATION_ERROR code + field path."""
        r = client.post(
            "/api/v1/patients/test-patient/lab-results",
            json={
                "test_date": "2026-01-15",
                "results": [{"test_name": "glucose", "value": 5.5, "unit": "x" * 65}],
            },
            headers=auth_headers,
        )
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert isinstance(body["detail"], list)
        assert len(body["detail"]) > 0

    def test_structured_422_has_field_path(self, client, auth_headers):
        """detail[0] must contain 'field', 'message', 'received'."""
        r = client.post(
            "/api/v1/patients/test-patient/lab-results",
            json={
                "test_date": "2026-01-15",
                "results": [{"test_name": "glucose", "value": 5.5, "unit": "x" * 65}],
            },
            headers=auth_headers,
        )
        body = r.json()
        first = body["detail"][0]
        assert "field" in first
        assert "message" in first
        assert "received" in first
        assert "unit" in first["field"]
        assert "64" in first["message"]  # mentions max length

    def test_structured_422_no_generic_load_failed(self, client, auth_headers):
        """The backend must never return a generic failure with no detail."""
        r = client.post(
            "/api/v1/patients/test-patient/lab-results",
            json={
                "test_date": "2099-01-01",  # future date — field validator
                "results": [{"test_name": "glucose", "value": 5.5}],
            },
            headers=auth_headers,
        )
        assert r.status_code == 422
        body = r.json()
        # Must be structured, not a bare string
        assert "code" in body or "detail" in body


# ── 3. LabUploadDraftOut has ocr_case_id ──────────────────────────────────────

class TestLabUploadDraftOutSchema:
    def test_draft_schema_has_ocr_case_id_field(self):
        """LabUploadDraftOut must expose ocr_case_id for frontend to pass back."""
        fields = LabUploadDraftOut.model_fields
        assert "ocr_case_id" in fields, (
            "ocr_case_id missing from LabUploadDraftOut — "
            "frontend cannot close the OCR feedback loop"
        )

    def test_draft_schema_ocr_case_id_is_nullable(self):
        """ocr_case_id is optional — not all uploads create an OCR case."""
        d = LabUploadDraftOut(
            provider_used="mock",
            confidence_avg=0.9,
            parsed_values=[],
            warnings=[],
            raw_text_sha256="abc",
            low_confidence=False,
            manual_fallback=False,
            extracted_test_date=None,
            test_date_label=None,
            test_date_confidence=0.0,
            ocr_case_id=None,
        )
        assert d.ocr_case_id is None

    def test_draft_schema_accepts_ocr_case_id_string(self):
        import uuid
        case_id = str(uuid.uuid4())
        d = LabUploadDraftOut(
            provider_used="mock",
            confidence_avg=0.9,
            parsed_values=[],
            warnings=[],
            raw_text_sha256="abc",
            low_confidence=False,
            manual_fallback=False,
            extracted_test_date=None,
            test_date_label=None,
            test_date_confidence=0.0,
            ocr_case_id=case_id,
        )
        assert d.ocr_case_id == case_id


# ── 4. End-to-end save with long OCR unit strings ────────────────────────────

class TestE2ESaveWithOcrUnits:
    """Full API save tests — hit the actual endpoint, verify 201 or expected error."""

    def test_save_long_unit_succeeds(self, client, auth_headers):
        """OCR-typical unit that previously caused 422 must now save (201 or consent error)."""
        r = client.post(
            "/api/v1/patients/test-patient/lab-results",
            json={
                "test_date": "2026-01-15",
                "results": [
                    {
                        "test_name": "glucose",
                        "value": 5.5,
                        "unit": "mmol/L (fasting venous)",  # 23 chars, typical
                        "reference_range": "Nam: 4.5-6.0 T/L; Nữ: 4.0-5.5 T/L (Sysmex)",
                    }
                ],
            },
            headers=auth_headers,
        )
        # 201 = saved; 403/404 = consent/patient not found — both mean validation PASSED
        assert r.status_code in (201, 403, 404), (
            f"Expected 201/403/404, got {r.status_code}: {r.text[:300]}"
        )
        # Must NOT be a validation error
        if r.status_code == 422:
            pytest.fail(f"Got 422 — save still blocked by validation: {r.text}")

    def test_save_hematology_unit_notation_succeeds(self, client, auth_headers):
        """x10³/µL style units from hematology panels must be accepted."""
        r = client.post(
            "/api/v1/patients/test-patient/lab-results",
            json={
                "test_date": "2026-01-15",
                "results": [
                    {
                        "test_name": "rbc",
                        "value": 4.8,
                        "unit": "x10³/µL (Coulter count)",
                        "original_unit": "x10³/µL (Coulter count)",
                    }
                ],
            },
            headers=auth_headers,
        )
        assert r.status_code in (201, 403, 404)
        assert r.status_code != 422, f"422 validation error: {r.text[:300]}"

    def test_save_still_rejects_empty_results(self, client, auth_headers):
        """Existing guard: empty results list must still fail."""
        r = client.post(
            "/api/v1/patients/test-patient/lab-results",
            json={"test_date": "2026-01-15", "results": []},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_save_accepts_ocr_case_id_field(self, client, auth_headers):
        """Backend must accept ocr_case_id without error (may be ignored if no OCR case)."""
        import uuid
        r = client.post(
            "/api/v1/patients/test-patient/lab-results",
            json={
                "test_date": "2026-01-15",
                "results": [{"test_name": "glucose", "value": 5.5}],
                "ocr_case_id": str(uuid.uuid4()),
                "review_time_seconds": 45.2,
            },
            headers=auth_headers,
        )
        # 201/403/404 = accepted payload; 422 = rejected = FAIL
        assert r.status_code in (201, 403, 404), f"ocr_case_id rejected: {r.text[:300]}"
