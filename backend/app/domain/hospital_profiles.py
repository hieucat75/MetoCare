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
        additional_aliases={},
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
    ),
    HospitalProfile(
        hospital_id="tam_anh",
        name="Tam Anh",
        header_patterns=(
            "tam anh",
            "benh vien tam anh",
            "tamanh",
            "benh vien da khoa tam anh",
        ),
        unit_system="SI",
        additional_aliases={},
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
        hospital_id="hong_ngoc",
        name="Hong Ngoc",
        header_patterns=(
            "hong ngoc",
            "benh vien hong ngoc",
            "hongngoc",
        ),
        unit_system="mixed",
        additional_aliases={},
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
        hospital_id="hospital_108",
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
        hospital_id="bach_mai",
        name="Bach Mai",
        header_patterns=(
            "bach mai",
            "benh vien bach mai",
            "bv bach mai",
        ),
        unit_system="conventional",
        additional_aliases={},
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


def detect_hospital(text: str) -> HospitalProfile | None:
    header = _strip_accents("\n".join(text.splitlines()[:30])).lower()
    for profile in HOSPITAL_PROFILES:
        for pattern in profile.header_patterns:
            if pattern in header:
                return profile
    return None
