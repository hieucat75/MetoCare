# Meto AI — Doctor Handoff Engine

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved
> **Phase:** 3 — Clinical Intelligence

---

## Tổng quan

Doctor Handoff Engine (DHE) là hệ thống quyết định khi nào Meto nên "dừng lại" và chuyển giao người dùng đến bác sĩ hoặc dịch vụ cấp cứu. DHE hoạt động ở **hai lớp**: code-level hardcoded rules (không thể bypass) và AI-assisted contextual assessment (flexible nhưng có guardrails).

**Triết học:** Meto tốt nhất khi biết giới hạn của mình. Đúng lúc, đúng chỗ, đúng cách.

**File backend:**
- `app/ai/doctor_handoff.py` — DHE core engine
- `app/ai/doctor_handoff/red_flags.py` — Red flag detection
- `app/ai/doctor_handoff/escalation_matrix.py` — Escalation decision
- `app/ai/doctor_handoff/templates.py` — Communication templates
- `app/ai/doctor_handoff/followup.py` — Post-escalation check-in

---

## 1. Escalation Philosophy

### 1.1 Meto hỗ trợ, không thay thế

```
CORE PRINCIPLE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Meto tồn tại để HỖ TRỢ người dùng hiểu sức khỏe của mình tốt hơn,
KHÔNG để thay thế đánh giá lâm sàng của bác sĩ.

Khi Meto gặp tình huống vượt quá khả năng trợ lý sức khỏe:
- Nhận biết ngay
- Thông báo rõ ràng
- Hướng dẫn người dùng đến nguồn hỗ trợ phù hợp
- Không gây hoảng loạn thêm
- Luôn sẵn sàng check-in sau khi escalate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 1.2 Hai lớp detection

```python
# Layer 1: Code-level hardcoded (KHÔNG AI, KHÔNG bypass)
class HardcodedEscalationLayer:
    """
    Chạy TRƯỚC khi gọi AI model.
    Nếu trigger → return escalation response ngay, KHÔNG gọi AI.
    """
    pass

# Layer 2: AI-assisted contextual assessment
class ContextualEscalationLayer:
    """
    Chạy trong CRL Stage 3 và RE.
    AI đánh giá toàn bộ context để quyết định action tier.
    Có thể escalate dựa trên pattern, trend, hoặc combination.
    """
    pass
```

---

## 2. 4-Tier Decision Framework

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DOCTOR HANDOFF DECISION TIERS                     │
│                                                                      │
│  TIER 4: EMERGENCY (Khẩn cấp — Gọi 115/113 ngay)                   │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Nguy hiểm tính mạng. Không chờ. Không vào ứng dụng.        │    │
│  │ Gọi cấp cứu hoặc đến bệnh viện ngay lập tức.               │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  TIER 3: URGENT (Khẩn — Gặp bác sĩ trong 24–48 giờ)               │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Cần đánh giá y tế sớm nhưng không phải cấp cứu ngay.       │    │
│  │ Liên hệ bác sĩ hôm nay hoặc sáng mai.                      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  TIER 2: RECOMMEND CHECK-UP (Nên khám — Lên lịch sớm)              │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Có dấu hiệu cần theo dõi bởi bác sĩ.                       │    │
│  │ Đặt lịch khám trong vài ngày đến 1 tuần.                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  TIER 1: CONTINUE SUPPORT (Meto tiếp tục hỗ trợ)                   │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Tình huống trong phạm vi Meto có thể giải thích.            │    │
│  │ Không có dấu hiệu cần can thiệp y tế khẩn.                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 Tier Definition & Response Time

```python
class EscalationLevel(str, Enum):
    CONTINUE_SUPPORT = "tier1_continue"
    RECOMMEND_CHECKUP = "tier2_checkup"
    URGENT = "tier3_urgent"
    EMERGENCY = "tier4_emergency"

TIER_METADATA = {
    EscalationLevel.CONTINUE_SUPPORT: {
        "response_time": None,
        "who_to_contact": None,
        "meto_action": "provide_support",
    },
    EscalationLevel.RECOMMEND_CHECKUP: {
        "response_time": "Trong 1–7 ngày",
        "who_to_contact": "Bác sĩ chăm sóc chính hoặc chuyên khoa",
        "meto_action": "recommend_and_support",
    },
    EscalationLevel.URGENT: {
        "response_time": "Trong 24–48 giờ",
        "who_to_contact": "Bác sĩ hoặc phòng khám hôm nay/sáng mai",
        "meto_action": "strongly_recommend_visit",
    },
    EscalationLevel.EMERGENCY: {
        "response_time": "NGAY LẬP TỨC",
        "who_to_contact": "115/113 hoặc phòng cấp cứu gần nhất",
        "meto_action": "bypass_all_hardcoded_emergency_response",
    },
}
```

---

## 3. Red Flags — Danh sách đầy đủ

### 3.1 Emergency Red Flags (Tier 4)

```python
# app/ai/doctor_handoff/red_flags.py

RED_FLAGS_EMERGENCY = {
    "cardiovascular": [
        # Chest pain / Đau ngực
        "đau ngực", "tức ngực", "đau thắt ngực", "áp lực ngực",
        "nặng ngực", "đau lan lên vai trái", "đau lan lên hàm",
        "chest pain", "chest tightness", "chest pressure",

        # Breathing / Khó thở
        "khó thở", "không thở được", "thở dốc đột ngột",
        "thở không đủ hơi", "hụt hơi đột ngột",
        "shortness of breath", "can't breathe",

        # Palpitations severe / Tim đập bất thường
        "tim đập quá nhanh không dừng", "tim đập loạn nhịp",
        "đánh trống ngực dữ dội đột ngột",
    ],
    "neurological": [
        # Stroke symptoms / Triệu chứng đột quỵ
        "liệt một bên tay", "liệt một bên chân", "liệt một bên mặt",
        "méo miệng đột ngột", "mặt xệ một bên",
        "nói không ra tiếng đột ngột", "không nói được",
        "không hiểu người khác nói đột ngột",
        "đột ngột mù một mắt", "nhìn đôi đột ngột",
        "đi loạng choạng đột ngột không rõ nguyên nhân",

        # Loss of consciousness / Mất ý thức
        "ngất xỉu", "bất tỉnh", "mất ý thức", "không tỉnh lại được",
        "lú lẫn đột ngột", "không biết đang ở đâu",
        "co giật", "động kinh",
        "syncope", "loss of consciousness", "unresponsive",
    ],
    "metabolic_critical": [
        # Extreme glucose / Đường huyết cực đoan
        "đường huyết trên 22 mmol", "đường huyết trên 400 mg",
        "glucose trên 400", "đường huyết 400",
        "đường huyết dưới 2.8", "đường huyết dưới 50",
        "hạ đường huyết nặng", "run rẩy không kiểm soát được",

        # DKA symptoms
        "nôn nhiều không dừng được", "thở nhanh sâu",
        "hơi thở có mùi ngọt", "đau bụng dữ dội kèm nôn",
    ],
    "bleeding_trauma": [
        "nôn ra máu", "ói máu",
        "đi cầu ra máu đỏ tươi nhiều",
        "ho ra máu nhiều",
        "chảy máu không cầm được",
        "tai nạn nghiêm trọng",
    ],
    "severe_allergic": [
        "sưng môi đột ngột", "sưng lưỡi", "sưng họng",
        "khó nuốt đột ngột sau khi ăn hoặc uống thuốc",
        "nổi mề đay toàn thân kèm khó thở",
        "phản ứng dị ứng nặng", "sốc phản vệ",
        "anaphylaxis",
    ],
    "mental_health_emergency": [
        # Self-harm / Tự hại
        "muốn tự làm hại bản thân", "muốn chết", "không muốn sống nữa",
        "có kế hoạch tự tử", "đang nghĩ đến việc tự tử",
        "tự làm đau mình", "self-harm", "suicidal",
        "không còn lý do để sống",
    ]
}

RED_FLAGS_EMERGENCY_FLAT = [
    phrase
    for group in RED_FLAGS_EMERGENCY.values()
    for phrase in group
]
```

### 3.2 Urgent Red Flags (Tier 3)

```python
RED_FLAGS_URGENT = {
    "metabolic_concerning": [
        "đường huyết trên 16 mmol", "đường huyết trên 300 mg",
        "glucose 300", "HbA1c > 10%",
        "huyết áp trên 180/110",
        "huyết áp rất cao",
    ],
    "symptoms_concerning": [
        # Fever / Sốt
        "sốt cao trên 39 độ liên tục 2 ngày",
        "sốt không hạ với thuốc hạ sốt",

        # Vision / Mắt
        "mờ mắt đột ngột", "nhìn mờ đột ngột",
        "nhìn thấy vầng hào quang",
        "mất thị lực một phần",

        # Swelling / Phù
        "sưng phù chân đột ngột", "phù mặt đột ngột",
        "tăng cân 2-3 kg trong 1-2 ngày không rõ nguyên nhân",

        # Pain / Đau
        "đau đầu dữ dội nhất từ trước đến nay",
        "đau bụng vùng thắt lưng dữ dội",

        # Urinary / Tiết niệu
        "tiểu máu", "nước tiểu đỏ",
        "không tiểu được vài tiếng",

        # Others
        "vàng da vàng mắt đột ngột",
        "da nổi ban đỏ lan rộng",
        "sưng đỏ nóng tại vết thương",
    ],
    "lab_urgent": [
        # Values triggering urgent (from escalation_thresholds in 14_CLINICAL_REASONING.md)
        "potassium_above_6",
        "creatinine_above_4",
        "hemoglobin_below_7",
    ],
    "medication_concerns": [
        "uống nhầm thuốc", "uống quá liều thuốc",
        "nghi ngờ ngộ độc thuốc",
        "phản ứng thuốc mới bắt đầu",
    ]
}
```

### 3.3 Yellow Flags (Tier 2 — Monitor & Recommend Check-up)

```python
YELLOW_FLAGS = {
    "persistent_symptoms": [
        "mệt mỏi kéo dài hơn 2 tuần không rõ nguyên nhân",
        "sụt cân không cố ý hơn 5kg trong 3 tháng",
        "đổ mồ hôi đêm kéo dài",
        "chán ăn kéo dài 2 tuần",
        "ho kéo dài hơn 3 tuần",
        "sốt nhẹ kéo dài (37.5–38.5°C) hơn 1 tuần",
    ],
    "pain_atypical": [
        "đau không điển hình khó tả vị trí",
        "đau tái phát nhiều lần không rõ nguyên nhân",
        "đau ngực không dữ dội nhưng kéo dài",
    ],
    "lab_borderline": [
        # From CRL output: BORDERLINE status for key analytes
        "HbA1c_borderline",        # 5.7-6.4% nếu chưa có chẩn đoán
        "glucose_borderline",
        "creatinine_borderline",
        "TSH_borderline",
        "hemoglobin_borderline",
    ],
    "trend_concerning": [
        # CRL flags: WORSENING trend for 3+ consecutive measurements
        "worsening_trend_3_consecutive",
    ]
}
```

### 3.4 Green Scenarios (Tier 1 — Continue Support)

```python
GREEN_SCENARIOS = [
    "lab_values_normal_and_stable",
    "asking_general_health_questions",
    "medication_adherence_reminders",
    "lifestyle_guidance_request",
    "lab_interpretation_in_normal_range",
    "care_plan_task_completion_help",
    "nutrition_question_no_red_flags",
    "exercise_question_no_red_flags",
    "medication_information_request_general",
    "appointment_preparation_questions",
    "health_goal_tracking_discussion",
    "previous_appointment_followup_in_normal_range",
]
```

---

## 4. Escalation Matrix

```python
ESCALATION_MATRIX = {
    # Format: (category, condition) → EscalationLevel

    # GLUCOSE
    ("glucose", "critical_high_above_400"): EscalationLevel.EMERGENCY,
    ("glucose", "critical_low_below_50"): EscalationLevel.EMERGENCY,
    ("glucose", "high_300_to_400"): EscalationLevel.URGENT,
    ("glucose", "high_250_to_300"): EscalationLevel.URGENT,
    ("glucose", "high_126_to_250"): EscalationLevel.RECOMMEND_CHECKUP,
    ("glucose", "prediabetes_range"): EscalationLevel.RECOMMEND_CHECKUP,
    ("glucose", "normal"): EscalationLevel.CONTINUE_SUPPORT,

    # BLOOD PRESSURE
    ("blood_pressure", "hypertensive_crisis_180_plus"): EscalationLevel.EMERGENCY,
    ("blood_pressure", "stage2_hypertension_160_179"): EscalationLevel.URGENT,
    ("blood_pressure", "stage1_hypertension_140_159"): EscalationLevel.RECOMMEND_CHECKUP,
    ("blood_pressure", "elevated_130_139"): EscalationLevel.CONTINUE_SUPPORT,
    ("blood_pressure", "normal"): EscalationLevel.CONTINUE_SUPPORT,
    ("blood_pressure", "hypotension_below_90"): EscalationLevel.URGENT,

    # HbA1c
    ("HbA1c", "above_10"): EscalationLevel.EMERGENCY,
    ("HbA1c", "8_to_10"): EscalationLevel.URGENT,
    ("HbA1c", "7_to_8"): EscalationLevel.RECOMMEND_CHECKUP,
    ("HbA1c", "below_7_diabetic"): EscalationLevel.CONTINUE_SUPPORT,
    ("HbA1c", "normal_nondiabetic"): EscalationLevel.CONTINUE_SUPPORT,

    # SPO2
    ("spo2", "below_90"): EscalationLevel.EMERGENCY,
    ("spo2", "90_to_93"): EscalationLevel.URGENT,
    ("spo2", "94_and_above"): EscalationLevel.CONTINUE_SUPPORT,

    # CREATININE
    ("creatinine", "above_4"): EscalationLevel.EMERGENCY,
    ("creatinine", "2_to_4"): EscalationLevel.URGENT,
    ("creatinine", "1.5_to_2"): EscalationLevel.RECOMMEND_CHECKUP,
    ("creatinine", "normal"): EscalationLevel.CONTINUE_SUPPORT,

    # POTASSIUM
    ("potassium", "above_6"): EscalationLevel.EMERGENCY,
    ("potassium", "5.5_to_6"): EscalationLevel.URGENT,
    ("potassium", "5_to_5.5"): EscalationLevel.RECOMMEND_CHECKUP,
    ("potassium", "below_3"): EscalationLevel.URGENT,
    ("potassium", "3_to_3.5"): EscalationLevel.RECOMMEND_CHECKUP,
    ("potassium", "normal"): EscalationLevel.CONTINUE_SUPPORT,

    # HEMOGLOBIN
    ("hemoglobin", "below_7"): EscalationLevel.URGENT,
    ("hemoglobin", "7_to_9"): EscalationLevel.RECOMMEND_CHECKUP,
    ("hemoglobin", "normal"): EscalationLevel.CONTINUE_SUPPORT,

    # SYMPTOMS
    ("symptom", "chest_pain"): EscalationLevel.EMERGENCY,
    ("symptom", "dyspnea_acute"): EscalationLevel.EMERGENCY,
    ("symptom", "loss_of_consciousness"): EscalationLevel.EMERGENCY,
    ("symptom", "sudden_weakness_one_side"): EscalationLevel.EMERGENCY,
    ("symptom", "suicidal_ideation"): EscalationLevel.EMERGENCY,
    ("symptom", "fever_above_39_persistent"): EscalationLevel.URGENT,
    ("symptom", "sudden_vision_change"): EscalationLevel.URGENT,
    ("symptom", "sudden_edema"): EscalationLevel.URGENT,
    ("symptom", "fatigue_unexplained_2weeks"): EscalationLevel.RECOMMEND_CHECKUP,
    ("symptom", "unexplained_weight_loss"): EscalationLevel.RECOMMEND_CHECKUP,
    ("symptom", "atypical_pain_recurrent"): EscalationLevel.RECOMMEND_CHECKUP,
}

async def determine_escalation_level(
    observation: ObservationSet,
    reported_symptoms: list[str],
    trend_analyses: list[TrendAnalysis],
    user_profile: dict
) -> EscalationResult:

    max_level = EscalationLevel.CONTINUE_SUPPORT

    # Check all labs against matrix
    for lab in observation.labs:
        lab_level = _lookup_lab_in_matrix(lab)
        if _severity(lab_level) > _severity(max_level):
            max_level = lab_level

    # Check symptoms
    for symptom in reported_symptoms:
        sym_level = _check_symptom_red_flags(symptom)
        if _severity(sym_level) > _severity(max_level):
            max_level = sym_level

    # Check trends
    for trend in trend_analyses:
        if (trend.direction == TrendDirection.WORSENING and
            trend.n_points >= 3 and
            max_level == EscalationLevel.CONTINUE_SUPPORT):
            max_level = EscalationLevel.RECOMMEND_CHECKUP

    return EscalationResult(
        level=max_level,
        triggers=[...],  # What triggered this level
        recommended_action=TIER_METADATA[max_level]
    )
```

---

## 5. Emergency Wording

### 5.1 Emergency Response Templates (Tier 4)

```python
EMERGENCY_TEMPLATES = {
    "default_emergency": """
⚠️ **{preferred_address} cần được hỗ trợ y tế NGAY LẬP TỨC**

Những gì Meto nhận ra cho thấy đây có thể là tình trạng khẩn cấp.

**Làm ngay bây giờ:**
🔴 Gọi **115** (cấp cứu) hoặc **113** (công an hỗ trợ cấp cứu)
🏥 Hoặc nhờ người đưa đến phòng cấp cứu gần nhất ngay

**Nếu {preferred_address} đang một mình:**
- Gọi cho người thân trước khi gọi 115
- Mở cửa để nhân viên cấp cứu có thể vào
- Ngồi hoặc nằm xuống, không đứng

Meto không có khả năng đánh giá tình trạng khẩn cấp — {preferred_address} cần sự hỗ trợ từ bác sĩ thực sự ngay lúc này.
""",

    "chest_pain_emergency": """
⚠️ **Đau ngực cần được đánh giá NGAY**

Đau ngực có thể có nhiều nguyên nhân, và một số trong đó cần điều trị khẩn cấp.

**Hãy làm ngay:**
🔴 Gọi **115** hoặc đến phòng cấp cứu gần nhất
❌ Không tự lái xe
❌ Không chờ xem có tự hết không

Trong khi chờ cấp cứu: ngồi hoặc nằm xuống, giữ bình tĩnh, gọi cho người thân.

Meto không thể đánh giá đau ngực qua chat — {preferred_address} cần bác sĩ đánh giá trực tiếp ngay.
""",

    "stroke_symptoms_emergency": """
⚠️ **{preferred_address} mô tả các dấu hiệu cần khám NGAY**

Liệt tay/chân đột ngột, méo miệng, hoặc không nói được là những dấu hiệu cần đánh giá y tế khẩn.

**Gọi 115 NGAY BÂY GIỜ**

Thời gian rất quan trọng trong các tình huống như thế này.
Meto không thể đánh giá qua chat — hãy gọi cấp cứu ngay.
""",

    "severe_hypoglycemia": """
⚠️ **Đường huyết rất thấp cần xử lý NGAY**

Nếu {preferred_address} còn tỉnh táo và có thể nuốt được:
- Uống 150ml nước ngọt (Coca-Cola, nước cam, hoặc nước đường)
- Hoặc ăn 15g đường (3-4 viên đường)
- Sau 15 phút, kiểm tra lại

**Nếu {preferred_address} đang lú lẫn hoặc không thể nuốt:**
🔴 Gọi **115** ngay — không cho ăn hoặc uống

Đây là thông tin sơ cứu chung. Sau khi ổn định, báo ngay cho bác sĩ.
""",

    "critical_glucose_high": """
⚠️ **Đường huyết ở mức rất cao**

Đường huyết {glucose_value} {unit} cần được đánh giá y tế.

**Hãy làm ngay:**
📞 Gọi cho bác sĩ của {preferred_address} NGAY HÔM NAY
🏥 Nếu không liên hệ được — đến phòng cấp cứu hoặc phòng khám khẩn

Trong khi chờ: uống nhiều nước (nếu không có hạn chế dịch), nghỉ ngơi.
Không tự ý điều chỉnh thuốc.

Meto không thể xử lý tình trạng này qua chat. Cần bác sĩ đánh giá trực tiếp.
""",

    "suicidal_ideation": """
Meto nghe thấy {preferred_address} và điều đó rất quan trọng.

Khi cảm thấy như vậy, điều cần nhất là được nói chuyện với người có thể thực sự giúp.

📞 **Đường dây hỗ trợ tâm lý:**
- Bệnh viện Tâm thần Trung ương 1: **(024) 3825-7202**
- Đường dây hỗ trợ sức khỏe tâm thần Bộ Y tế: **1800 599 920** (miễn phí)

Nếu {preferred_address} đang trong nguy hiểm ngay lúc này: **Gọi 115**

Meto ở đây, nhưng chuyên gia tâm lý là người có thể giúp tốt nhất trong lúc này.
"""
}
```

### 5.2 Urgent Response Templates (Tier 3)

```python
URGENT_TEMPLATES = {
    "default_urgent": """
Meto thấy những gì {preferred_address} chia sẻ cần được bác sĩ đánh giá sớm.

**Việc nên làm trong hôm nay hoặc sáng mai:**
📅 Liên hệ {doctor_name_or_your_doctor} để đặt lịch khám
🏥 Nếu không liên hệ được, đến phòng khám hoặc bệnh viện gần nhất

Trong khi chờ: giữ nguyên thuốc đang dùng, theo dõi triệu chứng.

Đây là thông tin để {preferred_address} có cuộc trò chuyện với bác sĩ — không phải để tự xử lý.
""",

    "lab_urgent": """
Kết quả {analyte} = {value} {unit} của {preferred_address} cần được bác sĩ xem trong thời gian sớm.

**Nên làm:**
- Liên hệ bác sĩ chăm sóc trong ngày hôm nay
- Nếu bác sĩ đặt lịch tái khám, nên đến đúng hẹn
- Tiếp tục thuốc đang dùng (không tự thay đổi)

Meto có thể giải thích ý nghĩa chung của {analyte}, nhưng bác sĩ mới có thể đánh giá đầy đủ với bối cảnh của {preferred_address}.
""",

    "high_blood_pressure": """
Huyết áp {value} của {preferred_address} cao hơn ngưỡng cần theo dõi.

**Nên làm hôm nay:**
📞 Liên hệ bác sĩ hoặc đến phòng khám để được đo lại và đánh giá

Trong khi chờ: nghỉ ngơi, hạn chế muối, không tự điều chỉnh thuốc huyết áp.
Nếu {preferred_address} có đau đầu dữ dội, buồn nôn, hoặc mờ mắt — đây là dấu hiệu cần đến cấp cứu ngay.
""",

    "high_glucose_urgent": """
Đường huyết {value} mg/dL ({value_mmol} mmol/L) của {preferred_address} cao hơn ngưỡng cần theo dõi.

**Nên làm trong ngày hôm nay:**
- Uống nhiều nước (nếu không có hạn chế dịch)
- Không bỏ thuốc đang dùng
- Liên hệ bác sĩ {doctor_name_if_available} để được hướng dẫn

Nếu {preferred_address} cảm thấy buồn nôn nhiều, đau bụng, hoặc thở nhanh — đến cấp cứu ngay.
"""
}
```

### 5.3 Recommend Check-up Templates (Tier 2)

```python
CHECKUP_TEMPLATES = {
    "default_checkup": """
{preferred_address} ơi, những gì Meto thấy gợi ý nên chia sẻ với bác sĩ trong thời gian sắp tới.

**Không phải khẩn cấp**, nhưng đặt lịch khám trong 1–2 tuần là ý tưởng tốt để bác sĩ đánh giá thêm.

Meto có thể giúp {preferred_address} chuẩn bị danh sách câu hỏi cho buổi khám nếu muốn.
""",

    "borderline_lab": """
Kết quả {analyte} = {value} {unit} của {preferred_address} ở mức cần theo dõi thêm.

**Trong phạm vi "theo dõi"** — không phải nguy hiểm ngay, nhưng nên được bác sĩ xem xét lần khám tới.

{additional_context}

{preferred_address} có lịch khám sắp tới không? Muốn Meto nhắc nhở nhớ đề cập điều này với bác sĩ?
""",

    "worsening_trend": """
Meto nhận thấy {analyte} của {preferred_address} có xu hướng {direction} qua {n_points} lần đo.

Xu hướng này đáng để chia sẻ với bác sĩ tại lần khám tới để được đánh giá.

Có muốn Meto lưu lại nhắc nhở hỏi bác sĩ về điều này không?
""",

    "preventive": """
Dựa trên tuổi và hồ sơ sức khỏe của {preferred_address}, {screening_type} được khuyến nghị theo hướng dẫn.

**Không có gì đáng lo ngại ngay bây giờ** — đây chỉ là tầm soát phòng ngừa định kỳ.

Anh/chị có muốn Meto thêm nhắc nhở về lịch tầm soát này không?
"""
}
```

---

## 6. Urgency Scoring

### 6.1 Urgency Score 0–10

```python
class UrgencyScorer:
    """
    Urgency score 0–10 để prioritize và communicate.
    0 = Bình thường
    10 = Đe dọa tính mạng ngay lập tức
    """

    URGENCY_MAP = {
        # Score → Tier
        (0, 2): EscalationLevel.CONTINUE_SUPPORT,
        (3, 5): EscalationLevel.RECOMMEND_CHECKUP,
        (6, 7): EscalationLevel.URGENT,
        (8, 10): EscalationLevel.EMERGENCY,
    }

    URGENCY_DESCRIPTORS = {
        0: "Bình thường",
        1: "Theo dõi nhẹ",
        2: "Nên chú ý",
        3: "Khuyến nghị theo dõi",
        4: "Nên đặt lịch khám",
        5: "Đặt lịch khám sớm",
        6: "Cần khám trong 48 giờ",
        7: "Cần khám trong 24 giờ",
        8: "Cần khám hôm nay hoặc cấp cứu",
        9: "Cấp cứu — đến cơ sở y tế ngay",
        10: "Cấp cứu — gọi 115 ngay",
    }

    def compute(
        self,
        escalation_level: EscalationLevel,
        trend: TrendAnalysis | None,
        symptom_count: int,
        critical_lab_count: int,
        user_age: int
    ) -> float:

        base_scores = {
            EscalationLevel.CONTINUE_SUPPORT: 1.0,
            EscalationLevel.RECOMMEND_CHECKUP: 4.0,
            EscalationLevel.URGENT: 7.0,
            EscalationLevel.EMERGENCY: 9.5,
        }
        score = base_scores[escalation_level]

        # Modifiers
        if trend and trend.direction == TrendDirection.WORSENING:
            score += min(1.5, 0.5 * trend.n_points)

        score += min(1.0, symptom_count * 0.3)
        score += min(1.5, critical_lab_count * 0.5)

        # Age modifier (elderly → higher base urgency for same findings)
        if user_age >= 75:
            score += 0.5
        elif user_age >= 65:
            score += 0.3

        return min(10.0, round(score, 1))
```

---

## 7. Communication Templates — 20+ Situational Templates

```python
SITUATIONAL_TEMPLATES = {

    # 1. After lab result — normal
    "lab_normal_reassure": (
        "Kết quả {analyte} = {value} {unit} của {preferred_address} trong giới hạn bình thường. "
        "Điều này là tín hiệu tốt. Tiếp tục duy trì những thói quen tích cực nhé!"
    ),

    # 2. After lab result — borderline, first time
    "lab_borderline_first": (
        "Kết quả {analyte} = {value} {unit} hơi cao/thấp hơn ngưỡng bình thường một chút. "
        "Một lần kết quả như vậy không đủ kết luận — cần theo dõi lần sau. "
        "Tốt nhất là chia sẻ với bác sĩ tại lần khám tới để được tư vấn."
    ),

    # 3. After lab result — abnormal but stable trend
    "lab_abnormal_stable_trend": (
        "{analyte} = {value} {unit} — cao/thấp hơn ngưỡng tham chiếu, "
        "nhưng ổn định qua {n_readings} lần đo gần đây. "
        "Bác sĩ đang theo dõi điều này là phù hợp. "
        "Hãy tiếp tục tuân thủ kế hoạch điều trị và tái khám theo lịch."
    ),

    # 4. After lab result — worsening trend
    "lab_worsening_trend": (
        "{analyte} của {preferred_address} đang có xu hướng tăng/giảm qua {n_readings} lần đo. "
        "Xu hướng này đáng để thông báo cho bác sĩ sớm — "
        "không phải khẩn cấp, nhưng đừng để đến lần khám quá xa."
    ),

    # 5. Medication reminder — gentle
    "med_reminder_gentle": (
        "{preferred_address} ơi, đã đến giờ uống {med_name} chưa? "
        "Uống thuốc đều đặn giúp {med_benefit} hiệu quả hơn nhiều. 💊"
    ),

    # 6. Medication missed — non-judgmental
    "med_missed_nonjudgment": (
        "Meto thấy {med_name} hôm nay chưa được ghi nhận. "
        "Việc quên là bình thường — điều quan trọng là quay lại lịch đều đặn. "
        "Nếu có điều gì khiến việc nhớ uống thuốc khó khăn, Meto có thể giúp điều chỉnh nhắc nhở."
    ),

    # 7. Upcoming appointment prep
    "appointment_prep": (
        "Lịch khám với {doctor_name} vào {appointment_date} đang đến gần. "
        "Muốn Meto giúp chuẩn bị danh sách câu hỏi để tận dụng tốt buổi khám không? "
        "Có nhiều điều để hỏi hơn mình nghĩ đó! 📋"
    ),

    # 8. After appointment — follow-up
    "post_appointment_followup": (
        "Anh/chị đã khám với bác sĩ rồi đúng không? "
        "Meto muốn biết bác sĩ có dặn dò gì không để Meto hỗ trợ tốt hơn. "
        "Anh/chị muốn chia sẻ kết quả không?"
    ),

    # 9. Symptom reported — encourage tracking
    "symptom_track_encourage": (
        "Cảm ơn {preferred_address} đã chia sẻ. "
        "Việc ghi nhận triệu chứng như vậy rất hữu ích để bác sĩ đánh giá chính xác hơn. "
        "Nếu triệu chứng kéo dài hơn {days} ngày hoặc trở nặng, "
        "hãy liên hệ bác sĩ nhé."
    ),

    # 10. User worried about diagnosis
    "worried_about_diagnosis": (
        "Meto hiểu {preferred_address} đang lo lắng — điều đó rất bình thường. "
        "Tuy nhiên, Meto không có khả năng chẩn đoán qua chat. "
        "Chỉ bác sĩ mới có thể đánh giá đầy đủ sau khi thăm khám trực tiếp. "
        "Muốn Meto giúp chuẩn bị câu hỏi để hỏi bác sĩ không?"
    ),

    # 11. User asks about medication change
    "asked_med_change": (
        "Việc thay đổi liều thuốc là quyết định cần bác sĩ kê đơn trực tiếp — "
        "Meto không có đủ thông tin để gợi ý điều này. "
        "Nếu {preferred_address} có thắc mắc về thuốc, hãy hỏi {doctor_name_or_doctor} "
        "hoặc dược sĩ tại lần khám tới nhé."
    ),

    # 12. Escalation to urgent — complete template
    "escalate_to_urgent_full": (
        "Meto lo ngại về {concern_reason} của {preferred_address}.\n\n"
        "Đây không phải tình trạng khẩn cấp ngay, nhưng cần được bác sĩ đánh giá sớm — "
        "lý tưởng là trong ngày hôm nay hoặc sáng mai.\n\n"
        "**Nên làm:**\n"
        "📞 Liên hệ {doctor_name_or_your_doctor}\n"
        "🏥 Nếu không liên hệ được: đến phòng khám hoặc bệnh viện gần nhất\n\n"
        "Trong khi chờ: tiếp tục thuốc đang dùng, theo dõi triệu chứng.\n"
        "Nếu tình trạng trở nặng đột ngột → gọi 115."
    ),

    # 13. After escalation — Meto stays available
    "post_escalation_available": (
        "Meto vẫn ở đây nếu {preferred_address} cần hỗ trợ thêm. "
        "Chúc anh/chị gặp được bác sĩ sớm. Hãy cho Meto biết kết quả nhé! 🤗"
    ),

    # 14. Emergency — concise version
    "emergency_concise": (
        "⚠️ {preferred_address} cần hỗ trợ y tế NGAY.\n"
        "🔴 Gọi **115** hoặc đến cấp cứu gần nhất.\n"
        "Không chờ. Meto không đủ khả năng hỗ trợ tình trạng này qua chat."
    ),

    # 15. User refuses escalation
    "user_refuses_escalation": (
        "Meto tôn trọng quyết định của {preferred_address}. "
        "Nếu {preferred_address} thay đổi ý kiến hoặc tình trạng thay đổi, "
        "Meto luôn ở đây. Và hãy liên hệ bác sĩ sớm nhé."
    ),

    # 16. Drug concern — general
    "drug_concern_general": (
        "Meto nhận thấy anh/chị có thắc mắc về {drug_name}. "
        "Meto có thể chia sẻ thông tin chung về thuốc này, "
        "nhưng câu hỏi cụ thể về liều lượng hoặc tương tác cần dược sĩ hoặc bác sĩ trả lời nhé."
    ),

    # 17. Low adherence — empathetic follow-up
    "low_adherence_empathy": (
        "Meto thấy {preferred_address} đã bỏ lỡ một số liều gần đây. "
        "Đây là điều rất nhiều người gặp phải — không phải lý do để tự trách mình. "
        "Có điều gì khiến việc uống thuốc đều đặn trở nên khó khăn không? "
        "Có thể Meto giúp điều chỉnh nhắc nhở hoặc tìm giải pháp phù hợp hơn."
    ),

    # 18. Lab interpretation disclaim
    "lab_interpretation_disclaim": (
        "Những thông tin Meto vừa chia sẻ là giải thích tham khảo chung — "
        "không phải đánh giá lâm sàng cho {preferred_address} cụ thể. "
        "Bác sĩ sẽ đánh giá trong bối cảnh đầy đủ của anh/chị."
    ),

    # 19. New symptom — prompt for more info
    "new_symptom_prompt": (
        "{preferred_address} vừa nhắc đến {symptom}. "
        "Để Meto hiểu rõ hơn: "
        "Triệu chứng này bắt đầu từ khi nào? Có kèm theo dấu hiệu nào khác không? "
        "Mức độ như thế nào trên thang 1-10?"
    ),

    # 20. Positive reinforcement
    "positive_reinforcement": (
        "🎉 {preferred_address} đã hoàn thành {task_or_goal}! "
        "Mỗi bước nhỏ đều quan trọng trong hành trình chăm sóc sức khỏe. "
        "Tiếp tục nhé!"
    ),

    # 21. Care plan completion prompt
    "care_plan_next_step": (
        "Sau khi hoàn thành {completed_task}, bước tiếp theo trong kế hoạch của {preferred_address} là: "
        "**{next_task}**. "
        "Muốn Meto nhắc nhở vào lúc {suggested_time} không?"
    ),

    # 22. Cannot help — outside scope
    "outside_scope": (
        "Câu hỏi này vượt ngoài những gì Meto có thể giúp một cách có trách nhiệm. "
        "Bác sĩ hoặc chuyên gia y tế là người phù hợp nhất để trả lời điều này cho {preferred_address}."
    ),
}
```

---

## 8. Safety Wording Guidelines

### 8.1 Nguyên tắc giao tiếp an toàn

```python
SAFETY_WORDING_PRINCIPLES = {
    "do_not": [
        "Đừng nói 'Đừng lo' — lo lắng là cảm xúc hợp lệ, không nên gạt đi",
        "Đừng nói 'Chắc không sao đâu' — Meto không biết chắc",
        "Đừng nói 'Bình thường thôi' với triệu chứng chưa được đánh giá",
        "Đừng dùng ngôn ngữ cực đoan như 'Rất nghiêm trọng' khi không cần thiết",
        "Đừng phán xét thói quen hoặc lối sống của người dùng",
        "Đừng minimise (giảm nhẹ) lo lắng để trấn an — đây có thể gây mất tin cậy",
    ],
    "do_use": [
        "Dùng ngôn ngữ empathetic: 'Meto hiểu điều này đáng lo' ",
        "Dùng ngôn ngữ action-oriented: 'Điều có thể làm ngay là...'",
        "Dùng ngôn ngữ encouraging khi tình huống ổn: 'Đây là dấu hiệu tốt'",
        "Thêm context khi escalate: giải thích TẠI SAO cần gặp bác sĩ, không chỉ 'hãy đi'",
        "Để lại không gian cho người dùng: 'Có câu hỏi gì thêm không?'",
        "Normalize fear: 'Điều này có thể khiến anh/chị lo lắng, và điều đó là bình thường'",
    ],
    "emergency_wording_rules": [
        "Emergency templates: ngắn gọn, rõ ràng, không quá nhiều thông tin",
        "Số điện thoại 115 phải xuất hiện trong mọi emergency response",
        "Không dùng thuật ngữ y tế trong emergency — đơn giản nhất có thể",
        "Sau emergency message: không thêm thông tin y tế thêm — focus vào hành động",
    ]
}
```

### 8.2 Anti-panic Phrasing

```python
ANTI_PANIC_PHRASES = {
    "instead_of_alarming": {
        "Kết quả rất nguy hiểm": "Kết quả này cần được bác sĩ đánh giá sớm",
        "Anh/chị có thể bị bệnh nặng": "Có một số dấu hiệu bác sĩ cần xem xét thêm",
        "Đây là dấu hiệu xấu": "Kết quả này đáng để theo dõi cùng bác sĩ",
        "Cần đi cấp cứu ngay" [tier3]: "Nên gặp bác sĩ trong ngày hôm nay",
        "Đây là triệu chứng nguy hiểm": "Triệu chứng này cần được bác sĩ đánh giá",
    }
}
```

---

## 9. Post-Escalation Follow-Up

### 9.1 Follow-up Schedule

```python
@dataclass
class PostEscalationFollowUp:
    escalation_id: str
    user_id: str
    escalation_level: EscalationLevel
    escalated_at: datetime
    follow_up_schedule: list[FollowUpCheckIn]

@dataclass
class FollowUpCheckIn:
    check_in_at: datetime
    message: str
    completed: bool = False
    user_response: str | None = None

FOLLOW_UP_SCHEDULES = {
    EscalationLevel.EMERGENCY: [
        # Emergency: no follow-up scheduled (user should be in care)
        # But if user comes back, Meto checks in
    ],
    EscalationLevel.URGENT: [
        FollowUpCheckIn(
            check_in_at=timedelta(hours=24),
            message=(
                "{preferred_address} ơi, hôm qua Meto có chia sẻ điều quan trọng. "
                "Anh/chị đã có cơ hội liên hệ bác sĩ chưa? 🤗"
            )
        ),
        FollowUpCheckIn(
            check_in_at=timedelta(hours=48),
            message=(
                "Meto muốn hỏi thăm — anh/chị đã đi khám chưa? "
                "Nếu chưa, hôm nay vẫn là thời điểm tốt để liên hệ bác sĩ."
            )
        ),
    ],
    EscalationLevel.RECOMMEND_CHECKUP: [
        FollowUpCheckIn(
            check_in_at=timedelta(days=7),
            message=(
                "Meto nhớ tuần trước có gợi ý {preferred_address} đặt lịch khám. "
                "Anh/chị đã lên lịch chưa? Có cần Meto nhắc nhở gì thêm không?"
            )
        ),
    ],
}
```

### 9.2 Follow-up Logic

```python
class PostEscalationManager:

    async def schedule_followup(
        self,
        escalation: EscalationAuditEntry,
        user_id: str
    ):
        schedule = FOLLOW_UP_SCHEDULES.get(escalation.level, [])
        for check_in in schedule:
            await db.insert("escalation_followups", {
                "escalation_id": escalation.id,
                "user_id": user_id,
                "scheduled_at": utcnow() + check_in.check_in_at,
                "message_template": check_in.message,
                "completed": False,
            })

    async def process_pending_followups(self):
        """Run by background job every 30 minutes"""
        pending = await db.fetch("""
            SELECT * FROM escalation_followups
            WHERE scheduled_at <= NOW()
              AND completed = FALSE
        """)

        for followup in pending:
            # Only send if user has active session or notification preference
            user_pref = await get_user_notification_pref(followup.user_id)
            if user_pref.get("followup_reminders_enabled", True):
                await notification_service.send(
                    user_id=followup.user_id,
                    message=self._format_followup_message(followup),
                    channel="push_or_chat"
                )
                await db.execute(
                    "UPDATE escalation_followups SET completed = TRUE WHERE id = :id",
                    {"id": followup.id}
                )
```

---

## 10. Audit Requirements

### 10.1 Escalation Audit Log

```python
@dataclass
class EscalationAuditEntry:
    id: str                            # UUID
    user_id: str
    session_id: str
    escalation_level: EscalationLevel
    urgency_score: float               # 0-10
    triggered_by: list[str]           # ["lab:glucose:critical", "symptom:chest_pain"]
    trigger_evidence: str             # Hash of evidence (no raw values in log)
    template_used: str                 # Template name
    response_delivered_at: datetime
    follow_up_scheduled: bool
    user_acknowledged: bool            # Did user respond?
    user_response_action: str | None   # "called_doctor" | "ignored" | "went_to_er" etc.
    provider_used: str
    created_at: datetime

# NOT logged:
# - Raw lab values (in lab_results table)
# - Full message content
# - User's personal conversation
```

### 10.2 Audit Retention

```
Emergency escalations: 5 năm (medical safety requirement)
Urgent escalations: 2 năm
Recommend check-up: 1 năm
Audit log (all tiers): minimum 2 năm
```

---

## 11. Decision Trees — Per Symptom Category

### 11.1 Chest Pain Decision Tree

```
User reports: "Đau ngực" / "Tức ngực"
        │
        ▼
[Is it severe, crushing, radiating to arm/jaw?]
        │
        ├── YES ─────────────────────────────▶ EMERGENCY (Template: chest_pain_emergency)
        │
        ├── User says mild, positional
        │        │
        │        ▼
        │   [Any associated symptoms? (shortness of breath, sweating, nausea)]
        │        │
        │        ├── YES ──────────────────────▶ EMERGENCY
        │        │
        │        └── NO ───────────────────────▶ URGENT
        │                                        "Vẫn cần bác sĩ đánh giá đau ngực"
        │
        └── User cannot describe clearly
                 │
                 ▼
           URGENT — "Đau ngực bất kỳ loại nào nên được bác sĩ đánh giá"
```

### 11.2 Glucose Out of Range Decision Tree

```
Glucose value received
        │
        ▼
[Value < 2.8 mmol/L (50 mg/dL)?]
        │
        ├── YES ─────────────────────────────▶ EMERGENCY (Template: severe_hypoglycemia)
        │
        ▼
[Value > 22.2 mmol/L (400 mg/dL)?]
        │
        ├── YES ─────────────────────────────▶ EMERGENCY (Template: critical_glucose_high)
        │
        ▼
[Value 16-22 mmol/L (300-400 mg/dL)?]
        │
        ├── YES ─────────────────────────────▶ URGENT (Template: high_glucose_urgent)
        │                                      Check: symptoms of DKA?
        │
        ▼
[Value 7-16 mmol/L (126-300 mg/dL)?]
        │
        ├── YES ─────────────────────────────▶ RECOMMEND_CHECKUP or URGENT
        │                                      Depends on: trend, symptoms, context
        │
        ▼
[Value 5.6-6.9 mmol/L (100-125 mg/dL)]
        │
        └─────────────────────────────────────▶ CONTINUE_SUPPORT
                                               (Explain prediabetes range if applicable)
```

### 11.3 Blood Pressure Decision Tree

```
BP value received
        │
        ▼
[Systolic ≥ 180 mmHg?]
        │
        ├── YES + symptoms (headache, vision change, chest pain) ──▶ EMERGENCY
        ├── YES, no symptoms ──────────────────────────────────────▶ URGENT
        │
        ▼
[Systolic 160-179?]
        │
        ├── YES, symptomatic ──────────────────────────────────────▶ URGENT
        ├── YES, asymptomatic ─────────────────────────────────────▶ RECOMMEND_CHECKUP
        │
        ▼
[Systolic 140-159?]
        │
        └── Any ──────────────────────────────────────────────────▶ RECOMMEND_CHECKUP
                                                                    "Liên hệ bác sĩ sớm"
```

---

## 12. Absolute Rules (KHÔNG ĐƯỢC vi phạm)

```python
ABSOLUTE_DHE_RULES = [
    # Rule 1: Emergency response must always include 115
    "Every EMERGENCY response includes phone number 115",

    # Rule 2: Never tell user "you don't need a doctor"
    "Never output 'không cần đi khám' in any form",

    # Rule 3: Never diagnose in escalation response
    "Escalation messages never include diagnosis",

    # Rule 4: No prescription advice in escalation
    "Never advise medication changes during escalation",

    # Rule 5: Suicidal ideation always emergency
    "Any self-harm intent → ALWAYS EMERGENCY, no other path",

    # Rule 6: User override accepted but documented
    "If user refuses escalation → acknowledge, document, keep available",

    # Rule 7: Post-escalation always offer continued support
    "After every escalation, offer continued Meto support",

    # Rule 8: Emergency response is final for that turn
    "EMERGENCY response → no additional health content in same turn",
]
```

---

## 13. Acceptance Criteria

### AC-DHE-001: Tier Detection
- [ ] All Emergency red flags trigger Tier 4 response within 1 response turn
- [ ] Glucose > 400 mg/dL → Emergency response (code-level, no AI)
- [ ] Systolic BP ≥ 180 with symptoms → Emergency response
- [ ] Suicidal ideation keywords → Emergency response immediately

### AC-DHE-002: Emergency Response Quality
- [ ] All emergency responses contain 115 phone number
- [ ] Emergency responses are ≤ 150 words
- [ ] Emergency responses do not contain medical diagnosis
- [ ] Anti-panic language principles applied

### AC-DHE-003: Tier 2 & 3 Responses
- [ ] URGENT: response includes "hôm nay" or "24-48 giờ" timeframe
- [ ] RECOMMEND_CHECKUP: response includes "trong 1-7 ngày" or similar
- [ ] All non-emergency templates non-judgmental and empathetic

### AC-DHE-004: Follow-up
- [ ] URGENT escalation schedules follow-up at 24h and 48h
- [ ] RECOMMEND_CHECKUP escalation schedules follow-up at 7 days
- [ ] Follow-up only sent if user notification preferences allow

### AC-DHE-005: Audit
- [ ] Every escalation creates audit entry
- [ ] Escalation audit stored for minimum 2 years (5 years for emergency)
- [ ] Follow-up outcomes captured in audit

### AC-DHE-006: Absolute Rules
- [ ] "không cần đi khám" never appears in any Meto output (automated test)
- [ ] Emergency response always includes 115 (automated test)
- [ ] Suicidal ideation always triggers mental health emergency response (automated test)

---

*Xem thêm: 14_CLINICAL_REASONING.md (escalation thresholds từ CRL), 04_SAFETY_PRIVACY.md (red flag detection từ user message), 15_RECOMMENDATION_ENGINE.md (recommendations hold back when escalation active)*
