"""Pilot data seed: 10 realistic Vietnamese demo patients for MetoCare pilot.

Creates demo patient accounts with mixed metabolic risk profiles, realistic
health metrics (100+), lab results (50+), medication schedules (30+), and
adherence records.

TRANSACTION SAFETY MODEL
------------------------
``auth.register()`` issues a COMMIT internally, so user creation is
immediately durable. All subsequent data for that patient (metrics, labs,
medications, adherence) is written inside a per-patient SAVEPOINT. If data
seeding fails for patient N the savepoint is rolled back — patient N's user
persists but with no data — and seeding continues for remaining patients.

On re-run the script skips user creation (``_get_or_create_patient`` returns
``created=False``) but still seeds any missing data categories, enabling clean
recovery from mid-seed crashes.

PRODUCTION GUARD
-----------------
Refuses to run when ``ENV=production`` unless ``ALLOW_DEMO_SEED=true`` is also
set. This prevents accidental seeding of a production database.

ALL data is synthetic — no real PHI.

Run from the backend directory:
    python scripts/seed_demo_pilot.py
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.clock import utcnow  # noqa: E402
from app.core.database import SessionLocal, create_all  # noqa: E402
from app.models.clinical import (  # noqa: E402
    HealthMetric,
    LabResult,
    Medication,
    MedicationAdherence,
)
from app.models.patient import PatientProfile  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services import auth  # noqa: E402
from app.services import medication as medication_svc  # noqa: E402
from sqlalchemy import select  # noqa: E402

# ---------------------------------------------------------------------------
# Patient definitions
# ---------------------------------------------------------------------------
# Each entry: (phone, password, full_name, dob, gender, height_cm, weight_kg,
#              waist_cm, risk_segment, known_conditions, allergies,
#              family_history, lifestyle_profile)
PILOT_PATIENTS = [
    # ── HIGH RISK ──────────────────────────────────────────────────────────
    (
        "+84901234501",
        "PilotPatient01!",
        "Nguyễn Văn An",
        "1972-03-15",
        "male",
        168.0,
        88.0,
        98.0,
        "high",
        "Đái tháo đường type 2 (phát hiện 2018), Tăng huyết áp độ 1",
        "Penicillin",
        "Bố mắc đái tháo đường type 2, mẹ tăng huyết áp",
        "Ít vận động, ăn nhiều tinh bột, ngủ 5-6 giờ/ngày, không hút thuốc",
    ),
    (
        "+84901234502",
        "PilotPatient02!",
        "Trần Thị Bình",
        "1979-07-22",
        "female",
        158.0,
        78.0,
        90.0,
        "high",
        "Rối loạn lipid máu hỗn hợp, Thừa cân độ 1",
        "Không có",
        "Mẹ mắc bệnh mạch vành, chị gái rối loạn lipid máu",
        "Ít vận động, ăn nhiều dầu mỡ, công việc văn phòng",
    ),
    (
        "+84901234504",
        "PilotPatient04!",
        "Phạm Thị Dung",
        "1969-11-08",
        "female",
        155.0,
        65.0,
        85.0,
        "high",
        "Đái tháo đường type 2 (điều trị insulin), Bệnh thận mạn giai đoạn 2",
        "Sulfa",
        "Bố mắc bệnh thận, mẹ đái tháo đường type 2",
        "Chế độ ăn kiêng muối, không vận động nặng, cần theo dõi thận định kỳ",
    ),
    (
        "+84901234507",
        "PilotPatient07!",
        "Đặng Văn Giang",
        "1963-04-30",
        "male",
        165.0,
        76.0,
        94.0,
        "high",
        "Bệnh tim mạch vành (nhồi máu cơ tim 2021), Đái tháo đường type 2, Tăng huyết áp độ 2",
        "Không có",
        "Bố mất vì nhồi máu cơ tim, anh trai tăng huyết áp",
        "Đã bỏ thuốc lá 2021, đi bộ 30 phút/ngày, ăn giảm muối và mỡ",
    ),
    # ── MEDIUM RISK ────────────────────────────────────────────────────────
    (
        "+84901234503",
        "PilotPatient03!",
        "Lê Quang Cường",
        "1986-09-14",
        "male",
        172.0,
        82.0,
        88.0,
        "medium",
        "Tiền đái tháo đường, Thừa cân",
        "Không có",
        "Không rõ tiền sử gia đình",
        "Đi xe máy nhiều, ăn trưa ngoài hàng, uống 1-2 bia/ngày cuối tuần",
    ),
    (
        "+84901234506",
        "PilotPatient06!",
        "Vũ Thị Phương",
        "1976-02-18",
        "female",
        160.0,
        70.0,
        84.0,
        "medium",
        "Tiền đái tháo đường, Suy giáp (đang điều trị Levothyroxine)",
        "Không có",
        "Mẹ suy giáp, bà ngoại đái tháo đường type 2",
        "Mệt mỏi mãn tính, ít vận động, cần theo dõi TSH mỗi 6 tháng",
    ),
    (
        "+84901234509",
        "PilotPatient09!",
        "Ngô Văn Inh",
        "1981-06-05",
        "male",
        170.0,
        78.0,
        88.0,
        "medium",
        "Thừa cân, Đang cai thuốc lá",
        "Không có",
        "Bố tăng huyết áp",
        "Hút thuốc 10 năm (đang cai), uống cà phê nhiều, ngủ không đủ giấc",
    ),
    (
        "+84901234510",
        "PilotPatient10!",
        "Dương Thị Khánh",
        "1974-12-01",
        "female",
        158.0,
        68.0,
        86.0,
        "medium",
        "Tiền mãn kinh, Rối loạn lipid máu nhẹ",
        "Không có",
        "Mẹ tăng huyết áp sau mãn kinh",
        "Đi bộ buổi sáng 20 phút, ăn uống cân bằng, stress công việc cao",
    ),
    # ── LOW RISK ───────────────────────────────────────────────────────────
    (
        "+84901234505",
        "PilotPatient05!",
        "Hoàng Văn Em",
        "1995-08-20",
        "male",
        175.0,
        68.0,
        78.0,
        "low",
        "Không có bệnh nền",
        "Không có",
        "Không có tiền sử bệnh đặc biệt",
        "Tập gym 4 buổi/tuần, ăn lành mạnh, không hút thuốc, không uống rượu",
    ),
    (
        "+84901234508",
        "PilotPatient08!",
        "Bùi Thị Hoa",
        "1990-05-11",
        "female",
        162.0,
        65.0,
        80.0,
        "low",
        "Không có bệnh nền",
        "Không có",
        "Gia đình khoẻ mạnh",
        "Yoga 3 buổi/tuần, ăn chay 2 ngày/tuần, ngủ đủ 7-8 giờ",
    ),
]

# ---------------------------------------------------------------------------
# Metric definitions per patient
# ---------------------------------------------------------------------------


def _status(value: float, nmin: float | None, nmax: float | None) -> str:
    if nmin is None or nmax is None:
        return "normal"
    if value < nmin:
        return "low"
    if value > nmax:
        return "high"
    return "normal"


# Per-patient metric spec: list of (metric_type, unit, value_fn(day_idx), nmin, nmax)
METRIC_SPECS: dict[str, list[tuple]] = {
    "+84901234501": [
        (
            "blood_pressure_systolic",
            "mmHg",
            lambda i: round(158.0 - i * 0.3 + (i % 3) * 1.5, 1),
            90.0,
            130.0,
        ),
        (
            "blood_pressure_diastolic",
            "mmHg",
            lambda i: round(96.0 - i * 0.15 + (i % 4) * 0.8, 1),
            60.0,
            85.0,
        ),
        (
            "fasting_glucose",
            "mg/dL",
            lambda i: round(182.0 - i * 0.8 + (i % 5) * 3.0, 1),
            70.0,
            99.0,
        ),
        ("weight_kg", "kg", lambda i: round(88.0 - i * 0.04, 1), None, None),
        ("heart_rate", "bpm", lambda i: round(82.0 + (i % 7) * 1.0, 0), 60.0, 100.0),
        ("hba1c", "%", lambda i: round(8.2 - i * 0.02, 1), 0.0, 5.7),
    ],
    "+84901234502": [
        ("total_cholesterol", "mg/dL", lambda i: round(238.0 - i * 0.5, 1), 0.0, 200.0),
        ("ldl_cholesterol", "mg/dL", lambda i: round(162.0 - i * 0.4, 1), 0.0, 100.0),
        ("hdl_cholesterol", "mg/dL", lambda i: round(42.0 + i * 0.1, 1), 50.0, 999.0),
        ("triglycerides", "mg/dL", lambda i: round(218.0 - i * 0.6, 1), 0.0, 150.0),
        ("fasting_glucose", "mg/dL", lambda i: round(105.0 + (i % 6) * 1.0, 1), 70.0, 99.0),
        ("weight_kg", "kg", lambda i: round(78.0 - i * 0.03, 1), None, None),
        ("blood_pressure_systolic", "mmHg", lambda i: round(136.0 + (i % 4) * 1.5, 1), 90.0, 130.0),
        ("blood_pressure_diastolic", "mmHg", lambda i: round(88.0 + (i % 3) * 1.0, 1), 60.0, 85.0),
    ],
    "+84901234504": [
        (
            "fasting_glucose",
            "mg/dL",
            lambda i: round(148.0 - i * 1.2 + (i % 4) * 4.0, 1),
            70.0,
            99.0,
        ),
        ("hba1c", "%", lambda i: round(9.1 - i * 0.04, 1), 0.0, 5.7),
        ("creatinine", "mg/dL", lambda i: round(1.42 + (i % 5) * 0.02, 2), 0.5, 1.1),
        ("egfr", "mL/min/1.73m²", lambda i: round(64.0 - i * 0.1, 1), 60.0, 999.0),
        ("blood_pressure_systolic", "mmHg", lambda i: round(144.0 - i * 0.2, 1), 90.0, 130.0),
        ("blood_pressure_diastolic", "mmHg", lambda i: round(88.0 - i * 0.1, 1), 60.0, 85.0),
        ("weight_kg", "kg", lambda i: round(65.0 + (i % 3) * 0.1, 1), None, None),
    ],
    "+84901234507": [
        (
            "blood_pressure_systolic",
            "mmHg",
            lambda i: round(152.0 - i * 0.4 + (i % 5) * 1.0, 1),
            90.0,
            130.0,
        ),
        ("blood_pressure_diastolic", "mmHg", lambda i: round(94.0 - i * 0.2, 1), 60.0, 85.0),
        (
            "fasting_glucose",
            "mg/dL",
            lambda i: round(168.0 - i * 0.9 + (i % 3) * 2.0, 1),
            70.0,
            99.0,
        ),
        ("hba1c", "%", lambda i: round(8.8 - i * 0.03, 1), 0.0, 5.7),
        ("ldl_cholesterol", "mg/dL", lambda i: round(88.0 - i * 0.2, 1), 0.0, 70.0),
        ("total_cholesterol", "mg/dL", lambda i: round(178.0 - i * 0.3, 1), 0.0, 200.0),
        ("heart_rate", "bpm", lambda i: round(74.0 + (i % 6) * 1.0, 0), 60.0, 100.0),
        ("weight_kg", "kg", lambda i: round(76.0 - i * 0.02, 1), None, None),
    ],
    "+84901234503": [
        (
            "fasting_glucose",
            "mg/dL",
            lambda i: round(106.0 + (i % 8) * 1.5 - i * 0.1, 1),
            70.0,
            99.0,
        ),
        ("weight_kg", "kg", lambda i: round(82.0 - i * 0.05, 1), None, None),
        (
            "blood_pressure_systolic",
            "mmHg",
            lambda i: round(132.0 + (i % 4) * 1.0 - i * 0.05, 1),
            90.0,
            130.0,
        ),
        ("blood_pressure_diastolic", "mmHg", lambda i: round(84.0 + (i % 3) * 0.5, 1), 60.0, 85.0),
        ("hba1c", "%", lambda i: 6.1, 0.0, 5.7),
        ("heart_rate", "bpm", lambda i: round(78.0 + (i % 5) * 1.0, 0), 60.0, 100.0),
    ],
    "+84901234506": [
        ("fasting_glucose", "mg/dL", lambda i: round(103.0 + (i % 6) * 1.0, 1), 70.0, 99.0),
        ("tsh", "mIU/L", lambda i: round(6.8 - i * 0.05, 2), 0.4, 4.0),
        ("weight_kg", "kg", lambda i: round(70.0 - i * 0.04, 1), None, None),
        ("blood_pressure_systolic", "mmHg", lambda i: round(128.0 + (i % 4) * 1.0, 1), 90.0, 130.0),
        ("blood_pressure_diastolic", "mmHg", lambda i: round(82.0 + (i % 3) * 0.5, 1), 60.0, 85.0),
    ],
    "+84901234509": [
        ("blood_pressure_systolic", "mmHg", lambda i: round(134.0 - i * 0.1, 1), 90.0, 130.0),
        ("blood_pressure_diastolic", "mmHg", lambda i: round(86.0 - i * 0.05, 1), 60.0, 85.0),
        ("fasting_glucose", "mg/dL", lambda i: round(99.0 + (i % 7) * 1.0, 1), 70.0, 99.0),
        ("weight_kg", "kg", lambda i: round(78.0 - i * 0.06, 1), None, None),
        ("heart_rate", "bpm", lambda i: round(86.0 - i * 0.3, 0), 60.0, 100.0),
    ],
    "+84901234510": [
        ("total_cholesterol", "mg/dL", lambda i: round(214.0 - i * 0.3, 1), 0.0, 200.0),
        ("ldl_cholesterol", "mg/dL", lambda i: round(138.0 - i * 0.25, 1), 0.0, 100.0),
        ("hdl_cholesterol", "mg/dL", lambda i: round(52.0 + i * 0.05, 1), 50.0, 999.0),
        ("fasting_glucose", "mg/dL", lambda i: round(97.0 + (i % 5) * 1.0, 1), 70.0, 99.0),
        ("weight_kg", "kg", lambda i: round(68.0 + (i % 4) * 0.1, 1), None, None),
    ],
    "+84901234505": [
        ("fasting_glucose", "mg/dL", lambda i: round(88.0 + (i % 5) * 1.0, 1), 70.0, 99.0),
        ("blood_pressure_systolic", "mmHg", lambda i: round(112.0 + (i % 4) * 1.0, 1), 90.0, 130.0),
        ("blood_pressure_diastolic", "mmHg", lambda i: round(72.0 + (i % 3) * 0.5, 1), 60.0, 85.0),
        ("heart_rate", "bpm", lambda i: round(58.0 + (i % 6) * 1.0, 0), 60.0, 100.0),
        ("weight_kg", "kg", lambda i: round(68.0 + (i % 3) * 0.2, 1), None, None),
        ("total_cholesterol", "mg/dL", lambda i: round(168.0 + (i % 4) * 1.0, 1), 0.0, 200.0),
    ],
    "+84901234508": [
        ("fasting_glucose", "mg/dL", lambda i: round(84.0 + (i % 5) * 0.8, 1), 70.0, 99.0),
        ("blood_pressure_systolic", "mmHg", lambda i: round(110.0 + (i % 4) * 0.8, 1), 90.0, 130.0),
        ("blood_pressure_diastolic", "mmHg", lambda i: round(70.0 + (i % 3) * 0.5, 1), 60.0, 85.0),
        ("heart_rate", "bpm", lambda i: round(68.0 + (i % 5) * 1.0, 0), 60.0, 100.0),
        ("weight_kg", "kg", lambda i: 65.0, None, None),
    ],
}

# ---------------------------------------------------------------------------
# Lab result definitions per patient
# Each patient entry is a list of sessions; each session is a list of result tuples:
# (test_name, canonical_name, value, unit, reference_range, status)
# ---------------------------------------------------------------------------
LAB_SPECS: dict[str, list[list[tuple]]] = {
    "+84901234501": [
        [
            ("Glucose đói (FBG)", "fasting_glucose", 196.0, "mg/dL", "70-99", "high"),
            ("HbA1c", "hba1c", 8.6, "%", "<5.7", "high"),
            ("Cholesterol toàn phần", "total_cholesterol", 228.0, "mg/dL", "<200", "high"),
            ("Triglycerid", "triglycerides", 188.0, "mg/dL", "<150", "high"),
            ("HDL Cholesterol", "hdl_cholesterol", 38.0, "mg/dL", ">50", "low"),
            ("LDL Cholesterol", "ldl_cholesterol", 148.0, "mg/dL", "<100", "high"),
        ],
        [
            ("Glucose đói (FBG)", "fasting_glucose", 164.0, "mg/dL", "70-99", "high"),
            ("HbA1c", "hba1c", 7.8, "%", "<5.7", "high"),
            ("Creatinine", "creatinine", 1.05, "mg/dL", "0.7-1.2", "normal"),
            ("eGFR", "egfr", 78.0, "mL/min/1.73m²", ">60", "normal"),
        ],
    ],
    "+84901234502": [
        [
            ("Cholesterol toàn phần", "total_cholesterol", 252.0, "mg/dL", "<200", "high"),
            ("LDL Cholesterol", "ldl_cholesterol", 174.0, "mg/dL", "<100", "high"),
            ("HDL Cholesterol", "hdl_cholesterol", 40.0, "mg/dL", ">50", "low"),
            ("Triglycerid", "triglycerides", 236.0, "mg/dL", "<150", "high"),
            ("Glucose đói (FBG)", "fasting_glucose", 108.0, "mg/dL", "70-99", "high"),
            ("ALT (SGPT)", "alt", 38.0, "U/L", "<40", "normal"),
        ],
        [
            ("Cholesterol toàn phần", "total_cholesterol", 224.0, "mg/dL", "<200", "high"),
            ("LDL Cholesterol", "ldl_cholesterol", 148.0, "mg/dL", "<100", "high"),
            ("HDL Cholesterol", "hdl_cholesterol", 44.0, "mg/dL", ">50", "low"),
            ("Triglycerid", "triglycerides", 192.0, "mg/dL", "<150", "high"),
        ],
    ],
    "+84901234503": [
        [
            ("Glucose đói (FBG)", "fasting_glucose", 108.0, "mg/dL", "70-99", "high"),
            ("HbA1c", "hba1c", 6.2, "%", "<5.7", "high"),
            ("Cholesterol toàn phần", "total_cholesterol", 198.0, "mg/dL", "<200", "normal"),
            ("LDL Cholesterol", "ldl_cholesterol", 128.0, "mg/dL", "<100", "high"),
            ("HDL Cholesterol", "hdl_cholesterol", 46.0, "mg/dL", ">50", "low"),
            ("Triglycerid", "triglycerides", 142.0, "mg/dL", "<150", "normal"),
        ],
    ],
    "+84901234504": [
        [
            ("Glucose đói (FBG)", "fasting_glucose", 188.0, "mg/dL", "70-99", "high"),
            ("HbA1c", "hba1c", 9.4, "%", "<5.7", "high"),
            ("Creatinine", "creatinine", 1.52, "mg/dL", "0.5-1.1", "high"),
            ("eGFR", "egfr", 58.0, "mL/min/1.73m²", ">60", "low"),
            ("Urea (BUN)", "urea", 28.0, "mg/dL", "6-20", "high"),
            ("Microalbumin niệu", "microalbuminuria", 82.0, "mg/g", "<30", "high"),
        ],
        [
            ("Glucose đói (FBG)", "fasting_glucose", 144.0, "mg/dL", "70-99", "high"),
            ("HbA1c", "hba1c", 8.4, "%", "<5.7", "high"),
            ("Creatinine", "creatinine", 1.46, "mg/dL", "0.5-1.1", "high"),
            ("eGFR", "egfr", 61.0, "mL/min/1.73m²", ">60", "normal"),
        ],
    ],
    "+84901234505": [
        [
            ("Glucose đói (FBG)", "fasting_glucose", 86.0, "mg/dL", "70-99", "normal"),
            ("Cholesterol toàn phần", "total_cholesterol", 164.0, "mg/dL", "<200", "normal"),
            ("LDL Cholesterol", "ldl_cholesterol", 88.0, "mg/dL", "<100", "normal"),
            ("HDL Cholesterol", "hdl_cholesterol", 62.0, "mg/dL", ">50", "normal"),
            ("Triglycerid", "triglycerides", 84.0, "mg/dL", "<150", "normal"),
            ("Creatinine", "creatinine", 0.88, "mg/dL", "0.7-1.2", "normal"),
        ],
    ],
    "+84901234506": [
        [
            ("TSH", "tsh", 7.2, "mIU/L", "0.4-4.0", "high"),
            ("FT4", "ft4", 0.72, "ng/dL", "0.7-1.8", "low"),
            ("Glucose đói (FBG)", "fasting_glucose", 104.0, "mg/dL", "70-99", "high"),
            ("HbA1c", "hba1c", 5.9, "%", "<5.7", "high"),
            ("Cholesterol toàn phần", "total_cholesterol", 218.0, "mg/dL", "<200", "high"),
            ("LDL Cholesterol", "ldl_cholesterol", 142.0, "mg/dL", "<100", "high"),
        ],
        [
            ("TSH", "tsh", 4.8, "mIU/L", "0.4-4.0", "high"),
            ("FT4", "ft4", 0.98, "ng/dL", "0.7-1.8", "normal"),
            ("Glucose đói (FBG)", "fasting_glucose", 102.0, "mg/dL", "70-99", "high"),
        ],
    ],
    "+84901234507": [
        [
            ("Glucose đói (FBG)", "fasting_glucose", 172.0, "mg/dL", "70-99", "high"),
            ("HbA1c", "hba1c", 9.2, "%", "<5.7", "high"),
            ("LDL Cholesterol", "ldl_cholesterol", 92.0, "mg/dL", "<70", "high"),
            ("Cholesterol toàn phần", "total_cholesterol", 182.0, "mg/dL", "<200", "normal"),
            ("HDL Cholesterol", "hdl_cholesterol", 42.0, "mg/dL", ">40", "normal"),
            ("Triglycerid", "triglycerides", 168.0, "mg/dL", "<150", "high"),
            ("Troponin I", "troponin_i", 0.01, "ng/mL", "<0.04", "normal"),
            ("Creatinine", "creatinine", 0.96, "mg/dL", "0.7-1.2", "normal"),
        ],
        [
            ("Glucose đói (FBG)", "fasting_glucose", 148.0, "mg/dL", "70-99", "high"),
            ("HbA1c", "hba1c", 8.2, "%", "<5.7", "high"),
            ("LDL Cholesterol", "ldl_cholesterol", 78.0, "mg/dL", "<70", "high"),
            ("Cholesterol toàn phần", "total_cholesterol", 168.0, "mg/dL", "<200", "normal"),
        ],
    ],
    "+84901234508": [
        [
            ("Glucose đói (FBG)", "fasting_glucose", 82.0, "mg/dL", "70-99", "normal"),
            ("Cholesterol toàn phần", "total_cholesterol", 172.0, "mg/dL", "<200", "normal"),
            ("HDL Cholesterol", "hdl_cholesterol", 68.0, "mg/dL", ">50", "normal"),
            ("LDL Cholesterol", "ldl_cholesterol", 88.0, "mg/dL", "<100", "normal"),
            ("Triglycerid", "triglycerides", 72.0, "mg/dL", "<150", "normal"),
            ("TSH", "tsh", 2.1, "mIU/L", "0.4-4.0", "normal"),
        ],
    ],
    "+84901234509": [
        [
            ("Glucose đói (FBG)", "fasting_glucose", 98.0, "mg/dL", "70-99", "normal"),
            ("Cholesterol toàn phần", "total_cholesterol", 204.0, "mg/dL", "<200", "high"),
            ("LDL Cholesterol", "ldl_cholesterol", 132.0, "mg/dL", "<100", "high"),
            ("HDL Cholesterol", "hdl_cholesterol", 44.0, "mg/dL", ">40", "normal"),
            ("Triglycerid", "triglycerides", 148.0, "mg/dL", "<150", "normal"),
            ("Axit uric", "uric_acid", 7.2, "mg/dL", "3.5-7.0", "high"),
        ],
    ],
    "+84901234510": [
        [
            ("Cholesterol toàn phần", "total_cholesterol", 218.0, "mg/dL", "<200", "high"),
            ("LDL Cholesterol", "ldl_cholesterol", 142.0, "mg/dL", "<100", "high"),
            ("HDL Cholesterol", "hdl_cholesterol", 54.0, "mg/dL", ">50", "normal"),
            ("Triglycerid", "triglycerides", 136.0, "mg/dL", "<150", "normal"),
            ("Glucose đói (FBG)", "fasting_glucose", 96.0, "mg/dL", "70-99", "normal"),
            ("FSH", "fsh", 28.4, "mIU/mL", "3.5-12.5", "high"),
        ],
        [
            ("Cholesterol toàn phần", "total_cholesterol", 206.0, "mg/dL", "<200", "high"),
            ("LDL Cholesterol", "ldl_cholesterol", 128.0, "mg/dL", "<100", "high"),
            ("HDL Cholesterol", "hdl_cholesterol", 56.0, "mg/dL", ">50", "normal"),
        ],
    ],
}

# ---------------------------------------------------------------------------
# Medication definitions per patient
# (name, dose, frequency, note)
# ---------------------------------------------------------------------------
MED_SPECS: dict[str, list[tuple]] = {
    "+84901234501": [
        (
            "Metformin",
            "500mg",
            "2 lần/ngày (sáng và tối, sau ăn)",
            "Uống với bữa ăn để giảm tác dụng phụ dạ dày",
        ),
        (
            "Glimepiride",
            "2mg",
            "1 lần/ngày (trước bữa sáng)",
            "Theo dõi hạ đường huyết, bắt đầu liều thấp",
        ),
        ("Lisinopril", "5mg", "1 lần/ngày (sáng)", "Theo dõi huyết áp hàng ngày"),
        ("Atorvastatin", "10mg", "1 lần/ngày (tối)", "Uống cố định buổi tối"),
        (
            "Vitamin D3",
            "2000 IU",
            "1 lần/ngày (trong bữa ăn)",
            "Bổ sung thiếu hụt vitamin D thường gặp ở bệnh nhân đái tháo đường",
        ),
    ],
    "+84901234502": [
        ("Atorvastatin", "20mg", "1 lần/ngày (tối)", "Theo dõi men gan sau 3 tháng"),
        ("Fenofibrate", "160mg", "1 lần/ngày (trong bữa ăn)", "Điều trị tăng triglycerid"),
        ("Omega-3", "1000mg", "2 lần/ngày (sau ăn)", "Hỗ trợ hạ triglycerid, uống cùng bữa ăn"),
    ],
    "+84901234503": [
        (
            "Metformin",
            "500mg",
            "1 lần/ngày (tối, sau ăn)",
            "Khởi đầu điều trị tiền đái tháo đường, tăng dần sau 4 tuần",
        ),
        (
            "Berberine",
            "500mg",
            "2 lần/ngày (trước ăn sáng và tối)",
            "Hỗ trợ kiểm soát đường huyết, theo dõi sau 3 tháng",
        ),
    ],
    "+84901234504": [
        (
            "Insulin glargine (Lantus)",
            "10 đơn vị",
            "1 lần/ngày (21h00)",
            "Tiêm dưới da vùng bụng, xoay vị trí tiêm",
        ),
        ("Metformin", "850mg", "2 lần/ngày (sáng và tối, sau ăn)", "Giảm liều nếu eGFR <45"),
        ("Lisinopril", "10mg", "1 lần/ngày (sáng)", "Bảo vệ thận, theo dõi creatinine mỗi 3 tháng"),
        ("Furosemide", "20mg", "1 lần/ngày (sáng)", "Uống buổi sáng để tránh tiểu đêm"),
        (
            "Calcium carbonate",
            "500mg",
            "2 lần/ngày (sau ăn)",
            "Bổ sung canxi cho bệnh nhân thận mạn, không uống cùng sắt",
        ),
        (
            "Vitamin B complex",
            "1 viên",
            "1 lần/ngày (sáng, sau ăn)",
            "Dự phòng thiếu hụt B12 do Metformin dài hạn",
        ),
    ],
    "+84901234505": [
        (
            "Vitamin D3",
            "1000 IU",
            "1 lần/ngày (sau ăn)",
            "Bổ sung duy trì, xét nghiệm lại sau 6 tháng",
        ),
        (
            "Magnesium glycinate",
            "400mg",
            "1 lần/ngày (tối)",
            "Hỗ trợ phục hồi cơ và giấc ngủ cho người tập luyện cường độ cao",
        ),
    ],
    "+84901234506": [
        (
            "Levothyroxine",
            "50mcg",
            "1 lần/ngày (sáng, lúc đói)",
            "Uống trước ăn sáng 30 phút, không uống cùng canxi/sắt",
        ),
        (
            "Metformin",
            "500mg",
            "1 lần/ngày (tối, sau ăn)",
            "Điều trị tiền đái tháo đường, theo dõi chức năng thận",
        ),
        (
            "Calcium + Vitamin D3",
            "500mg + 400 IU",
            "1 lần/ngày (sau ăn trưa)",
            "Cách xa Levothyroxine ít nhất 4 giờ",
        ),
    ],
    "+84901234507": [
        (
            "Aspirin",
            "81mg",
            "1 lần/ngày (sau ăn sáng)",
            "Phòng ngừa huyết khối, không ngừng đột ngột",
        ),
        (
            "Clopidogrel",
            "75mg",
            "1 lần/ngày (sau ăn)",
            "Kháng kết tập tiểu cầu kép sau nhồi máu cơ tim, duy trì 12 tháng",
        ),
        ("Atorvastatin", "40mg", "1 lần/ngày (tối)", "Mục tiêu LDL <70 mg/dL"),
        ("Metformin", "500mg", "2 lần/ngày (sáng và tối, sau ăn)", "Theo dõi chức năng thận"),
        ("Amlodipine", "5mg", "1 lần/ngày (sáng)", "Theo dõi phù chân"),
        ("Bisoprolol", "2.5mg", "1 lần/ngày (sáng)", "Không ngừng đột ngột, theo dõi nhịp tim"),
    ],
    "+84901234508": [
        (
            "Sắt (II) fumarat",
            "60mg",
            "1 lần/ngày (sáng, lúc đói)",
            "Bổ sung sắt cho phụ nữ, uống kèm nước cam để hấp thu tốt hơn",
        ),
        (
            "Acid folic",
            "400mcg",
            "1 lần/ngày (sáng)",
            "Bổ sung dự phòng cho phụ nữ trong độ tuổi sinh sản",
        ),
    ],
    "+84901234509": [
        (
            "Miếng dán Nicotine",
            "14mg/24h",
            "1 miếng/ngày (dán sáng, gỡ trước ngủ)",
            "Hỗ trợ cai thuốc lá — tuần 1-6; giảm xuống 7mg/24h sau 6 tuần",
        ),
        (
            "Omega-3",
            "1000mg",
            "1 lần/ngày (sau ăn tối)",
            "Hỗ trợ tim mạch, theo dõi mỡ máu sau 3 tháng",
        ),
    ],
    "+84901234510": [
        ("Atorvastatin", "10mg", "1 lần/ngày (tối)", "Bắt đầu liều thấp, đánh giá lại sau 6 tuần"),
        (
            "Calcium carbonate + Vitamin D3",
            "600mg + 400 IU",
            "2 lần/ngày (sau ăn sáng và tối)",
            "Dự phòng loãng xương giai đoạn tiền mãn kinh",
        ),
        ("Omega-3", "1000mg", "1 lần/ngày (sau ăn)", "Hỗ trợ tim mạch và hạ triglycerid nhẹ"),
        (
            "Vitamin E",
            "400 IU",
            "1 lần/ngày (sau ăn)",
            "Hỗ trợ triệu chứng tiền mãn kinh — theo dõi hiệu quả sau 8 tuần",
        ),
    ],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_not_production() -> None:
    """Refuse to run against a production database unless explicitly overridden.

    Raises RuntimeError when ENV=production and ALLOW_DEMO_SEED is not 'true'.
    """
    env = os.environ.get("ENV", "").strip().lower()
    allow = os.environ.get("ALLOW_DEMO_SEED", "").strip().lower()
    if env == "production" and allow != "true":
        raise RuntimeError(
            "SAFETY: seed_demo_pilot.py refused to run against production.\n"
            "Environment ENV=production detected. This script seeds synthetic\n"
            "demo data and must NOT be run against real patient databases.\n\n"
            "If you genuinely need to seed a production-like environment, set:\n"
            "    ALLOW_DEMO_SEED=true\n"
        )


def _get_or_create_patient(db, phone: str, password: str, full_name: str) -> tuple[User, bool]:
    existing = db.execute(select(User).where(User.phone == phone)).scalar_one_or_none()
    if existing is not None:
        return existing, False
    user = auth.register(
        db,
        phone=phone,
        password=password,
        full_name=full_name,
        role=UserRole.PATIENT,
    )
    return user, True


def _profile(db, user: User) -> PatientProfile:
    return db.execute(select(PatientProfile).where(PatientProfile.user_id == user.id)).scalar_one()


def _seed_metrics(db, patient_id: str, phone: str, now: dt.datetime) -> int:
    specs = METRIC_SPECS.get(phone, [])
    if not specs:
        return 0
    existing = db.execute(
        select(HealthMetric).where(HealthMetric.patient_id == patient_id).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return 0
    count = 0
    n_days = 45
    step = 3
    for day_offset in range(n_days, -1, -step):
        measured_at = now - dt.timedelta(days=day_offset)
        day_idx = (n_days - day_offset) // step
        for metric_type, unit, value_fn, nmin, nmax in specs:
            value = float(value_fn(day_idx))
            db.add(
                HealthMetric(
                    patient_id=patient_id,
                    metric_type=metric_type,
                    value=value,
                    unit=unit,
                    measured_at=measured_at,
                    source="seed_pilot",
                    normal_range_min=nmin,
                    normal_range_max=nmax,
                    status=_status(value, nmin, nmax),
                )
            )
            count += 1
    return count


def _seed_labs(db, patient_id: str, phone: str, now: dt.datetime) -> int:
    sessions = LAB_SPECS.get(phone, [])
    existing = db.execute(
        select(LabResult).where(LabResult.patient_id == patient_id).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return 0
    count = 0
    session_offsets = [90, 30]
    for session_idx, results in enumerate(sessions):
        days_ago = session_offsets[session_idx] if session_idx < len(session_offsets) else 14
        test_date = (now - dt.timedelta(days=days_ago)).date()
        for test_name, canonical, value, unit, ref_range, status in results:
            db.add(
                LabResult(
                    patient_id=patient_id,
                    test_name=test_name,
                    canonical_name=canonical,
                    value=value,
                    unit=unit,
                    reference_range=ref_range,
                    status=status,
                    test_date=test_date,
                    ocr_confidence=1.0,
                    verified_by_user=True,
                    verified_by_doctor=False,
                )
            )
            count += 1
    return count


def _seed_medications(db, patient_id: str, phone: str) -> list[Medication]:
    specs = MED_SPECS.get(phone, [])
    existing = db.execute(
        select(Medication).where(Medication.patient_id == patient_id).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return []
    meds = []
    for name, dose, frequency, note in specs:
        # Statement-first (ADR-04): the service is the only sanctioned write
        # path — seeding must not bypass medication_statements/audit either.
        med = medication_svc.add_medication(
            db,
            patient_id=patient_id,
            data={"name": name, "dose": dose, "frequency": frequency, "note": note},
            actor_role="seed_script",
            commit=False,  # the seed owns its per-patient savepoint
        )
        meds.append(med)
    return meds


def _seed_adherence(db, patient_id: str, meds: list[Medication], now: dt.datetime) -> int:
    if not meds:
        return 0
    db.flush()
    count = 0
    for med in meds:
        for day_offset in range(14, 0, -1):
            taken_at = now - dt.timedelta(days=day_offset, hours=1)
            skipped = day_offset % 7 == 0
            db.add(
                MedicationAdherence(
                    medication_id=med.id,
                    patient_id=patient_id,
                    scheduled_time=taken_at - dt.timedelta(minutes=30),
                    taken_at=None if skipped else taken_at,
                    skipped=skipped,
                    note="Quên uống" if skipped else None,
                )
            )
            count += 1
    return count


# ---------------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------------


def seed(db) -> dict:
    """Seed all pilot patients.

    Transaction safety
    ------------------
    auth.register() commits immediately (its own internal commit). After that
    commit, a per-patient SAVEPOINT wraps all data seeding (metrics, labs,
    medications, adherence). A failure inside the savepoint rolls back only
    that patient's data; the user record and all other patients are unaffected.
    Re-running the script recovers partial seeds because each _seed_* helper
    checks for existing rows before inserting.

    Idempotency
    -----------
    * Existing users → skipped by _get_or_create_patient (created=False)
    * Existing data  → each _seed_* helper checks for existing rows first
    * Safe to run multiple times; already-complete patients are always skipped
    """
    _check_not_production()

    summary: dict = {
        "patients_created": [],
        "patients_skipped": [],
        "patients_failed": [],
        "metrics": 0,
        "lab_results": 0,
        "medications": 0,
        "adherence_records": 0,
    }
    now = utcnow()

    for row in PILOT_PATIENTS:
        (
            phone,
            password,
            full_name,
            dob,
            gender,
            height_cm,
            weight_kg,
            waist_cm,
            risk_segment,
            known_conditions,
            allergies,
            family_history,
            lifestyle_profile,
        ) = row

        # User creation commits immediately — cannot be rolled back.
        user, created = _get_or_create_patient(db, phone, password, full_name)
        if created:
            summary["patients_created"].append(full_name)
        else:
            summary["patients_skipped"].append(full_name)

        # Per-patient SAVEPOINT: data failures roll back only this patient's
        # data. The user record (committed above) is always preserved.
        sp = db.begin_nested()
        try:
            profile = _profile(db, user)
            if created:
                profile.dob = dob
                profile.gender = gender
                profile.height_cm = height_cm
                profile.weight_kg = weight_kg
                profile.waist_cm = waist_cm
                profile.risk_segment = risk_segment
                profile.known_conditions = known_conditions
                profile.allergies = allergies
                profile.family_history = family_history
                profile.lifestyle_profile = lifestyle_profile
                db.flush()

            patient_id = profile.id
            summary["metrics"] += _seed_metrics(db, patient_id, phone, now)
            summary["lab_results"] += _seed_labs(db, patient_id, phone, now)
            meds = _seed_medications(db, patient_id, phone)
            summary["medications"] += len(meds)
            summary["adherence_records"] += _seed_adherence(db, patient_id, meds, now)
            sp.commit()
        except Exception as exc:
            sp.rollback()
            summary["patients_failed"].append({"name": full_name, "error": str(exc)})

    db.commit()
    return summary


if __name__ == "__main__":
    create_all()
    with SessionLocal() as db:
        result = seed(db)

    print("\n── Pilot Seed Complete ──────────────────────────────")
    print(f"  Created   : {len(result['patients_created'])} patients")
    for name in result["patients_created"]:
        print(f"              • {name}")
    if result["patients_skipped"]:
        print(f"  Skipped   : {result['patients_skipped']}")
    if result["patients_failed"]:
        print(f"  FAILED    : {len(result['patients_failed'])} patients")
        for entry in result["patients_failed"]:
            print(f"              ✗ {entry['name']}: {entry['error']}")
    print(f"  Metrics   : {result['metrics']}")
    print(f"  Lab results: {result['lab_results']}")
    print(f"  Medications: {result['medications']}")
    print(f"  Adherence  : {result['adherence_records']} records")
    print("─────────────────────────────────────────────────────\n")
    if result["patients_failed"]:
        sys.exit(1)
