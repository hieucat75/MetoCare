"""AI safety policy constants for the Metabolic Care Platform.

This module is the single source of truth (in code) for what the AI is allowed
and prohibited to do. It is a direct, reviewable encoding of
``docs/AI_Safety_Guardrail.md`` sections 3.1, 3.2, 3.3, 4.1–4.5.

Design rules:
- Pure standard library only. No framework / DB / network imports.
- These lists are *configuration* approved by the medical board, NOT decided by
  an LLM at runtime. The rule engines (guardrails, triage) consume them.
- Vietnamese-first content because the product audience is Vietnamese.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Allowed vs prohibited actions (AI_Safety_Guardrail.md §3.1, §3.2)
# --------------------------------------------------------------------------- #

ALLOWED_ACTIONS: tuple[str, ...] = (
    "explain_lab_results",
    "daily_reminders",
    "lifestyle_recommendation",
    "metabolic_score",
    "estimate_meal_risk",
    "ask_followup_symptoms",
    "suggest_see_doctor",
    "prepare_pre_consult_summary",
    "track_care_plan_adherence",
    "cite_approved_guideline",
)

PROHIBITED_ACTIONS: tuple[str, ...] = (
    "definitive_diagnosis",      # ❌ chẩn đoán khẳng định
    "prescribe_medication",      # ❌ kê đơn / gợi ý thuốc cụ thể
    "change_medication_dose",    # ❌ thay đổi liều
    "start_stop_medication",     # ❌ bảo bắt đầu/ngừng thuốc
    "treat_emergency_as_routine",
    "downplay_red_flag",
    "clinical_treatment_protocol",
    "fabricate_data_or_guideline",
    "certain_prognosis",
    "leak_other_patient_data",
)

# --------------------------------------------------------------------------- #
# Red flag symptoms (AI_Safety_Guardrail.md §4.1) — medical-board approved v0.
# Each entry: canonical key + Vietnamese keyword variants used for matching.
# false-negative target = 0 → keyword set is intentionally broad.
# --------------------------------------------------------------------------- #

RED_FLAG_SYMPTOMS: dict[str, tuple[str, ...]] = {
    "chest_pain": ("đau ngực", "tức ngực", "đau thắt ngực", "nặng ngực"),
    "dyspnea": ("khó thở", "hụt hơi", "thở gấp", "không thở được"),
    "cold_sweat": ("vã mồ hôi", "toát mồ hôi lạnh", "đổ mồ hôi lạnh"),
    "stroke_signs": (
        "yếu liệt", "liệt nửa người", "méo miệng", "nói khó", "nói đớ",
        "tê nửa người", "đột quỵ", "lú lẫn",
    ),
    "syncope": ("ngất", "bất tỉnh", "mất ý thức", "xỉu"),
    "severe_hypertension_combo": ("đau đầu dữ dội", "mờ mắt", "hoa mắt dữ dội"),
    "hyperglycemia_combo": ("nôn", "mệt lả", "lơ mơ", "khát nước dữ dội"),
    "severe_hypoglycemia": ("run tay", "vã mồ hôi lú lẫn", "hạ đường huyết nặng", "co giật"),
    "severe_abdominal_pain": ("đau bụng dữ dội", "đau bụng quặn dữ dội"),
    "cyanosis": ("tím tái", "môi tím", "tím môi"),
}

# Vital-sign hard thresholds that constitute a red flag on their own
# (independent of free-text). Keyed by HealthMetric.metric_type.
# These are conservative screening thresholds, NOT diagnostic criteria.
RED_FLAG_VITAL_THRESHOLDS: dict[str, dict[str, float]] = {
    # systolic BP (mmHg)
    "blood_pressure_systolic": {"critical_high": 180.0, "critical_low": 80.0},
    # diastolic BP (mmHg)
    "blood_pressure_diastolic": {"critical_high": 120.0, "critical_low": 50.0},
    # glucose (mg/dL)
    "fasting_glucose": {"critical_high": 300.0, "critical_low": 54.0},
    "postprandial_glucose": {"critical_high": 350.0, "critical_low": 54.0},
}

# --------------------------------------------------------------------------- #
# Output-validator patterns (AI_Safety_Guardrail.md §3.2, §4.2, §4.3, §4.12)
# Regex-friendly substrings (lowercased, no-diacritic-insensitive handled in
# guardrails.py). Each maps to the prohibited action it represents.
# --------------------------------------------------------------------------- #

# Phrases that assert a definitive diagnosis ("bạn bị X").
DIAGNOSIS_ASSERTION_PATTERNS: tuple[str, ...] = (
    r"bạn (đã |chắc chắn )?bị (tiểu đường|đái tháo đường|ung thư|suy thận|nhồi máu|đột quỵ)",
    r"bạn (đã |chắc chắn )?mắc bệnh",
    r"chẩn đoán( của bạn)? là",
    r"bạn bị .* type ?2",
    r"kết luận bạn bị",
)

# Phrases that prescribe or name a specific drug + dose.
PRESCRIPTION_PATTERNS: tuple[str, ...] = (
    r"\buống\b.*\b(mg|viên|mcg)\b",
    r"\bmetformin\b",
    r"\binsulin\b.*\b(đơn vị|ui|iu|mg)\b",
    r"\bamlodipin",
    r"\batorvastatin",
    r"\bnên (uống|dùng) thuốc\b",
    r"\bkê (đơn|toa)\b",
    r"\bliều\b.*\b(mg|viên|đơn vị)\b",
)

# Phrases that change a medication dose.
DOSE_CHANGE_PATTERNS: tuple[str, ...] = (
    r"(tăng|giảm|gấp đôi|gấp ba|tăng gấp) liều",
    r"đổi liều",
    r"(ngừng|dừng|bỏ) thuốc",
    r"(tăng|giảm) (số )?viên",
)

# Phrases that downplay an emergency / red flag.
DOWNPLAY_PATTERNS: tuple[str, ...] = (
    r"(chỉ |chắc )?do căng thẳng thôi",
    r"không (sao|nghiêm trọng|đáng lo)( đâu)?,? nghỉ",
    r"nghỉ (ngơi )?(chút|tí) là (hết|khỏi)",
    r"không cần đi (khám|viện|bác sĩ)",
)

# Phrases asserting a certain prognosis.
PROGNOSIS_PATTERNS: tuple[str, ...] = (
    r"bạn sẽ khỏi (hẳn |hoàn toàn )?sau",
    r"chắc chắn sẽ (khỏi|hết)",
    r"đảm bảo (khỏi|hết) bệnh",
)

# Sources outside the approved RAG corpus.
UNAPPROVED_SOURCE_PATTERNS: tuple[str, ...] = (
    r"theo (một )?(nghiên cứu|bài viết|trang web|nguồn) (trên mạng|trên internet)",
    r"tôi (đọc được|thấy) trên (google|internet|mạng)",
)

# --------------------------------------------------------------------------- #
# Mandatory disclaimer (AI_Safety_Guardrail.md §4.9, §4.10)
# --------------------------------------------------------------------------- #

DISCLAIMER_VI = "Thông tin này không thay thế tư vấn bác sĩ."

EMERGENCY_MESSAGE_VI = (
    "Mình ghi nhận dấu hiệu có thể nguy hiểm. Bạn nên liên hệ cơ sở y tế hoặc "
    "gọi cấp cứu ngay bây giờ. Mình sẽ gắn cảnh báo này để bác sĩ theo dõi. "
    + DISCLAIMER_VI
)

SAFE_REFUSAL_MEDICATION_VI = (
    "Việc sử dụng hoặc điều chỉnh thuốc cần do bác sĩ hoặc dược sĩ quyết định dựa trên "
    "tình trạng cụ thể của bạn. Mình không thể tư vấn về thuốc hay liều lượng. "
    + DISCLAIMER_VI
)
