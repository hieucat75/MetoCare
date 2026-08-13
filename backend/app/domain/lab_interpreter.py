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

import re
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
    # Absolute physiological bounds: values outside these are OCR errors or impossible.
    physiological_min: float | None = None
    physiological_max: float | None = None


# Adult, fasting where relevant. Screening reference ranges only.
BIOMARKERS: tuple[BiomarkerSpec, ...] = (
    BiomarkerSpec(
        "fasting_glucose",
        (
            "glucose",
            "đường huyết đói",
            "glucose máu",
            "duong huyet",
            "duong huyet luc doi",
            "dinh luong glucose",
            "glucose huyet tuong",
            "blood glucose",
            "fbg",
            "fbs",
            "fasting plasma glucose",
            "fpg",
            "fasting blood glucose",
            # Tam Anh / accented forms
            "đường huyết lúc đói",
            "duong huyet luc doi",
            "glucose luc doi",
        ),
        "mg/dL",
        70,
        99,
        critical_low=54,
        critical_high=500,
        si_unit="mmol/L",
        si_factor=18.018,
        incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L"),
        physiological_min=20,
        physiological_max=1500,
    ),
    BiomarkerSpec(
        "hba1c",
        (
            "hba1c",
            "a1c",
            "đường huyết trung bình",
            "hemoglobin a1c",
            "haemoglobin a1c",
            "glycated hemoglobin",
            "glycohemoglobin",
        ),
        "%",
        4.0,
        5.6,
        critical_high=10.0,
        physiological_min=2,
        physiological_max=20,
    ),
    BiomarkerSpec(
        "ldl",
        ("ldl", "ldl-c", "ldl cholesterol", "ldl-cholesterol", "cholesterol xấu"),
        "mg/dL",
        0,
        99,
        critical_high=190,
        si_unit="mmol/L",
        si_factor=38.67,
        incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L"),
        physiological_min=0,
        physiological_max=800,
    ),
    BiomarkerSpec(
        "hdl",
        ("hdl", "hdl-c", "hdl-cholesterol", "cholesterol tốt"),
        "mg/dL",
        40,
        200,
        critical_low=20,
        si_unit="mmol/L",
        si_factor=38.67,
        incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L"),
        physiological_min=5,
        physiological_max=200,
    ),
    BiomarkerSpec(
        "triglyceride",
        (
            "triglyceride",
            "triglycerides",
            "triglycerid",
            "tg",
            "mỡ máu",
            "trig",
            "tg mau",
            "mo mau",
        ),
        "mg/dL",
        0,
        149,
        critical_high=500,
        si_unit="mmol/L",
        si_factor=88.57,
        incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L"),
        physiological_min=10,
        physiological_max=10000,
    ),
    BiomarkerSpec(
        "total_cholesterol",
        (
            "cholesterol toàn phần",
            "total cholesterol",
            "cholesterol",
            "tc",
            "total chol",
            "chol tp",
            "cholesterol tp",
        ),
        "mg/dL",
        0,
        199,
        critical_high=300,
        si_unit="mmol/L",
        si_factor=38.67,
        incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L"),
        physiological_min=50,
        physiological_max=1000,
    ),
    BiomarkerSpec(
        "alt",
        (
            "alt",
            "sgpt",
            "men gan alt",
            "alanine aminotransferase",
            "alanine transaminase",
            "gpt",
            "alat",
        ),
        "U/L",
        7,
        56,
        critical_high=300,
        incompatible_units=("mg/dL", "mmol/L", "mIU/L", "µIU/mL", "pmol/L", "nmol/L"),
        physiological_min=0,
        physiological_max=15000,
    ),
    BiomarkerSpec(
        "ast",
        (
            "ast",
            "sgot",
            "men gan ast",
            "aspartate aminotransferase",
            "aspartate transaminase",
            "got",
            "asat",
        ),
        "U/L",
        10,
        40,
        critical_high=300,
        incompatible_units=("mg/dL", "mmol/L", "mIU/L", "µIU/mL", "pmol/L", "nmol/L"),
        physiological_min=0,
        physiological_max=15000,
    ),
    BiomarkerSpec(
        "creatinine",
        ("creatinine", "creatinin", "crea", "creat", "creatinine mau", "serum creatinine", "scr"),
        "mg/dL",
        0.6,
        1.3,
        critical_high=4.0,
        si_unit="µmol/L",
        si_factor=0.011312,  # 1/88.42 µmol/L → mg/dL
        physiological_min=0.1,
        physiological_max=30,
        incompatible_units=(
            "pmol/L", "nmol/L", "mmol/L", "IU/L", "U/L", "mIU/L", "ng/mL", "µIU/mL"
        ),
    ),
    BiomarkerSpec(
        "egfr",
        (
            "egfr",
            "gfr",
            "mức lọc cầu thận",
            "muc loc cau than",
            "estimated gfr",
            "ckd-epi",
            "mdrd epi",
        ),
        "mL/min/1.73m²",
        60,
        200,
        critical_low=15,
        physiological_min=0,
        physiological_max=200,
    ),
    BiomarkerSpec(
        "urea",
        (
            "urea",
            "ure",
            "urê",
            "bun",
            "blood urea nitrogen",
            "u rê",
            "ure mau",
            "urea mau",
            "bun serum",
        ),
        "mg/dL",
        15,
        40,
        critical_high=200,
        si_unit="mmol/L",
        si_factor=6.006,  # mmol/L urea × 6.006 → mg/dL urea
        physiological_min=1,
        physiological_max=1000,
    ),
    BiomarkerSpec(
        "ggt",
        ("ggt", "gamma gt", "gamma-glutamyl", "men gan ggt"),
        "U/L",
        9,
        48,
        critical_high=300,
        physiological_min=0,
        physiological_max=5000,
    ),
    BiomarkerSpec(
        "tsh",
        ("tsh", "thyroid stimulating hormone", "thyrotropin"),
        "mIU/L",
        0.4,
        4.0,
        critical_low=0.01,
        critical_high=20.0,
        si_unit="µIU/mL",
        si_factor=1.0,
        incompatible_units=("mg/dL", "mmol/L", "g/dL", "U/L", "ng/mL", "pmol/L"),
        physiological_min=0,
        physiological_max=500,
    ),
    BiomarkerSpec(
        "ft4",
        ("ft4", "free t4", "ft 4", "free thyroxine"),
        "pmol/L",
        12.0,
        22.0,
        critical_low=3.0,
        critical_high=50.0,
        incompatible_units=("mg/dL", "mmol/L", "g/dL", "mIU/L", "µIU/mL", "U/L"),
        physiological_min=0,
        physiological_max=100,
    ),
    BiomarkerSpec(
        "ft3",
        ("ft3", "free t3", "ft 3", "free triiodothyronine"),
        "pmol/L",
        3.1,
        6.8,
        critical_low=1.0,
        critical_high=20.0,
        incompatible_units=("mg/dL", "mmol/L", "g/dL", "mIU/L", "µIU/mL", "U/L"),
        physiological_min=0,
        physiological_max=50,
    ),
    # ---- Basic CBC (detected when present) ----
    BiomarkerSpec(
        "hemoglobin",
        ("hemoglobin", "hgb", "hb", "huyết sắc tố", "huyet sac to", "haemoglobin"),
        "g/dL",
        12.0,
        17.5,
        critical_low=7.0,
        critical_high=20.0,
        physiological_min=1,
        physiological_max=25,
    ),
    BiomarkerSpec(
        "wbc",
        ("wbc", "bạch cầu", "bach cau", "white blood cell", "leukocyte"),
        "10^9/L",
        4.0,
        10.0,
        critical_low=1.0,
        critical_high=30.0,
        physiological_min=0,
        physiological_max=500,
    ),
    BiomarkerSpec(
        "platelet",
        ("platelet", "plt", "tiểu cầu", "tieu cau"),
        "10^9/L",
        150,
        400,
        critical_low=50,
        critical_high=1000,
        physiological_min=0,
        physiological_max=3000,
    ),
    BiomarkerSpec(
        "rbc",
        ("rbc", "hồng cầu", "hong cau", "red blood cell"),
        "10^12/L",
        4.2,
        5.9,
        critical_low=2.5,
        # 0.5 admitted a hematocrit FRACTION as a red cell count. No adult RBC
        # count is below ~1.0 x10^12/L; severe anaemia still classifies critical.
        physiological_min=1.0,
        physiological_max=10,
    ),
    BiomarkerSpec(
        "hematocrit",
        # Every VN name for hematocrit CONTAINS "hồng cầu", which is also the RBC
        # alias. Only "dung tích hồng cầu" was registered, so the other standard
        # forms matched the shorter RBC alias instead and a hematocrit fraction
        # was stored as a red cell count. Longest-alias-wins shadows the generic
        # token once the full phrase is present — so these must be exhaustive.
        (
            "hematocrit",
            "hct",
            "pcv",
            "dung tích hồng cầu",
            "dung tich hong cau",
            "thể tích khối hồng cầu",
            "the tich khoi hong cau",
            "tỷ lệ thể tích hồng cầu",
            "ty le the tich hong cau",
            "thể tích hồng cầu",
            "the tich hong cau",
            "khối hồng cầu",
            "khoi hong cau",
        ),
        "%",
        36.0,
        50.0,
        critical_low=20.0,
        physiological_min=5,
        physiological_max=75,
    ),
    # ---- Electrolytes ----
    BiomarkerSpec(
        "sodium",
        ("sodium", "natri", "na+", "na serum", "serum sodium", "dien giai na"),
        "mmol/L",
        136,
        145,
        critical_low=125,
        critical_high=155,
        incompatible_units=("mg/dL", "µmol/L", "mIU/L", "µIU/mL", "U/L", "pmol/L"),
        physiological_min=100,
        physiological_max=200,
    ),
    BiomarkerSpec(
        "potassium",
        ("potassium", "kali", "k+", "k serum", "serum potassium", "dien giai k"),
        "mmol/L",
        3.5,
        5.0,
        critical_low=2.5,
        critical_high=6.5,
        incompatible_units=("mg/dL", "µmol/L", "mIU/L", "µIU/mL", "U/L", "pmol/L"),
        physiological_min=1.0,
        physiological_max=10.0,
    ),
    BiomarkerSpec(
        "chloride",
        ("chloride", "clo", "cl-", "cl serum", "serum chloride", "dien giai cl"),
        "mmol/L",
        98,
        106,
        critical_low=80,
        critical_high=120,
        incompatible_units=("mg/dL", "µmol/L", "mIU/L", "µIU/mL", "U/L", "pmol/L"),
        physiological_min=60,
        physiological_max=160,
    ),
    # ---- Electrolytes (extended) ----
    BiomarkerSpec(
        "calcium",
        (
            "calcium",
            "canxi",
            "ca2+",
            "ca serum",
            "serum calcium",
            "canxi mau",
            "canxi (ca2+)",
            "calcium (ca2+)",
        ),
        "mg/dL",
        8.5,
        10.5,
        critical_low=7.0,
        critical_high=13.0,
        si_unit="mmol/L",
        si_factor=0.2495,
        incompatible_units=("µmol/L", "mIU/L", "µIU/mL", "U/L", "pmol/L"),
        physiological_min=4.0,
        physiological_max=20.0,
    ),
    # ---- Tumour / thyroid markers ----
    BiomarkerSpec(
        "thyroglobulin",
        ("thyroglobulin", "thyroglobuline", "tg serum", "thyroglobulin serum"),
        "ng/mL",
        1.4,
        78.0,
        critical_high=300.0,
        incompatible_units=("mg/dL", "mmol/L", "mIU/L", "µIU/mL", "U/L", "pmol/L"),
        physiological_min=0,
        physiological_max=10000,
    ),
    # ---- Additional required biomarkers ----
    BiomarkerSpec(
        "uric_acid",
        # "đ" is a stroke letter, not a combining mark — keep accented forms so
        # _strip_accents produces the same output as from scanned Vietnamese text.
        ("uric acid", "axit uric", "axit uric máu", "acid uric", "uric"),
        "mg/dL",
        3.5,
        7.0,
        critical_high=10.0,
        si_unit="µmol/L",
        si_factor=0.016813,  # µmol/L ÷ 59.48 → mg/dL
        physiological_min=0.5,
        physiological_max=30,
    ),
    BiomarkerSpec(
        "random_glucose",
        # Accented Vietnamese aliases: "đường" keeps "đ" after NFD stripping,
        # matching OCR output from scanned Vietnamese lab reports.
        (
            "random glucose",
            "đường huyết ngẫu nhiên",
            "glucose ngẫu nhiên",
            "đường huyết bất kỳ",
            "rbs",
            "random blood sugar",
        ),
        "mg/dL",
        70,
        139,
        critical_low=54,
        critical_high=500,
        si_unit="mmol/L",
        si_factor=18.018,
        incompatible_units=("IU/mL", "mIU/L", "mIU/mL", "µIU/mL", "pmol/L", "nmol/L"),
        physiological_min=20,
        physiological_max=1500,
    ),
    # ---- Adrenal / stress hormones ----
    BiomarkerSpec(
        "cortisol",
        ("cortisol", "hydrocortisone", "cortisol mau", "cortisol huyet thanh"),
        "nmol/L",
        138,
        635,
        critical_low=50,
        critical_high=1500,
        incompatible_units=("mg/dL", "mmol/L", "mIU/L", "µIU/mL", "U/L", "pmol/L"),
        physiological_min=0.1,
        physiological_max=5000,
    ),
)

_ALIAS_INDEX: dict[str, BiomarkerSpec] = {}
for _spec in BIOMARKERS:
    _ALIAS_INDEX[_spec.canonical] = _spec
    for _a in _spec.aliases:
        _ALIAS_INDEX[_a.lower()] = _spec

# Regex to strip parenthetical suffixes from raw OCR test names.
# Examples: "ALT (GPT)" -> "ALT", "LDL-Cholesterol (Tinh)" -> "LDL-Cholesterol",
#           "Glucose (mau) (Cobas C502)" -> "Glucose" (applied iteratively).
_PAREN_SUFFIX_RE = re.compile(r"\s*[\(\uff08][^)\uff09]*[\)\uff09]\s*$")


def _strip_paren_suffix(s: str) -> str:
    """Remove all trailing parenthetical groups, e.g. 'ALT (GPT)' -> 'ALT'."""
    prev = None
    while prev != s:
        prev = s
        s = _PAREN_SUFFIX_RE.sub("", s).strip()
    return s


def normalize_biomarker(name: str) -> str | None:
    """Map a raw test name to a canonical biomarker key, or None if unknown.

    Normalization pipeline:
    1. Strip leading/trailing whitespace, lowercase.
    2. Strip trailing parenthetical suffixes (e.g. '(GPT)', '(Tinh)', '(Cobas C502)').
    3. Exact alias lookup (stripped form first, then original).
    4. Loose contains-match across all known aliases (using stripped form).
    """
    if not name:
        return None
    key = name.strip().lower()
    # Step 2: strip parenthetical suffixes before alias lookup
    key_stripped = _strip_paren_suffix(key)
    # Step 3: exact alias lookup -- try stripped form first, then original
    for k in (key_stripped, key):
        spec = _ALIAS_INDEX.get(k)
        if spec:
            return spec.canonical
    # Step 4: loose contains match (use stripped form for higher precision)
    for alias, spec in _ALIAS_INDEX.items():
        if alias in key_stripped or key_stripped in alias:
            return spec.canonical
    return None


@dataclass
class ConfidenceDetail:
    """Per-dimension confidence breakdown for one parsed biomarker row."""

    ocr: float  # OCR text extraction quality (0..1)
    mapping: float  # Biomarker name recognition quality (0..1)
    conversion: float  # Unit matching / conversion quality (0..1)
    clinical: float  # Physiological plausibility (0..1)
    overall: float  # Weighted: 40%×ocr + 25%×mapping + 25%×conversion + 10%×clinical
    reasons: list[str]


@dataclass
class RawLabValue:
    test_name: str
    value: float
    unit: str | None = None
    ocr_confidence: float = 1.0
    confidence_detail: ConfidenceDetail | None = None
    # Raw OCR value/unit before SI conversion or OCR correction — used by the
    # review UI to show "OCR gốc" alongside the normalized display value.
    original_value: float | None = None
    original_unit: str | None = None
    # Display fields: exact printed label and Vietnamese catalog name.
    raw_test_name: str = ""  # as OCR'd: "CHOLESTEROL TOAN PHAN", "Ure", etc.
    display_name_vi: str = ""  # Vietnamese label from catalog: "Cholesterol toàn phần"
    ocr_reference_range: str | None = None  # as-printed from same OCR row/cell
    # P0 safety gate: True when the row is suspected to carry a machine model
    # number as value, or is otherwise too low-confidence to auto-save.
    # Rows with requires_review=True must NOT be persisted without user confirmation.
    requires_review: bool = False
    # Forward the suspect_machine_id flag from OcrTableRow for audit/UI use.
    suspect_machine_id: bool = False


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
    confidence_detail: ConfidenceDetail | None = None
    original_value: float | None = None
    original_unit: str | None = None
    raw_test_name: str = ""
    display_name_vi: str = ""
    display_reference_range: str | None = None  # ref range in display unit (for review UI)


def _norm_unit_interp(u: str) -> str:
    """Normalize unit for comparison (avoids circular import with lab_parser)."""
    return u.replace("µ", "u").replace("μ", "u").replace("mc", "u").strip().lower()


def _compute_display_ref(
    ocr_reference_range: str | None,
    original_unit: str | None,
    spec: BiomarkerSpec,
) -> str | None:
    """Compute reference range string in the display unit shown on the patient's report.

    Priority:
    1. OCR-extracted range from same row/cell — already in display unit.
    2. Catalog range converted to display unit when display_unit == spec.si_unit.
    3. Catalog range in canonical unit with (MetoCare) label as fallback.
    """
    display_unit = original_unit
    if ocr_reference_range:
        return f"{ocr_reference_range} {display_unit}" if display_unit else ocr_reference_range
    if spec.ref_low is None or spec.ref_high is None:
        return None
    label = " (MetoCare)"
    if display_unit is None:
        return f"{spec.ref_low}–{spec.ref_high} {spec.unit}{label}"
    norm_disp = _norm_unit_interp(display_unit)
    if spec.si_unit and _norm_unit_interp(spec.si_unit) == norm_disp and spec.si_factor:
        lo = round(spec.ref_low / spec.si_factor, 3)
        hi = round(spec.ref_high / spec.si_factor, 3)
        return f"{lo}–{hi} {display_unit}{label}"
    if _norm_unit_interp(spec.unit) == norm_disp:
        return f"{spec.ref_low}–{spec.ref_high} {spec.unit}{label}"
    return f"{spec.ref_low}–{spec.ref_high} {spec.unit}{label}"


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
            raw_test_name=raw.raw_test_name,
            display_name_vi=raw.display_name_vi,
        )

    spec = _ALIAS_INDEX[canonical]

    # ── CBC dimensional guard ────────────────────────────────────────────────
    # This is the layer the parser fix does NOT reach. Below, `unit or spec.unit`
    # stamps the canonical unit onto a unit-free row: an unlabelled
    # "Hồng cầu 0.50" becomes `rbc 0.50 10^12/L`, which then looks CANONICAL to
    # the read-path guard and classifies CRITICAL — the original incident, with
    # the allowlist fooled rather than bypassed.
    #
    # Runs before the plausibility check so a legitimate hematocrit fraction
    # (0.45 L/L) is converted to 45 % first, instead of being judged against the
    # percent bounds and flagged "ngoài giới hạn sinh lý".
    from .analyte_units import ALLOWED_UNITS, is_unsafe_pair, to_canonical_unit

    value_for_status = raw.value
    guarded = canonical in ALLOWED_UNITS
    if guarded:
        if is_unsafe_pair(canonical, raw.unit):
            return InterpretedBiomarker(
                canonical=canonical,
                raw_name=raw.test_name,
                value=raw.value,
                # NEVER invent the unit for a guarded analyte.
                unit=raw.unit or "",
                status=LabStatus.UNKNOWN,
                reference_range="N/A",
                ocr_confidence=raw.ocr_confidence,
                needs_verification=True,
                patient_note=(
                    "Chỉ số cần được kiểm tra lại do đơn vị hoặc loại xét nghiệm chưa khớp."
                ),
                confidence_detail=raw.confidence_detail,
                original_value=raw.original_value,
                original_unit=raw.original_unit,
                raw_test_name=raw.raw_test_name,
                display_name_vi=raw.display_name_vi,
                display_reference_range=None,
            )
        converted = to_canonical_unit(canonical, raw.value, raw.unit)
        if converted is not None:
            value_for_status = converted[0]

    check_lo = spec.physiological_min is not None and value_for_status < spec.physiological_min
    check_hi = spec.physiological_max is not None and value_for_status > spec.physiological_max
    if check_lo or check_hi:
        return InterpretedBiomarker(
            canonical=canonical,
            raw_name=raw.test_name,
            value=raw.value,
            unit=raw.unit if guarded else (raw.unit or spec.unit),
            status=LabStatus.UNKNOWN,
            reference_range=str(spec.ref_low) + "-" + str(spec.ref_high) + " " + spec.unit,
            ocr_confidence=0.0,
            needs_verification=True,
            patient_note="Gia tri vuot ngoai gioi han sinh ly. Vui long kiem tra lai.",
            confidence_detail=raw.confidence_detail,
            original_value=raw.original_value,
            original_unit=raw.original_unit,
            raw_test_name=raw.raw_test_name,
            display_name_vi=raw.display_name_vi,
            display_reference_range=None,
        )
    status = classify_value(canonical, value_for_status)
    needs_verification = raw.ocr_confidence < OCR_CONFIDENCE_THRESHOLD
    ref = f"{spec.ref_low}–{spec.ref_high} {spec.unit}"
    # #155: for a guarded analyte, `raw.ocr_reference_range` was converted to the
    # SAME canonical unit as `raw.value`/`raw.unit` (analyte_units.to_canonical_range
    # runs alongside to_canonical_unit) — it is no longer expressed in
    # `original_unit`. Labelling it with `original_unit` prints numerically
    # converted bounds under the pre-conversion unit (a converted "13–17" shown as
    # "13–17 g/L" instead of "13–17 g/dL") — silently understating the range by the
    # same factor that converted the value, the exact two-contradictory-claims
    # hazard this branch exists to remove. Non-guarded rows are never touched by
    # to_canonical_range, so their range stays in original_unit as before.
    display_ref_unit = raw.unit if guarded else raw.original_unit
    display_ref = _compute_display_ref(raw.ocr_reference_range, display_ref_unit, spec)
    # Quote the value in the SAME unit as the range. A converted hematocrit
    # otherwise read "hematocrit = 0.45 %" against "36.0–50.0 %", from which a
    # patient self-derives catastrophic anaemia off a row we just called normal —
    # the exact hazard the serializer avoids by clearing an unsafe range.
    note_value = value_for_status if guarded else raw.value
    note = f"{spec.canonical} = {note_value} {spec.unit}: {_PATIENT_NOTE[status]}"
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
        confidence_detail=raw.confidence_detail,
        original_value=raw.original_value,
        original_unit=raw.original_unit,
        raw_test_name=raw.raw_test_name,
        display_name_vi=raw.display_name_vi,
        display_reference_range=display_ref,
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
