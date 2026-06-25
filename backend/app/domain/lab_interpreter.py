"""Lab Result Interpreter foundation.

Implements ``docs/AI_Safety_Guardrail.md`` §4.4 (lab interpretation policy) and
``Technical_Architecture.md`` Lab OCR & Interpreter row. Provides:

- biomarker name normalization (Vietnamese + English aliases)
- reference ranges (adult, screening-oriented — NOT diagnostic criteria)
- classification: normal / low / high / critical
- patient-friendly explanation (probabilistic language + disclaimer)
- doctor summary (data only, no clinical conclusion)
- a MOCK OCR mode so the pipeline runs in dev/test without a real provider

Pure standard library. No real OCR / LLM calls. The classifier NEVER concludes a
diagnosis — it only flags values relative to reference ranges and suggests next
steps, per policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from . import policies


class LabStatus(StrEnum):
    NORMAL = "normal"
    LOW = "low"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"  # biomarker not recognized / no reference range


# Canonical biomarker -> (aliases, unit, ref_low, ref_high, critical_low, critical_high, ...)
@dataclass(frozen=True)
class BiomarkerSpec:
    canonical: str
    aliases: tuple[str, ...]
    unit: str
    ref_low: float | None
    ref_high: float | None
    critical_low: float | None = None
    critical_high: float | None = None
    # SI-equivalent unit: multiply extracted value by si_factor to reach canonical unit.
    # Example: glucose in mmol/L × 18.018 → mg/dL.
    si_unit: str | None = None
    si_factor: float = 1.0
    # Units that are clinically impossible for this biomarker — trigger confidence=0.
    incompatible_units: tuple[str, ...] = ()


# Adult, fasting where relevant. Screening reference ranges only.
BIOMARKERS: tuple[BiomarkerSpec, ...] = (
    BiomarkerSpec("fasting_glucose", ("glucose", "đường huyết đói", "glucose máu", "duong huyet"),
                  "mg/dL", 70, 99, critical_low=54, critical_high=300,
                  si_unit="mmol/L", si_factor=18.018,
                  incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L")),
    BiomarkerSpec("hba1c", ("hba1c", "a1c", "đường huyết trung bình"),
                  "%", 4.0, 5.6, critical_high=10.0),
    BiomarkerSpec("ldl", ("ldl", "ldl-c", "ldl cholesterol", "cholesterol xấu"),
                  "mg/dL", 0, 99, critical_high=190,
                  si_unit="mmol/L", si_factor=38.67,
                  incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L")),
    BiomarkerSpec("hdl", ("hdl", "hdl-c", "cholesterol tốt"),
                  "mg/dL", 40, 200, critical_low=20,
                  si_unit="mmol/L", si_factor=38.67,
                  incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L")),
    BiomarkerSpec("triglyceride",
                  ("triglyceride", "triglycerides", "triglycerid", "tg", "mỡ máu"),
                  "mg/dL", 0, 149, critical_high=500,
                  si_unit="mmol/L", si_factor=88.57,
                  incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L")),
    BiomarkerSpec("total_cholesterol",
                  ("cholesterol toàn phần", "total cholesterol", "cholesterol"),
                  "mg/dL", 0, 199, critical_high=300,
                  si_unit="mmol/L", si_factor=38.67,
                  incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L")),
    BiomarkerSpec("alt", ("alt", "sgpt", "men gan alt"),
                  "U/L", 7, 56, critical_high=300,
                  incompatible_units=("mg/dL", "mmol/L", "mIU/L", "µIU/mL", "pmol/L", "nmol/L")),
    BiomarkerSpec("ast", ("ast", "sgot", "men gan ast"),
                  "U/L", 10, 40, critical_high=300,
                  incompatible_units=("mg/dL", "mmol/L", "mIU/L", "µIU/mL", "pmol/L", "nmol/L")),
    BiomarkerSpec("creatinine", ("creatinine", "creatinin"),
                  "mg/dL", 0.6, 1.3, critical_high=4.0),
    BiomarkerSpec("egfr", ("egfr", "gfr", "mức lọc cầu thận", "muc loc cau than"),
                  "mL/min/1.73m²", 60, 200, critical_low=15),
    BiomarkerSpec("urea", ("urea", "ure", "bun", "blood urea nitrogen", "u rê"),
                  "mg/dL", 7, 20, critical_high=100),
    BiomarkerSpec("ggt", ("ggt", "gamma gt", "gamma-glutamyl", "men gan ggt"),
                  "U/L", 9, 48, critical_high=300),
    BiomarkerSpec("tsh", ("tsh",),
                  "mIU/L", 0.4, 4.0, critical_low=0.01, critical_high=20.0,
                  si_unit="µIU/mL", si_factor=1.0,
                  incompatible_units=("mg/dL", "mmol/L", "g/dL", "U/L", "ng/mL", "pmol/L")),
    BiomarkerSpec("ft4", ("ft4", "free t4", "ft 4", "free thyroxine"),
                  "pmol/L", 12.0, 22.0, critical_low=3.0, critical_high=50.0,
                  incompatible_units=("mg/dL", "mmol/L", "g/dL", "mIU/L", "µIU/mL", "U/L")),
    BiomarkerSpec("ft3", ("ft3", "free t3", "ft 3", "free triiodothyronine"),
                  "pmol/L", 3.1, 6.8, critical_low=1.0, critical_high=20.0,
                  incompatible_units=("mg/dL", "mmol/L", "g/dL", "mIU/L", "µIU/mL", "U/L")),
    # ---- Basic CBC (detected when present) ----
    BiomarkerSpec("hemoglobin", ("hemoglobin", "hgb", "hb", "huyết sắc tố", "huyet sac to"),
                  "g/dL", 12.0, 17.5, critical_low=7.0, critical_high=20.0),
    BiomarkerSpec("wbc", ("wbc", "bạch cầu", "bach cau", "white blood cell", "leukocyte"),
                  "10^9/L", 4.0, 10.0, critical_low=1.0, critical_high=30.0),
    BiomarkerSpec("platelet", ("platelet", "plt", "tiểu cầu", "tieu cau"),
                  "10^9/L", 150, 400, critical_low=50, critical_high=1000),
    BiomarkerSpec("rbc", ("rbc", "hồng cầu", "hong cau", "red blood cell"),
                  "10^12/L", 4.2, 5.9, critical_low=2.5),
    BiomarkerSpec("hematocrit", ("hematocrit", "hct", "dung tích hồng cầu"),
                  "%", 36.0, 50.0, critical_low=20.0),
    # ---- Additional required biomarkers ----
    BiomarkerSpec(
        "uric_acid",
        # "đ" is a stroke letter, not a combining mark — keep accented forms so
        # _strip_accents produces the same output as from scanned Vietnamese text.
        ("uric acid", "axit uric", "axit uric máu", "acid uric", "uric"),
        "mg/dL", 3.5, 7.0, critical_high=10.0,
    ),
    BiomarkerSpec(
        "random_glucose",
        # Accented Vietnamese aliases: "đường" keeps "đ" after NFD stripping,
        # matching OCR output from scanned Vietnamese lab reports.
        ("random glucose", "đường huyết ngẫu nhiên", "glucose ngẫu nhiên",
         "đường huyết bất kỳ", "rbs", "random blood sugar"),
        "mg/dL", 70, 139, critical_low=54, critical_high=300,
        si_unit="mmol/L", si_factor=18.018,
        incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L"),
    ),
)

_ALIAS_INDEX: dict[str, BiomarkerSpec] = {}
for _spec in BIOMARKERS:
    _ALIAS_INDEX[_spec.canonical] = _spec
    for _a in _spec.aliases:
        _ALIAS_INDEX[_a.lower()] = _spec


def normalize_biomarker(name: str) -> str | None:
    """Map a raw test name to a canonical biomarker key, or None if unknown."""
    if not name:
        return None
    key = name.strip().lower()
    spec = _ALIAS_INDEX.get(key)
    if spec:
        return spec.canonical
    # loose contains match
    for alias, spec in _ALIAS_INDEX.items():
        if alias in key or key in alias:
            return spec.canonical
    return None


@dataclass
class RawLabValue:
    test_name: str
    value: float
    unit: str | None = None
    ocr_confidence: float = 1.0


@dataclass
class InterpretedBiomarker:
    canonical: str
    raw_name: str
    value: float
    unit: str
    status: LabStatus
    reference_range: str
    ocr_confidence: float
    needs_verification: bool
    patient_note: str = ""


def classify_value(canonical: str, value: float) -> LabStatus:
    spec = _ALIAS_INDEX.get(canonical)
    if spec is None:
        return LabStatus.UNKNOWN
    if spec.critical_high is not None and value >= spec.critical_high:
        return LabStatus.CRITICAL
    if spec.critical_low is not None and value <= spec.critical_low:
        return LabStatus.CRITICAL
    if spec.ref_high is not None and value > spec.ref_high:
        return LabStatus.HIGH
    if spec.ref_low is not None and value < spec.ref_low:
        return LabStatus.LOW
    return LabStatus.NORMAL


_PATIENT_NOTE: dict[LabStatus, str] = {
    LabStatus.NORMAL: "đang trong khoảng tham chiếu.",
    LabStatus.HIGH: "đang cao hơn khoảng tham chiếu; bạn nên trao đổi với bác sĩ để được đánh giá.",
    LabStatus.LOW: "đang thấp hơn khoảng tham chiếu; bạn nên trao đổi với bác sĩ để được đánh giá.",
    LabStatus.CRITICAL: "ở mức cần lưu ý đặc biệt; bạn nên sớm gặp bác sĩ để được kiểm tra.",
    LabStatus.UNKNOWN: "chưa có khoảng tham chiếu trong hệ thống; cần bác sĩ xác nhận.",
}

# Low OCR confidence => require verification before any interpretation is trusted.
OCR_CONFIDENCE_THRESHOLD = 0.75


def interpret_value(raw: RawLabValue) -> InterpretedBiomarker:
    canonical = normalize_biomarker(raw.test_name)
    if canonical is None:
        return InterpretedBiomarker(
            canonical="unknown",
            raw_name=raw.test_name,
            value=raw.value,
            unit=raw.unit or "",
            status=LabStatus.UNKNOWN,
            reference_range="N/A",
            ocr_confidence=raw.ocr_confidence,
            needs_verification=True,
            patient_note=f"Chỉ số '{raw.test_name}' {_PATIENT_NOTE[LabStatus.UNKNOWN]}",
        )

    spec = _ALIAS_INDEX[canonical]
    status = classify_value(canonical, raw.value)
    needs_verification = raw.ocr_confidence < OCR_CONFIDENCE_THRESHOLD
    ref = f"{spec.ref_low}–{spec.ref_high} {spec.unit}"
    note = f"{spec.canonical} = {raw.value} {spec.unit}: {_PATIENT_NOTE[status]}"
    if needs_verification:
        note += " (Độ tin cậy OCR thấp — cần xác nhận lại số liệu.)"
    return InterpretedBiomarker(
        canonical=canonical,
        raw_name=raw.test_name,
        value=raw.value,
        unit=raw.unit or spec.unit,
        status=status,
        reference_range=ref,
        ocr_confidence=raw.ocr_confidence,
        needs_verification=needs_verification,
        patient_note=note,
    )


@dataclass
class LabInterpretation:
    biomarkers: list[InterpretedBiomarker] = field(default_factory=list)
    abnormal: list[str] = field(default_factory=list)
    critical: list[str] = field(default_factory=list)
    needs_verification: bool = False
    patient_explanation: str = ""
    doctor_summary: str = ""


def interpret_panel(values: list[RawLabValue]) -> LabInterpretation:
    """Interpret a full lab panel. Patient explanation uses probabilistic
    language and ALWAYS ends with the mandatory disclaimer. Doctor summary is
    data-only (no clinical conclusion)."""
    interpreted = [interpret_value(v) for v in values]
    abnormal = [b.canonical for b in interpreted if b.status in (LabStatus.HIGH, LabStatus.LOW)]
    critical = [b.canonical for b in interpreted if b.status == LabStatus.CRITICAL]
    needs_verification = any(b.needs_verification for b in interpreted)

    # ---- Patient-friendly explanation (policy §4.4) ----
    lines: list[str] = []
    if critical:
        lines.append(
            "Một số chỉ số đang ở mức cần lưu ý đặc biệt: "
            + ", ".join(critical)
            + ". Bạn nên sớm gặp bác sĩ để được kiểm tra."
        )
    if abnormal:
        lines.append("Các chỉ số ngoài khoảng tham chiếu: " + ", ".join(abnormal) + ".")
    if not critical and not abnormal:
        lines.append("Các chỉ số nhìn chung đang trong khoảng tham chiếu.")
    for b in interpreted:
        lines.append("• " + b.patient_note)
    lines.append(
        "Đây là giải thích tham khảo, không phải kết luận bệnh. "
        "Bạn nên trao đổi với bác sĩ để được đánh giá đầy đủ."
    )
    patient_explanation = " ".join(lines)
    if policies.DISCLAIMER_VI not in patient_explanation:
        patient_explanation += " " + policies.DISCLAIMER_VI

    # ---- Doctor summary (data only) ----
    doc_lines = ["Pre-consult lab summary (data only, no AI conclusion):"]
    for b in interpreted:
        flag = "" if b.status == LabStatus.NORMAL else f"  [{b.status.value.upper()}]"
        verify = "  (verify OCR)" if b.needs_verification else ""
        doc_lines.append(
            f"- {b.canonical}: {b.value} {b.unit} (ref {b.reference_range}){flag}{verify}"
        )
    doctor_summary = "\n".join(doc_lines)

    return LabInterpretation(
        biomarkers=interpreted,
        abnormal=abnormal,
        critical=critical,
        needs_verification=needs_verification,
        patient_explanation=patient_explanation,
        doctor_summary=doctor_summary,
    )


# --------------------------------------------------------------------------- #
# MOCK OCR — dev/test only. NEVER calls a real provider. NEVER contains real PHI.
# --------------------------------------------------------------------------- #

def mock_ocr_extract(document_ref: str) -> list[RawLabValue]:
    """Deterministic fake OCR output for development and tests.

    Returns a small synthetic panel keyed off the document reference so tests
    are reproducible. Replace with a real OCR worker in P1 (config MCP_OCR_MODE).
    """
    # Synthetic, obviously-fake values. No real patient data.
    return [
        RawLabValue("Glucose", 110.0, "mg/dL", ocr_confidence=0.95),
        RawLabValue("Triglyceride", 220.0, "mg/dL", ocr_confidence=0.92),
        RawLabValue("HDL", 38.0, "mg/dL", ocr_confidence=0.60),  # low confidence on purpose
        RawLabValue("HbA1c", 6.1, "%", ocr_confidence=0.90),
    ]
