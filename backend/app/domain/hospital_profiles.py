"""Hospital profile registry for OCR hint-loading.

Profiles declare accent-stripped lowercase header_patterns that identify the
originating hospital from the first 30 OCR lines. Adding a new hospital requires
only a new HospitalProfile entry - no parser logic changes needed.

``additional_aliases`` maps **biomarker canonical names** (e.g. ``"fasting_glucose"``)
to tuples of extra accent-stripped lowercase alias strings that are specific to
that hospital's report format.  Hospital name / header OCR variants belong in
``hospital_name_variants`` instead.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ColumnMap:
    """Explicit column-index mapping for a known hospital table layout.

    All indices are 0-based (Azure DI columnIndex).  ``None`` means the column
    is absent in this hospital's report format.

    ``skip_cols`` lists column indices that must never be used as the result
    value column (e.g. method/instrument columns, price columns).
    """

    test_name: int
    value: int
    unit: int | None = None
    reference: int | None = None
    stt: int | None = None
    skip_cols: tuple[int, ...] = field(default_factory=tuple)


@dataclass
class HospitalProfile:
    hospital_id: str
    name: str
    header_patterns: tuple[str, ...]
    unit_system: str
    # Maps biomarker canonical names → extra OCR alias strings for that hospital.
    # Keys must be valid canonical biomarker names present in lab_interpreter.BIOMARKERS.
    additional_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    ocr_corrections: dict[str, str] = field(default_factory=dict)
    # OCR variants of the hospital name/header (not biomarker aliases).
    hospital_name_variants: tuple[str, ...] = field(default_factory=tuple)
    # Column header texts that identify non-result columns carrying method/instrument
    # names.  lab_table_extractor uses this to ensure these columns are NEVER
    # mapped to value_col.  Accent-stripped, lowercase.
    method_column_headers: tuple[str, ...] = field(default_factory=tuple)
    # When set, provides an explicit deterministic column mapping for this hospital's
    # table layout, bypassing heuristic column-role detection entirely.
    column_map: ColumnMap | None = None
    # Accent-stripped lowercase substrings that identify footer rows (totals,
    # signatures, disclaimers) that must be excluded from data extraction.
    footer_patterns: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class DetectionResult:
    """Result of hospital detection — bundles the matched profile and a confidence float."""

    profile: HospitalProfile
    confidence: float = 1.0


class HospitalDetector:
    """Stateless hospital detector wrapping HOSPITAL_PROFILES."""

    def __init__(self, profiles: tuple[HospitalProfile, ...] | None = None) -> None:
        # Deferred import to avoid circular reference at module load time;
        # HOSPITAL_PROFILES is defined later in this module.
        if profiles is None:
            self._profiles_override = None
        else:
            self._profiles_override = profiles

    @property
    def _profiles(self) -> tuple[HospitalProfile, ...]:
        if self._profiles_override is not None:
            return self._profiles_override
        return HOSPITAL_PROFILES

    def detect(self, text: str) -> HospitalProfile | None:
        result = self.detect_or_unknown(text)
        return None if result.profile is UNKNOWN_PROFILE else result.profile

    def detect_or_unknown(self, text: str) -> DetectionResult:
        """Detect hospital with position-weighted confidence.

        Confidence tiers (by the earliest line where any alias matches):
          lines  1–10 → 0.9   (hospital name clearly in report header)
          lines 11–30 → 0.7   (found in preamble / secondary header)
          lines 31–50 → 0.5   (buried — review required downstream)
          no match    → 0.0   (UNKNOWN_PROFILE)

        When multiple profiles or aliases match, the one with the highest
        confidence wins.  Ties broken by earlier line, then longer alias
        (more specific matches rank higher).
        """
        lines = text.splitlines()[:50]
        stripped_lines = [_strip_accents(line).lower() for line in lines]

        best_profile: HospitalProfile | None = None
        best_confidence: float = 0.0
        best_line_idx: int = 9999
        best_alias_len: int = 0

        for profile in self._profiles:
            for pattern in profile.header_patterns:
                for line_idx, line_norm in enumerate(stripped_lines):
                    if pattern in line_norm:
                        line_num = line_idx + 1
                        confidence = (
                            0.9 if line_num <= 10
                            else 0.7 if line_num <= 30
                            else 0.5
                        )
                        is_better = (
                            confidence > best_confidence
                            or (confidence == best_confidence and line_idx < best_line_idx)
                            or (
                                confidence == best_confidence
                                and line_idx == best_line_idx
                                and len(pattern) > best_alias_len
                            )
                        )
                        if is_better:
                            best_profile = profile
                            best_confidence = confidence
                            best_line_idx = line_idx
                            best_alias_len = len(pattern)
                        break  # this pattern matched; skip remaining lines for it

        if best_profile is not None:
            return DetectionResult(profile=best_profile, confidence=best_confidence)
        return DetectionResult(profile=UNKNOWN_PROFILE, confidence=0.0)


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


HOSPITAL_PROFILES: tuple[HospitalProfile, ...] = (
    HospitalProfile(
        hospital_id="vinmec",
        name="Vinmec",
        header_patterns=(
            "vinmec",
            "benh vien da khoa quoc te vinmec",
            "vinmec international",
        ),
        unit_system="SI",
        additional_aliases={},
        hospital_name_variants=(
            "vinmec international hospital",
            "vimec",
            "vinmeck",
        ),
        ocr_corrections={
            "vinmec intemational": "vinmec international",
            "vinnmec": "vinmec",
            "vinm3c": "vinmec",
        },
        # Vinmec 6-column layout:
        # col 0=STT, col 1=Tên xét nghiệm, col 2=Kết quả,
        # col 3=Đơn vị, col 4=Giá trị bình thường, col 5=Thiết bị (device — must skip)
        column_map=ColumnMap(
            stt=0,
            test_name=1,
            value=2,
            unit=3,
            reference=4,
            skip_cols=(5,),
        ),
    ),
    HospitalProfile(
        hospital_id="medlatec",
        name="Medlatec",
        header_patterns=(
            "medlatec",
            "benh vien da khoa medlatec",
            "he thong y te medlatec",
        ),
        unit_system="SI",
        additional_aliases={
            "triglyceride": ("triglycerid",),
            "hdl": ("hdl-cholesterol", "hdl cholesterol"),
            "ldl": ("ldl-cholesterol", "ldl cholesterol"),
        },
        hospital_name_variants=(
            "med latec",
            "medla tec",
            "medlatec general hospital",
        ),
        ocr_corrections={
            "medlatee": "medlatec",
            "med1atec": "medlatec",
            "mediatec": "medlatec",
        },
        # Medlatec lab reports include a "Phương pháp / Máy" (Method / Machine)
        # column that contains strings like "Cobas C502".  This column must NEVER
        # be used as the result value column.
        method_column_headers=(
            "phuong phap / may",
            "phuong phap",
            "may xet nghiem",
            "pp/may",
            "pp / may",
            "cobas",
            "instrument",
            "method",
        ),
        # Medlatec 6-column layout:
        # col 0=STT, col 1=Tên xét nghiệm, col 2=Kết quả,
        # col 3=Đơn vị, col 4=Khoảng tham chiếu, col 5=Phương pháp/Máy (method — must skip)
        column_map=ColumnMap(
            stt=0,
            test_name=1,
            value=2,
            unit=3,
            reference=4,
            skip_cols=(5,),
        ),
    ),
    HospitalProfile(
        hospital_id="tamanh",
        name="Tam Anh",
        header_patterns=(
            "tam anh",
            "benh vien tam anh",
            "tamanh",
            "benh vien da khoa tam anh",
        ),
        unit_system="SI",
        additional_aliases={
            "fasting_glucose": ("duong huyet luc doi", "glucose luc doi"),
            "hdl": ("hdl cholesterol", "hdl-c"),
            "ldl": ("ldl cholesterol", "ldl-c"),
            "alt": ("sgpt", "alat"),
            "ast": ("sgot", "asat"),
            "triglyceride": ("triglycerides",),
        },
        hospital_name_variants=(
            "tam anh hospital",
            "tam anh general hospital",
            "bv tam anh",
        ),
        ocr_corrections={
            "tarn anh": "tam anh",
            "tam ahn": "tam anh",
            "tamanh general": "benh vien da khoa tam anh",
        },
    ),
    HospitalProfile(
        hospital_id="hongngoc",
        name="Hong Ngoc",
        header_patterns=(
            "hong ngoc",
            "benh vien hong ngoc",
            "hongngoc",
        ),
        unit_system="mixed",
        additional_aliases={
            "fasting_glucose": ("glucose mau", "glucose toan phan"),
            "hdl": ("hdl-c", "hdl cholesterol"),
            "ldl": ("ldl-c", "ldl cholesterol"),
            "alt": ("alt (gpt)", "sgpt"),
            "ast": ("ast (got)", "sgot"),
            "total_cholesterol": ("cholesterol toan phan",),
        },
        hospital_name_variants=(
            "hong ngoc hospital",
            "bv hong ngoc",
            "hong ngoc general hospital",
        ),
        ocr_corrections={
            "hong ng0c": "hong ngoc",
            "h0ng ngoc": "hong ngoc",
            "hongng0c": "hongngoc",
        },
    ),
    HospitalProfile(
        hospital_id="bachmai108",
        name="108 Military Hospital",
        header_patterns=(
            "vien quan y 108",
            "benh vien 108",
            "quan doi 108",
            "108 hospital",
        ),
        unit_system="conventional",
        additional_aliases={},
        hospital_name_variants=(
            "108 military central hospital",
            "benh vien trung uong quan doi 108",
            "vien 108",
        ),
        ocr_corrections={
            "vien quan y l08": "vien quan y 108",
            "benh vien l08": "benh vien 108",
            "108 hospita1": "108 hospital",
        },
    ),
    HospitalProfile(
        hospital_id="bachmai",
        name="Bach Mai",
        header_patterns=(
            "bach mai",
            "benh vien bach mai",
            "bv bach mai",
        ),
        unit_system="conventional",
        additional_aliases={
            "ldl": ("ldl-cholesterol (tinh)", "ldl (tinh)", "ldl cholesterol tinh"),
            "triglyceride": ("triglycerid",),
            "hdl": ("hdl-cholesterol", "hdl cholesterol"),
            "alt": ("alt (sgpt)", "sgpt"),
            "ast": ("ast (sgot)", "sgot"),
        },
        footer_patterns=(
            "bac si ky ten",
            "chu ky",
            "ghi chu",
            "disclaimer",
            "luu y",
            "ket luan",
        ),
        hospital_name_variants=(
            "bach mai hospital",
            "benh vien da khoa bach mai",
            "national hospital bach mai",
        ),
        ocr_corrections={
            "bach rn ai": "bach mai",
            "bach m ai": "bach mai",
            "bvbachmai": "bv bach mai",
        },
    ),
    HospitalProfile(
        hospital_id="fv",
        name="FV Hospital",
        header_patterns=(
            "fv hospital",
            "benh vien fv",
            "french vietnam",
            "franco-vietnamese",
        ),
        unit_system="SI",
        additional_aliases={},
        hospital_name_variants=(
            "fv healthcare",
            "francais vietnam",
            "franco vietnamien",
            "benh vien phap viet",
        ),
        ocr_corrections={
            "fv hospita1": "fv hospital",
            "f v hospital": "fv hospital",
            "french-vietnam": "french vietnam",
        },
    ),
)


UNKNOWN_PROFILE = HospitalProfile(
    hospital_id="unknown",
    name="Unknown",
    header_patterns=(),
    unit_system="SI",
)

_DETECTOR = HospitalDetector(HOSPITAL_PROFILES)


def detect_hospital(text: str) -> HospitalProfile | None:
    return _DETECTOR.detect(text)


def detect_hospital_result(text: str) -> DetectionResult:
    """Return DetectionResult (profile + position-weighted confidence) for the OCR text."""
    return _DETECTOR.detect_or_unknown(text)
