"""OCR providers for the lab-document pipeline (P2 #3).

`MockOCRProvider` (default) returns a deterministic synthetic panel from a fixture
map keyed by storage_key — no real OCR, no network, no real PHI. A storage_key
containing "fail" / "corrupt" raises `OCRExtractionError` so the failure path is
testable. `TesseractProvider` / `CloudOCRProvider` are config-gated skeletons that
never call out.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.domain.lab_interpreter import RawLabValue


class OCRError(Exception):
    """Base class for OCR errors."""


class OCRExtractionError(OCRError):
    """OCR failed to extract text/values from a document."""


class OCRConfigError(OCRError):
    """A real OCR provider was selected without being wired up (skeleton)."""


@dataclass
class OCRExtraction:
    text: str
    values: list[RawLabValue] = field(default_factory=list)
    confidence: float = 1.0


class OCRProvider(ABC):
    name: str = "base"

    @abstractmethod
    def extract(self, storage_key: str) -> OCRExtraction: ...


# Deterministic fixture panels keyed by a token in the storage_key. The default
# panel is returned for any unmatched key. Values are obviously synthetic.
_DEFAULT_PANEL = [
    RawLabValue("Glucose", 110.0, "mg/dL", ocr_confidence=0.95),
    RawLabValue("Triglyceride", 220.0, "mg/dL", ocr_confidence=0.92),
    RawLabValue("HDL", 38.0, "mg/dL", ocr_confidence=0.60),
    RawLabValue("HbA1c", 6.1, "%", ocr_confidence=0.90),
]

_FIXTURE_PANELS: dict[str, list[RawLabValue]] = {
    "normal": [
        RawLabValue("Glucose", 88.0, "mg/dL", ocr_confidence=0.97),
        RawLabValue("HbA1c", 5.2, "%", ocr_confidence=0.95),
    ],
    "critical": [
        RawLabValue("Glucose", 320.0, "mg/dL", ocr_confidence=0.93),
        RawLabValue("Triglyceride", 540.0, "mg/dL", ocr_confidence=0.91),
    ],
}


class MockOCRProvider(OCRProvider):
    name = "mock"

    def extract(self, storage_key: str) -> OCRExtraction:
        key = (storage_key or "").lower()
        if "fail" in key or "corrupt" in key:
            raise OCRExtractionError(f"Mock OCR failed for storage_key={storage_key!r}")
        values = _DEFAULT_PANEL
        for token, panel in _FIXTURE_PANELS.items():
            if token in key:
                values = panel
                break
        text = "PHIẾU XÉT NGHIỆM (mock)\n" + "\n".join(
            f"{v.test_name}: {v.value} {v.unit or ''}".strip() for v in values
        )
        confidence = min((v.ocr_confidence for v in values), default=1.0)
        return OCRExtraction(text=text, values=list(values), confidence=confidence)


class TesseractProvider(OCRProvider):
    name = "tesseract"

    def extract(self, storage_key: str) -> OCRExtraction:
        raise OCRConfigError(
            "TesseractProvider is a skeleton (needs pytesseract + binary). "
            "Set MCP_OCR_PROVIDER=mock for dev/test."
        )


class CloudOCRProvider(OCRProvider):
    name = "cloud"

    def extract(self, storage_key: str) -> OCRExtraction:
        raise OCRConfigError(
            "CloudOCRProvider is a skeleton (needs cloud OCR credentials). "
            "Set MCP_OCR_PROVIDER=mock for dev/test."
        )


def get_ocr_provider() -> OCRProvider:
    name = get_settings().ocr_provider
    if name == "mock":
        return MockOCRProvider()
    if name == "tesseract":
        return TesseractProvider()
    if name == "cloud":
        return CloudOCRProvider()
    raise OCRConfigError(f"Unknown MCP_OCR_PROVIDER: {name!r}")
