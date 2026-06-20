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
                prepared, lang=lang, config="--psm 6",
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
                                {"type": "image", "source": {
                                    "type": "base64", "media_type": mime, "data": b64}},
                                {"type": "text", "text": (
                                    "Transcribe every line of this lab report verbatim as "
                                    "plain text. Keep each test name and its value/unit on "
                                    "the same line. Do not interpret or summarise.")},
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
    name = "azure"

    @staticmethod
    def configured() -> bool:
        return bool(os.getenv("AZURE_DOC_INTEL_KEY") and os.getenv("AZURE_DOC_INTEL_ENDPOINT"))

    def run(self, image_bytes: bytes, mime: str) -> OcrTextResult:
        key = os.getenv("AZURE_DOC_INTEL_KEY")
        endpoint = os.getenv("AZURE_DOC_INTEL_ENDPOINT")
        if not (key and endpoint):
            raise OcrEngineError("AZURE_DOC_INTEL_* chưa được cấu hình.")
        import time

        import httpx

        analyze = (
            f"{endpoint.rstrip('/')}/documentintelligence/documentModels/"
            "prebuilt-read:analyze?api-version=2024-02-29-preview"
        )
        try:
            submit = httpx.post(
                analyze,
                headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": mime},
                content=image_bytes,
                timeout=30.0,
            )
            submit.raise_for_status()
            op_url = submit.headers.get("operation-location")
            if not op_url:
                raise OcrEngineError("Azure Doc Intel không trả operation-location.")
            for _ in range(15):
                poll = httpx.get(
                    op_url, headers={"Ocp-Apim-Subscription-Key": key}, timeout=30.0
                )
                poll.raise_for_status()
                body = poll.json()
                if body.get("status") in ("succeeded", "failed"):
                    break
                time.sleep(1.0)
            text = body.get("analyzeResult", {}).get("content", "")
        except httpx.HTTPError as exc:
            raise OcrEngineError("Cloud OCR (Azure) thất bại.") from exc
        return OcrTextResult(text=text, confidence=0.9, provider=self.name)


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


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #

def run_ocr(image_bytes: bytes, mime: str) -> OcrTextResult:
    """Run local Tesseract; escalate to cloud only when permitted AND low-confidence.

    Never raises for the cloud path — a cloud failure logs + falls back to the
    local result with a warning, so the draft endpoint stays available.
    """
    warnings: list[str] = []
    if not TesseractEngine.available():
        raise OcrEngineError(
            "Tesseract chưa được cài đặt trong môi trường này."
        )
    local = TesseractEngine().run(image_bytes)

    if local.confidence >= OCR_CONFIDENCE_THRESHOLD:
        return local

    cloud = _cloud_engine()
    if cloud is None:
        # Low confidence and no permitted fallback — surface it for manual review.
        local.warnings.append(
            "Độ tin cậy OCR thấp — vui lòng kiểm tra lại các chỉ số trước khi lưu."
        )
        return local

    try:
        result = cloud.run(image_bytes, mime)
        result.warnings.extend(warnings)
        result.warnings.append("Đã dùng OCR đám mây (fallback) do độ tin cậy cục bộ thấp.")
        # Keep whichever transcription is more confident.
        return result if result.confidence >= local.confidence else local
    except OcrEngineError:
        logger.warning("cloud_ocr_fallback_failed provider=%s", cloud.name)
        local.warnings.append(
            "OCR đám mây không khả dụng — dùng kết quả cục bộ, vui lòng kiểm tra lại."
        )
        return local
