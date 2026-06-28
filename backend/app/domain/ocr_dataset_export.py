"""OCR dataset export — writes anonymized samples to ocr_dataset/benchmark/<hospital>/.

Export is only allowed when MCP_ENV in ("staging", "dev") OR user_consent_granted=True.

Written expected.json uses corrected rows as ground truth.
contains_phi is set to True and anonymized=False until admin manually reviews —
the admin must rename the flag after PHI removal before committing to git.

No image bytes are written here. The image file is placed by the admin
after PHI review into images/<sample_id>.<ext> locally (never committed).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

_logger = logging.getLogger("mcp.ocr_dataset_export")

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = _BACKEND_DIR / "ocr_dataset"

_ALLOWED_ENVS = frozenset({"staging", "dev"})
_KNOWN_HOSPITALS = frozenset(
    {
        "vinmec",
        "medlatec",
        "tamanh",
        "hongngoc",
        "bachmai",
        "bachmai108",
        "fv",
        "hoanmy",
        "thucuc",
        "vietduc",
    }
)


@dataclass(frozen=True)
class ExportResult:
    exported: bool
    sample_id: str | None
    reason: str
    dataset_path: str | None = None


def is_export_allowed(*, user_consent_granted: bool = False) -> bool:
    """True only when BOTH env is staging/dev AND MCP_OCR_DATASET_EXPORT_ENABLED=true,
    OR the user has individually granted data export consent.
    Fails closed: missing flag blocks export even in dev to prevent accidental PHI writes."""
    s = get_settings()
    env_ok = s.env.lower() in _ALLOWED_ENVS and s.ocr_dataset_export_enabled
    return env_ok or user_consent_granted


def _safe_hospital(hospital_id: str | None) -> str:
    if hospital_id and hospital_id in _KNOWN_HOSPITALS:
        return hospital_id
    return "other"


def export_case(
    *,
    sample_id: str,
    hospital_id: str | None,
    corrected_rows: list[dict],
    test_date: str | None,
    gap_report: dict | None,
    hospital_confidence: float | None,
    parser_version: str | None,
    azure_json: dict | None = None,
    user_consent_granted: bool = False,
) -> ExportResult:
    """Write benchmark sample to disk. Non-blocking — callers catch all errors."""
    if not is_export_allowed(user_consent_granted=user_consent_granted):
        return ExportResult(exported=False, sample_id=sample_id, reason="policy_disallow")

    hospital = _safe_hospital(hospital_id)
    base = DATASET_DIR / "benchmark" / hospital

    if not (base / "expected").exists():
        _logger.warning("ocr_export_missing_dir hospital=%s path=%s", hospital, base)
        return ExportResult(exported=False, sample_id=sample_id, reason="dir_missing")

    try:
        _write_expected(base, sample_id, hospital, corrected_rows, test_date)
        if azure_json:
            _write_azure_cache(base, sample_id, azure_json)
        _write_notes(base, sample_id, gap_report, hospital_confidence, parser_version)
    except OSError as exc:
        _logger.error("ocr_export_io_error sample=%s err=%s", sample_id, exc)
        return ExportResult(exported=False, sample_id=sample_id, reason=f"io_error:{exc}")

    rel_path = f"ocr_dataset/benchmark/{hospital}/{sample_id}"
    _logger.info("ocr_export_success sample=%s hospital=%s path=%s", sample_id, hospital, rel_path)
    return ExportResult(exported=True, sample_id=sample_id, reason="ok", dataset_path=rel_path)


def _write_expected(
    base: Path,
    sample_id: str,
    hospital: str,
    corrected_rows: list[dict],
    test_date: str | None,
) -> None:
    rows_out = [
        {
            "row_index": idx,
            "original_test_name": row.get("original_test_name") or row.get("test_name") or "",
            "display_name_vi": row.get("display_name_vi") or "",
            "mapped_metric_type": row.get("mapped_metric_type") or None,
            "value": row.get("value"),
            "unit": row.get("unit") or "",
            "reference_range": row.get("reference_range") or None,
            "status": row.get("status") or None,
        }
        for idx, row in enumerate(corrected_rows, start=1)
    ]
    payload = {
        "sample_id": sample_id,
        "hospital": hospital,
        "report_type": "lab_result",
        "language": "vi",
        "test_date": test_date or "",
        "source": {
            "uploaded_by": "user_correction",
            "anonymized": False,  # admin must verify PHI removal before setting True
            "contains_phi": True,  # assumed until admin confirms — never commit as-is
        },
        "rows": rows_out,
    }
    out = base / "expected" / f"{sample_id}.expected.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_azure_cache(base: Path, sample_id: str, azure_json: dict) -> None:
    out = base / "azure_cache" / f"{sample_id}.azure.json"
    out.write_text(json.dumps(azure_json, ensure_ascii=False), encoding="utf-8")


def _write_notes(
    base: Path,
    sample_id: str,
    gap_report: dict | None,
    hospital_confidence: float | None,
    parser_version: str | None,
) -> None:
    conf_str = f"{hospital_confidence:.2f}" if hospital_confidence is not None else "unknown"
    lines = [
        f"# OCR Case: {sample_id}",
        "",
        "- **source**: user_correction",
        f"- **parser_version**: {parser_version or 'unknown'}",
        f"- **hospital_confidence**: {conf_str}",
        "",
    ]
    if gap_report:
        lines += [
            "## Accuracy",
            f"- row_accuracy: {gap_report.get('row_accuracy', 0):.1%}",
            f"- value_accuracy: {gap_report.get('value_accuracy', 0):.1%}",
            f"- unit_accuracy: {gap_report.get('unit_accuracy', 0):.1%}",
            f"- editing_rate: {gap_report.get('editing_rate', 0):.1%}",
            f"- rows_total: {gap_report.get('total_extracted_rows', 0)}",
            f"- false_positives: {gap_report.get('false_positive_rows', 0)}",
            f"- missing_rows: {gap_report.get('missing_rows', 0)}",
            "",
        ]
    lines += [
        "## TODO (admin before commit)",
        "- [ ] Verify PHI removed from image (patient name/DOB/ID/address)",
        "- [ ] Set `anonymized: true` and `contains_phi: false` in expected JSON",
        "- [ ] Move image to images/<sample_id>.<ext>",
    ]
    out = base / "notes" / f"{sample_id}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
