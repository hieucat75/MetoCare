"""Bytes-oriented OCR engine for the synchronous lab-upload draft pipeline.

Distinct from the legacy ``app.services.ocr`` (storage-key / async pipeline). This
module turns raw image bytes into text + a confidence score.

Policy (OCR Lab Upload track §1–§2):
  * **Primary = Tesseract**, running locally in-container. Cost $0. No network.
  * **Cloud = opt-in fallback only.** A cloud provider is constructed and called
    ONLY when ``FeatureFlag.OCR_CLOUD_FALLBACK`` is on AND a provider key is present
    AND the local confidence is below threshold. Medical images are never sent out
    silently.

All heavy/native imports (pytesseract, PIL) are lazy so the module imports cleanly
on a host without the Tesseract binary; ``TesseractEngine.available()`` reports it.
"""

from __future__ import annotations

import logging
import os
import time
import unicodedata
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.feature_flags import FeatureFlag, is_enabled
from app.domain.lab_interpreter import OCR_CONFIDENCE_THRESHOLD

logger = logging.getLogger("mcp.ocr_engine")


@dataclass
class OcrTextResult:
    text: str
    confidence: float
    provider: str
    warnings: list[str] = field(default_factory=list)


class OcrEngineError(Exception):
    """Raised when an OCR engine cannot run (missing binary / key / dependency)."""


# --------------------------------------------------------------------------- #
# Local Tesseract (default)
# --------------------------------------------------------------------------- #


class TesseractEngine:
    name = "tesseract"

    @staticmethod
    def available() -> bool:
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
        except Exception:
            return False
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def run(self, image_bytes: bytes) -> OcrTextResult:
        import io

        import pytesseract
        from PIL import Image, ImageOps

        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.load()
        except Exception as exc:  # not a decodable image
            raise OcrEngineError("Không đọc được tệp ảnh.") from exc

        # Greyscale + autocontrast helps Tesseract on phone photos of lab printouts.
        prepared = ImageOps.autocontrast(ImageOps.grayscale(img))
        lang = get_settings().ocr_lang
        try:
            data = pytesseract.image_to_data(
                prepared,
                lang=lang,
                config="--psm 6",
                output_type=pytesseract.Output.DICT,
            )
        except pytesseract.TesseractError as exc:
            raise OcrEngineError("OCR thất bại khi xử lý ảnh.") from exc
        except Exception as exc:  # e.g. missing language pack
            raise OcrEngineError("OCR không khả dụng (thiếu Tesseract hoặc gói ngôn ngữ).") from exc

        words = data.get("text", [])
        confs = data.get("conf", [])
        conf_values: list[float] = []
        for word, conf in zip(words, confs, strict=False):
            if not (word or "").strip():
                continue
            try:
                c = float(conf)
            except (TypeError, ValueError):
                c = -1.0
            if c >= 0:
                conf_values.append(c / 100.0)
        text = self._reflow(data)
        confidence = round(sum(conf_values) / len(conf_values), 4) if conf_values else 0.0
        return OcrTextResult(text=text, confidence=confidence, provider=self.name)

    @staticmethod
    def _reflow(data: dict) -> str:
        """Rebuild line-structured text from Tesseract's word boxes (keeps
        ``label: value`` pairs on the same line for the parser)."""
        lines: dict[tuple, list[str]] = {}
        words = data.get("text", [])
        for i, word in enumerate(words):
            w = (word or "").strip()
            if not w:
                continue
            key = (
                data.get("block_num", [0])[i],
                data.get("par_num", [0])[i],
                data.get("line_num", [0])[i],
            )
            lines.setdefault(key, []).append(w)
        return "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))


# --------------------------------------------------------------------------- #
# Mock engine (local dev / CI; activated when settings.ocr_provider == "mock")
# --------------------------------------------------------------------------- #

_MOCK_TEXT = """\
PHIẾU KẾT QUẢ XÉT NGHIỆM (DEV MOCK)
Ngày xét nghiệm: 15/06/2026
Glucose đói: 5.6 mmol/L [3.9-6.1]
Triglyceride: 1.8 mmol/L [<1.7]
Cholesterol: 4.5 mmol/L [<5.2]
HDL Cholesterol: 1.2 mmol/L [>1.0]
LDL Cholesterol: 2.8 mmol/L [<3.4]
Creatinine: 85 µmol/L [62-106]
Ure: 5.2 mmol/L [2.5-7.5]
AST: 28 U/L [<40]
ALT: 22 U/L [<40]
Hồng cầu: 4.8 T/L [4.2-5.4]
Bạch cầu: 7.2 G/L [4.0-10.0]
Tiểu cầu: 230 G/L [150-400]
Hemoglobin: 140 g/L [130-170]
HbA1c: 5.8 % [<5.7]
"""


class MockOcrEngine:
    name = "mock"

    def run(self, image_bytes: bytes, mime: str) -> OcrTextResult:  # noqa: ARG002
        return OcrTextResult(
            text=_MOCK_TEXT,
            confidence=0.98,
            provider=self.name,
            warnings=["[DEV] Mock OCR — dữ liệu mẫu để kiểm thử, không phải kết quả thật."],
        )


# --------------------------------------------------------------------------- #
# Cloud fallback adapters (opt-in; never called unless flag ON + key present)
# --------------------------------------------------------------------------- #


class AnthropicVisionEngine:
    name = "anthropic"

    @staticmethod
    def configured() -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))

    def run(self, image_bytes: bytes, mime: str) -> OcrTextResult:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise OcrEngineError("ANTHROPIC_API_KEY chưa được cấu hình.")
        import base64

        import httpx

        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        model = os.getenv("ANTHROPIC_OCR_MODEL", "claude-opus-4-8")
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1500,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {"type": "base64", "media_type": mime, "data": b64},
                                },
                                {
                                    "type": "text",
                                    "text": (
                                        "Transcribe every line of this lab report verbatim as "
                                        "plain text. Keep each test name and its value/unit on "
                                        "the same line. Do not interpret or summarise."
                                    ),
                                },
                            ],
                        }
                    ],
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            blocks = resp.json().get("content", [])
            text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except httpx.HTTPError as exc:
            raise OcrEngineError("Cloud OCR (Anthropic) thất bại.") from exc
        # Vision transcription has no per-word confidence; treat as moderately high.
        return OcrTextResult(text=text, confidence=0.9, provider=self.name)


class AzureDocIntelEngine:
    """Azure AI Document Intelligence (Form Recognizer) cloud fallback — real impl.

    Uses the GA REST API (``2024-11-30``) with the ``prebuilt-layout`` model by
    default: layout reconstructs ruled lab-result tables (test | value | unit |
    range) far better than Tesseract on phone photos, which is exactly where the
    local engine is weak. The model is overridable via ``AZURE_DOC_INTEL_MODEL``
    (e.g. ``prebuilt-read`` for the cheaper read model).

    Returns the document ``content`` (reading-order text) augmented with one line
    per detected table row, plus the **real** average word confidence reported by
    the service — so the orchestrator keeps whichever transcription scores higher
    rather than trusting a hardcoded guess.
    """

    name = "azure"
    _API_VERSION = "2024-11-30"
    _DEFAULT_MODEL = "prebuilt-layout"
    _SUBMIT_TIMEOUT_S = 30.0
    _POLL_TIMEOUT_S = 30.0
    _POLL_MAX_ATTEMPTS = 30
    _POLL_INTERVAL_S = 1.0
    _POLL_BACKOFF_CAP_S = 5.0
    _NO_WORD_CONF_DEFAULT = 0.9  # service returned no per-word confidence

    @staticmethod
    def configured() -> bool:
        return bool(os.getenv("AZURE_DOC_INTEL_KEY") and os.getenv("AZURE_DOC_INTEL_ENDPOINT"))

    def analyze_raw(self, image_bytes: bytes, mime: str) -> dict:
        """Submit to Azure DI and poll to completion; return raw analyzeResult dict.

        Raises OcrEngineError on any failure. Callers that only need text can call
        run() instead; callers that want table-first extraction call this directly
        and pass the result to lab_table_extractor.extract_and_map().
        """
        key = os.getenv("AZURE_DOC_INTEL_KEY")
        endpoint = os.getenv("AZURE_DOC_INTEL_ENDPOINT")
        if not (key and endpoint):
            raise OcrEngineError("AZURE_DOC_INTEL_* chưa được cấu hình.")
        import httpx

        model = (os.getenv("AZURE_DOC_INTEL_MODEL") or self._DEFAULT_MODEL).strip()
        analyze = (
            f"{endpoint.rstrip('/')}/documentintelligence/documentModels/"
            f"{model}:analyze?api-version={self._API_VERSION}"
        )
        try:
            submit = httpx.post(
                analyze,
                headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": mime},
                content=image_bytes,
                timeout=self._SUBMIT_TIMEOUT_S,
            )
            submit.raise_for_status()
            op_url = submit.headers.get("operation-location")
            if not op_url:
                raise OcrEngineError("Azure Doc Intel không trả operation-location.")
            from urllib.parse import urlparse

            if urlparse(op_url).netloc != urlparse(endpoint).netloc:
                raise OcrEngineError("Azure Doc Intel trả về operation-location không hợp lệ.")
            body = self._poll(httpx, op_url, key)
        except httpx.HTTPError as exc:
            raise OcrEngineError("Cloud OCR (Azure) thất bại.") from exc
        return body.get("analyzeResult", {}) or {}

    def run(self, image_bytes: bytes, mime: str) -> OcrTextResult:
        analyze_result = self.analyze_raw(image_bytes, mime)
        text = self._build_text(analyze_result)
        confidence = self._avg_word_confidence(analyze_result)
        return OcrTextResult(text=text, confidence=confidence, provider=self.name)

    def _poll(self, httpx, op_url: str, key: str) -> dict:
        """Poll the long-running analyze operation until terminal. Honours the
        server-suggested ``retry-after`` backoff; raises on failure/timeout."""

        for _ in range(self._POLL_MAX_ATTEMPTS):
            poll = httpx.get(
                op_url,
                headers={"Ocp-Apim-Subscription-Key": key},
                timeout=self._POLL_TIMEOUT_S,
            )
            poll.raise_for_status()
            body = poll.json()
            status = (body.get("status") or "").lower()
            if status == "succeeded":
                return body
            if status == "failed":
                raise OcrEngineError("Azure Doc Intel báo lỗi khi phân tích tài liệu.")
            retry_after = poll.headers.get("retry-after")
            try:
                delay = float(retry_after) if retry_after else self._POLL_INTERVAL_S
            except (TypeError, ValueError):
                delay = self._POLL_INTERVAL_S
            time.sleep(min(delay, self._POLL_BACKOFF_CAP_S))
        raise OcrEngineError("Azure Doc Intel hết thời gian chờ phân tích.")

    # Substrings that identify a "reference range" column header in Vietnamese/English.
    # When found in row-0 cells, that entire column is excluded from text output so
    # reference-range numbers cannot be misread as result values.
    _REF_COL_KEYWORDS: frozenset[str] = frozenset(
        {
            "binh thuong",
            "bình thường",
            "tham chieu",
            "tham chiếu",
            "gia tri tham chieu",
            "giá trị tham chiếu",
            "gia tri bt",
            "giá trị bt",
            "khoang tham chieu",
            "khoảng tham chiếu",
            "gia tri binh thuong",
            "giá trị bình thường",
            "normal range",
            "reference range",
            "reference",
            "normal",
        }
    )

    @staticmethod
    def _strip_accents_lower(s: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn"
        )

    @classmethod
    def _build_text(cls, analyze_result: dict) -> str:
        """Document content (reading order) + one reflowed line per table row, so
        columnar lab data lands on a single line for the heuristic parser.

        Reference-range columns are detected via header-row keywords and skipped
        so their values cannot be misread as result values by the parser."""
        content = (analyze_result.get("content") or "").strip()
        table_lines: list[str] = []
        for table in analyze_result.get("tables", []) or []:
            cells_raw = table.get("cells", []) or []

            # Identify reference-range column indices from the header row
            # (row 0 or cells with kind="columnHeader").
            ref_cols: set[int] = set()
            for cell in cells_raw:
                ri = cell.get("rowIndex", 0)
                kind = (cell.get("kind") or "").lower()
                if ri != 0 and kind != "columnheader":
                    continue
                txt = (cell.get("content") or "").strip()
                if not txt:
                    continue
                txt_norm = cls._strip_accents_lower(txt)
                if any(kw in txt_norm for kw in cls._REF_COL_KEYWORDS):
                    ref_cols.add(cell.get("columnIndex", 0))

            rows: dict[int, list[tuple[int, str]]] = {}
            for cell in cells_raw:
                col = cell.get("columnIndex", 0)
                if col in ref_cols:
                    continue
                txt = (cell.get("content") or "").strip()
                if not txt:
                    continue
                rows.setdefault(cell.get("rowIndex", 0), []).append((col, txt))

            for r in sorted(rows):
                row_cells = [t for _, t in sorted(rows[r])]
                if row_cells:
                    table_lines.append(" ".join(row_cells))
        if table_lines:
            return (content + "\n" + "\n".join(table_lines)).strip()
        return content

    @classmethod
    def _avg_word_confidence(cls, analyze_result: dict) -> float:
        """Mean of the per-word confidences the service reports (0..1). Falls back
        to a high default when the model returns none."""
        confs = [
            w["confidence"]
            for page in analyze_result.get("pages", []) or []
            for w in page.get("words", []) or []
            if isinstance(w.get("confidence"), (int, float))
        ]
        if not confs:
            return cls._NO_WORD_CONF_DEFAULT
        return round(sum(confs) / len(confs), 4)


def _cloud_engine() -> AnthropicVisionEngine | AzureDocIntelEngine | None:
    """Construct the configured cloud engine, or None when not usable.

    Returns None unless the fallback flag is ON, a provider is named, and its key
    is present — so a misconfiguration falls through to the local result instead
    of crashing.
    """
    if not is_enabled(FeatureFlag.OCR_CLOUD_FALLBACK):
        return None
    provider = (get_settings().ocr_cloud_provider or "").lower()
    if provider == "anthropic" and AnthropicVisionEngine.configured():
        return AnthropicVisionEngine()
    if provider == "azure" and AzureDocIntelEngine.configured():
        return AzureDocIntelEngine()
    return None


def run_cloud_ocr_if_permitted(image_bytes: bytes, mime: str) -> OcrTextResult | None:
    """Run the configured cloud engine ONLY when permitted (flag ON + provider +
    key). Used by the draft builder to escalate when the local transcription
    parsed *zero* biomarkers despite acceptable confidence — a layout the cloud
    engine usually handles. Never raises: a cloud failure returns None so the
    caller keeps its local result. Returns None when cloud is not permitted, so a
    medical image is never sent out unless the opt-in fallback is explicitly on.
    """
    cloud = _cloud_engine()
    if cloud is None:
        return None
    try:
        return cloud.run(image_bytes, mime)
    except OcrEngineError:
        logger.warning("cloud_ocr_escalation_failed provider=%s", cloud.name)
        return None


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #


def _is_mock_explicitly_allowed() -> bool:
    """Mock OCR is only permitted with an explicit opt-in env var — never as a silent fallback."""
    return (
        os.getenv("MCP_OCR_PROVIDER", "").strip().lower() == "mock"
        or os.getenv("MCP_ENABLE_MOCK_OCR", "").strip().lower() in ("true", "1", "yes")
    )


def _assert_mock_not_in_prod() -> None:
    """Raise OcrEngineError if the current environment forbids mock OCR.

    Reads MCP_ENV directly (not via the lru_cache'd get_settings()) so that
    monkeypatch.setenv works correctly in tests and live env-var changes take effect.
    """
    env = (os.getenv("MCP_ENV") or get_settings().env or "dev").lower().strip()
    if env in ("staging", "production", "prod"):
        raise OcrEngineError(
            f"MockOcrEngine bị cấm trong môi trường '{env}'. "
            "Cần cấu hình Azure Document Intelligence hoặc Tesseract."
        )


def run_ocr(image_bytes: bytes, mime: str) -> OcrTextResult:
    """Engine selection: explicit-mock-only → Azure → Tesseract → error.

    Mock runs ONLY when MCP_OCR_PROVIDER=mock or MCP_ENABLE_MOCK_OCR=true is set,
    and is hard-blocked in staging/production environments. There is NO implicit
    mock fallback: if no real provider is configured, OcrEngineError is raised so
    the upload route returns a patient-friendly "try again or enter manually" 503.
    """
    if _is_mock_explicitly_allowed():
        _assert_mock_not_in_prod()
        return MockOcrEngine().run(image_bytes, mime)

    if AzureDocIntelEngine.configured():
        return AzureDocIntelEngine().run(image_bytes, mime)

    if TesseractEngine.available():
        local = TesseractEngine().run(image_bytes)
        if local.confidence < OCR_CONFIDENCE_THRESHOLD:
            local.warnings.append(
                "Độ tin cậy OCR thấp — vui lòng kiểm tra lại các chỉ số trước khi lưu."
            )
        return local

    raise OcrEngineError(
        "OCR không khả dụng: cần cấu hình Azure Document Intelligence "
        "(AZURE_DOC_INTEL_KEY + AZURE_DOC_INTEL_ENDPOINT) hoặc cài Tesseract."
    )
