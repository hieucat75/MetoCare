"""OCR Lab Upload track — draft pipeline, parser, SSRF guard, flags, confirm-save.

These tests are CI-safe: they NEVER require the tesseract binary. The OCR step is
monkeypatched with deterministic text where a draft is needed; the parser, SSRF
guard, PDF text-layer, validation, flags, RBAC, and confirm-save paths run for
real. One opt-in test exercising the real Tesseract binary is skipped when it is
not installed.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from app.core import ssrf
from app.domain.lab_interpreter import LabStatus, classify_value, interpret_value
from app.services import lab_parser, lab_upload
from app.services.ocr_engine import OcrTextResult

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

PNG_HEADER = b"\x89PNG\r\n\x1a\n"
JPEG_HEADER = b"\xff\xd8\xff\xe0"

SAMPLE_VN_LAB = """PHÒNG KHÁM ĐA KHOA — PHIẾU KẾT QUẢ XÉT NGHIỆM
Glucose lúc đói: 126 mg/dL  (3.9 - 6.1)
HbA1c: 6.8 %
Cholesterol toàn phần 210 mg/dL
Triglyceride 320 mg/dL
HDL-C 38 mg/dL
LDL-C 145 mg/dL
Creatinine 1.1 mg/dL
ALT (SGPT) 45 U/L
TSH 2.1 mIU/L
"""


@pytest.fixture
def ocr_on(monkeypatch):
    monkeypatch.setenv("MCP_FEATURE_OCR", "true")


def _png(data_text: bytes = b"x" * 32) -> bytes:
    return PNG_HEADER + data_text


def _patch_ocr(monkeypatch, text=SAMPLE_VN_LAB, confidence=0.92, provider="tesseract"):
    monkeypatch.setattr(
        lab_upload, "run_ocr",
        lambda data, mime: OcrTextResult(text=text, confidence=confidence, provider=provider),
    )


# --------------------------------------------------------------------------- #
# Parser (pure python — no binary)
# --------------------------------------------------------------------------- #

def test_parser_recognises_core_panel():
    values = lab_parser.parse_lab_text(SAMPLE_VN_LAB)
    by_name = {v.test_name: v for v in values}
    assert by_name["fasting_glucose"].value == 126.0
    assert by_name["hba1c"].value == 6.8
    assert by_name["total_cholesterol"].value == 210.0
    assert by_name["triglyceride"].value == 320.0
    assert by_name["hdl"].value == 38.0
    assert by_name["ldl"].value == 145.0
    assert by_name["creatinine"].value == 1.1
    assert by_name["alt"].value == 45.0
    assert by_name["tsh"].value == 2.1
    assert len(values) >= 7


def test_parser_handles_vn_decimal_comma():
    values = lab_parser.parse_lab_text("Creatinine: 1,2 mg/dL")
    assert values and values[0].value == pytest.approx(1.2)


def test_parser_drops_unknown_lines():
    assert lab_parser.parse_lab_text("Tên bệnh nhân: Nguyễn Văn A\nĐịa chỉ: Hà Nội") == []


def test_additional_aliases_injected_for_canonical_biomarker():
    """additional_aliases keyed by a real canonical name are injected into the parser."""
    from app.domain.hospital_profiles import HospitalProfile

    profile = HospitalProfile(
        hospital_id="test_hospital",
        name="Test Hospital",
        header_patterns=("test hospital",),
        unit_system="conventional",
        additional_aliases={
            "fasting_glucose": ("duong huyet doi", "xet nghiem glucose"),
        },
    )
    text = "test hospital\nxet nghiem glucose 95 mg/dL"
    values = lab_parser.parse_lab_text(text, hospital_profile=profile)
    by_name = {v.test_name: v for v in values}
    assert "fasting_glucose" in by_name, (
        "hospital-specific alias 'xet nghiem glucose' was not injected for fasting_glucose"
    )
    assert by_name["fasting_glucose"].value == pytest.approx(95.0)


def test_parser_extended_biomarkers():
    text = (
        "eGFR 85 mL/min\nUrea 18 mg/dL\nGGT 30 U/L\n"
        "FT4 15 pmol/L\nHemoglobin 13.5 g/dL\nTiểu cầu 250"
    )
    names = {v.test_name for v in lab_parser.parse_lab_text(text)}
    assert {"egfr", "urea", "ggt", "ft4", "hemoglobin", "platelet"} <= names


def test_parser_uric_acid_vn_alias():
    values = lab_parser.parse_lab_text("Axit uric: 6.2 mg/dL")
    assert values and values[0].test_name == "uric_acid"
    assert values[0].value == pytest.approx(6.2)


def test_parser_uric_acid_english_alias():
    values = lab_parser.parse_lab_text("Uric Acid 8.5 mg/dL")
    assert values and values[0].test_name == "uric_acid"
    assert values[0].value == pytest.approx(8.5)


def test_parser_random_glucose_vn_alias():
    values = lab_parser.parse_lab_text("Đường huyết ngẫu nhiên: 145 mg/dL")
    assert values and values[0].test_name == "random_glucose"
    assert values[0].value == pytest.approx(145.0)


def test_parser_random_glucose_english_alias():
    values = lab_parser.parse_lab_text("Random Blood Sugar 180 mg/dL")
    assert values and values[0].test_name == "random_glucose"
    assert values[0].value == pytest.approx(180.0)


def test_parser_uric_acid_and_random_glucose_in_panel():
    """Both new biomarkers appear in a realistic mixed-language panel."""
    text = (
        "HbA1c 6.8 %\n"
        "Đường huyết ngẫu nhiên: 165 mg/dL\n"
        "Axit uric 7.4 mg/dL\n"
        "Creatinine 1.0 mg/dL"
    )
    by_name = {v.test_name: v for v in lab_parser.parse_lab_text(text)}
    assert "random_glucose" in by_name
    assert by_name["random_glucose"].value == pytest.approx(165.0)
    assert "uric_acid" in by_name
    assert by_name["uric_acid"].value == pytest.approx(7.4)
    assert "hba1c" in by_name
    assert "creatinine" in by_name


def test_uric_acid_critical_high_classified():
    """Value above critical_high (10.0) should be CRITICAL."""
    from app.domain.lab_interpreter import LabStatus, classify_value
    assert classify_value("uric_acid", 11.0) == LabStatus.CRITICAL


def test_uric_acid_normal_classified():
    from app.domain.lab_interpreter import LabStatus, classify_value
    assert classify_value("uric_acid", 5.5) == LabStatus.NORMAL


def test_random_glucose_high_classified():
    from app.domain.lab_interpreter import LabStatus, classify_value
    assert classify_value("random_glucose", 200.0) == LabStatus.HIGH


def test_new_biomarkers_promote_to_health_metric(client, patient, ocr_on):
    """uric_acid and random_glucose saved via manual-entry are promoted to health_metrics."""
    pid = patient["patient_id"]
    save = client.post(
        f"/api/v1/patients/{pid}/lab-results",
        json={
            "test_date": "2026-06-01",
            "lab_name": "Test Lab",
            "results": [
                {"test_name": "uric_acid", "value": 6.2, "unit": "mg/dL"},
                {"test_name": "random_glucose", "value": 145.0, "unit": "mg/dL"},
            ],
        },
        headers=patient["headers"],
    )
    assert save.status_code == 201, save.text
    metrics_resp = client.get(
        f"/api/v1/patients/{pid}/metrics",
        headers=patient["headers"],
    )
    assert metrics_resp.status_code == 200
    metric_types = {m["metric_type"] for m in metrics_resp.json()}
    assert "uric_acid" in metric_types
    assert "random_glucose" in metric_types


# --------------------------------------------------------------------------- #
# MIME sniff + validation
# --------------------------------------------------------------------------- #

def test_sniff_mime():
    assert lab_upload.sniff_mime(JPEG_HEADER) == "image/jpeg"
    assert lab_upload.sniff_mime(PNG_HEADER) == "image/png"
    assert lab_upload.sniff_mime(b"%PDF-1.7 ...") == "application/pdf"
    assert lab_upload.sniff_mime(b"plain text") is None


def test_validate_rejects_wrong_mime():
    with pytest.raises(lab_upload.UnsupportedMediaError):
        lab_upload.validate_upload(b"this is not an image")


def test_validate_rejects_oversize(monkeypatch):
    monkeypatch.setattr(
        lab_upload, "get_settings",
        lambda: SimpleNamespace(ocr_max_upload_mb=0, ocr_pdf_max_pages=3, ocr_lang="vie+eng"),
    )
    with pytest.raises(lab_upload.PayloadTooLargeError):
        lab_upload.validate_upload(_png())


def test_validate_accepts_png_within_limit():
    assert lab_upload.validate_upload(_png()) == "image/png"


# --------------------------------------------------------------------------- #
# Draft build (OCR monkeypatched)
# --------------------------------------------------------------------------- #

def test_build_draft_success(monkeypatch):
    _patch_ocr(monkeypatch)
    draft = lab_upload.process_bytes(_png())
    names = {i.canonical for i in draft.parsed_values}
    assert "fasting_glucose" in names
    glu = next(i for i in draft.parsed_values if i.canonical == "fasting_glucose")
    assert glu.value == 126.0 and glu.status == "high"  # 126 > ref 99
    assert draft.provider_used == "tesseract"
    assert draft.raw_text_sha256  # text hash present (audit), not the text itself
    assert not draft.manual_fallback


def test_build_draft_low_confidence_warns(monkeypatch):
    _patch_ocr(monkeypatch, confidence=0.4)
    draft = lab_upload.process_bytes(_png())
    assert draft.low_confidence is True
    assert any("tin cậy" in w.lower() for w in draft.warnings)
    assert all(i.needs_verification for i in draft.parsed_values)


def test_build_draft_ocr_fail_manual_fallback(monkeypatch):
    _patch_ocr(monkeypatch, text="@@@ ###  ???", confidence=0.1)
    draft = lab_upload.process_bytes(_png())
    assert draft.manual_fallback is True
    assert draft.parsed_values == []
    assert any("nhập tay" in w.lower() for w in draft.warnings)


def test_build_draft_pdf_text_layer():
    # A real digital PDF with a text layer (reportlab) — exercises pypdf, no OCR.
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i, line in enumerate(["Glucose 95 mg/dL", "HbA1c 5.4 %", "TSH 1.8 mIU/L"]):
        c.drawString(72, 760 - i * 20, line)
    c.save()
    draft = lab_upload.process_bytes(buf.getvalue())
    names = {i.canonical for i in draft.parsed_values}
    assert {"fasting_glucose", "hba1c", "tsh"} <= names
    assert draft.provider_used == "pdf_text"


# --------------------------------------------------------------------------- #
# SSRF guard
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("url", [
    "http://127.0.0.1/lab.png",
    "http://10.0.0.5/lab.png",
    "http://172.16.0.9/lab.png",
    "http://192.168.1.10/lab.png",
    "http://169.254.169.254/latest/meta-data/",   # IMDS
    "http://169.254.169.254/metadata/instance",    # Azure IMDS
    "https://[::1]/lab.png",
    "ftp://example.com/lab.png",                    # bad scheme
    "file:///etc/passwd",                           # bad scheme
])
def test_ssrf_blocks_private_and_bad_scheme(url):
    with pytest.raises(ssrf.SSRFError):
        ssrf.validate_public_url(url)


def test_ssrf_allows_public_ip_literal():
    assert ssrf.validate_public_url("https://1.1.1.1/lab.png") == ["1.1.1.1"]


def test_ssrf_blocks_metadata_hostname():
    with pytest.raises(ssrf.SSRFError):
        ssrf.validate_public_url("http://metadata.google.internal/x")


# --------------------------------------------------------------------------- #
# Cloud fallback gating (opt-in only; never silently called)
# --------------------------------------------------------------------------- #

def _force_local(monkeypatch, confidence):
    from app.services import ocr_engine
    monkeypatch.setattr(ocr_engine.TesseractEngine, "available", staticmethod(lambda: True))
    monkeypatch.setattr(
        ocr_engine.TesseractEngine, "run",
        lambda self, data: OcrTextResult(
            text="Glucose 99 mg/dL", confidence=confidence, provider="tesseract"
        ),
    )
    return ocr_engine


def test_cloud_not_called_when_flag_off(monkeypatch):
    monkeypatch.delenv("MCP_FEATURE_OCR_CLOUD_FALLBACK", raising=False)
    ocr_engine = _force_local(monkeypatch, confidence=0.3)  # low -> would escalate

    def _boom(*a, **k):
        raise AssertionError("cloud must NOT be called when fallback flag is off")

    monkeypatch.setattr(ocr_engine.AnthropicVisionEngine, "run", _boom)
    res = ocr_engine.run_ocr(b"x", "image/png")
    assert res.provider == "tesseract"
    assert any("tin cậy" in w.lower() for w in res.warnings)


def test_tesseract_no_cloud_escalation_on_low_confidence(monkeypatch):
    """run_ocr never escalates to cloud on low confidence — removed from this layer.
    Zero-biomarker escalation still exists in build_draft(), not in run_ocr()."""
    monkeypatch.delenv("AZURE_DOC_INTEL_KEY", raising=False)
    monkeypatch.delenv("AZURE_DOC_INTEL_ENDPOINT", raising=False)
    ocr_engine = _force_local(monkeypatch, confidence=0.3)

    def _boom(self, data, mime):
        raise AssertionError("cloud must NOT be called from run_ocr()")

    monkeypatch.setattr(ocr_engine.AnthropicVisionEngine, "run", _boom)
    res = ocr_engine.run_ocr(b"x", "image/png")
    assert res.provider == "tesseract"
    assert any("tin cậy" in w.lower() for w in res.warnings)


def test_cloud_flag_on_but_no_key_falls_through(monkeypatch):
    monkeypatch.setenv("MCP_FEATURE_OCR_CLOUD_FALLBACK", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ocr_engine = _force_local(monkeypatch, confidence=0.3)
    monkeypatch.setattr(
        ocr_engine, "get_settings",
        lambda: SimpleNamespace(ocr_cloud_provider="anthropic", ocr_lang="vie+eng"),
    )
    res = ocr_engine.run_ocr(b"x", "image/png")  # must NOT crash
    assert res.provider == "tesseract"


# --------------------------------------------------------------------------- #
# Azure Document Intelligence provider (real impl, mocked HTTP)
# --------------------------------------------------------------------------- #

class _FakeResp:
    """Minimal stand-in for an httpx.Response."""

    def __init__(self, *, headers=None, json_body=None):
        self.headers = headers or {}
        self._json = json_body or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


# A realistic prebuilt-layout success payload: content text + a ruled table +
# per-word confidences.
_AZURE_SUCCESS = {
    "status": "succeeded",
    "analyzeResult": {
        "content": "Ngày xét nghiệm: 15/10/2024\nHbA1c 6.8 %",
        "pages": [{"words": [{"confidence": 0.99}, {"confidence": 0.97}, {"confidence": 0.95}]}],
        "tables": [
            {
                "cells": [
                    {"rowIndex": 0, "columnIndex": 0, "content": "Chỉ số"},
                    {"rowIndex": 0, "columnIndex": 1, "content": "Kết quả"},
                    {"rowIndex": 1, "columnIndex": 0, "content": "Glucose lúc đói"},
                    {"rowIndex": 1, "columnIndex": 1, "content": "126 mg/dL"},
                ]
            }
        ],
    },
}


def _patch_azure_http(monkeypatch, *, poll_body=_AZURE_SUCCESS):
    import httpx

    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: _FakeResp(headers={"operation-location": "https://az/op/123"}),
    )
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp(json_body=poll_body))


def test_azure_build_text_reflows_tables():
    from app.services.ocr_engine import AzureDocIntelEngine

    text = AzureDocIntelEngine._build_text(_AZURE_SUCCESS["analyzeResult"])
    # Table row is reflowed onto one line so the parser sees "name ... value unit".
    assert "Glucose lúc đói 126 mg/dL" in text
    assert "HbA1c 6.8 %" in text  # content preserved too


def test_azure_avg_word_confidence_real_and_default():
    from app.services.ocr_engine import AzureDocIntelEngine

    assert AzureDocIntelEngine._avg_word_confidence(
        _AZURE_SUCCESS["analyzeResult"]
    ) == pytest.approx(0.97, abs=1e-3)
    # No per-word confidence -> high default, never 0.
    assert AzureDocIntelEngine._avg_word_confidence({"pages": []}) == 0.9


def test_azure_provider_run_parses_layout(monkeypatch):
    from app.services.ocr_engine import AzureDocIntelEngine

    monkeypatch.setenv("AZURE_DOC_INTEL_KEY", "k")
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", "https://docintel.example.com")
    _patch_azure_http(monkeypatch)
    res = AzureDocIntelEngine().run(b"\xff\xd8\xff", "image/jpeg")
    assert res.provider == "azure"
    assert res.confidence == pytest.approx(0.97, abs=1e-3)
    # Real-world: the parser turns the Azure text into canonical biomarkers.
    parsed = {v.test_name for v in lab_parser.parse_lab_text(res.text)}
    assert {"fasting_glucose", "hba1c"} <= parsed


def test_azure_provider_raises_on_failed_status(monkeypatch):
    from app.services.ocr_engine import AzureDocIntelEngine, OcrEngineError

    monkeypatch.setenv("AZURE_DOC_INTEL_KEY", "k")
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", "https://docintel.example.com")
    _patch_azure_http(monkeypatch, poll_body={"status": "failed"})
    with pytest.raises(OcrEngineError):
        AzureDocIntelEngine().run(b"\xff\xd8\xff", "image/jpeg")


def test_run_ocr_uses_azure_primary_ignoring_local_confidence(monkeypatch):
    """Azure runs first regardless of what Tesseract would have returned."""
    monkeypatch.setenv("AZURE_DOC_INTEL_KEY", "k")
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", "https://docintel.example.com")
    ocr_engine = _force_local(monkeypatch, confidence=0.3)
    monkeypatch.setattr(
        ocr_engine.AzureDocIntelEngine, "run",
        lambda self, data, mime: OcrTextResult(
            text="Glucose 99 mg/dL", confidence=0.96, provider="azure"
        ),
    )
    res = ocr_engine.run_ocr(b"x", "image/png")
    assert res.provider == "azure"


def test_run_ocr_falls_back_to_tesseract_when_azure_not_configured(monkeypatch):
    """Without Azure credentials, run_ocr uses Tesseract — Azure is never called."""
    monkeypatch.delenv("AZURE_DOC_INTEL_KEY", raising=False)
    monkeypatch.delenv("AZURE_DOC_INTEL_ENDPOINT", raising=False)
    ocr_engine = _force_local(monkeypatch, confidence=0.3)

    def _boom(self, data, mime):
        raise AssertionError("Azure must NOT be called when not configured")

    monkeypatch.setattr(ocr_engine.AzureDocIntelEngine, "run", _boom)
    res = ocr_engine.run_ocr(b"x", "image/png")
    assert res.provider == "tesseract"
    assert any("tin cậy" in w.lower() for w in res.warnings)


def test_zero_biomarker_escalation_uses_cloud(monkeypatch):
    # Local OCR is high-confidence but parses nothing -> escalate to permitted cloud.
    _patch_ocr(monkeypatch, text="(ảnh mờ không đọc được)", confidence=0.95)
    monkeypatch.setattr(
        lab_upload, "run_cloud_ocr_if_permitted",
        lambda data, mime: OcrTextResult(
            text="Glucose lúc đói 126 mg/dL", confidence=0.97, provider="azure"
        ),
    )
    draft = lab_upload.process_bytes(_png())
    assert draft.provider_used == "azure"
    assert any(i.canonical == "fasting_glucose" for i in draft.parsed_values)
    assert any("đám mây" in w.lower() for w in draft.warnings)


def test_zero_biomarker_no_escalation_when_cloud_not_permitted(monkeypatch):
    _patch_ocr(monkeypatch, text="(ảnh mờ không đọc được)", confidence=0.95)
    monkeypatch.setattr(
        lab_upload, "run_cloud_ocr_if_permitted", lambda data, mime: None
    )
    draft = lab_upload.process_bytes(_png())
    assert draft.provider_used == "tesseract"
    assert draft.manual_fallback is True
    assert draft.parsed_values == []


# --------------------------------------------------------------------------- #
# Endpoint: flag gate, RBAC, file + url, confirm-save
# --------------------------------------------------------------------------- #

def test_endpoint_503_when_flag_off(client, patient, monkeypatch):
    # FEATURE_OCR (unprefixed) takes precedence over MCP_FEATURE_OCR — clear both.
    monkeypatch.delenv("FEATURE_OCR", raising=False)
    monkeypatch.delenv("MCP_FEATURE_OCR", raising=False)
    r = client.post(
        "/api/v1/lab-uploads",
        files={"file": ("lab.png", _png(), "image/png")},
        headers=patient["headers"],
    )
    assert r.status_code == 503


def test_endpoint_draft_from_file(client, patient, monkeypatch, ocr_on):
    _patch_ocr(monkeypatch)
    r = client.post(
        "/api/v1/lab-uploads",
        files={"file": ("lab.png", _png(), "image/png")},
        headers=patient["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_used"] == "tesseract"
    assert any(v["canonical"] == "fasting_glucose" for v in body["parsed_values"])


def test_endpoint_requires_exactly_one_input(client, patient, ocr_on):
    r = client.post("/api/v1/lab-uploads", data={}, headers=patient["headers"])
    assert r.status_code == 400


def test_endpoint_url_ssrf_blocked(client, patient, ocr_on):
    r = client.post(
        "/api/v1/lab-uploads",
        data={"url": "http://169.254.169.254/latest/meta-data/"},
        headers=patient["headers"],
    )
    assert r.status_code == 400
    assert "nội bộ" in r.json()["detail"] or "không được phép" in r.json()["detail"]


def test_endpoint_doctor_forbidden(client, token_for, ocr_on):
    r = client.post(
        "/api/v1/lab-uploads",
        files={"file": ("lab.png", _png(), "image/png")},
        headers=token_for("doc-1", role="doctor"),
    )
    assert r.status_code == 403


def test_confirm_save_persists_canonical_record(client, patient, monkeypatch, ocr_on):
    # 1) get draft
    _patch_ocr(monkeypatch)
    draft = client.post(
        "/api/v1/lab-uploads",
        files={"file": ("lab.png", _png(), "image/png")},
        headers=patient["headers"],
    ).json()
    # 2) confirm via the existing manual-entry endpoint (review/edit then save)
    results = [
        {"test_name": v["canonical"], "value": v["value"], "unit": v["unit"],
         "reference_range": v["reference_range"]}
        for v in draft["parsed_values"]
    ]
    pid = patient["patient_id"]
    save = client.post(
        f"/api/v1/patients/{pid}/lab-results",
        json={"lab_name": "Phòng khám test", "test_date": "2026-06-12", "results": results},
        headers=patient["headers"],
    )
    assert save.status_code == 201, save.text
    saved = save.json()
    assert saved["total"] == len(results)
    assert all(row["patient_id"] == pid and row["verified_by_user"] for row in saved["items"])


# --------------------------------------------------------------------------- #
# Real Tesseract (opt-in; skipped when the binary is absent)
# --------------------------------------------------------------------------- #

def test_real_tesseract_roundtrip(monkeypatch, ocr_on):
    from app.services.ocr_engine import TesseractEngine

    if not TesseractEngine.available():
        pytest.skip("tesseract binary not installed")
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (520, 140), "white")
    d = ImageDraw.Draw(img)
    d.text((10, 20), "Glucose 126 mg/dL", fill="black")
    d.text((10, 60), "HbA1c 6.8 %", fill="black")
    d.text((10, 100), "Cholesterol 210 mg/dL", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    draft = lab_upload.process_bytes(buf.getvalue())
    names = {i.canonical for i in draft.parsed_values}
    assert "fasting_glucose" in names


# --------------------------------------------------------------------------- #
# Test-date extraction (parser) + required/validated test_date (endpoint)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text,expected,label_has", [
    ("Ngày xét nghiệm: 15/10/2024\nGlucose 90 mg/dL", "2024-10-15", "xét nghiệm"),
    # sample date wins over the print/report date:
    ("Ngày lấy mẫu: 03/01/2025\nNgày in báo cáo: 05/01/2025", "2025-01-03", "lấy mẫu"),
    ("Sample date 07-08-2023\nGlucose 90", "2023-08-07", "Sample"),
    ("Ngày thực hiện\n22.09.2024", "2024-09-22", "thực hiện"),  # date on next line
    ("Kết quả xét nghiệm ngày 02 tháng 03 năm 2024", "2024-03-02", None),
])
def test_parse_test_date_labels(text, expected, label_has):
    res = lab_parser.parse_test_date(text)
    assert res is not None and res.iso == expected, f"got {res}"
    if label_has:
        assert label_has.lower() in (res.raw_label or "").lower()


def test_parse_test_date_none_when_absent():
    assert lab_parser.parse_test_date("Glucose 126 mg/dL\nHbA1c 6.8 %") is None


def test_parse_test_date_rejects_impossible():
    # 32/13 is not a calendar date -> no labelled match, no fallback.
    assert lab_parser.parse_test_date("Ngày xét nghiệm: 32/13/2024") is None


def test_draft_includes_extracted_test_date(monkeypatch):
    _patch_ocr(monkeypatch, text="Ngày xét nghiệm: 15/10/2024\nGlucose 126 mg/dL")
    draft = lab_upload.process_bytes(_png())
    assert draft.extracted_test_date == "2024-10-15"
    assert draft.test_date_confidence > 0.7
    assert "xét nghiệm" in (draft.test_date_label or "").lower()


def test_draft_warns_when_no_test_date(monkeypatch):
    _patch_ocr(monkeypatch, text="Glucose 126 mg/dL\nHbA1c 6.8 %")
    draft = lab_upload.process_bytes(_png())
    assert draft.extracted_test_date is None
    assert any("ngày xét nghiệm" in w.lower() for w in draft.warnings)


def test_manual_entry_requires_test_date(client, patient):
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/lab-results",
        json={"results": [{"test_name": "Glucose", "value": 90, "unit": "mg/dL"}]},
        headers=patient["headers"],
    )
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# Azure DI as primary (Phase 1 OCR policy)
# --------------------------------------------------------------------------- #

def test_run_ocr_azure_primary_bypasses_tesseract(monkeypatch):
    """When Azure credentials are present, run_ocr goes to Azure without touching Tesseract."""
    monkeypatch.setenv("AZURE_DOC_INTEL_KEY", "k")
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", "https://docintel.example.com")
    from app.services import ocr_engine

    def _boom(self, data):
        raise AssertionError("Tesseract must NOT be called when Azure is configured")

    monkeypatch.setattr(ocr_engine.TesseractEngine, "available", staticmethod(lambda: True))
    monkeypatch.setattr(ocr_engine.TesseractEngine, "run", _boom)
    monkeypatch.setattr(
        ocr_engine.AzureDocIntelEngine, "run",
        lambda self, data, mime: OcrTextResult(
            text="Glucose 99 mg/dL", confidence=0.97, provider="azure"
        ),
    )
    res = ocr_engine.run_ocr(b"\xff\xd8\xff", "image/jpeg")
    assert res.provider == "azure"
    assert res.confidence == pytest.approx(0.97)


def test_pdf_routes_directly_to_azure_when_configured(monkeypatch):
    """PDF bytes go to Azure DI natively — no rasterization, no pypdf text-layer first."""
    monkeypatch.setenv("AZURE_DOC_INTEL_KEY", "k")
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", "https://docintel.example.com")
    from app.services import ocr_engine as _ocr
    monkeypatch.setattr(
        _ocr.AzureDocIntelEngine, "run",
        lambda self, data, mime: OcrTextResult(
            text="HbA1c 6.8 %\nGlucose 99 mg/dL", confidence=0.97, provider="azure"
        ),
    )
    pdf_bytes = b"%PDF-1.7 " + b"x" * 32
    draft = lab_upload.process_bytes(pdf_bytes)
    assert draft.provider_used == "azure"
    assert any(i.canonical == "hba1c" for i in draft.parsed_values)


def test_manual_entry_rejects_future_date(client, patient):
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/lab-results",
        json={"test_date": "2099-01-01", "results": [{"test_name": "Glucose", "value": 90}]},
        headers=patient["headers"],
    )
    assert r.status_code == 422, r.text


def test_manual_entry_rejects_too_old_date(client, patient):
    r = client.post(
        f"/api/v1/patients/{patient['patient_id']}/lab-results",
        json={"test_date": "1900-01-01", "results": [{"test_name": "Glucose", "value": 90}]},
        headers=patient["headers"],
    )
    assert r.status_code == 422, r.text


def test_lab_results_sorted_by_test_date_desc(client, patient):
    pid = patient["patient_id"]
    # Insert out of chronological order; older exam date uploaded last.
    for td, name in [("2024-01-10", "Old"), ("2025-12-01", "New"), ("2024-06-15", "Mid")]:
        client.post(
            f"/api/v1/patients/{pid}/lab-results",
            json={"test_date": td, "results": [{"test_name": name, "value": 1}]},
            headers=patient["headers"],
        )
    resp = client.get(f"/api/v1/patients/{pid}/lab-results", headers=patient["headers"])
    items = resp.json()["items"]
    dates = [it["test_date"] for it in items]
    assert dates == sorted(dates, reverse=True), f"not test_date DESC: {dates}"
    assert dates[0] == "2025-12-01"


# --------------------------------------------------------------------------- #
# Boundary classification — uric_acid and random_glucose critical thresholds
# --------------------------------------------------------------------------- #


def test_uric_acid_critical_at_exact_threshold():
    assert classify_value("uric_acid", 10.0) == LabStatus.CRITICAL


def test_uric_acid_high_just_below_critical():
    assert classify_value("uric_acid", 9.9) == LabStatus.HIGH


def test_uric_acid_normal_within_range():
    assert classify_value("uric_acid", 5.0) == LabStatus.NORMAL


def test_uric_acid_high_at_ref_boundary():
    # 7.0 is the ref_high — a value of exactly 7.0 is still within range
    assert classify_value("uric_acid", 7.0) == LabStatus.NORMAL
    # 7.01 is above ref_high
    assert classify_value("uric_acid", 7.01) == LabStatus.HIGH


def test_random_glucose_critical_low_at_exact_threshold():
    assert classify_value("random_glucose", 54.0) == LabStatus.CRITICAL


def test_random_glucose_low_just_above_critical_low():
    assert classify_value("random_glucose", 55.0) == LabStatus.LOW


def test_random_glucose_normal_at_upper_ref_boundary():
    # ref_high=139 — exactly 139 is still normal
    assert classify_value("random_glucose", 139.0) == LabStatus.NORMAL
    assert classify_value("random_glucose", 139.1) == LabStatus.HIGH


def test_random_glucose_critical_high_at_exact_threshold():
    assert classify_value("random_glucose", 300.0) == LabStatus.CRITICAL


def test_rbs_alias_resolves_to_random_glucose():
    values = lab_parser.parse_lab_text("RBS 160 mg/dL")
    assert values and values[0].test_name == "random_glucose"


# --------------------------------------------------------------------------- #
# Vinmec ground-truth regression — SI unit conversion + incompatible unit guard
#
# Source: Vinmec lab report (Vietnamese hospital, SI units).
# Glucose/lipids are reported in mmol/L; the mapping layer converts to canonical
# mg/dL so classification remains clinically correct.
# TSH: µIU/mL is numerically identical to mIU/L (factor=1.0).
# --------------------------------------------------------------------------- #

_VINMEC_TEXT = """\
GLUCOSE 4.78 mmol/L 3.9 - 6.1
ALT (SGPT) 58.4 U/L 7 - 56
CHOLESTEROL TOAN PHAN 5.99 mmol/L 0 - 5.2
TRIGLYCERID 2.7 mmol/L 0 - 1.7
HDL-C 1.08 mmol/L 0.9 - 1.6
LDL-C 4.24 mmol/L 0 - 3.4
TSH 1.26 uIU/mL 0.4 - 4.0
FT3 4.64 pmol/L 3.1 - 6.8
FT4 18 pmol/L 12.0 - 22.0
"""


def _vinmec(canonical: str):
    return next(
        (v for v in lab_parser.parse_lab_text(_VINMEC_TEXT) if v.test_name == canonical),
        None,
    )


class TestVinmecGroundTruth:
    def test_all_nine_biomarkers_extracted(self):
        values = lab_parser.parse_lab_text(_VINMEC_TEXT)
        found = {v.test_name for v in values}
        expected = {
            "fasting_glucose", "alt", "total_cholesterol", "triglyceride",
            "hdl", "ldl", "tsh", "ft3", "ft4",
        }
        assert expected.issubset(found), f"Missing: {expected - found}"

    def test_glucose_converted_to_mg_dl_and_classified_normal(self):
        v = _vinmec("fasting_glucose")
        assert v is not None
        assert v.unit == "mg/dL"
        assert v.value == pytest.approx(4.78 * 18.018, rel=1e-3)
        assert v.ocr_confidence == 1.0
        assert interpret_value(v).status == LabStatus.NORMAL

    def test_alt_recognized_unit_l_classified_high(self):
        v = _vinmec("alt")
        assert v is not None
        assert v.value == pytest.approx(58.4, rel=1e-3)
        assert v.unit == "U/L"
        assert v.ocr_confidence == 1.0
        assert interpret_value(v).status == LabStatus.HIGH

    def test_cholesterol_converted_to_mg_dl(self):
        v = _vinmec("total_cholesterol")
        assert v is not None
        assert v.unit == "mg/dL"
        assert v.value == pytest.approx(5.99 * 38.67, rel=1e-3)
        assert v.ocr_confidence == 1.0

    def test_triglycerid_alias_recognized_and_converted(self):
        v = _vinmec("triglyceride")
        assert v is not None, "triglyceride (alias: triglycerid) not recognized"
        assert v.unit == "mg/dL"
        assert v.value == pytest.approx(2.7 * 88.57, rel=1e-3)
        assert v.ocr_confidence == 1.0

    def test_hdl_converted_to_mg_dl(self):
        v = _vinmec("hdl")
        assert v is not None
        assert v.unit == "mg/dL"
        assert v.value == pytest.approx(1.08 * 38.67, rel=1e-3)
        assert v.ocr_confidence == 1.0

    def test_ldl_converted_to_mg_dl(self):
        v = _vinmec("ldl")
        assert v is not None
        assert v.unit == "mg/dL"
        assert v.value == pytest.approx(4.24 * 38.67, rel=1e-3)
        assert v.ocr_confidence == 1.0

    def test_tsh_uiu_ml_accepted_no_conversion_full_confidence(self):
        v = _vinmec("tsh")
        assert v is not None
        assert v.value == pytest.approx(1.26, rel=1e-3)
        assert v.unit == "mIU/L"
        assert v.ocr_confidence == 1.0
        assert interpret_value(v).status == LabStatus.NORMAL

    def test_ft3_pmol_l_recognized(self):
        v = _vinmec("ft3")
        assert v is not None
        assert v.value == pytest.approx(4.64, rel=1e-3)
        assert v.unit == "pmol/L"
        assert v.ocr_confidence == 1.0

    def test_ft4_pmol_l_recognized(self):
        v = _vinmec("ft4")
        assert v is not None
        assert v.value == pytest.approx(18.0, rel=1e-3)
        assert v.unit == "pmol/L"
        assert v.ocr_confidence == 1.0

    def test_no_clinically_incorrect_unit_value_combinations(self):
        """Success criterion: no incompatible unit survives with confidence > 0."""
        values = lab_parser.parse_lab_text(_VINMEC_TEXT)
        for v in values:
            assert v.ocr_confidence > 0.0, (
                f"{v.test_name}: incompatible unit '{v.unit}' leaked through"
            )


# --------------------------------------------------------------------------- #
# Azure DI OCR correction regression — creatinine mol/L + TSH pIU/mL
#
# Azure Document Intelligence is known to:
#   • Drop the µ prefix from µmol/L → bare mol/L  (creatinine, urea)
#   • Misread µ as p before IU → pIU/mL            (TSH, Insulin)
#   • Misread µ as Greek rho ρ → ρIU/mL            (TSH, rarer variant)
#
# After the global OCR corrections + SI conversion the draft must NEVER expose
# the broken raw unit as the canonical display value.
# --------------------------------------------------------------------------- #

_AZURE_DI_BUGGY_TEXT = """\
CREATININE 82.2 mol/L 44 - 80
TSH 1.26 pIU/mL 0.4 - 4.0
UREA 4.47 mmol/L 2.5 - 7.5
GLUCOSE 5.1 mmol/L 3.9 - 6.1
"""

_AZURE_DI_BUGGY_RHO = """\
TSH 2.5 ρIU/mL 0.4 - 4.0
"""


class TestAzureDiOcrCorrections:
    def test_creatinine_mol_l_corrected_to_umol_l_and_converted(self):
        """Azure DI drops µ from µmol/L → mol/L. Must be corrected and SI-converted."""
        values = lab_parser.parse_lab_text("Creatinine 82.2 mol/L")
        assert values, "creatinine not parsed"
        v = values[0]
        assert v.unit == "mg/dL", f"expected canonical mg/dL, got '{v.unit}'"
        assert v.value == pytest.approx(82.2 * 0.011312, rel=1e-3)
        assert v.ocr_confidence > 0.7, f"confidence too low: {v.ocr_confidence}"
        # original_value/original_unit capture the pre-conversion raw OCR
        assert v.original_value == pytest.approx(82.2)
        assert v.original_unit == "µmol/L"

    def test_creatinine_no_mol_l_in_draft(self):
        """Draft payload must never expose bare mol/L for creatinine."""
        values = lab_parser.parse_lab_text(_AZURE_DI_BUGGY_TEXT)
        by_name = {v.test_name: v for v in values}
        assert "creatinine" in by_name
        cr = by_name["creatinine"]
        assert cr.unit != "mol/L", "bare mol/L leaked through as canonical unit"

    def test_tsh_piu_ml_corrected_and_converted(self):
        """Azure DI misreads µ as p → pIU/mL. Must be corrected to mIU/L."""
        values = lab_parser.parse_lab_text("TSH 1.26 pIU/mL")
        assert values, "TSH not parsed"
        v = values[0]
        assert v.unit == "mIU/L", f"expected mIU/L, got '{v.unit}'"
        assert v.value == pytest.approx(1.26, rel=1e-3)
        assert v.ocr_confidence > 0.7, f"confidence too low: {v.ocr_confidence}"

    def test_tsh_piu_ml_not_in_draft(self):
        """Draft payload must never expose pIU/mL for TSH."""
        values = lab_parser.parse_lab_text(_AZURE_DI_BUGGY_TEXT)
        by_name = {v.test_name: v for v in values}
        assert "tsh" in by_name
        assert by_name["tsh"].unit != "pIU/mL", "pIU/mL leaked through as canonical unit"

    def test_tsh_greek_rho_variant_corrected(self):
        """Greek rho ρ (U+03C1) variant of µ misread → must also be corrected."""
        values = lab_parser.parse_lab_text(_AZURE_DI_BUGGY_RHO)
        assert values, "TSH not parsed from ρIU/mL text"
        v = values[0]
        assert v.unit == "mIU/L", f"expected mIU/L, got '{v.unit}'"

    def test_mmol_l_not_corrupted_by_mol_l_correction(self):
        """mol/L correction must NOT touch mmol/L (glucose/urea use mmol/L)."""
        values = lab_parser.parse_lab_text("GLUCOSE 5.1 mmol/L\nUREA 4.47 mmol/L")
        by_name = {v.test_name: v for v in values}
        assert by_name["fasting_glucose"].unit == "mg/dL"
        assert by_name["urea"].unit == "mg/dL"
        assert by_name["fasting_glucose"].ocr_confidence > 0.7
        assert by_name["urea"].ocr_confidence > 0.7

    def test_si_converted_item_has_original_value_unit(self):
        """When SI conversion fires, original_value/original_unit must be set."""
        values = lab_parser.parse_lab_text("GLUCOSE 5.1 mmol/L")
        assert values
        v = values[0]
        assert v.original_value == pytest.approx(5.1)
        assert v.original_unit == "mmol/L"
        assert v.unit == "mg/dL"

    def test_no_conversion_original_matches_value(self):
        """When no SI conversion, original_value/original_unit equal the parsed value."""
        values = lab_parser.parse_lab_text("Glucose 126 mg/dL")
        assert values
        v = values[0]
        assert v.original_value == pytest.approx(126.0)
        assert v.original_unit == "mg/dL"

    def test_draft_build_no_mol_l_for_creatinine(self, monkeypatch):
        """build_draft: creatinine in draft must not have mol/L as unit."""
        _patch_ocr(monkeypatch, text=_AZURE_DI_BUGGY_TEXT, confidence=0.95)
        draft = lab_upload.process_bytes(_png())
        by_canonical = {i.canonical: i for i in draft.parsed_values}
        if "creatinine" in by_canonical:
            assert by_canonical["creatinine"].unit != "mol/L"

    def test_draft_build_no_piu_ml_for_tsh(self, monkeypatch):
        """build_draft: TSH in draft must not have pIU/mL as unit."""
        _patch_ocr(monkeypatch, text=_AZURE_DI_BUGGY_TEXT, confidence=0.95)
        draft = lab_upload.process_bytes(_png())
        by_canonical = {i.canonical: i for i in draft.parsed_values}
        if "tsh" in by_canonical:
            assert by_canonical["tsh"].unit != "pIU/mL"


# --------------------------------------------------------------------------- #
# Vinmec 16-biomarker golden fixture — OCR accuracy ≥ 80% (≥13/16 correct)
#
# Source: Vinmec International Hospital lab report (Vietnamese, SI units).
# "Correct" = all three match: canonical name + numeric value + unit.
# Reference ranges are intentionally included to verify they don't corrupt
# result extraction (row-integrity hard rule).
# --------------------------------------------------------------------------- #

_VINMEC_16_TEXT = """\
URE 4.47 mmol/L 2.5 - 7.5
CREATININ 82.2 mol/L 44 - 80
GLUCOSE 4.78 mmol/L 3.9 - 6.1
AST (GOT) 34.7 U/L 0 - 40
ALT (GPT) 58.4 U/L 0 - 56
CHOLESTEROL TOAN PHAN 5.99 mmol/L 0 - 5.2
TRIGLYCERID 2.7 mmol/L 0 - 1.7
HDL-C 1.08 mmol/L 0.9 - 1.6
LDL-C 4.24 mmol/L 0 - 3.4
NATRI 140 mmol/L 136 - 145
KALI 3.95 mmol/L 3.5 - 5.0
CLO 100.7 mmol/L 98 - 106
FT3 4.64 pmol/L 3.1 - 6.8
FT4 18 pmol/L 12.0 - 22.0
TSH 1.26 pIU/mL 0.4 - 4.0
THYROGLOBULIN 0.118 ng/mL < 55
"""

# Expected original (as-printed) names and (value, unit).
# value/unit here are what appears on the lab report, NOT after SI conversion.
# creatinine: mol/L → µmol/L correction fires (global OCR fix), so original_unit=µmol/L.
# tsh: pIU/mL → µIU/mL correction fires, so original_unit=µIU/mL.
_VINMEC_16_EXPECTED: dict[str, tuple[float, str]] = {
    "urea":              (4.47,   "mmol/L"),   # as printed
    "creatinine":        (82.2,   "µmol/L"),   # after mol→µmol OCR correction
    "fasting_glucose":   (4.78,   "mmol/L"),   # as printed
    "ast":               (34.7,   "U/L"),
    "alt":               (58.4,   "U/L"),
    "total_cholesterol": (5.99,   "mmol/L"),   # as printed
    "triglyceride":      (2.7,    "mmol/L"),   # as printed
    "hdl":               (1.08,   "mmol/L"),   # as printed
    "ldl":               (4.24,   "mmol/L"),   # as printed
    "sodium":            (140.0,  "mmol/L"),
    "potassium":         (3.95,   "mmol/L"),
    "chloride":          (100.7,  "mmol/L"),
    "ft3":               (4.64,   "pmol/L"),
    "ft4":               (18.0,   "pmol/L"),
    "tsh":               (1.26,   "µIU/mL"),   # after pIU→µIU OCR correction
    "thyroglobulin":     (0.118,  "ng/mL"),
}


class TestVinmec16Accuracy:
    """Vinmec 16-biomarker golden fixture — P0 OCR accuracy gate (≥80% = ≥13/16)."""

    def _parse(self) -> dict[str, object]:
        return {v.test_name: v for v in lab_parser.parse_lab_text(_VINMEC_16_TEXT)}

    def test_all_16_biomarkers_extracted(self):
        found = set(self._parse())
        missing = set(_VINMEC_16_EXPECTED) - found
        assert not missing, f"Missing biomarkers: {sorted(missing)}"

    def test_accuracy_at_least_80_percent(self):
        """At least 13/16 biomarkers must be value+unit correct (strict ≥80% gate).
        Checks original_value/original_unit (as-printed), not canonical."""
        parsed = self._parse()
        correct = 0
        report: list[str] = []
        for canonical, (exp_val, exp_unit) in _VINMEC_16_EXPECTED.items():
            row = parsed.get(canonical)
            if row is None:
                report.append(f"  MISSING  {canonical}")
                continue
            act_val = row.original_value if row.original_value is not None else row.value
            act_unit = row.original_unit if row.original_unit is not None else row.unit
            val_ok = abs(act_val - exp_val) / max(abs(exp_val), 1e-9) < 0.01
            unit_ok = act_unit == exp_unit
            if val_ok and unit_ok:
                correct += 1
                report.append(f"  OK       {canonical}: {act_val:.4f} {act_unit}")
            else:
                detail = []
                if not val_ok:
                    detail.append(f"value {act_val:.4f} ≠ {exp_val:.4f}")
                if not unit_ok:
                    detail.append(f"unit '{act_unit}' ≠ '{exp_unit}'")
                report.append(f"  WRONG    {canonical}: {', '.join(detail)}")
        pct = correct / len(_VINMEC_16_EXPECTED) * 100
        summary = "\n".join(report)
        assert correct >= 13, (
            f"Accuracy {correct}/16 ({pct:.1f}%) < 80% threshold.\n{summary}"
        )

    def test_no_clinically_wrong_unit_survives(self):
        """No biomarker must have ocr_confidence=0 (incompatible unit or impossible value)."""
        for row in lab_parser.parse_lab_text(_VINMEC_16_TEXT):
            assert row.ocr_confidence > 0.0, (
                f"{row.test_name}: confidence=0 (incompatible unit '{row.unit}'?)"
            )

    def test_row_integrity_no_ref_range_as_value(self):
        """Hard rule: reference-range numbers must never appear as result values."""
        parsed = self._parse()
        ref_lows = {"urea": 2.5, "sodium": 136.0, "potassium": 3.5, "chloride": 98.0}
        for canonical, ref_lo in ref_lows.items():
            row = parsed.get(canonical)
            if row is None:
                continue
            assert abs(row.value - ref_lo) > 0.001, (
                f"{canonical}: value {row.value} looks like ref_low {ref_lo} — "
                "reference range leaked as result value"
            )

    def test_si_converted_rows_have_original_fields(self):
        """All rows (including SI-converted ones) must expose original_value/original_unit
        set to the as-printed values (not the canonical SI values)."""
        parsed = self._parse()
        si_biomarkers = {"urea", "creatinine", "fasting_glucose",
                         "total_cholesterol", "triglyceride", "hdl", "ldl"}
        for canonical in si_biomarkers:
            row = parsed.get(canonical)
            if row is None:
                continue
            assert row.original_value is not None, (
                f"{canonical}: original_value missing"
            )
            assert row.original_unit is not None, (
                f"{canonical}: original_unit missing"
            )
            # For SI-converted rows, original_unit must be the SI (as-printed) unit,
            # NOT the canonical unit (the canonical value is in row.value).
            assert row.original_unit != row.unit, (
                f"{canonical}: original_unit '{row.original_unit}' should differ from "
                f"canonical unit '{row.unit}' for SI-converted rows"
            )

    @pytest.mark.parametrize("canonical,exp_val,exp_unit", [
        ("sodium",        140.0,  "mmol/L"),
        ("potassium",     3.95,   "mmol/L"),
        ("chloride",      100.7,  "mmol/L"),
        ("thyroglobulin", 0.118,  "ng/mL"),
    ])
    def test_new_biomarkers_extracted_correctly(self, canonical, exp_val, exp_unit):
        """New biomarkers (electrolytes + thyroglobulin) parse correctly."""
        parsed = self._parse()
        row = parsed.get(canonical)
        assert row is not None, f"{canonical} not extracted"
        assert abs(row.value - exp_val) / max(abs(exp_val), 1e-9) < 0.01, (
            f"{canonical}: value {row.value} ≠ {exp_val}"
        )
        assert row.unit == exp_unit, f"{canonical}: unit '{row.unit}' ≠ '{exp_unit}'"
        assert row.ocr_confidence > 0.7, f"{canonical}: low confidence {row.ocr_confidence}"


class TestIncompatibleUnitRejection:
    """Clinically nonsensical units must produce ocr_confidence=0.0."""

    def test_glucose_in_miu_ml_rejected(self):
        values = lab_parser.parse_lab_text("Glucose 4.78 mIU/mL")
        assert values and values[0].ocr_confidence == 0.0

    def test_triglyceride_in_iu_ml_rejected(self):
        values = lab_parser.parse_lab_text("Triglyceride 150 IU/mL")
        assert values and values[0].ocr_confidence == 0.0

    def test_tsh_in_mmol_l_rejected(self):
        values = lab_parser.parse_lab_text("TSH 1.26 mmol/L")
        assert values and values[0].ocr_confidence == 0.0

    def test_ft3_in_mg_dl_rejected(self):
        values = lab_parser.parse_lab_text("FT3 4.64 mg/dL")
        assert values and values[0].ocr_confidence == 0.0

    def test_alt_in_pmol_l_rejected(self):
        values = lab_parser.parse_lab_text("ALT 58 pmol/L")
        assert values and values[0].ocr_confidence == 0.0
