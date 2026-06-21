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


def test_parser_extended_biomarkers():
    text = (
        "eGFR 85 mL/min\nUrea 18 mg/dL\nGGT 30 U/L\n"
        "FT4 15 pmol/L\nHemoglobin 13.5 g/dL\nTiểu cầu 250"
    )
    names = {v.test_name for v in lab_parser.parse_lab_text(text)}
    assert {"egfr", "urea", "ggt", "ft4", "hemoglobin", "platelet"} <= names


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


def test_cloud_called_when_flag_on_low_conf_key_set(monkeypatch):
    monkeypatch.setenv("MCP_FEATURE_OCR_CLOUD_FALLBACK", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    ocr_engine = _force_local(monkeypatch, confidence=0.3)
    monkeypatch.setattr(
        ocr_engine, "get_settings",
        lambda: SimpleNamespace(ocr_cloud_provider="anthropic", ocr_lang="vie+eng"),
    )
    monkeypatch.setattr(
        ocr_engine.AnthropicVisionEngine, "run",
        lambda self, data, mime: OcrTextResult(
            text="Glucose 99 mg/dL", confidence=0.95, provider="anthropic"
        ),
    )
    res = ocr_engine.run_ocr(b"x", "image/png")
    assert res.provider == "anthropic"


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


def test_azure_fallback_used_on_low_confidence(monkeypatch):
    monkeypatch.setenv("MCP_FEATURE_OCR_CLOUD_FALLBACK", "true")
    monkeypatch.setenv("AZURE_DOC_INTEL_KEY", "k")
    monkeypatch.setenv("AZURE_DOC_INTEL_ENDPOINT", "https://docintel.example.com")
    ocr_engine = _force_local(monkeypatch, confidence=0.3)  # low -> escalate
    monkeypatch.setattr(
        ocr_engine, "get_settings",
        lambda: SimpleNamespace(ocr_cloud_provider="azure", ocr_lang="vie+eng"),
    )
    monkeypatch.setattr(
        ocr_engine.AzureDocIntelEngine, "run",
        lambda self, data, mime: OcrTextResult(
            text="Glucose 99 mg/dL", confidence=0.96, provider="azure"
        ),
    )
    res = ocr_engine.run_ocr(b"x", "image/png")
    assert res.provider == "azure"


def test_azure_fallback_skipped_when_no_key(monkeypatch):
    monkeypatch.setenv("MCP_FEATURE_OCR_CLOUD_FALLBACK", "true")
    monkeypatch.delenv("AZURE_DOC_INTEL_KEY", raising=False)
    monkeypatch.delenv("AZURE_DOC_INTEL_ENDPOINT", raising=False)
    ocr_engine = _force_local(monkeypatch, confidence=0.3)
    monkeypatch.setattr(
        ocr_engine, "get_settings",
        lambda: SimpleNamespace(ocr_cloud_provider="azure", ocr_lang="vie+eng"),
    )

    def _boom(self, data, mime):
        raise AssertionError("Azure must NOT be called without a key")

    monkeypatch.setattr(ocr_engine.AzureDocIntelEngine, "run", _boom)
    res = ocr_engine.run_ocr(b"x", "image/png")  # must NOT crash
    assert res.provider == "tesseract"


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
