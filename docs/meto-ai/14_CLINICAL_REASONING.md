# Meto AI — Clinical Reasoning Layer

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved
> **Phase:** 3 — Clinical Intelligence

---

## Tổng quan

Clinical Reasoning Layer (CRL) là lớp suy luận có cấu trúc của Meto, chịu trách nhiệm chuyển đổi **dữ liệu sức khỏe thô** thành **diễn giải có ngữ cảnh** và **khuyến nghị phù hợp** cho người dùng — trong khi duy trì tuyệt đối ranh giới "trợ lý sức khỏe, không phải bác sĩ".

**Triết học cốt lõi:** Meto quan sát, không chẩn đoán. Meto diễn giải, không kê đơn. Meto gợi ý, không quyết định.

**File backend:**
- `app/ai/clinical_reasoning.py` — CRL core engine
- `app/ai/clinical_reasoning/stages.py` — Pipeline stages
- `app/ai/clinical_reasoning/confidence.py` — Confidence scoring
- `app/ai/clinical_reasoning/trend.py` — Trend interpretation
- `app/ai/clinical_reasoning/unit_converter.py` — Unit normalization
- `app/ai/clinical_reasoning/reference_ranges.py` — Reference range lookup

---

## 1. Clinical Reasoning Philosophy

### 1.1 Nguyên tắc Observation-Only

Meto **tuyệt đối không chẩn đoán** bệnh lý, không xác nhận hay phủ nhận bất kỳ tình trạng y tế nào. CRL được thiết kế trên 3 nguyên tắc bất biến:

```
NGUYÊN TẮC 1: QUAN SÁT (Observe)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Meto nhận biết dữ liệu như nó là.
"HbA1c = 7.8%, cao hơn ngưỡng tham chiếu < 7.0%"
✓ ĐƯỢC: Mô tả giá trị và vị trí so với ngưỡng
✗ KHÔNG: "Bạn đang bị đái tháo đường không kiểm soát tốt"

NGUYÊN TẮC 2: DIỄN GIẢI (Interpret)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Meto giải thích ý nghĩa lâm sàng chung, không áp dụng cho cá nhân.
"HbA1c 7.8% phản ánh mức đường huyết trung bình ~175 mg/dL trong 2-3 tháng qua"
✓ ĐƯỢC: Giải thích ý nghĩa sinh lý học chung
✗ KHÔNG: "Điều này có nghĩa là bệnh của anh/chị đang nặng hơn"

NGUYÊN TẮC 3: GỢI Ý (Recommend)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Meto đề xuất hành động phù hợp với vai trò trợ lý.
"Nên chia sẻ kết quả này với bác sĩ tại lần khám tiếp theo"
✓ ĐƯỢC: Gợi ý hành động trong phạm vi trợ lý sức khỏe
✗ KHÔNG: "Nên tăng liều Metformin lên 1000mg"
```

### 1.2 Ranh giới rõ ràng

| Meto CÓ THỂ làm | Meto KHÔNG được làm |
|-----------------|---------------------|
| Mô tả giá trị lab so với ngưỡng tham chiếu | Chẩn đoán bệnh lý mới |
| Giải thích ý nghĩa sinh lý học của biomarker | Thay đổi liều thuốc |
| Nhận biết xu hướng (trend) của chỉ số | Kê đơn thuốc mới |
| Gợi ý khi nào nên gặp bác sĩ | Nói "không cần đi khám" |
| Cảnh báo khi có giá trị bất thường | Đánh giá triệu chứng lâm sàng phức tạp |
| Correlate biomarkers để giải thích tình hình chung | Giải thích trực tiếp nguyên nhân của triệu chứng |
| Nhắc thuốc có thể ảnh hưởng đến lab result | Đề xuất ngừng hay đổi thuốc |

---

## 2. Pipeline: 3-Stage Reasoning

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CLINICAL REASONING PIPELINE                       │
│                                                                      │
│  INPUT                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Lab Data │  │ Metrics  │  │ Meds     │  │ Profile  │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       └─────────────┴──────────────┴─────────────┘                  │
│                              │                                       │
│                              ▼                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  STAGE 1: OBSERVATION                                         │  │
│  │  ├─ Unit normalization                                        │  │
│  │  ├─ Reference range lookup (age/sex/lab-method adjusted)      │  │
│  │  ├─ Status classification: normal / borderline / high / low / │  │
│  │  │   critical                                                 │  │
│  │  ├─ Drug-lab interaction flag                                 │  │
│  │  ├─ Missing data detection                                    │  │
│  │  └─ GUARDRAIL: Fail-safe if ambiguous → defer to Stage 2      │  │
│  │                                                               │  │
│  │  Output: ObservationSet {classified_labs, flags, gaps}        │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  STAGE 2: INTERPRETATION                                      │  │
│  │  ├─ Trend analysis (direction, velocity, acceleration)        │  │
│  │  ├─ Multi-lab correlation (VD: HbA1c + Glucose + Insulin)    │  │
│  │  ├─ Multi-condition reasoning (comorbidity weighting)         │  │
│  │  ├─ Differential explanation (A / B / C without diagnosing)  │  │
│  │  ├─ Confidence scoring per interpretation                     │  │
│  │  ├─ Conflicting data resolution                               │  │
│  │  └─ GUARDRAIL: confidence < threshold → escalate or defer    │  │
│  │                                                               │  │
│  │  Output: InterpretationResult {explanations, confidence}     │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  STAGE 3: RECOMMENDATION                                      │  │
│  │  ├─ Action tier selection (explain / suggest / escalate)     │  │
│  │  ├─ Risk priority matrix (severity × likelihood × trend)     │  │
│  │  ├─ Population-specific adjustments (age, sex, pregnancy)    │  │
│  │  ├─ Personalization from Memory Engine                       │  │
│  │  ├─ Response composition (language, format)                  │  │
│  │  └─ GUARDRAIL: Safety-first defaults, red flag bypass        │  │
│  │                                                               │  │
│  │  Output: RecommendationOutput {tier, message, escalation}    │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  FINAL OUTPUT: Structured response to Conversation Engine            │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 Stage 1: Observation

```python
@dataclass
class ObservationSet:
    labs: list[ClassifiedLab]
    metrics: list[ClassifiedMetric]
    drug_lab_flags: list[DrugLabFlag]
    missing_critical: list[str]        # Critical values that are absent
    data_quality_score: float          # 0.0-1.0 (completeness)
    population_adjustments_applied: list[str]  # "age_adjusted", "sex_adjusted", etc.

@dataclass
class ClassifiedLab:
    analyte: str                       # e.g., "HbA1c"
    original_value: float
    original_unit: str
    normalized_value: float            # Always in SI unit
    normalized_unit: str
    reference_low: float | None
    reference_high: float | None
    reference_source: str              # "ADA_2025", "WHO", "local_lab"
    status: LabStatus                  # NORMAL | BORDERLINE | HIGH | LOW | CRITICAL_HIGH | CRITICAL_LOW
    deviation_percent: float           # How far from reference midpoint
    age_adjusted: bool
    sex_adjusted: bool
    lab_method: str | None             # HPLC, immunoassay, etc.

class LabStatus(str, Enum):
    NORMAL = "normal"
    BORDERLINE = "borderline"          # Within 10% of reference boundary
    LOW = "low"
    HIGH = "high"
    CRITICAL_LOW = "critical_low"
    CRITICAL_HIGH = "critical_high"
    INDETERMINATE = "indeterminate"    # Cannot classify without more info

async def observe(
    labs: list[RawLab],
    metrics: list[RawMetric],
    medications: list[Medication],
    user_profile: UserProfile,
    is_pregnant: bool = False
) -> ObservationSet:
    classified_labs = []
    for lab in labs:
        normalized = unit_converter.normalize(lab.value, lab.unit, lab.analyte)
        ref_range = reference_range_db.lookup(
            analyte=lab.analyte,
            age=user_profile.age,
            sex=user_profile.gender,
            method=lab.method,
            pregnant=is_pregnant
        )
        status = classify_status(normalized, ref_range)
        classified_labs.append(ClassifiedLab(...))

    drug_flags = drug_lab_checker.check(medications, classified_labs)
    missing = detect_missing_critical(classified_labs, user_profile.conditions)

    return ObservationSet(
        labs=classified_labs,
        drug_lab_flags=drug_flags,
        missing_critical=missing,
        data_quality_score=compute_quality(classified_labs)
    )
```

**Stage 1 Guardrails:**
- Nếu analyte không nhận dạng được → `status = INDETERMINATE`, log, skip interpretation
- Nếu giá trị nằm ngoài physiologically plausible range → flag as potential data entry error
- Nếu thiếu thông tin cần thiết (age, sex) → sử dụng generic adult ranges, ghi chú
- Nếu unit không thể normalize → defer toàn bộ lab này, thông báo cần user xác nhận

### 2.2 Stage 2: Interpretation

```python
@dataclass
class InterpretationResult:
    overall_impression: str            # Mô tả tổng thể, không chẩn đoán
    lab_interpretations: list[LabInterpretation]
    trend_analyses: list[TrendAnalysis]
    correlation_findings: list[CorrelationFinding]
    differential_explanations: list[DifferentialExplanation]
    conflicts_detected: list[DataConflict]
    overall_confidence: float          # 0-100
    interpretation_gaps: list[str]     # Điều không thể kết luận

@dataclass
class LabInterpretation:
    analyte: str
    plain_language_status: str         # "Cao hơn ngưỡng bình thường khoảng 11%"
    clinical_significance: str         # Ý nghĩa lâm sàng chung của biomarker này
    common_reasons_if_high: list[str]  # Nguyên nhân phổ biến, không chẩn đoán
    common_reasons_if_low: list[str]
    confidence: float                  # 0-100
    requires_more_data: list[str]      # Dữ liệu bổ sung cần có để diễn giải chính xác hơn
    drug_interaction_note: str | None  # Thuốc đang dùng có thể ảnh hưởng không?

@dataclass
class DifferentialExplanation:
    """
    Giải thích 'có thể do A, B, hoặc C' mà không chẩn đoán.
    Chỉ dùng khi có đủ dữ liệu để đưa ra differential cụ thể.
    """
    analyte: str
    observation: str                   # "Calcium thấp kéo dài 2 lần xét nghiệm"
    possible_explanations: list[str]   # ["Có thể do chế độ ăn thiếu Vitamin D",
                                       #  "Có thể do thuốc như furosemide",
                                       #  "Có thể do yếu tố hấp thu"]
    important_note: str                # "Bác sĩ cần đánh giá để xác định nguyên nhân"
    confidence: float
```

**Stage 2 Guardrails:**
- Confidence < 40 → không đưa ra differential explanation
- Conflicting data detected → trình bày cả 2 mặt, không chọn 1 giải thích
- Missing critical context → thêm vào `interpretation_gaps`, không suy đoán
- Pattern that suggests serious pathology → tăng escalation priority, không chẩn đoán

### 2.3 Stage 3: Recommendation

```python
@dataclass
class RecommendationOutput:
    action_tier: ActionTier
    primary_message: str               # Nội dung chính gửi user
    supporting_details: list[str]      # Chi tiết thêm nếu user muốn biết thêm
    actionable_steps: list[str]        # Bước cụ thể user có thể làm ngay
    escalation_required: bool
    escalation_level: EscalationLevel  # See 17_DOCTOR_HANDOFF.md
    confidence: float
    response_rationale: str            # Dùng cho audit, không hiển thị user

class ActionTier(str, Enum):
    EXPLAIN = "explain"                # Giải thích thông tin, không hành động đặc biệt
    SUGGEST = "suggest"                # Đề xuất hành động chủ động
    ESCALATE = "escalate"              # Chuyển hướng đến bác sĩ
    EMERGENCY = "emergency"            # Khẩn cấp, cần gọi 115 ngay
```

**Stage 3 Guardrails:**
- Emergency tier → bypass tất cả reasoning → immediate hardcoded response
- ESCALATE tier → không thêm suggestion nào khác, focus vào việc gặp bác sĩ
- SUGGEST tier → mọi suggestion phải ở mức lifestyle/adherence, không clinical
- Pregnancy flag → auto-downgrade confidence, auto-suggest "tham khảo bác sĩ sản"

---

## 3. Confidence Scoring

### 3.1 Thang điểm 0–100

```python
class ConfidenceScorer:
    """
    Confidence score phản ánh mức độ Meto chắc chắn về một diễn giải.
    Không phải xác suất lâm sàng — chỉ phản ánh độ đầy đủ dữ liệu
    và độ rõ ràng của pattern.
    """

    def compute(self, observation: ObservationSet, context: dict) -> float:
        base_score = 50.0

        # Data completeness
        completeness = observation.data_quality_score  # 0.0-1.0
        base_score += (completeness - 0.5) * 30        # ±15 points

        # Reference range certainty
        if all(lab.reference_source in ["ADA_2025", "WHO_2024"] for lab in observation.labs):
            base_score += 10
        elif any(lab.reference_source == "fallback_generic" for lab in observation.labs):
            base_score -= 10

        # Context richness
        has_trend_data = context.get("historical_labs") is not None
        has_medications = len(context.get("medications", [])) > 0
        has_comorbidities = len(context.get("conditions", [])) > 0

        if has_trend_data:
            base_score += 10
        if has_medications:
            base_score += 5  # More context = better interpretation
        if has_comorbidities:
            base_score += 5  # Know what we're dealing with

        # Penalty factors
        if observation.missing_critical:
            base_score -= len(observation.missing_critical) * 8
        if observation.drug_lab_flags:
            base_score -= len(observation.drug_lab_flags) * 5  # Uncertainty due to drug effects
        if any(lab.status == LabStatus.INDETERMINATE for lab in observation.labs):
            base_score -= 15
        if len(observation.labs) < 2 and len(observation.metrics) < 2:
            base_score -= 10  # Too few data points

        return max(0.0, min(100.0, base_score))
```

### 3.2 Confidence → Action Tier Mapping

```
Confidence Score    Action Tier            Meto behavior
━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
85–100             EXPLAIN hoặc SUGGEST   Diễn giải đầy đủ + gợi ý cụ thể
60–84              EXPLAIN               Diễn giải với disclaimer "cần thêm thông tin"
40–59              EXPLAIN (limited)     Chỉ thông tin có độ chắc cao; gợi ý hỏi bác sĩ
20–39              DEFER                 "Meto chưa đủ thông tin để diễn giải chính xác"
0–19               ESCALATE             "Nên để bác sĩ đánh giá trực tiếp"
N/A (red flag)     EMERGENCY             Bypass confidence — hardcoded response
```

### 3.3 Per-Stage Confidence Thresholds

```python
CONFIDENCE_THRESHOLDS = {
    "stage1_observation": {
        "min_to_proceed": 30,          # Dưới 30 → skip interpretation
        "note_borderline": 50,          # 30-50 → add uncertainty note
    },
    "stage2_interpretation": {
        "min_for_differential": 50,     # Dưới 50 → không đưa ra differential
        "min_for_correlation": 60,      # Dưới 60 → không correlate multi-lab
        "min_for_trend": 55,            # Dưới 55 → không phân tích trend
    },
    "stage3_recommendation": {
        "min_for_suggest": 65,          # Dưới 65 → chỉ EXPLAIN, không SUGGEST
        "min_for_detailed_steps": 75,   # Dưới 75 → gợi ý generic, không chi tiết
    }
}
```

---

## 4. Uncertainty Handling

### 4.1 Khi nào nói "chưa đủ dữ liệu"

```python
INSUFFICIENT_DATA_CONDITIONS = [
    # Thiếu dữ liệu cơ bản
    "analyte_unrecognized",            # Analyte không trong knowledge base
    "unit_unrecognizable",             # Unit không thể normalize
    "value_physiologically_implausible", # Giá trị không hợp lý sinh lý học
    "reference_range_unavailable",     # Không có reference range phù hợp
    "single_data_point_only",          # Chỉ có 1 điểm dữ liệu, không có lịch sử

    # Thiếu context quan trọng
    "pregnancy_status_unknown",        # Kết quả lab phụ thuộc thai kỳ
    "fasting_status_unknown",          # Glucose/lipids cần biết lúc đói hay không
    "lab_method_unknown",              # Một số analyte (PSA, TSH) method-dependent
    "timing_relative_to_medication_unknown",  # Drug-lab interaction không thể assess

    # Conflicting signals
    "contradictory_lab_values",        # Hai kết quả mâu thuẫn không giải thích được
    "conflicting_with_symptoms",       # Lab bình thường nhưng symptoms nặng
]

def generate_insufficient_data_response(condition: str, analyte: str) -> str:
    templates = {
        "analyte_unrecognized": (
            f"Meto chưa có thông tin về xét nghiệm '{analyte}'. "
            f"Vui lòng hỏi bác sĩ hoặc nhân viên xét nghiệm để được giải thích."
        ),
        "pregnancy_status_unknown": (
            f"Để diễn giải kết quả {analyte} chính xác, Meto cần biết "
            f"anh/chị có đang mang thai không. Vì giá trị tham chiếu thay đổi đáng kể trong thai kỳ."
        ),
        "single_data_point_only": (
            f"Kết quả {analyte} hiện tại cần được đánh giá cùng với các lần đo trước "
            f"để có bức tranh đầy đủ. Meto sẽ diễn giải tốt hơn khi có thêm dữ liệu lịch sử."
        ),
        "contradictory_lab_values": (
            f"Meto nhận thấy một số kết quả xét nghiệm có vẻ không nhất quán với nhau. "
            f"Trường hợp này cần bác sĩ đánh giá trực tiếp để loại trừ sai số."
        ),
    }
    return templates.get(condition, (
        "Meto chưa đủ thông tin để diễn giải chính xác kết quả này. "
        "Bác sĩ của anh/chị là người phù hợp nhất để giải thích."
    ))
```

### 4.2 Khi nào nói "nên hỏi bác sĩ"

```
LUÔN thêm "nên hỏi bác sĩ" khi:
├─ Kết quả critical (bất kể confidence)
├─ Confidence < 50
├─ Trend xấu liên tục ≥ 3 lần đo
├─ Bất kỳ giá trị nào ở trạng thái HIGH hoặc LOW với deviation > 30%
├─ Drug-lab interaction detected
├─ Patient có ≥ 3 comorbidities (complexity threshold)
├─ User hỏi "Tôi có bệnh gì không?"
├─ User hỏi "Có cần thay đổi thuốc không?"
└─ User mô tả triệu chứng mới hoặc nặng hơn
```

---

## 5. Trend Interpretation

### 5.1 Single Point vs Trend

```python
class TrendAnalyzer:

    MIN_POINTS_FOR_TREND = 2           # Cần ít nhất 2 điểm để nói có trend
    MIN_POINTS_FOR_VELOCITY = 3        # 3 điểm để tính velocity
    MIN_POINTS_FOR_ACCELERATION = 4    # 4 điểm để tính acceleration

    def analyze(self, time_series: list[tuple[datetime, float]]) -> TrendAnalysis:
        if len(time_series) < self.MIN_POINTS_FOR_TREND:
            return TrendAnalysis(
                direction=TrendDirection.INSUFFICIENT_DATA,
                note="Cần ít nhất 2 lần đo để nhận biết xu hướng"
            )

        # Sort by time
        series = sorted(time_series, key=lambda x: x[0])
        values = [v for _, v in series]

        direction = self._compute_direction(values)
        velocity = self._compute_velocity(series) if len(series) >= 3 else None
        acceleration = self._compute_acceleration(series) if len(series) >= 4 else None

        return TrendAnalysis(
            direction=direction,
            velocity=velocity,
            acceleration=acceleration,
            n_points=len(series),
            timespan_days=(series[-1][0] - series[0][0]).days,
            is_statistically_meaningful=self._check_significance(values)
        )

    def _compute_direction(self, values: list[float]) -> TrendDirection:
        """Linear regression slope"""
        slope = linregress(range(len(values)), values).slope
        if abs(slope) < 0.02 * statistics.mean(values):  # < 2% change per unit time
            return TrendDirection.STABLE
        return TrendDirection.IMPROVING if slope < 0 else TrendDirection.WORSENING
        # Note: "improving" context-dependent — defined per analyte

    def _compute_velocity(self, series) -> float:
        """Rate of change per month"""
        days_elapsed = (series[-1][0] - series[0][0]).days
        if days_elapsed == 0:
            return 0.0
        total_change = series[-1][1] - series[0][1]
        return (total_change / days_elapsed) * 30  # per month

    def _compute_acceleration(self, series) -> float:
        """Second derivative — is the rate of change speeding up or slowing down?"""
        velocities = []
        for i in range(1, len(series)):
            dt = (series[i][0] - series[i-1][0]).days or 1
            dv = (series[i][1] - series[i-1][1]) / dt
            velocities.append(dv)
        if len(velocities) < 2:
            return 0.0
        return velocities[-1] - velocities[-2]  # positive = accelerating

@dataclass
class TrendAnalysis:
    direction: TrendDirection          # IMPROVING | WORSENING | STABLE | INSUFFICIENT_DATA
    velocity: float | None            # Change per month
    acceleration: float | None        # Is rate of change speeding up?
    n_points: int
    timespan_days: int
    is_statistically_meaningful: bool
    interpretation: str               # Human-readable summary
    concern_level: str                # "none" | "watch" | "attention" | "urgent"
```

### 5.2 Trend Language Guide

```python
TREND_LANGUAGE = {
    ("HbA1c", TrendDirection.WORSENING, "velocity_high"): (
        "HbA1c của anh/chị đang có xu hướng tăng khá nhanh "
        "({velocity:.1f}% mỗi tháng trong {n_points} lần đo gần nhất). "
        "Đây là thông tin quan trọng cần chia sẻ với bác sĩ."
    ),
    ("HbA1c", TrendDirection.IMPROVING, "any"): (
        "HbA1c của anh/chị đang có xu hướng giảm — tín hiệu tích cực "
        "cho thấy kiểm soát đường huyết đang cải thiện."
    ),
    ("blood_pressure", TrendDirection.WORSENING, "velocity_high"): (
        "Huyết áp đang có xu hướng tăng. "
        "Nên theo dõi chặt hơn và thông báo cho bác sĩ."
    ),
}

# Fallback template khi không có specific language
TREND_FALLBACK = (
    "{analyte} có xu hướng {direction_vi} trong {timespan_days} ngày qua "
    "({n_points} lần đo). "
    "{concern_note}"
)
```

---

## 6. Multi-Lab Reasoning

### 6.1 Correlation Patterns

```python
# Patterns được định nghĩa trong knowledge base, không hardcode trong business logic
CORRELATION_PATTERNS = {
    "glucose_metabolism": {
        "biomarkers": ["HbA1c", "fasting_glucose", "insulin", "c_peptide"],
        "primary": "HbA1c",
        "correlate_when": "at_least_2_present",
        "interpretation_logic": "glucose_metabolism_interpretation",
        "clinical_note": "Bộ 3 xét nghiệm đường huyết cho bức tranh toàn diện về kiểm soát glucose"
    },
    "thyroid_function": {
        "biomarkers": ["TSH", "free_T4", "free_T3", "anti_TPO"],
        "primary": "TSH",
        "correlate_when": "at_least_2_present",
        "interpretation_logic": "thyroid_interpretation",
        "clinical_note": "Đánh giá toàn diện chức năng tuyến giáp"
    },
    "lipid_panel": {
        "biomarkers": ["total_cholesterol", "LDL", "HDL", "triglycerides", "non_HDL"],
        "primary": "LDL",
        "correlate_when": "at_least_3_present",
        "interpretation_logic": "lipid_interpretation",
        "clinical_note": "Đánh giá nguy cơ tim mạch từ bộ mỡ máu"
    },
    "renal_function": {
        "biomarkers": ["creatinine", "BUN", "eGFR", "uric_acid", "microalbumin"],
        "primary": "eGFR",
        "correlate_when": "at_least_2_present",
        "interpretation_logic": "renal_interpretation",
        "clinical_note": "Đánh giá chức năng thận"
    },
    "liver_panel": {
        "biomarkers": ["ALT", "AST", "ALP", "GGT", "bilirubin", "albumin"],
        "primary": "ALT",
        "correlate_when": "at_least_3_present",
        "interpretation_logic": "liver_interpretation",
        "clinical_note": "Đánh giá chức năng gan"
    },
    "inflammatory_markers": {
        "biomarkers": ["CRP", "ESR", "WBC", "neutrophils"],
        "primary": "CRP",
        "correlate_when": "at_least_2_present",
        "interpretation_logic": "inflammatory_interpretation",
        "clinical_note": "Đánh giá tình trạng viêm"
    }
}

async def perform_multi_lab_correlation(
    classified_labs: list[ClassifiedLab],
    user_conditions: list[str]
) -> list[CorrelationFinding]:
    findings = []
    present_analytes = {lab.analyte for lab in classified_labs}

    for pattern_name, pattern in CORRELATION_PATTERNS.items():
        present_from_pattern = present_analytes.intersection(set(pattern["biomarkers"]))

        # Check if enough biomarkers present
        min_required = 2 if pattern["correlate_when"] == "at_least_2_present" else 3
        if len(present_from_pattern) < min_required:
            continue

        # Run correlation logic
        correlation_result = await knowledge_resolver.interpret_correlation(
            pattern_name=pattern_name,
            labs={lab.analyte: lab for lab in classified_labs if lab.analyte in present_from_pattern},
            user_conditions=user_conditions
        )

        findings.append(CorrelationFinding(
            pattern=pattern_name,
            biomarkers_used=list(present_from_pattern),
            finding=correlation_result.summary,
            confidence=correlation_result.confidence,
            clinical_note=pattern["clinical_note"]
        ))

    return findings
```

---

## 7. Multi-Condition Reasoning

### 7.1 Comorbidity Prioritization

```python
class ComorbidityPrioritizer:
    """
    Khi user có nhiều bệnh đồng thời, quyết định bối cảnh nào
    cần được ưu tiên trong diễn giải.
    """

    # Priority weights — higher = more critical to consider first
    CONDITION_PRIORITY = {
        "cardiovascular": 10,          # Tim mạch — ưu tiên cao nhất
        "renal_failure": 9,            # Suy thận — ảnh hưởng nhiều biomarker
        "liver_disease": 8,            # Gan — ảnh hưởng chuyển hóa thuốc
        "diabetes_type2": 7,
        "diabetes_type1": 7,
        "hypertension": 6,
        "dyslipidemia": 5,
        "hypothyroidism": 5,
        "hyperthyroidism": 5,
        "anemia": 4,
        "obesity": 3,
        "osteoporosis": 3,
    }

    def prioritize(
        self,
        conditions: list[str],
        analytes_in_question: list[str]
    ) -> list[tuple[str, int, str]]:
        """Returns: [(condition, priority, reason_for_relevance)]"""
        result = []
        for condition in conditions:
            priority = self.CONDITION_PRIORITY.get(condition.lower(), 1)

            # Boost priority if condition directly affects the analyte
            if self._condition_affects_analytes(condition, analytes_in_question):
                priority += 3
                reason = f"Bệnh {condition} có liên quan trực tiếp đến {', '.join(analytes_in_question)}"
            else:
                reason = f"Bệnh nền {condition} cần được xem xét"

            result.append((condition, priority, reason))

        return sorted(result, key=lambda x: x[1], reverse=True)

    def _condition_affects_analytes(self, condition: str, analytes: list[str]) -> bool:
        CONDITION_ANALYTE_MAP = {
            "diabetes_type2": ["glucose", "HbA1c", "insulin", "creatinine", "microalbumin"],
            "hypertension": ["blood_pressure", "creatinine", "eGFR", "potassium"],
            "renal_failure": ["creatinine", "eGFR", "BUN", "potassium", "phosphorus", "calcium"],
            "hypothyroidism": ["TSH", "free_T4", "cholesterol", "LDL", "CK"],
            "liver_disease": ["ALT", "AST", "ALP", "GGT", "bilirubin", "albumin", "INR"],
            "anemia": ["hemoglobin", "hematocrit", "MCV", "MCH", "iron", "ferritin", "B12", "folate"],
        }
        relevant_analytes = set(CONDITION_ANALYTE_MAP.get(condition.lower(), []))
        return bool(relevant_analytes.intersection(set(a.lower() for a in analytes)))
```

### 7.2 Reasoning trong bối cảnh đa bệnh

```
Ví dụ: Patient có Tiểu đường type 2 + Suy thận độ 3 + Tăng huyết áp
Analyte: Creatinine = 2.1 mg/dL

Single-condition reasoning (Tiểu đường):
→ "Creatinine cao có thể liên quan đến biến chứng thận do tiểu đường"

Multi-condition reasoning:
→ "Creatinine 2.1 mg/dL cao hơn ngưỡng bình thường. Với bối cảnh anh/chị có
   suy thận độ 3, đây là con số cần theo dõi chặt, đặc biệt khi cũng có tiểu đường
   và tăng huyết áp — cả hai đều có thể ảnh hưởng đến chức năng thận. Bác sĩ cần
   đánh giá xu hướng của creatinine và điều chỉnh kế hoạch chăm sóc phù hợp."

Ưu điểm: Không chẩn đoán. Không prescribe. Nhưng diễn giải có ngữ cảnh đa chiều.
```

---

## 8. Drug-Lab Interaction Reasoning

### 8.1 Drug-Lab Interaction Patterns

```python
DRUG_LAB_INTERACTIONS = {
    # Format: (drug_class_or_name, analyte, effect, mechanism_simple)
    ("statins", "CK", "increase", "statins có thể làm tăng CK do tác động lên cơ"),
    ("statins", "LDL", "decrease", "statins được thiết kế để giảm LDL"),
    ("metformin", "B12", "decrease", "metformin dùng lâu dài có thể giảm hấp thu B12"),
    ("metformin", "folate", "decrease", "metformin có thể ảnh hưởng nhẹ đến folate"),
    ("furosemide", "potassium", "decrease", "furosemide làm mất kali qua nước tiểu"),
    ("furosemide", "calcium", "decrease", "furosemide làm tăng thải calcium"),
    ("furosemide", "magnesium", "decrease", "furosemide làm mất magiê qua nước tiểu"),
    ("ACE_inhibitors", "potassium", "increase", "ACE inhibitors có thể giữ kali"),
    ("ACE_inhibitors", "creatinine", "increase_transient", "tăng creatinine nhẹ ban đầu là bình thường"),
    ("ARBs", "potassium", "increase", "ARBs có thể giữ kali, tương tự ACE inhibitors"),
    ("corticosteroids", "glucose", "increase", "corticosteroids làm tăng đường huyết"),
    ("corticosteroids", "WBC", "increase", "corticosteroids gây tăng bạch cầu"),
    ("thyroid_hormones", "TSH", "decrease", "thyroxine thay thế làm giảm TSH — cần target range"),
    ("warfarin", "INR", "increase", "warfarin được điều chỉnh theo INR target"),
    ("biotin", "TSH", "interfere", "biotin liều cao gây sai kết quả TSH miễn dịch"),
    ("biotin", "free_T4", "interfere", "biotin liều cao gây sai kết quả T4"),
    ("NSAIDs", "creatinine", "increase", "NSAIDs lâu dài có thể ảnh hưởng thận"),
    ("NSAIDs", "potassium", "increase", "NSAIDs có thể giữ kali"),
    ("beta_blockers", "glucose", "mask_hypoglycemia", "beta-blockers có thể che dấu triệu chứng hạ đường huyết"),
    ("beta_blockers", "triglycerides", "increase", "một số beta-blockers có thể tăng triglycerides"),
    ("iron_supplements", "ferritin", "increase", "đang bổ sung sắt sẽ tăng ferritin"),
    ("iron_supplements", "iron_serum", "increase", "bổ sung sắt làm tăng sắt huyết thanh"),
    ("contraceptives_oral", "cholesterol", "increase", "viên tránh thai estrogen có thể tăng cholesterol"),
    ("contraceptives_oral", "triglycerides", "increase", "viên tránh thai có thể tăng triglycerides"),
}

@dataclass
class DrugLabFlag:
    medication_name: str
    analyte: str
    effect: str                        # "increase" | "decrease" | "interfere"
    note: str                          # Patient-friendly explanation
    clinical_significance: str         # "high" | "medium" | "low"
    action_suggested: str              # What Meto recommends doing about it

def generate_drug_lab_note(flag: DrugLabFlag) -> str:
    return (
        f"Lưu ý: {flag.medication_name} mà anh/chị đang dùng "
        f"có thể ảnh hưởng đến kết quả {flag.analyte} "
        f"({flag.note}). "
        f"Nên thông báo cho bác sĩ để được đánh giá đúng hơn."
    )
```

---

## 9. Risk Prioritization

### 9.1 Risk Scoring Matrix

```python
class RiskPrioritizer:
    """
    Risk score = f(severity, likelihood, trend)
    Dùng để quyết định item nào cần attention nhất trong 1 batch kết quả.
    """

    def compute_risk_score(
        self,
        lab: ClassifiedLab,
        trend: TrendAnalysis | None,
        user_conditions: list[str]
    ) -> RiskScore:

        # Severity: how far from normal
        severity = self._severity_score(lab)

        # Likelihood: probability this is clinically significant
        likelihood = self._likelihood_score(lab, user_conditions)

        # Trend: multiplier based on direction and velocity
        trend_multiplier = self._trend_multiplier(trend)

        raw_score = (severity * 0.4 + likelihood * 0.4) * trend_multiplier
        priority_level = self._to_priority(raw_score)

        return RiskScore(
            lab_name=lab.analyte,
            severity=severity,
            likelihood=likelihood,
            trend_multiplier=trend_multiplier,
            composite=raw_score,
            priority_level=priority_level
        )

    def _severity_score(self, lab: ClassifiedLab) -> float:
        SEVERITY_MAP = {
            LabStatus.NORMAL: 0.0,
            LabStatus.BORDERLINE: 0.2,
            LabStatus.LOW: 0.5,
            LabStatus.HIGH: 0.5,
            LabStatus.CRITICAL_LOW: 1.0,
            LabStatus.CRITICAL_HIGH: 1.0,
        }
        base = SEVERITY_MAP.get(lab.status, 0.3)
        # Boost by deviation from reference midpoint
        if lab.deviation_percent:
            base += min(0.5, lab.deviation_percent / 100)
        return min(1.0, base)

    def _likelihood_score(self, lab: ClassifiedLab, conditions: list[str]) -> float:
        """Is this abnormal value likely to be clinically significant for this patient?"""
        # Known condition → higher likelihood of significance
        CONDITION_ANALYTE_RELEVANCE = {
            ("diabetes_type2", "HbA1c"): 1.0,
            ("diabetes_type2", "fasting_glucose"): 0.9,
            ("hypertension", "blood_pressure"): 1.0,
            ("dyslipidemia", "LDL"): 1.0,
            ("hypothyroidism", "TSH"): 1.0,
        }
        base = 0.5
        for condition in conditions:
            key = (condition.lower(), lab.analyte.lower())
            relevance = CONDITION_ANALYTE_RELEVANCE.get(key)
            if relevance:
                base = max(base, relevance)
        return base

    def _trend_multiplier(self, trend: TrendAnalysis | None) -> float:
        if trend is None:
            return 1.0
        MULTIPLIERS = {
            TrendDirection.WORSENING: 1.5,
            TrendDirection.STABLE: 1.0,
            TrendDirection.IMPROVING: 0.7,
            TrendDirection.INSUFFICIENT_DATA: 1.0,
        }
        multiplier = MULTIPLIERS.get(trend.direction, 1.0)
        # Boost for high-velocity worsening
        if trend.velocity and trend.velocity > 0.5:  # >50% change per month
            multiplier *= 1.3
        return multiplier

    def _to_priority(self, score: float) -> str:
        if score >= 0.8: return "urgent"
        if score >= 0.6: return "attention"
        if score >= 0.3: return "watch"
        return "monitor"
```

### 9.2 Priority Display

```
Risk Matrix (displayed as section header in Meto response):

🔴 CẦN CHÚ Ý NGAY   — score ≥ 0.8  → Suggest bác sĩ sớm
🟡 NÊN THEO DÕI     — score 0.6-0.8 → Mention + track
🟢 ĐANG ĐI ĐÚNG     — score 0.3-0.6 → Acknowledge + encourage
⚪ BÌNH THƯỜNG       — score < 0.3   → Confirm normal briefly
```

---

## 10. Conflicting Data Strategy

### 10.1 Khi lab mâu thuẫn với symptom

```python
class ConflictResolver:
    """
    Ví dụ: HbA1c = 6.5% (borderline) nhưng user mô tả "uống nhiều, tiểu nhiều"
    → Lab và symptom không nhất quán → Không bỏ qua symptom vì "lab bình thường"
    """

    def resolve_lab_symptom_conflict(
        self,
        lab_finding: str,
        lab_status: LabStatus,
        reported_symptoms: list[str]
    ) -> ConflictResolution:

        # Symptoms always take priority over lab — escalate
        if reported_symptoms and lab_status in (LabStatus.NORMAL, LabStatus.BORDERLINE):
            return ConflictResolution(
                has_conflict=True,
                resolution_type="symptom_overrides_lab",
                message=(
                    "Kết quả xét nghiệm của anh/chị trong ngưỡng bình thường, "
                    "nhưng những triệu chứng anh/chị mô tả vẫn cần được bác sĩ đánh giá. "
                    "Xét nghiệm không thể nắm bắt toàn bộ tình trạng sức khỏe — "
                    "chỉ bác sĩ mới có thể đánh giá đầy đủ."
                ),
                escalation_required=True
            )

        # Both lab and symptom abnormal → reinforce escalation
        if reported_symptoms and lab_status in (LabStatus.HIGH, LabStatus.LOW):
            return ConflictResolution(
                has_conflict=False,  # Actually consistent
                resolution_type="lab_and_symptom_consistent",
                message="Cả kết quả xét nghiệm và triệu chứng đều cho thấy cần được theo dõi.",
                escalation_required=True
            )

        return ConflictResolution(has_conflict=False, resolution_type="no_conflict")

    def resolve_contradictory_labs(
        self,
        lab_a: ClassifiedLab,
        lab_b: ClassifiedLab
    ) -> ConflictResolution:
        """
        Ví dụ: Creatinine cao nhưng eGFR bình thường (có thể do lab method)
        Ví dụ: TSH thấp nhưng free T4 thấp (không điển hình cho hyperthyroid)
        """
        return ConflictResolution(
            has_conflict=True,
            resolution_type="contradictory_labs",
            message=(
                f"Kết quả {lab_a.analyte} và {lab_b.analyte} có vẻ không hoàn toàn "
                f"nhất quán với nhau. Điều này có thể do sai số xét nghiệm hoặc "
                f"yếu tố kỹ thuật. Bác sĩ cần đánh giá để xác định."
            ),
            escalation_required=False,
            follow_up_suggested=True
        )
```

---

## 11. Missing Data Strategy

### 11.1 Partial Reasoning vs Defer

```python
def decide_reasoning_strategy(
    available_labs: list[ClassifiedLab],
    required_context: list[str],
    data_quality_score: float
) -> ReasoningStrategy:
    """
    Quyết định có tiếp tục reasoning với data không đầy đủ,
    hay defer hoàn toàn.
    """
    missing = set(required_context) - {lab.analyte for lab in available_labs}
    critical_missing = [m for m in missing if is_critical_for_interpretation(m)]

    if not critical_missing:
        if data_quality_score >= 0.6:
            return ReasoningStrategy.PROCEED_FULL
        else:
            return ReasoningStrategy.PROCEED_PARTIAL_WITH_CAVEATS
    elif len(critical_missing) <= 2:
        # Can reason partially, but must note missing data clearly
        return ReasoningStrategy.PROCEED_PARTIAL_WITH_CAVEATS
    else:
        # Too many critical gaps → don't reason, just flag
        return ReasoningStrategy.DEFER_TO_DOCTOR

class ReasoningStrategy(str, Enum):
    PROCEED_FULL = "proceed_full"
    PROCEED_PARTIAL_WITH_CAVEATS = "proceed_partial_with_caveats"
    DEFER_TO_DOCTOR = "defer_to_doctor"
```

### 11.2 Partial Reasoning Response Template

```
Khi PROCEED_PARTIAL_WITH_CAVEATS:
"Meto có thể chia sẻ một số thông tin dựa trên dữ liệu hiện có,
nhưng để có bức tranh đầy đủ hơn, cần thêm kết quả [missing analytes].

Dựa trên những gì hiện có: [partial interpretation]

Để diễn giải chính xác hơn, bác sĩ có thể cần thêm [missing context]."

Khi DEFER_TO_DOCTOR:
"Với các dữ liệu hiện có, Meto chưa đủ thông tin để đưa ra diễn giải có ý nghĩa.
Bác sĩ là người phù hợp nhất để đánh giá trong trường hợp này,
vì cần xem xét đầy đủ [list key missing factors]."
```

---

## 12. Escalation Thresholds

### 12.1 Bảng giá trị → Escalation Level

```python
ESCALATION_THRESHOLDS = {
    # Glucose / Đường huyết
    "fasting_glucose": {
        "unit": "mg/dL",
        "levels": [
            (0, 50, EscalationLevel.EMERGENCY),         # Hypoglycemia severe
            (50, 70, EscalationLevel.URGENT),
            (70, 99, EscalationLevel.NONE),              # Normal
            (100, 125, EscalationLevel.WATCH),           # Prediabetes range
            (126, 249, EscalationLevel.RECOMMEND_CHECKUP),
            (250, 399, EscalationLevel.URGENT),
            (400, float("inf"), EscalationLevel.EMERGENCY),
        ]
    },
    # HbA1c
    "HbA1c": {
        "unit": "%",
        "levels": [
            (0, 4.0, EscalationLevel.URGENT),
            (4.0, 5.6, EscalationLevel.NONE),
            (5.7, 6.4, EscalationLevel.WATCH),           # Prediabetes
            (6.5, 7.9, EscalationLevel.RECOMMEND_CHECKUP),
            (8.0, 9.9, EscalationLevel.URGENT),
            (10.0, float("inf"), EscalationLevel.EMERGENCY),
        ]
    },
    # Huyết áp
    "systolic_bp": {
        "unit": "mmHg",
        "levels": [
            (0, 90, EscalationLevel.URGENT),             # Hypotension
            (90, 119, EscalationLevel.NONE),
            (120, 129, EscalationLevel.WATCH),           # Elevated
            (130, 139, EscalationLevel.RECOMMEND_CHECKUP),
            (140, 179, EscalationLevel.URGENT),
            (180, float("inf"), EscalationLevel.EMERGENCY),
        ]
    },
    # SpO2
    "spo2": {
        "unit": "%",
        "levels": [
            (0, 89, EscalationLevel.EMERGENCY),
            (90, 93, EscalationLevel.URGENT),
            (94, 100, EscalationLevel.NONE),
        ]
    },
    # Creatinine (approximate — need eGFR for full picture)
    "creatinine": {
        "unit": "mg/dL",
        "adult_male_levels": [
            (0, 0.6, EscalationLevel.WATCH),
            (0.6, 1.3, EscalationLevel.NONE),
            (1.3, 2.0, EscalationLevel.RECOMMEND_CHECKUP),
            (2.0, 4.0, EscalationLevel.URGENT),
            (4.0, float("inf"), EscalationLevel.EMERGENCY),
        ],
        "adult_female_levels": [
            (0, 0.5, EscalationLevel.WATCH),
            (0.5, 1.1, EscalationLevel.NONE),
            (1.1, 1.8, EscalationLevel.RECOMMEND_CHECKUP),
            (1.8, 3.5, EscalationLevel.URGENT),
            (3.5, float("inf"), EscalationLevel.EMERGENCY),
        ]
    },
    # Potassium
    "potassium": {
        "unit": "mEq/L",
        "levels": [
            (0, 3.0, EscalationLevel.URGENT),
            (3.0, 3.5, EscalationLevel.WATCH),
            (3.5, 5.0, EscalationLevel.NONE),
            (5.0, 5.5, EscalationLevel.WATCH),
            (5.5, 6.0, EscalationLevel.URGENT),
            (6.0, float("inf"), EscalationLevel.EMERGENCY),
        ]
    },
}

class EscalationLevel(str, Enum):
    NONE = "none"
    WATCH = "watch"                    # Theo dõi
    RECOMMEND_CHECKUP = "recommend_checkup"  # Nên gặp bác sĩ
    URGENT = "urgent"                  # Cần gặp sớm trong 24-48h
    EMERGENCY = "emergency"            # Cấp cứu ngay
```

---

## 13. Safety-First Reasoning & Hallucination Prevention

### 13.1 Fail-Safe Defaults

```python
# Khi không chắc → action mặc định an toàn nhất
FAIL_SAFE_DEFAULTS = {
    "uncertain_lab_status": "Recommend checking with doctor",
    "multiple_conflicting_signals": "Escalate, do not interpret",
    "provider_error_mid_reasoning": "Deliver partial safe response",
    "confidence_below_minimum": "Acknowledge data, defer interpretation",
    "red_flag_detected": "Emergency response — bypass all reasoning",
    "pregnancy_unknown_with_affected_analyte": "Flag and defer",
    "pediatric_patient_detected": "Always escalate — no CRL for under 18",
}
```

### 13.2 Grounding Requirements

```python
class GroundingEnforcer:
    """
    Meto chỉ được sử dụng thông tin đã có trong context.
    Không bịa đặt, không suy luận vượt quá data.
    """

    GROUNDING_RULES = [
        # Rule 1: Chỉ cite những gì có trong context
        "Every clinical statement must reference a specific lab value or metric from context",
        # Rule 2: Không dùng external knowledge để claim về bệnh của user
        "Never use general medical knowledge to make claims about THIS specific patient",
        # Rule 3: Uncertainty phải được nêu rõ
        "All interpretations must include confidence qualifier",
        # Rule 4: Differential phải ở dạng 'có thể', không phải 'chắc chắn'
        "Differential explanations must use possibility language, never certainty",
    ]

    def validate_response(self, response: str, context: dict) -> ValidationResult:
        """
        Kiểm tra response trước khi gửi:
        1. Tất cả lab values được cite phải khớp với context
        2. Không có claim chắc chắn về chẩn đoán
        3. Không có recommendation vượt phạm vi
        """
        issues = []

        # Check no diagnosis statements
        DIAGNOSIS_PATTERNS = [
            r"\banh/chị bị\b",
            r"\bbệnh của anh/chị là\b",
            r"\bchẩn đoán\b.*\banh/chị\b",
            r"\bkết quả cho thấy anh/chị\b.*\bbị\b",
        ]
        for pattern in DIAGNOSIS_PATTERNS:
            if re.search(pattern, response):
                issues.append(f"Potential diagnosis statement detected: {pattern}")

        # Check prescription statements
        PRESCRIPTION_PATTERNS = [
            r"\buống thêm\b.*\bmg\b",
            r"\btăng liều\b",
            r"\bgiảm liều\b",
            r"\bdùng thuốc\b.*\bthêm\b",
        ]
        for pattern in PRESCRIPTION_PATTERNS:
            if re.search(pattern, response):
                issues.append(f"Potential prescription statement: {pattern}")

        return ValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            requires_human_review=len(issues) > 2
        )
```

---

## 14. Unit Normalization

### 14.1 Conversion Library

```python
# app/ai/clinical_reasoning/unit_converter.py

UNIT_CONVERSIONS = {
    # Glucose
    ("glucose", "mmol/L", "mg/dL"): lambda x: x * 18.0,
    ("glucose", "mg/dL", "mmol/L"): lambda x: x / 18.0,

    # Cholesterol / Lipids
    ("cholesterol", "mmol/L", "mg/dL"): lambda x: x * 38.67,
    ("cholesterol", "mg/dL", "mmol/L"): lambda x: x / 38.67,
    ("triglycerides", "mmol/L", "mg/dL"): lambda x: x * 88.57,
    ("triglycerides", "mg/dL", "mmol/L"): lambda x: x / 88.57,

    # TSH
    ("TSH", "mIU/L", "µIU/mL"): lambda x: x,   # 1:1 ratio
    ("TSH", "µIU/mL", "mIU/L"): lambda x: x,

    # Creatinine
    ("creatinine", "µmol/L", "mg/dL"): lambda x: x / 88.4,
    ("creatinine", "mg/dL", "µmol/L"): lambda x: x * 88.4,

    # Hemoglobin
    ("hemoglobin", "g/L", "g/dL"): lambda x: x / 10.0,
    ("hemoglobin", "g/dL", "g/L"): lambda x: x * 10.0,

    # Iron
    ("iron", "µmol/L", "µg/dL"): lambda x: x * 5.585,
    ("iron", "µg/dL", "µmol/L"): lambda x: x / 5.585,

    # Calcium
    ("calcium", "mmol/L", "mg/dL"): lambda x: x * 4.008,
    ("calcium", "mg/dL", "mmol/L"): lambda x: x / 4.008,

    # Uric Acid
    ("uric_acid", "µmol/L", "mg/dL"): lambda x: x / 59.48,
    ("uric_acid", "mg/dL", "µmol/L"): lambda x: x * 59.48,

    # eGFR: direct computation from creatinine, age, sex (CKD-EPI)
    # Not a simple conversion — handled by dedicated eGFR calculator
}

SI_UNITS = {
    "glucose": "mmol/L",
    "HbA1c": "%",             # Percentage is standard
    "cholesterol": "mmol/L",
    "LDL": "mmol/L",
    "HDL": "mmol/L",
    "triglycerides": "mmol/L",
    "creatinine": "µmol/L",
    "TSH": "mIU/L",
    "free_T4": "pmol/L",
    "free_T3": "pmol/L",
    "hemoglobin": "g/L",
    "iron": "µmol/L",
    "ferritin": "µg/L",
    "B12": "pmol/L",
    "folate": "nmol/L",
    "calcium": "mmol/L",
    "phosphorus": "mmol/L",
    "potassium": "mmol/L",
    "sodium": "mmol/L",
    "uric_acid": "µmol/L",
}

# VN Labs thường dùng mg/dL cho glucose → tự động detect và convert
VN_LAB_COMMON_UNITS = {
    "glucose": "mg/dL",
    "cholesterol": "mg/dL",
    "LDL": "mg/dL",
    "HDL": "mg/dL",
    "triglycerides": "mg/dL",
    "creatinine": "mg/dL",
    "uric_acid": "mg/dL",
}

class UnitConverter:
    def normalize(self, value: float, from_unit: str, analyte: str) -> tuple[float, str]:
        """Normalize to SI unit"""
        target_unit = SI_UNITS.get(analyte.lower())
        if target_unit is None or from_unit == target_unit:
            return value, from_unit

        key = (analyte.lower(), from_unit, target_unit)
        converter = UNIT_CONVERSIONS.get(key)
        if converter:
            return round(converter(value), 3), target_unit

        # Try reverse
        reverse_key = (analyte.lower(), target_unit, from_unit)
        if reverse_key in UNIT_CONVERSIONS:
            # Cannot do reverse conversion without the inverse function
            # Log and return original
            logger.warning(f"Unit conversion not available: {from_unit} → {target_unit} for {analyte}")
            return value, from_unit

        return value, from_unit
```

---

## 15. Reference Range Handling

### 15.1 Age-Adjusted, Sex-Adjusted, Lab-Specific Ranges

```python
@dataclass
class ReferenceRange:
    analyte: str
    low: float | None
    high: float | None
    unit: str
    source: str                        # "ADA_2025", "WHO_2024", "VN_MOH_2023", etc.
    applicable_population: str         # "adult_general", "adult_male", "adult_female",
                                       # "elderly_65plus", "pediatric", "pregnant"
    age_min: int | None
    age_max: int | None
    sex: str | None                    # "male" | "female" | None (both)
    lab_method: str | None             # Some tests vary by method
    notes: str | None                  # E.g., "Fasting required", "Serum only"

class ReferenceRangeDatabase:
    """
    Load từ knowledge base, không hardcode trong code.
    Cho phép update reference ranges mà không cần deploy lại.
    """

    def lookup(
        self,
        analyte: str,
        age: int,
        sex: str,
        lab_method: str | None = None,
        pregnant: bool = False
    ) -> ReferenceRange:

        # Priority: pregnant > age-specific > sex-specific > general
        if pregnant:
            ref = self._lookup_pregnant(analyte)
            if ref:
                return ref

        # Age-specific lookup
        age_specific = self._lookup_age_specific(analyte, age, sex)
        if age_specific:
            return age_specific

        # General adult
        return self._lookup_general(analyte, sex)

    def _age_bracket(self, age: int) -> str:
        if age < 18: return "pediatric"
        if age < 65: return "adult"
        if age < 80: return "elderly"
        return "very_elderly"
```

### 15.2 Adult vs Elderly Differences

```python
ELDERLY_ADJUSTMENTS = {
    # Một số giá trị "bình thường" thay đổi theo tuổi
    # KHÔNG thay đổi reference range (vì bác sĩ vẫn dùng standard)
    # Nhưng Meto ghi chú khi diễn giải

    "creatinine": {
        "note": "Ở người cao tuổi, creatinine có thể bình thường nhưng eGFR vẫn thấp do giảm khối lượng cơ",
        "recommendation": "Dùng eGFR thay vì creatinine đơn thuần để đánh giá thận ở người ≥65 tuổi"
    },
    "hemoglobin": {
        "note": "Thiếu máu nhẹ thường gặp hơn ở người cao tuổi nhưng không nên bỏ qua",
    },
    "TSH": {
        "note": "TSH có xu hướng nhẹ cao hơn ở người cao tuổi — cần cân nhắc khi đọc kết quả",
    },
    "blood_pressure": {
        "note": "Mục tiêu huyết áp cho người cao tuổi ≥65 tuổi có thể khác — bác sĩ sẽ quyết định target phù hợp",
    },
    "alkaline_phosphatase": {
        "note": "ALP thường tăng nhẹ theo tuổi, đặc biệt ở phụ nữ sau mãn kinh",
    }
}

def add_elderly_context(lab: ClassifiedLab, user_age: int) -> str | None:
    if user_age < 65:
        return None
    adjustment = ELDERLY_ADJUSTMENTS.get(lab.analyte)
    if adjustment:
        return adjustment.get("note")
    return None
```

### 15.3 Pregnancy Considerations

```python
PREGNANCY_PROTOCOL = {
    "detection": [
        "user_profile.is_pregnant == True",
        "recent_lab has 'beta_hCG' > 0",
        "user mentions 'đang mang thai' in conversation",
    ],
    "action_on_detection": [
        "Set is_pregnant = True in reasoning context",
        "Apply pregnancy reference ranges",
        "Add mandatory note: 'Diễn giải trong thai kỳ cần được bác sĩ sản khoa xác nhận'",
        "Auto-escalate for any value outside pregnancy-specific reference range",
        "NEVER reason about medication safety in pregnancy — always defer",
    ],
    "deferred_analytes": [
        "All drug dosing concerns",
        "Medication additions or changes",
        "Any symptom that could indicate obstetric emergency",
    ],
    "pregnancy_specific_ranges_needed": [
        "hemoglobin", "hematocrit", "ferritin",
        "thyroid_function", "blood_glucose", "HbA1c",
        "platelet_count", "blood_pressure",
        "albumin", "alkaline_phosphatase",
    ]
}
```

---

## 16. Decision Trees

### 16.1 Lab Result Interpretation Decision Tree

```
LAB RESULT RECEIVED
        │
        ▼
[1. Unit normalization]
        │
        ├── Unknown unit ──────────────────▶ FLAG "Cần xác nhận đơn vị"
        │
        ▼
[2. Reference range lookup]
        │
        ├── No range available ────────────▶ FLAG "Không có ngưỡng tham chiếu"
        │                                         → Defer to doctor
        ▼
[3. Status classification]
        │
        ├── CRITICAL ──────────────────────▶ EMERGENCY response immediately
        │
        ├── HIGH / LOW ────────────────────▶ [4. Check drug-lab interaction]
        │                                         │
        │                                         ├── Drug interaction found ──▶ Add drug note
        │                                         │
        │                                         ▼
        │                                   [5. Compute confidence]
        │                                         │
        │                                         ├── < 40 ─────────────▶ DEFER
        │                                         │
        │                                         ├── 40-64 ────────────▶ EXPLAIN + caveats
        │                                         │
        │                                         └── ≥ 65 ─────────────▶ [6. Trend + Correlation]
        │                                                                         │
        │                                                                         ▼
        │                                                               FULL INTERPRETATION
        │
        ├── BORDERLINE ──────────────────────▶ EXPLAIN with "watch" framing
        │
        └── NORMAL ──────────────────────────▶ CONFIRM + encourage
```

### 16.2 Escalation Decision Tree

```
CLINICAL REASONING RESULT
        │
        ▼
[Check: Any CRITICAL value?]
        │
        ├── YES ──────────────────────────▶ EMERGENCY (bypass reasoning)
        │
        ▼
[Check: Red flags in user message?] (See 04_SAFETY_PRIVACY.md)
        │
        ├── YES (Emergency) ──────────────▶ EMERGENCY response
        ├── YES (Urgent) ──────────────────▶ URGENT — recommend visit today
        │
        ▼
[Check: Risk score ≥ 0.8?]
        │
        ├── YES ──────────────────────────▶ RECOMMEND_CHECKUP (soon)
        │
        ▼
[Check: Confidence < 40?]
        │
        ├── YES ──────────────────────────▶ DEFER ("insufficient data")
        │
        ▼
[Check: Trend = WORSENING + 3 consecutive?]
        │
        ├── YES ──────────────────────────▶ RECOMMEND_CHECKUP
        │
        ▼
[Check: Multiple comorbidities with interaction?]
        │
        ├── YES ──────────────────────────▶ SUGGEST + recommend sharing with doctor
        │
        ▼
[Normal path → EXPLAIN or SUGGEST based on confidence tier]
```

---

## 17. Sequence Diagram

### 17.1 Full Clinical Reasoning Flow

```
User             ConversationEngine    ClinicalReasoningLayer    KnowledgeBase    SafetyGuard
 │                       │                       │                    │                │
 │  [HbA1c kết quả?]     │                       │                    │                │
 ├──────────────────────▶│                       │                    │                │
 │                       │  assemble_context()   │                    │                │
 │                       ├───────────────────────▶                    │                │
 │                       │  context {labs, meds, profile}             │                │
 │                       │◀───────────────────────                    │                │
 │                       │                       │                    │                │
 │                       │  safety_check()                            │               │
 │                       ├──────────────────────────────────────────────────────────▶│
 │                       │  no_red_flags                                              │
 │                       │◀──────────────────────────────────────────────────────────│
 │                       │                       │                    │                │
 │                       │  reason(context)      │                    │                │
 │                       ├──────────────────────▶│                    │                │
 │                       │                       │  lookup_ranges()   │                │
 │                       │                       ├───────────────────▶│                │
 │                       │                       │◀───────────────────│                │
 │                       │                       │                    │                │
 │                       │                       │  Stage1: Observe   │                │
 │                       │                       ├──────────────────────────────────▶│
 │                       │                       │  (drug-lab check)                  │
 │                       │                       │◀──────────────────────────────────│
 │                       │                       │                    │                │
 │                       │                       │  Stage2: Interpret │                │
 │                       │                       │  (trend + correl.) │                │
 │                       │                       │                    │                │
 │                       │                       │  Stage3: Recommend │                │
 │                       │                       │  (action_tier)     │                │
 │                       │                       │                    │                │
 │                       │  ReasoningOutput      │                    │                │
 │                       │◀──────────────────────│                    │                │
 │                       │                       │                    │                │
 │                       │  validate_output()                                         │
 │                       ├──────────────────────────────────────────────────────────▶│
 │                       │  valid                                                     │
 │                       │◀──────────────────────────────────────────────────────────│
 │                       │                       │                    │                │
 │  [Meto response]      │                       │                    │                │
 │◀──────────────────────│                       │                    │                │
```

---

## 18. Acceptance Criteria

### AC-CRL-001: Pipeline
- [ ] Tất cả 3 stages đều có guardrails được kiểm tra
- [ ] Emergency values bypass pipeline và trigger immediate response
- [ ] Confidence score được tính cho mọi interpretation
- [ ] Missing data detection chạy ở Stage 1

### AC-CRL-002: Unit Normalization
- [ ] Glucose mg/dL ↔ mmol/L conversion chính xác (x18)
- [ ] Cholesterol mg/dL ↔ mmol/L conversion chính xác
- [ ] Creatinine mg/dL ↔ µmol/L conversion chính xác
- [ ] Unknown units → flag, không crash

### AC-CRL-003: Reference Ranges
- [ ] Lookup trả về age-adjusted range khi có
- [ ] Lookup trả về sex-adjusted range khi có
- [ ] Pregnancy flag → pregnancy reference ranges
- [ ] Elderly (≥65) → thêm elderly context note

### AC-CRL-004: Drug-Lab Interactions
- [ ] Metformin → B12 flag khi dùng > 6 tháng
- [ ] Statins → CK flag
- [ ] Furosemide → potassium, calcium, magnesium flags
- [ ] Corticosteroids → glucose flag

### AC-CRL-005: Safety
- [ ] Meto không bao giờ output câu chẩn đoán (regex validation pass)
- [ ] Meto không output câu kê đơn (regex validation pass)
- [ ] Confidence < 40 → never SUGGEST, only EXPLAIN or DEFER
- [ ] Grounding validator chạy trước mọi response

### AC-CRL-006: Trend
- [ ] Cần ≥2 data points để claim trend
- [ ] Velocity computed từ ≥3 data points
- [ ] Acceleration computed từ ≥4 data points
- [ ] Worsening trend 3 consecutive → auto-recommend checkup

---

*Xem thêm: 15_RECOMMENDATION_ENGINE.md (outputs của CRL đi vào đây), 17_DOCTOR_HANDOFF.md (escalation thresholds chi tiết), 16_KNOWLEDGE_BASE.md (reference ranges và drug knowledge)*
