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
        json={"lab_name": "Phòng khám test", "results": results},
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
