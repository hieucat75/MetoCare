# Meto AI — Recommendation Engine

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved
> **Phase:** 3 — Clinical Intelligence

---

## Tổng quan

Recommendation Engine (RE) là hệ thống sinh khuyến nghị cá nhân hóa, an toàn của Meto. RE nhận đầu vào từ Clinical Reasoning Layer (CRL) và nhiều nguồn context khác, sau đó tạo ra các khuyến nghị phù hợp về lifestyle, adherence, và chăm sóc sức khỏe — **trong phạm vi hoàn toàn phi lâm sàng**.

**Ranh giới tuyệt đối:** RE không prescribe thuốc, không thay đổi liều, không chẩn đoán bệnh.

**File backend:**
- `app/ai/recommendation_engine.py` — Core engine
- `app/ai/recommendations/` — Per-category recommendation handlers
- `app/ai/recommendation_engine/trigger.py` — Trigger detection
- `app/ai/recommendation_engine/priority_queue.py` — Priority & deduplication
- `app/models/recommendation.py` — DB models

---

## 1. Kiến trúc Recommendation Engine

```
┌──────────────────────────────────────────────────────────────────────┐
│                    RECOMMENDATION ENGINE                              │
│                                                                      │
│  INPUTS                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │CRL Output│ │Context   │ │Memory    │ │Care Plan │ │User      │ │
│  │          │ │Blocks    │ │Engine    │ │Tasks     │ │Feedback  │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ │
│       └─────────────┴────────────┴─────────────┴─────────────┘      │
│                                 │                                    │
│                                 ▼                                    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  TRIGGER DETECTOR                                             │  │
│  │  Scans all inputs for recommendation triggers                 │  │
│  │  Output: list[Trigger] with type, evidence, priority         │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                 │                                    │
│                                 ▼                                    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  RECOMMENDATION BUILDER (per category)                        │  │
│  │  For each trigger → build RecommendationCandidate            │  │
│  │  Includes: context_assembly, personalization, contracheck     │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                 │                                    │
│                                 ▼                                    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  PRIORITY QUEUE                                               │  │
│  │  Sort by: urgency × relevance × user_feedback_history        │  │
│  │  Deduplication: suppress if same rec shown < 24h ago         │  │
│  │  Staleness check: discard if trigger context is stale        │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                 │                                    │
│                                 ▼                                    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  DELIVERY ROUTER                                              │  │
│  │  Routes to: chat_message | push_notification | care_plan     │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                 │                                    │
│                                 ▼                                    │
│  OUTPUTS: Delivered recommendations + Audit log + Feedback capture  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Models

```python
@dataclass
class RecommendationCandidate:
    id: str                            # UUID
    category: RecommendationCategory
    trigger_type: str
    trigger_evidence: dict             # What data triggered this

    # Content
    headline: str                      # Short title (≤80 chars)
    body: str                          # Full recommendation text
    actionable_steps: list[str]        # 1-3 concrete steps
    rationale: str                     # Why Meto is suggesting this (for audit)

    # Metadata
    priority: float                    # 0.0-1.0 (computed by priority queue)
    urgency: str                       # "now" | "today" | "this_week" | "routine"
    confidence: float                  # 0-100
    expiration_at: datetime            # When recommendation becomes stale
    delivery_channel: DeliveryChannel
    contraindications_checked: bool = False
    personalization_applied: bool = False

    # Consent & audit
    requires_consent_type: str | None  # Which consent block needed
    audit_id: str                      # Links to recommendation_audit_log

@dataclass
class RecommendationFeedback:
    recommendation_id: str
    user_id: str
    action: FeedbackAction             # ACTED_ON | DISMISSED | SNOOZED | HELPFUL | NOT_HELPFUL
    timestamp: datetime
    snooze_until: datetime | None

class RecommendationCategory(str, Enum):
    MEDICATION_ADHERENCE = "medication_adherence"
    NUTRITION = "nutrition"
    EXERCISE = "exercise"
    SLEEP = "sleep"
    STRESS = "stress"
    HYDRATION = "hydration"
    FOLLOW_UP = "follow_up"
    PREVENTIVE_SCREENING = "preventive_screening"
    VACCINATION = "vaccination"
    LIFESTYLE = "lifestyle"
    CARE_PLAN = "care_plan"
    REMINDER_OPTIMIZATION = "reminder_optimization"
```

---

## 3. Nhóm 1: Medication Adherence

### Trigger Detection
```python
MEDICATION_ADHERENCE_TRIGGERS = [
    # Trigger 1: Missed dose pattern
    {
        "trigger_id": "med_skip_pattern",
        "condition": "medication.adherence_last_7d < 0.8",
        "description": "Adherence rate below 80% in last 7 days",
        "priority": 0.8,
    },
    # Trigger 2: Upcoming dose
    {
        "trigger_id": "upcoming_dose",
        "condition": "next_dose_time within 30 minutes",
        "description": "Medication due soon",
        "priority": 0.9,
    },
    # Trigger 3: Skip detected today
    {
        "trigger_id": "skip_detected_today",
        "condition": "missed_medications_today is not empty",
        "description": "At least one dose missed today",
        "priority": 0.85,
    },
    # Trigger 4: Chronic low adherence
    {
        "trigger_id": "chronic_low_adherence",
        "condition": "average_adherence_30d < 0.7",
        "description": "Sustained low adherence over 30 days",
        "priority": 0.7,
    }
]
```

### Recommendation Spec
```
CATEGORY: medication_adherence

TRIGGER: missed_dose or skip_pattern
REQUIRED_CONTEXT: active_medications, today_context
PERSONALIZATION:
  - Preferred timing from Memory Engine (MemoryCategory.PREFERENCE)
  - User's skip pattern (morning vs evening)
  - Which specific medications missed
CONTRAINDICATIONS:
  - Không suggest để bù liều đã bỏ lỡ (drug-specific — defer to doctor)
  - Không nói "uống 2 viên để bù" — đây là y tế
CONFIDENCE_THRESHOLD: 70 (direct data from medication_logs)
EXPLANATION_FORMAT: empathetic, non-judgmental, practical
PRIORITY: urgent if high-risk medication (insulin, anticoagulant), medium otherwise
EXPIRATION: 4 hours from trigger
AUDIT: log medication_name, adherence_rate, trigger_type

TEMPLATES:
"Meto thấy {med_name} buổi {time_of_day} hôm nay chưa được ghi nhận.
Đây là thuốc quan trọng trong kế hoạch của anh/chị.
Nếu anh/chị chưa uống, đây là thời điểm phù hợp. 💊"

"Trong 7 ngày qua, anh/chị đã uống {med_name} được {adherence_pct}%.
Việc uống thuốc đều đặn giúp {med_benefit_simple}. 
Có điều gì khiến việc nhớ uống thuốc khó khăn không?"

CONSENT_REQUIRED: medications_granted
UX_FLOW: inline chat suggestion + optional "Tạo nhắc nhở" quick action
```

---

## 4. Nhóm 2: Nutrition

### Recommendation Spec
```
CATEGORY: nutrition

TRIGGERS:
  - User has diabetes AND no nutrition log for 3+ days
  - HbA1c trending up (from CRL)
  - BMI flag in health profile
  - User asks about food/eating

REQUIRED_CONTEXT: health_summary, recent_labs, recent_metrics
PERSONALIZATION:
  - Primary conditions → food group guidance
    - diabetes_type2 → low-GI foods emphasis
    - hypertension → low-sodium emphasis
    - dyslipidemia → heart-healthy fats
    - renal_failure → low-potassium, low-phosphorus (defer specifics to dietitian)
  - User's known preferences from Memory Engine
  - VN cultural food context (cơm, phở, bún, etc.)
CONTRAINDICATIONS:
  - Không tạo specific meal plan (cần dietitian)
  - Không nói "tránh hoàn toàn" — chỉ "hạn chế" hoặc "ưu tiên"
  - Không đưa ra carb counting target (cần doctor)
  - Renal patients → chỉ general guidance, defer specifics immediately
CONFIDENCE_THRESHOLD: 60
EXPLANATION_FORMAT: practical, VN food examples, gentle not preachy
PRIORITY: routine unless CRL flags nutrition-related lab changes
EXPIRATION: 24 hours
AUDIT: conditions_considered, trigger_type

TEMPLATES:
"Với tiểu đường type 2, ưu tiên thực phẩm có chỉ số đường huyết thấp như
gạo lứt, rau xanh, đậu, và protein nạc. Cơm trắng nên ăn lượng vừa phải.
Bác sĩ hoặc chuyên gia dinh dưỡng có thể tư vấn kế hoạch cụ thể hơn cho anh/chị."

"Với tăng huyết áp, hạn chế thực phẩm nhiều muối như mắm, nước tương đậm,
thức ăn chế biến sẵn. Rau xanh và trái cây giàu kali (chuối, cam) rất tốt
— trừ khi bác sĩ có chỉ định riêng do chức năng thận."

CONSENT_REQUIRED: health_summary_granted
UX_FLOW: chat message, can follow up with specific food question
```

---

## 5. Nhóm 3: Exercise

### Recommendation Spec
```
CATEGORY: exercise

TRIGGERS:
  - User has condition benefiting from physical activity
  - Metrics show sedentary pattern (step count, activity from wearable)
  - User asks about exercise
  - Post-lab result where physical activity is relevant

REQUIRED_CONTEXT: health_summary, recent_metrics
PERSONALIZATION:
  - Age → appropriate intensity language
  - Conditions → activity-specific guidance
  - Known barriers from Memory Engine (e.g., "knee pain")
CONTRAINDICATIONS:
  - Không prescribe exercise plan (không đưa ra "tập X phút mỗi ngày")
  - Không suggest high-intensity if: heart condition, uncontrolled BP, joint issues
  - Không suggest fasted exercise if diabetic on insulin
  - Always: "tham khảo bác sĩ trước khi bắt đầu chương trình tập mới"
CONFIDENCE_THRESHOLD: 65
EXPLANATION_FORMAT: encouraging, positive, realistic for Vietnam urban context
PRIORITY: routine
EXPIRATION: 48 hours
AUDIT: conditions_considered, contraindications_checked

EXERCISE_GUIDANCE_BY_CONDITION:
  diabetes_type2:
    safe_activities: ["đi bộ", "bơi lội", "yoga", "đạp xe nhẹ"]
    avoid_without_clearance: ["tập nặng khi đường huyết >250"]
    note: "Đi bộ sau bữa ăn giúp kiểm soát đường huyết sau ăn"
  hypertension:
    safe_activities: ["đi bộ", "bơi lội", "yoga"]
    avoid_without_clearance: ["nâng tạ nặng", "tập cường độ rất cao"]
    note: "Hoạt động aerobic vừa phải giúp huyết áp"
  heart_disease:
    safe_activities: ["đi bộ nhẹ"]
    avoid_without_clearance: ["mọi hoạt động cường độ cao"]
    note: "Cần cardiac clearance trước khi bắt đầu chương trình tập"
  osteoporosis:
    safe_activities: ["đi bộ", "tập cân bằng", "strength training nhẹ"]
    avoid: ["các hoạt động có nguy cơ ngã cao"]
    note: "Hoạt động weight-bearing giúp mật độ xương"

CONSENT_REQUIRED: health_summary_granted
UX_FLOW: inline chat with condition-specific guidance
```

---

## 6. Nhóm 4: Sleep

### Recommendation Spec
```
CATEGORY: sleep

TRIGGERS:
  - Wearable data shows poor sleep score (< 70/100) for 3+ consecutive nights
  - User mentions "mất ngủ", "khó ngủ", "ngủ không ngon"
  - HRV data shows sleep-related pattern (future wearable integration)
  - Care plan has sleep-related task not completed

REQUIRED_CONTEXT: recent_metrics (if wearable), health_summary, active_medications
PERSONALIZATION:
  - Age → elderly patients have different sleep architecture
  - Medications that affect sleep (beta-blockers → vivid dreams, diuretics → nocturia)
  - Known patterns from Memory Engine
CONTRAINDICATIONS:
  - Không prescribe sleep aids (Melatonin, antihistamines, etc.)
  - Không suggest specific OTC drugs for sleep
  - If sleep apnea suspected → escalate only
CONFIDENCE_THRESHOLD: 60
EXPLANATION_FORMAT: practical, gentle, evidence-based hygiene tips
PRIORITY: medium
EXPIRATION: 72 hours
AUDIT: trigger_source, medications_considered

SLEEP_HYGIENE_TIPS:
  universal:
    - "Giữ giờ ngủ và giờ thức đều đặn, kể cả cuối tuần"
    - "Tránh màn hình điện thoại ít nhất 30 phút trước ngủ"
    - "Nhiệt độ phòng mát mẻ giúp ngủ tốt hơn (khoảng 22-25°C)"
  for_hypertension:
    - "Huyết áp cao có thể liên quan đến chất lượng giấc ngủ kém — lưu ý theo dõi"
  for_diabetes:
    - "Đường huyết không ổn định có thể ảnh hưởng đến giấc ngủ"
    - "Kiểm tra đường huyết trước ngủ nếu bác sĩ khuyến nghị"
  drug_related_notes:
    - "Một số thuốc lợi tiểu có thể gây tiểu đêm — hỏi bác sĩ về thời điểm uống tốt nhất"

CONSENT_REQUIRED: metrics_granted (if wearable data)
UX_FLOW: chat message + optional "Thêm vào care plan" quick action
```

---

## 7. Nhóm 5: Stress

### Recommendation Spec
```
CATEGORY: stress

TRIGGERS:
  - HRV significantly below personal baseline for 3+ days (wearable)
  - User explicitly mentions stress, anxiety, worry
  - Physiological metrics show stress pattern (elevated HR at rest)
  - Adherence drops (indirect stress indicator)

REQUIRED_CONTEXT: recent_metrics, health_summary, memory (for patterns)
PERSONALIZATION:
  - Known stress triggers from Memory Engine
  - Cultural context (VN: work, family, finances as common stressors)
  - Preferred coping style (if known)
CONTRAINDICATIONS:
  - Không diagnose anxiety disorder
  - Không recommend psychotropic medication
  - Không replace mental health professional
  - If suicidal ideation detected → immediate escalation to emergency protocol
CONFIDENCE_THRESHOLD: 55 (stress is harder to quantify)
EXPLANATION_FORMAT: empathetic, normalize, practical
PRIORITY: medium (high if combined with physical symptoms)
EXPIRATION: 48 hours
AUDIT: trigger_source, escalation_considered

TECHNIQUES_TO_SUGGEST:
  breathing:
    - "Kỹ thuật thở 4-7-8: hít vào 4 giây, nín thở 7 giây, thở ra 8 giây"
    - "Thở bụng sâu 5-10 hơi có thể giảm nhịp tim nhanh chóng"
  mindfulness:
    - "5 phút chú tâm vào hơi thở mỗi sáng"
    - "Ứng dụng thiền như Headspace, Calm, hoặc Simply Being"
  physical:
    - "Đi bộ 10-15 phút ngoài trời thường giúp giảm căng thẳng"
  social:
    - "Chia sẻ với người thân đáng tin cậy"
  professional:
    - "Nếu căng thẳng kéo dài, chuyên gia tâm lý có thể giúp hiệu quả"

SUICIDAL_IDEATION_TRIGGERS:  # → EMERGENCY protocol
  - "muốn chết", "không muốn sống", "tự làm hại"
  - "không còn lý do để sống"

CONSENT_REQUIRED: metrics_granted
UX_FLOW: empathetic chat response, no quick-action (too personal)
```

---

## 8. Nhóm 6: Hydration

### Recommendation Spec
```
CATEGORY: hydration

TRIGGERS:
  - Kidney function markers elevated (creatinine, BUN)
  - User is on medications that require adequate hydration (lithium, NSAIDs, metformin)
  - Hot weather context (date + Vietnam climate data)
  - User mentions "khát nước", "nước tiểu vàng"
  - Diabetic patient (glucose osmotic diuresis risk)

REQUIRED_CONTEXT: health_summary, active_medications, recent_labs
PERSONALIZATION:
  - Renal patients: specific ranges → defer to doctor
  - Heart failure patients: fluid restriction → defer to doctor
  - Diabetic patients: higher fluid needs
  - Weather context (summer in VN)
CONTRAINDICATIONS:
  - Không suggest specific ml targets for renal patients → defer to nephrologist
  - Không suggest specific ml targets for heart failure → defer to cardiologist
  - Không suggest increased fluids if edema present → escalate
CONFIDENCE_THRESHOLD: 65
EXPLANATION_FORMAT: simple, practical, culturally relevant (trà, nước lọc, nước dừa)
PRIORITY: routine unless labs show renal concern
EXPIRATION: 24 hours
AUDIT: medications_considered, conditions_considered

TEMPLATES:
"Với Metformin, duy trì đủ nước là quan trọng để hỗ trợ thận.
8-10 ly nước mỗi ngày là mục tiêu chung — nước lọc, trà không đường,
hoặc canh đều tính. Điều chỉnh tùy thời tiết và mức độ vận động."

"Thời tiết nóng như hiện tại ở Việt Nam làm tăng nhu cầu nước.
Nước tiểu màu vàng nhạt là dấu hiệu đủ nước — màu đậm hơn → uống thêm."

CONSENT_REQUIRED: health_summary_granted, medications_granted
UX_FLOW: inline chat message
```

---

## 9. Nhóm 7: Follow-Up

### Recommendation Spec
```
CATEGORY: follow_up

TRIGGERS:
  - Lab result was "high" or "low" and > 30 days with no follow-up lab
  - Metric trend worsening for 14+ consecutive days
  - Appointment upcoming in 48h (prepare questions)
  - CRL recommended follow-up (from stage 3 output)
  - Care plan has pending follow-up task

REQUIRED_CONTEXT: recent_labs, recent_metrics, today_context, current_care_plan
PERSONALIZATION:
  - Upcoming appointment doctor name (from today_context)
  - Specific lab that needs follow-up
CONTRAINDICATIONS:
  - Không suggest specific timeline for repeat labs (that's doctor's decision)
  - Only say "nên trao đổi với bác sĩ khi nào nên đo lại"
CONFIDENCE_THRESHOLD: 70 (data-driven trigger)
EXPLANATION_FORMAT: practical, reminder-style
PRIORITY: medium to high depending on what needs follow-up
EXPIRATION: 7 days or until follow-up completed
AUDIT: what_triggered, last_result_value, days_since_last_result

TEMPLATES:
"HbA1c gần nhất của anh/chị đo vào {last_date} đã {days_since} ngày.
Với kết quả {value}%, bác sĩ thường khuyến nghị đo lại sau 3 tháng.
Anh/chị có muốn Meto thêm nhắc nhở lần đo tiếp theo không?"

"Lịch khám với {doctor_name} sắp tới vào {appointment_date}.
Muốn Meto giúp chuẩn bị danh sách câu hỏi để hỏi bác sĩ không?"

CONSENT_REQUIRED: lab_results_granted or metrics_granted
UX_FLOW: chat message + "Tạo nhắc nhở" or "Chuẩn bị câu hỏi" quick actions
```

---

## 10. Nhóm 8: Preventive Screening

### Recommendation Spec
```
CATEGORY: preventive_screening

TRIGGERS:
  - Age + sex + risk factors match screening guideline criteria
  - User hasn't had specific screening in recommended interval
  - Risk factor detected in health profile (smoking, family history)

REQUIRED_CONTEXT: health_summary, user_profile_summary, recent_labs
PERSONALIZATION:
  - Age and sex-specific screening calendar
  - Risk factors in profile (smoking, family history, BMI)
  - Previous screening history (if available in care plan)
CONTRAINDICATIONS:
  - Không diagnose based on screening results
  - Always "trao đổi với bác sĩ để được tư vấn phù hợp"
CONFIDENCE_THRESHOLD: 75 (guideline-based)
EXPLANATION_FORMAT: informative, not alarming
PRIORITY: routine (not urgent unless missed by >2 years)
EXPIRATION: 30 days
AUDIT: screening_type, age, risk_factors_considered

SCREENING_CALENDAR_VN:
  breast_cancer:
    eligible: women ≥ 40
    interval: annual mammography
    source: "Hướng dẫn VNHOD"
  cervical_cancer:
    eligible: women 21-65
    interval: Pap smear every 3 years OR HPV test every 5 years
    source: "Bộ Y tế VN 2023"
  colorectal_cancer:
    eligible: adults ≥ 45
    interval: colonoscopy every 10 years
    source: "ACS Guidelines adapted"
  diabetes_screening:
    eligible: overweight adults ≥ 35 or any adult ≥ 45
    interval: fasting glucose every 3 years
    source: "ADA 2025"
  hypertension_screening:
    eligible: adults ≥ 18
    interval: BP check every 2 years if normal
    source: "JNC8"
  lipid_screening:
    eligible: men ≥ 35, women ≥ 45 (earlier if risk factors)
    interval: every 5 years
  osteoporosis:
    eligible: women ≥ 65, men ≥ 70 (earlier if risk factors)
    interval: DEXA every 2 years

CONSENT_REQUIRED: health_summary_granted
UX_FLOW: chat message, suggest adding to care plan
```

---

## 11. Nhóm 9: Vaccination

### Recommendation Spec
```
CATEGORY: vaccination

TRIGGERS:
  - Age-based schedule (flu shot, pneumococcal, etc.)
  - Condition-based need (diabetes → pneumococcal, flu)
  - Travel planned (user mentions)
  - No vaccination record in care plan

REQUIRED_CONTEXT: health_summary, user_profile_summary
PERSONALIZATION:
  - Age-specific vaccines
  - Condition-specific vaccines (diabetes → flu, pneumococcal)
  - Immunocompromised status (if any)
CONTRAINDICATIONS:
  - Không comment on live vaccine safety in immunocompromised → defer
  - Không override any doctor instruction about vaccine contraindications
  - Allergy to vaccine components → flag and defer
CONFIDENCE_THRESHOLD: 80 (guideline-based, clear criteria)
EXPLANATION_FORMAT: matter-of-fact, not alarming
PRIORITY: routine
EXPIRATION: 30 days
AUDIT: vaccine_type, criteria_met

VACCINATION_SCHEDULE_VN:
  influenza:
    eligible: all adults, priority: elderly ≥65, diabetics, heart disease, CKD
    interval: annual (recommended October-November in Vietnam)
  pneumococcal:
    eligible: adults ≥65, diabetics, heart/lung/kidney/liver disease
    source: "CDC Advisory Committee on Immunization Practices"
  hepatitis_B:
    eligible: unvaccinated adults, especially healthcare workers, diabetics ≥60
  tetanus_diphtheria:
    eligible: all adults
    interval: booster every 10 years
  herpes_zoster (Shingrix):
    eligible: adults ≥50
    schedule: 2 doses 2-6 months apart
  COVID_19:
    follow: MOH Vietnam current guidance

TEMPLATES:
"Với tiểu đường, tiêm phòng cúm hàng năm và vaccine phế cầu khuẩn
được khuyến nghị vì nguy cơ biến chứng cao hơn. Anh/chị đã tiêm
những vaccine này chưa? Bác sĩ có thể tư vấn lịch tiêm phù hợp."

CONSENT_REQUIRED: health_summary_granted
UX_FLOW: chat message
```

---

## 12. Nhóm 10: Lifestyle

### Recommendation Spec
```
CATEGORY: lifestyle

TRIGGERS:
  - User is newly onboarded (first week)
  - User asks general health question
  - Seasonal context (new year resolutions, etc.)
  - Lab trends improving → positive reinforcement

REQUIRED_CONTEXT: health_summary, user_profile_summary
PERSONALIZATION:
  - Primary conditions → relevant lifestyle focus
  - Age group → appropriate framing
  - Cultural context (VN food culture, urban lifestyle)
CONTRAINDICATIONS:
  - Không preachy or moralizing
  - Keep positive framing
CONFIDENCE_THRESHOLD: 50 (general guidance)
EXPLANATION_FORMAT: warm, encouraging, practical
PRIORITY: low (background/ambient recommendations)
EXPIRATION: 72 hours
AUDIT: trigger_type

LIFESTYLE_PILLARS:
  nutrition: "Ăn cân bằng, đủ màu sắc rau củ"
  movement: "Vận động đều đặn, dù nhẹ"
  sleep: "Ngủ đủ giấc (7-8 tiếng)"
  stress: "Quản lý căng thẳng chủ động"
  social: "Kết nối xã hội tích cực"
  monitoring: "Theo dõi sức khỏe định kỳ"
  medication: "Tuân thủ phác đồ điều trị"
  smoking_alcohol: "Bỏ hoặc giảm thiểu thuốc lá, rượu bia"

CONSENT_REQUIRED: none (general advice)
UX_FLOW: inline chat, positive and warm tone
```

---

## 13. Nhóm 11: Care Plan

### Recommendation Spec
```
CATEGORY: care_plan

TRIGGERS:
  - Pending task in care plan not completed by due time
  - Task overdue (past due date)
  - User opens Dashboard with pending tasks
  - Consecutive missed tasks pattern

REQUIRED_CONTEXT: current_care_plan, today_context
PERSONALIZATION:
  - Task type → appropriate reminder tone
  - Missed pattern → adjust reminder strategy
  - User's known barriers from Memory Engine
CONTRAINDICATIONS:
  - Không create new tasks without user confirmation
  - Không auto-complete tasks
  - Không delete tasks
CONFIDENCE_THRESHOLD: 85 (direct data from care_plan)
EXPLANATION_FORMAT: practical, action-oriented
PRIORITY: high if high-priority task, medium for others
EXPIRATION: 2 hours (tasks are time-sensitive)
AUDIT: task_id, task_title, days_overdue

TEMPLATES:
"Anh/chị có {pending_count} task chưa hoàn thành hôm nay:
• {task_1} (ưu tiên cao)
• {task_2}
Muốn Meto nhắc lại sau 1 giờ không?"

"Task '{task_title}' đã quá hạn {days} ngày.
Anh/chị có muốn đánh dấu đã hoàn thành, hoặc cần hỗ trợ gì không?"

CONSENT_REQUIRED: care_plan_granted
UX_FLOW: chat message + action buttons (Complete / Snooze / Help)
```

---

## 14. Nhóm 12: Reminder Optimization

### Recommendation Spec
```
CATEGORY: reminder_optimization

TRIGGERS:
  - Pattern: user consistently ignores reminders at certain times
  - Pattern: user interacts more at certain hours (from session timestamps)
  - Adherence data shows timing-based skip pattern

REQUIRED_CONTEXT: medication_logs, session_history (anonymized timestamps only)
PERSONALIZATION:
  - Optimal reminder time based on interaction pattern
  - Morning person vs evening person (from Memory Engine)
  - Work schedule context (if mentioned in chat)
CONTRAINDICATIONS:
  - Không use raw conversation content for timing analysis
  - Only use session start timestamps and medication log timestamps
CONFIDENCE_THRESHOLD: 70 (pattern detection)
EXPLANATION_FORMAT: conversational, ask for confirmation
PRIORITY: low
EXPIRATION: 7 days
AUDIT: pattern_detected, current_reminder_times, suggested_times

TEMPLATES:
"Meto nhận thấy anh/chị thường mở ứng dụng vào buổi {best_time}.
Muốn Meto điều chỉnh giờ nhắc nhở thuốc sang {suggested_time} không?
Việc nhắc vào thời điểm phù hợp thường giúp uống thuốc đều hơn."

UX_FLOW: chat suggestion + Yes/No buttons
CONSENT_REQUIRED: chat_history_granted (for pattern analysis)
```

---

## 15. Recommendation Engine Architecture — Chi tiết

### 15.1 Trigger Detection

```python
class TriggerDetector:
    async def detect(
        self,
        context: dict,
        crl_output: RecommendationOutput | None,
        memory: list[MemoryItem],
        user_message: str | None
    ) -> list[Trigger]:

        triggers = []

        # Run all category detectors in parallel
        detector_results = await asyncio.gather(
            self._detect_medication_triggers(context),
            self._detect_nutrition_triggers(context, crl_output),
            self._detect_exercise_triggers(context),
            self._detect_sleep_triggers(context, memory),
            self._detect_stress_triggers(context, user_message),
            self._detect_hydration_triggers(context),
            self._detect_follow_up_triggers(context, crl_output),
            self._detect_screening_triggers(context),
            self._detect_vaccination_triggers(context),
            self._detect_lifestyle_triggers(context),
            self._detect_care_plan_triggers(context),
            self._detect_reminder_optimization_triggers(context),
        )

        for result in detector_results:
            triggers.extend(result)

        # Deduplicate by trigger_id + category
        seen = set()
        unique_triggers = []
        for t in triggers:
            key = (t.category, t.trigger_id)
            if key not in seen:
                seen.add(key)
                unique_triggers.append(t)

        return unique_triggers
```

### 15.2 Context Assembly per Recommendation

```python
class RecommendationContextAssembler:
    async def assemble(
        self,
        category: RecommendationCategory,
        user_id: str,
        base_context: dict,
        memory: list[MemoryItem]
    ) -> RecommendationContext:

        REQUIRED_BLOCKS = {
            RecommendationCategory.MEDICATION_ADHERENCE: [
                "active_medications", "today_context"
            ],
            RecommendationCategory.NUTRITION: [
                "health_summary", "recent_labs"
            ],
            RecommendationCategory.EXERCISE: [
                "health_summary", "recent_metrics"
            ],
            RecommendationCategory.SLEEP: [
                "recent_metrics", "active_medications"
            ],
            RecommendationCategory.STRESS: [
                "recent_metrics", "health_summary"
            ],
            RecommendationCategory.HYDRATION: [
                "health_summary", "active_medications", "recent_labs"
            ],
            RecommendationCategory.FOLLOW_UP: [
                "recent_labs", "today_context", "current_care_plan"
            ],
            RecommendationCategory.PREVENTIVE_SCREENING: [
                "health_summary", "user_profile_summary"
            ],
            RecommendationCategory.VACCINATION: [
                "health_summary", "user_profile_summary"
            ],
            RecommendationCategory.CARE_PLAN: [
                "current_care_plan", "today_context"
            ],
        }

        required = REQUIRED_BLOCKS.get(category, [])
        assembled = {block: base_context.get(block) for block in required}

        # Add relevant memory
        assembled["relevant_memory"] = [
            m for m in memory if self._memory_relevant_to_category(m, category)
        ]

        return RecommendationContext(**assembled)
```

### 15.3 Personalization Layer

```python
class PersonalizationEngine:
    def personalize(
        self,
        candidate: RecommendationCandidate,
        memory: list[MemoryItem],
        user_profile: dict
    ) -> RecommendationCandidate:

        # Apply preferred_address
        preferred_address = self._get_preferred_address(memory, user_profile)
        candidate.headline = candidate.headline.replace("{preferred_address}", preferred_address)
        candidate.body = candidate.body.replace("{preferred_address}", preferred_address)

        # Apply explanation style preference
        explanation_style = self._get_explanation_style(memory)
        if explanation_style == "simple":
            candidate.body = self._simplify_text(candidate.body)
        elif explanation_style == "detailed":
            candidate.body += self._add_detail(candidate.category)

        # Apply cultural context
        candidate.body = self._apply_vn_context(candidate.body, user_profile.get("language", "vi"))

        candidate.personalization_applied = True
        return candidate

    def _get_preferred_address(self, memory: list[MemoryItem], profile: dict) -> str:
        for m in memory:
            if m.key == "preferred_address":
                return m.value
        # Fallback by age and gender
        age = profile.get("age", 30)
        gender = profile.get("gender", "unknown")
        if age >= 60: return "bác"
        if gender == "female": return "chị"
        return "anh"
```

### 15.4 Contraindication Check

```python
class ContraindicationChecker:
    async def check(
        self,
        candidate: RecommendationCandidate,
        health_summary: dict,
        active_medications: list[dict]
    ) -> tuple[bool, str | None]:
        """Returns: (is_safe, contraindication_reason_if_any)"""

        category = candidate.category

        # Exercise contraindications
        if category == RecommendationCategory.EXERCISE:
            conditions = health_summary.get("primary_conditions", [])
            if any("heart" in c.lower() or "cardiac" in c.lower() for c in conditions):
                return False, "Cần cardiac clearance trước khi gợi ý tập thể dục"
            if self._has_uncontrolled_bp(health_summary):
                return False, "Huyết áp chưa kiểm soát — hoãn gợi ý tập"

        # Hydration contraindications
        if category == RecommendationCategory.HYDRATION:
            if self._has_heart_failure(health_summary):
                return False, "Heart failure — fluid restriction needed, defer to doctor"
            if self._has_edema_signs(health_summary):
                return False, "Edema present — do not suggest increased fluids"

        # Nutrition contraindications
        if category == RecommendationCategory.NUTRITION:
            if self._has_renal_failure(health_summary):
                # Can still give general nutrition, but must flag
                candidate.body += ("\n\n*Lưu ý: Với suy thận, chế độ ăn cần được "
                                   "chuyên gia dinh dưỡng tư vấn riêng.*")

        candidate.contraindications_checked = True
        return True, None
```

### 15.5 Priority Queue

```python
class RecommendationPriorityQueue:

    def __init__(self):
        self.queue: list[RecommendationCandidate] = []
        self.delivered_cache: dict[str, datetime] = {}  # rec_id → delivered_at

    def add(self, candidate: RecommendationCandidate):
        # Deduplication: has same category rec been delivered recently?
        cache_key = f"{candidate.category}:{candidate.trigger_type}"
        last_delivered = self.delivered_cache.get(cache_key)
        if last_delivered:
            hours_since = (utcnow() - last_delivered).total_seconds() / 3600
            min_interval = self._get_min_interval(candidate.category)
            if hours_since < min_interval:
                return  # Suppress — shown too recently

        # Staleness check
        if candidate.expiration_at and utcnow() > candidate.expiration_at:
            return  # Expired trigger

        self.queue.append(candidate)

    def get_top_n(self, n: int = 3) -> list[RecommendationCandidate]:
        """Sort by priority and return top N"""
        sorted_queue = sorted(
            self.queue,
            key=lambda c: (
                c.priority * 0.5 +
                self._urgency_score(c.urgency) * 0.3 +
                c.confidence / 100 * 0.2
            ),
            reverse=True
        )
        return sorted_queue[:n]

    def _get_min_interval(self, category: RecommendationCategory) -> float:
        """Minimum hours between same-category recommendations"""
        MIN_INTERVALS = {
            RecommendationCategory.MEDICATION_ADHERENCE: 4,  # Every 4 hours max
            RecommendationCategory.CARE_PLAN: 2,
            RecommendationCategory.NUTRITION: 24,
            RecommendationCategory.EXERCISE: 48,
            RecommendationCategory.SLEEP: 72,
            RecommendationCategory.STRESS: 48,
            RecommendationCategory.HYDRATION: 24,
            RecommendationCategory.FOLLOW_UP: 168,           # Once a week
            RecommendationCategory.PREVENTIVE_SCREENING: 720, # Once a month
            RecommendationCategory.VACCINATION: 720,
            RecommendationCategory.LIFESTYLE: 72,
            RecommendationCategory.REMINDER_OPTIMIZATION: 168,
        }
        return MIN_INTERVALS.get(category, 24)

    def _urgency_score(self, urgency: str) -> float:
        return {"now": 1.0, "today": 0.8, "this_week": 0.5, "routine": 0.2}.get(urgency, 0.2)

    def mark_delivered(self, candidate: RecommendationCandidate):
        cache_key = f"{candidate.category}:{candidate.trigger_type}"
        self.delivered_cache[cache_key] = utcnow()
```

### 15.6 Delivery Channel

```python
class DeliveryRouter:
    async def route(
        self,
        candidates: list[RecommendationCandidate],
        session_active: bool,
        user_notification_preferences: dict
    ) -> dict[str, list[RecommendationCandidate]]:

        routed = {
            "chat": [],
            "push_notification": [],
            "care_plan": [],
        }

        for candidate in candidates:
            # Active session → prefer chat
            if session_active and candidate.urgency in ("now", "today"):
                routed["chat"].append(candidate)

            # High priority + no active session → push notification
            elif candidate.priority >= 0.8 and not session_active:
                if user_notification_preferences.get("push_enabled", True):
                    routed["push_notification"].append(candidate)

            # Care plan suggestions → care plan channel
            elif candidate.category == RecommendationCategory.CARE_PLAN:
                routed["care_plan"].append(candidate)

            # Default → chat (will be shown next time user opens app)
            else:
                routed["chat"].append(candidate)

        return routed

class DeliveryChannel(str, Enum):
    CHAT = "chat"
    PUSH_NOTIFICATION = "push_notification"
    CARE_PLAN = "care_plan"
```

### 15.7 Audit Log

```python
@dataclass
class RecommendationAuditEntry:
    id: str                            # UUID
    user_id: str
    category: str
    trigger_type: str
    trigger_evidence_hash: str         # Hash of trigger data (no raw values)
    confidence: float
    priority: float
    action_tier: str
    delivery_channel: str
    contraindications_checked: bool
    personalization_applied: bool
    delivered_at: datetime | None
    user_feedback: str | None          # "acted_on" | "dismissed" | "snoozed"
    feedback_at: datetime | None
    created_at: datetime

# NOT stored in audit:
# - Raw lab values (in health data tables)
# - Full recommendation text (only category + trigger)
# - User's conversation content
```

### 15.8 User Feedback Loop

```python
class FeedbackProcessor:
    async def process(
        self,
        feedback: RecommendationFeedback,
        engine: RecommendationEngine
    ):
        # Update delivery cache based on feedback
        if feedback.action == FeedbackAction.DISMISSED:
            # Suppress this category for longer period
            engine.priority_queue.extend_suppression(
                category=feedback.category,
                extra_hours=24
            )

        elif feedback.action == FeedbackAction.SNOOZED:
            engine.priority_queue.snooze_until(
                recommendation_id=feedback.recommendation_id,
                until=feedback.snooze_until
            )

        elif feedback.action == FeedbackAction.ACTED_ON:
            # Positive signal → learn optimal timing
            await memory_engine.update_interaction_pattern(
                user_id=feedback.user_id,
                pattern_type="responds_to_recommendation",
                hour_of_day=utcnow().hour,
                category=feedback.category
            )

        elif feedback.action == FeedbackAction.NOT_HELPFUL:
            # Negative feedback → adjust personalization
            await memory_engine.note(
                user_id=feedback.user_id,
                category="interaction",
                key=f"not_helpful_{feedback.recommendation_category}",
                value="true"
            )

        # Log feedback
        await audit_log_recommendation_feedback(feedback)
```

---

## 16. Scope Boundary — Tuyệt đối

```python
SCOPE_VIOLATIONS = [
    # Điều RE không bao giờ được làm
    "prescribe_medication",
    "change_medication_dose",
    "suggest_stopping_medication",
    "diagnose_condition",
    "replace_medical_professional",
    "provide_specific_calorie_targets_without_dietitian",
    "provide_specific_fluid_targets_for_renal_patients",
    "comment_on_vaccine_safety_for_immunocompromised",
    "create_exercise_plan_for_cardiac_patients",
    "interpret_mental_health_symptoms_as_diagnosis",
]

# Code-level enforced — not just guidelines
class ScopeGuard:
    FORBIDDEN_PATTERNS_IN_RECOMMENDATIONS = [
        r"uống thêm\s+\d+\s*mg",      # Drug dosing
        r"tăng liều|giảm liều",         # Dose changes
        r"dừng thuốc|ngừng uống",      # Stop medication
        r"bị mắc bệnh|chẩn đoán\s+\w",# Diagnosis
        r"cụ thể là\s+\d+\s*ml\s*mỗi ngày",  # Specific fluid targets
    ]

    def validate(self, recommendation_text: str) -> ValidationResult:
        for pattern in self.FORBIDDEN_PATTERNS_IN_RECOMMENDATIONS:
            if re.search(pattern, recommendation_text, re.IGNORECASE):
                return ValidationResult(
                    is_valid=False,
                    violation_pattern=pattern,
                    action="BLOCK_AND_LOG"
                )
        return ValidationResult(is_valid=True)
```

---

## 17. Acceptance Criteria

### AC-RE-001: Coverage
- [ ] Tất cả 12 recommendation categories có trigger detection
- [ ] Mỗi category có ít nhất 2 trigger conditions
- [ ] Mỗi category có personalization applied

### AC-RE-002: Safety
- [ ] ScopeGuard passes all 12 category templates
- [ ] ContraindicationChecker blocks exercise rec for uncontrolled heart conditions
- [ ] ContraindicationChecker blocks hydration increase for heart failure
- [ ] No diagnosis statement in any recommendation template (regex validated)

### AC-RE-003: Deduplication
- [ ] Same category recommendation not shown within minimum interval
- [ ] Dismissed recommendation → extended suppression (24h extra)
- [ ] Snoozed recommendation → not shown until snooze expiry

### AC-RE-004: Priority
- [ ] Medication adherence (urgent) prioritized over lifestyle (routine)
- [ ] CRL escalation output → overrides all recommendations with appropriate escalation

### AC-RE-005: Audit
- [ ] Every recommendation delivery creates audit entry
- [ ] User feedback captured and linked to audit entry
- [ ] No raw health values in audit log

### AC-RE-006: Feedback Loop
- [ ] ACTED_ON → memory updated for timing optimization
- [ ] NOT_HELPFUL → category deprioritized for that user
- [ ] DISMISSED × 3 for same category → flag for review

---

*Xem thêm: 14_CLINICAL_REASONING.md (CRL output feeds RE), 17_DOCTOR_HANDOFF.md (escalation takes priority over RE), 10_MEMORY_ENGINE.md (personalization source), 09_TOOLS_AND_ACTIONS.md (RE triggers can call tools)*
