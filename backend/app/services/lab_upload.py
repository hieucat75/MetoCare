"""Lab-upload draft orchestrator (OCR Lab Upload track §5).

Flow:  bytes/URL  ->  MIME sniff + validate  ->  OCR (image) or text-layer (PDF)
       ->  parse to canonical values  ->  interpret (status/ref/verification)
       ->  **draft** response (NEVER persisted).

The draft is review-only. Nothing is written to the patient record here — the
frontend shows the draft, the patient edits/confirms, and ONLY then does the
existing manual-entry endpoint (`POST /patients/{id}/lab-results`) persist a
canonical lab record. Raw image bytes and raw OCR text are never stored or
logged; only a short SHA-256 prefix of the text is returned for audit/debug.

MIME is detected from file *content* (magic bytes), not the client-declared type,
so a renamed/poisoned extension cannot smuggle an unsupported format past us.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.domain import lab_interpreter
from app.services import lab_parser
from app.services.ocr_engine import OcrEngineError, run_cloud_ocr_if_permitted, run_ocr

logger = logging.getLogger("mcp.lab_upload")

JPEG = "image/jpeg"
PNG = "image/png"
PDF = "application/pdf"
ALLOWED_MIME = {JPEG, PNG, PDF}


class LabUploadError(Exception):
    """Base error carrying an HTTP status + user-safe message."""

    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class UnsupportedMediaError(LabUploadError):
    status_code = 415


class PayloadTooLargeError(LabUploadError):
    status_code = 413


@dataclass
class DraftItem:
    test_name: str          # canonical key (maps to LabResultItemIn.test_name)
    canonical: str
    value: float
    unit: str
    reference_range: str | None
    status: str
    confidence: float
    needs_verification: bool


@dataclass
class LabUploadDraft:
    provider_used: str
    confidence_avg: float
    parsed_values: list[DraftItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_text_sha256: str = ""
    low_confidence: bool = False
    manual_fallback: bool = False
    # Exam date detected from the report (ISO YYYY-MM-DD) — distinct from upload time.
    extracted_test_date: str | None = None
    test_date_label: str | None = None
    test_date_confidence: float = 0.0


def sniff_mime(data: bytes) -> str | None:
    """Detect MIME from leading magic bytes (jpeg/png/pdf), else None."""
    if data[:3] == b"\xff\xd8\xff":
        return JPEG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return PNG
    if data[:5] == b"%PDF-":
        return PDF
    return None


def validate_upload(data: bytes, *, declared_mime: str | None = None) -> str:
    """Validate size + content type; return the *sniffed* MIME. Raises on failure."""
    settings = get_settings()
    max_bytes = settings.ocr_max_upload_mb * 1024 * 1024
    if not data:
        raise LabUploadError("Tệp rỗng.")
    if len(data) > max_bytes:
        raise PayloadTooLargeError(
            f"Tệp vượt quá dung lượng cho phép ({settings.ocr_max_upload_mb}MB)."
        )
    mime = sniff_mime(data)
    if mime is None or mime not in ALLOWED_MIME:
        raise UnsupportedMediaError("Chỉ chấp nhận ảnh JPG/PNG hoặc tệp PDF.")
    return mime


# --------------------------------------------------------------------------- #
# Text extraction
# --------------------------------------------------------------------------- #

def _extract_pdf_text(data: bytes) -> tuple[str, float, str, list[str]]:
    """PDF: prefer the embedded text layer (digital lab PDFs); if empty, try to
    rasterize the first N pages and OCR them. Either way, never raise — fall back
    to empty text + a manual-review warning so upload always succeeds."""
    warnings: list[str] = []
    settings = get_settings()

    # 1) Text layer (pypdf) — works for digital lab reports, no OCR needed.
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages[: settings.ocr_pdf_max_pages]
        text = "\n".join((p.extract_text() or "") for p in pages).strip()
        if len(text) >= 16:
            return text, 0.95, "pdf_text", warnings
    except Exception:
        logger.info("pdf_text_layer_unavailable")

    # 2) Rasterize + OCR (needs poppler + tesseract). Optional.
    try:
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(
            data, first_page=1, last_page=settings.ocr_pdf_max_pages, fmt="png"
        )
        import io as _io

        texts: list[str] = []
        confs: list[float] = []
        provider = "tesseract"
        for img in images:
            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            res = run_ocr(buf.getvalue(), PNG)
            texts.append(res.text)
            confs.append(res.confidence)
            provider = res.provider
            warnings.extend(res.warnings)
        text = "\n".join(texts).strip()
        conf = round(sum(confs) / len(confs), 4) if confs else 0.0
        if text:
            return text, conf, provider, warnings
    except OcrEngineError:
        warnings.append("Không OCR được PDF — vui lòng nhập tay hoặc tải ảnh rõ hơn.")
    except Exception:
        warnings.append("PDF dạng ảnh chưa hỗ trợ OCR tự động — vui lòng nhập tay.")

    warnings.append("Không trích xuất được nội dung PDF — vui lòng nhập tay.")
    return "", 0.0, "pdf_text", warnings


def _extract_text(data: bytes, mime: str) -> tuple[str, float, str, list[str]]:
    if mime == PDF:
        return _extract_pdf_text(data)
    # image
    try:
        res = run_ocr(data, mime)
        return res.text, res.confidence, res.provider, list(res.warnings)
    except OcrEngineError as exc:
        # OCR unavailable/failed: never block — return empty draft for manual entry.
        return "", 0.0, "tesseract", [str(exc) or "OCR thất bại — vui lòng nhập tay."]


# --------------------------------------------------------------------------- #
# Build draft
# --------------------------------------------------------------------------- #

def build_draft(data: bytes, mime: str) -> LabUploadDraft:
    text, ocr_conf, provider, warnings = _extract_text(data, mime)
    raw_values = lab_parser.parse_lab_text(text)

    # Zero-biomarker escalation: the local engine may report acceptable confidence
    # yet parse nothing on a tricky layout (the confidence trigger inside run_ocr
    # would not have fired). When cloud OCR is permitted (flag + provider + key),
    # try it once and adopt the result only if it actually recognizes biomarkers.
    # Skipped when the transcription already came from a cloud provider.
    if not raw_values and provider in ("tesseract", "pdf_text"):
        cloud_res = run_cloud_ocr_if_permitted(data, mime)
        if cloud_res is not None:
            cloud_values = lab_parser.parse_lab_text(cloud_res.text)
            if cloud_values:
                text, ocr_conf, provider = cloud_res.text, cloud_res.confidence, cloud_res.provider
                raw_values = cloud_values
                warnings.extend(cloud_res.warnings)
                warnings.append(
                    "Đã dùng OCR đám mây (fallback) do không nhận diện được chỉ số nào."
                )

    raw_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else ""
    detected_date = lab_parser.parse_test_date(text)

    # Combine OCR-text confidence with the per-line parse confidence, then let the
    # interpreter classify + flag low-confidence rows needing verification.
    for rv in raw_values:
        rv.ocr_confidence = round((ocr_conf or 0.0) * rv.ocr_confidence, 4)

    interpretation = lab_interpreter.interpret_panel(raw_values)
    items: list[DraftItem] = []
    for b in interpretation.biomarkers:
        if b.canonical == "unknown":
            continue
        items.append(
            DraftItem(
                test_name=b.canonical,
                canonical=b.canonical,
                value=b.value,
                unit=b.unit,
                reference_range=b.reference_range,
                status=b.status.value,
                confidence=round(b.ocr_confidence, 4),
                needs_verification=b.needs_verification,
            )
        )

    confidence_avg = (
        round(sum(i.confidence for i in items) / len(items), 4) if items else 0.0
    )
    low_confidence = bool(items) and confidence_avg < lab_interpreter.OCR_CONFIDENCE_THRESHOLD
    manual_fallback = not items

    if low_confidence and not any("tin cậy" in w.lower() for w in warnings):
        warnings.append(
            "Một số chỉ số có độ tin cậy thấp — vui lòng kiểm tra lại trước khi lưu."
        )
    if manual_fallback:
        warnings.append(
            "Chưa nhận diện được chỉ số nào — bạn có thể nhập tay kết quả xét nghiệm."
        )
    if detected_date is None:
        warnings.append(
            "Chưa nhận diện được ngày xét nghiệm — vui lòng chọn ngày khám trước khi lưu."
        )

    return LabUploadDraft(
        provider_used=provider,
        confidence_avg=confidence_avg,
        parsed_values=items,
        warnings=warnings,
        raw_text_sha256=raw_hash,
        low_confidence=low_confidence,
        manual_fallback=manual_fallback,
        extracted_test_date=detected_date.iso if detected_date else None,
        test_date_label=detected_date.raw_label if detected_date else None,
        test_date_confidence=round(detected_date.confidence, 4) if detected_date else 0.0,
    )


def process_bytes(data: bytes, *, declared_mime: str | None = None) -> LabUploadDraft:
    mime = validate_upload(data, declared_mime=declared_mime)
    draft = build_draft(data, mime)
    logger.info(
        "lab_upload_draft provider=%s items=%d conf=%.2f hash=%s",
        draft.provider_used, len(draft.parsed_values), draft.confidence_avg,
        draft.raw_text_sha256 or "-",
    )
    return draft
