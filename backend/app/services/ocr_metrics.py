"""OCR pipeline metrics (internal only - not exposed to patient API)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)


@dataclass
class OcrMetrics:
    total_uploads: int = 0
    successful_extractions: int = 0
    failed_extractions: int = 0
    unknown_biomarker_count: int = 0
    low_confidence_count: int = 0
    hospital_counts: dict[str, int] = field(default_factory=dict)
    _confidence_sum: float = 0.0
    _biomarkers_processed: int = 0

    def record_upload(
        self,
        *,
        hospital_id: str | None,
        biomarkers_found: int,
        unknown_biomarkers: int,
        avg_confidence: float,
        success: bool,
    ) -> None:
        self.total_uploads += 1
        if success:
            self.successful_extractions += 1
        else:
            self.failed_extractions += 1
        self.unknown_biomarker_count += unknown_biomarkers
        if avg_confidence < 0.6:
            self.low_confidence_count += 1
        hid = hospital_id or "unknown"
        self.hospital_counts[hid] = self.hospital_counts.get(hid, 0) + 1
        self._confidence_sum += avg_confidence * biomarkers_found
        self._biomarkers_processed += biomarkers_found
        _logger.info(
            "ocr_upload_recorded",
            extra={
                "hospital_id": hid,
                "biomarkers_found": biomarkers_found,
                "unknown_biomarkers": unknown_biomarkers,
                "avg_confidence": round(avg_confidence, 3),
                "success": success,
            },
        )

    @property
    def avg_confidence(self) -> float:
        if self._biomarkers_processed == 0:
            return 0.0
        return round(self._confidence_sum / self._biomarkers_processed, 3)

    @property
    def success_rate(self) -> float:
        if self.total_uploads == 0:
            return 0.0
        return round(self.successful_extractions / self.total_uploads, 3)


_metrics = OcrMetrics()


def get_metrics() -> OcrMetrics:
    return _metrics
