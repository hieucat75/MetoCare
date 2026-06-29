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
from app.domain.hospital_profiles import UNKNOWN_PROFILE, detect_hospital_result
from app.domain.lab_interpreter import ConfidenceDetail
from app.domain.lab_table_extractor import extract_and_map as _extract_table_and_map
from app.domain.ocr_date_resolver import OcrDateResolver
from app.services import lab_parser
from app.services.ocr_engine import (
    AzureDocIntelEngine,
    OcrEngineError,
    run_cloud_ocr_if_permitted,
    run_ocr,
)

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
    test_name: str  # canonical key (maps to LabResultItemIn.test_name)
    canonical: str
    value: float
    unit: str
    reference_range: str | None
    status: str
    confidence: float
    needs_verification: bool
    confidence_reasons: list[str] = field(default_factory=list)
    # Raw OCR value/unit — always set to the as-printed values for display.
    original_value: float | None = None
    original_unit: str | None = None
    original_test_name: str = ""  # as OCR'd printed label
    display_name_vi: str = ""  # Vietnamese label from catalog
    canonical_value: float = 0.0  # canonical SI value (for save/metrics)
    canonical_unit: str = ""  # canonical SI unit  (for save/metrics)
    display_reference_range: str | None = None  # ref range in display unit (same unit as result)


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
    # Hospital detection (populated by build_draft; used by route to create OCRCase).
    hospital_id: str | None = None
    hospital_confidence: float = 0.0
    # Date resolver output — True when user should confirm the exam date.
    date_needs_confirmation: bool = False


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
    """PDF extraction: text layer first (free, instant for digital reports);
    Azure DI fallback for scanned/image PDFs; rasterize+Tesseract last resort.
    Never raises — falls back to empty text so upload always succeeds."""
    warnings: list[str] = []
    settings = get_settings()

    # 0) Text layer (pypdf) — zero cost for digital lab reports; try first.
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

    # 1) Azure Document Intelligence — table-aware OCR for scanned printouts.
    if AzureDocIntelEngine.configured():
        try:
            res = AzureDocIntelEngine().run(data, PDF)
            return res.text, res.confidence, res.provider, list(res.warnings)
        except OcrEngineError as exc:
            warnings.append(str(exc))

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
    warnings: list[str] = []
    raw_values: list = []
    text = ""
    ocr_conf = 0.0
    provider = "unknown"
    azure_succeeded = False

    # Table-first path: Azure DI → extract_table_rows → map_table_rows_to_raw_values.
    # PDFs route through _extract_text (text layer first, then Azure) so that
    # digital lab reports use the free text-layer path and hospital parsers apply.
    # Azure table-first is for image uploads only.
    if AzureDocIntelEngine.configured() and mime != PDF:
        try:
            engine = AzureDocIntelEngine()
            analyze_result = engine.analyze_raw(data, mime)
            ocr_conf = AzureDocIntelEngine._avg_word_confidence(analyze_result)
            text = AzureDocIntelEngine._build_text(analyze_result)
            provider = engine.name
            azure_succeeded = True
            raw_values = _extract_table_and_map(analyze_result, ocr_conf=ocr_conf)
            if not raw_values:
                # Tables empty or no recognizable biomarkers — fall back to text+regex
                # on the same already-extracted text (no second network call).
                raw_values = lab_parser.parse_lab_text(text)
        except OcrEngineError as exc:
            warnings.append(str(exc))

    if not azure_succeeded:
        text, ocr_conf, provider, text_warnings = _extract_text(data, mime)
        warnings.extend(text_warnings)
        raw_values = lab_parser.parse_lab_text(text)

    # Zero-biomarker escalation for non-Azure providers only.
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

    # Run detected date through OCR Date Resolver to guard against DOB misclassification.
    date_needs_confirmation = False
    date_resolver = OcrDateResolver()
    if detected_date is not None:
        raw_dates = [
            {
                "value": detected_date.iso,
                "label": detected_date.raw_label or "",
                "confidence": round(detected_date.confidence, 4),
            }
        ]
        resolved_dates = date_resolver.resolve(raw_dates)
        best_date = date_resolver.best_exam_date(resolved_dates)
        date_needs_confirmation = date_resolver.needs_user_confirmation(resolved_dates)
        # If resolver determines the detected date is a DOB, discard it.
        if best_date is None:
            detected_date = None
            warnings.append(
                "Ngày phát hiện có thể là ngày sinh — vui lòng nhập ngày xét nghiệm thủ công."
            )
        elif date_needs_confirmation:
            warnings.append(
                "Ngày xét nghiệm cần xác nhận — độ tin cậy thấp hoặc không rõ nguồn gốc."
            )
    elif detected_date is None:
        date_needs_confirmation = False

    hospital_detection = detect_hospital_result(text) if text else None
    hospital_id: str | None = None
    hospital_confidence: float = 0.0
    if hospital_detection and hospital_detection.profile is not UNKNOWN_PROFILE:
        hospital_id = hospital_detection.profile.hospital_id
        hospital_confidence = hospital_detection.confidence

    # Combine OCR-text confidence with the per-line parse confidence, then let the
    # interpreter classify + flag low-confidence rows needing verification.
    # Reconstruct confidence_detail so reasons stay consistent with the final score.
    for rv in raw_values:
        rv.ocr_confidence = round((ocr_conf or 0.0) * rv.ocr_confidence, 4)
        if rv.confidence_detail is not None:
            engine_pct = round((ocr_conf or 0.0) * 100)
            engine_note = (
                f"⚠ Chất lượng OCR ảnh: {engine_pct}% — kiểm tra lại giá trị"
                if (ocr_conf or 0.0) < 0.9
                else f"✓ Chất lượng OCR ảnh: {engine_pct}%"
            )
            rv.confidence_detail = ConfidenceDetail(
                ocr=rv.confidence_detail.ocr,
                mapping=rv.confidence_detail.mapping,
                conversion=rv.confidence_detail.conversion,
                clinical=rv.confidence_detail.clinical,
                overall=rv.ocr_confidence,
                reasons=[engine_note] + rv.confidence_detail.reasons,
            )

    interpretation = lab_interpreter.interpret_panel(raw_values)
    items: list[DraftItem] = []
    for b in interpretation.biomarkers:
        if b.canonical == "unknown":
            continue
        # Use original (as-printed) value/unit for display; canonical for save path.
        disp_value = b.original_value if b.original_value is not None else b.value
        disp_unit = b.original_unit if b.original_unit is not None else b.unit
        items.append(
            DraftItem(
                test_name=b.canonical,
                canonical=b.canonical,
                value=disp_value,
                unit=disp_unit,
                reference_range=b.reference_range,
                status=b.status.value,
                confidence=round(b.ocr_confidence, 4),
                needs_verification=b.needs_verification,
                confidence_reasons=(b.confidence_detail.reasons if b.confidence_detail else []),
                original_value=disp_value,
                original_unit=disp_unit,
                original_test_name=b.raw_test_name,
                display_name_vi=b.display_name_vi,
                canonical_value=b.value,
                canonical_unit=b.unit,
                display_reference_range=b.display_reference_range,
            )
        )

    confidence_avg = round(sum(i.confidence for i in items) / len(items), 4) if items else 0.0
    low_confidence = bool(items) and confidence_avg < lab_interpreter.OCR_CONFIDENCE_THRESHOLD
    manual_fallback = not items

    if low_confidence and not any("tin cậy" in w.lower() for w in warnings):
        warnings.append("Một số chỉ số có độ tin cậy thấp — vui lòng kiểm tra lại trước khi lưu.")
    if manual_fallback:
        warnings.append("Chưa nhận diện được chỉ số nào — bạn có thể nhập tay kết quả xét nghiệm.")
    if detected_date is None and not any(
        "ngày" in w.lower() and "sinh" in w.lower() for w in warnings
    ):
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
        hospital_id=hospital_id,
        hospital_confidence=hospital_confidence,
        date_needs_confirmation=date_needs_confirmation,
    )


def process_bytes(data: bytes, *, declared_mime: str | None = None) -> LabUploadDraft:
    mime = validate_upload(data, declared_mime=declared_mime)
    draft = build_draft(data, mime)
    logger.info(
        "lab_upload_draft provider=%s items=%d conf=%.2f hash=%s",
        draft.provider_used,
        len(draft.parsed_values),
        draft.confidence_avg,
        draft.raw_text_sha256 or "-",
    )
    return draft
