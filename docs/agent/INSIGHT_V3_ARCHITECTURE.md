# MetoCare — AI Health Intelligence Engine v3 Architecture

**Status:** DESIGN DRAFT — pending PTH approval before implementation  
**Date:** 2026-06-28  
**Author:** OpenClaw (Architecture Design Sprint — Option A)

---

## 1. Mission

Upgrade MetoCare from "Lab Interpretation App" → "AI Health Copilot".

- AI analyses the patient's **entire health context**, not isolated biomarkers.
- One coherent **Health Story**, not N isolated warnings.
- **Ranked priorities**, not N equal warnings.
- **Personalized** recommendations — adapts to age, sex, BMI, meds, history.
- Longitudinal intelligence — trends over time.
- Goal tracking — current vs target vs progress %.
- Every conclusion is explainable. Never hallucinate.

---

## 2. Current Architecture (v2)

```
PatientInsightRequest {batch_id, sex, age, waist_cm}
    ↓
[Lab results from DB]
    ↓
assess_biomarker() × N          → findings: list[ClinicalFinding]
compute_all_derived()            → derived: dict[str, DerivedMetricResult]
detect_patterns()                → patterns: list[PatternDetection]
compute_trends()                 → trends: list[BiomarkerTrend]
    ↓
generate_patient_insight()
    → _build_insight_cards()     → list[InsightCard] (max 5)
    → _build_action_cards()      → list[ActionCard]
    → _build_timeline()          → list[TimelineSummaryItem]
    ↓
PatientInsightReport {
  overall_status, insights, action_cards, timeline,
  urgent_alerts, positive_reinforcement, top_priorities
}
```

**Gaps:** No context adaptation. No health story. No priority explanation. No goals. No medication awareness. No lifestyle adaptation.

---

## 3. Target Architecture (v3)

```
PatientInsightRequest v3 {
  batch_id, lab_result_ids,
  patient_context: PatientContext   ← NEW (from PatientProfile + frontend)
}
    ↓
PatientContextEngine.build()       ← NEW Engine 1
    → PatientContext (enriched)
    ↓
[Lab results from DB] + PatientContext
    ↓
assess_biomarker(context=ctx) × N  ← UPDATED — context-aware thresholds
compute_all_derived(context=ctx)   ← UPDATED — context-aware ranges
    ↓
CrossMarkerCorrelationEngine        ← NEW Engine 2 (replaces detect_patterns)
    → list[ClinicalPattern]
    ↓
PriorityEngine.rank()               ← NEW Engine 4
    → list[PriorityIssue] (ranked, with explanation)
    ↓
LongitudinalEngine.analyse()        ← UPDATED Engine 5 (upgrade BiomarkerTrend)
    → list[TrendAnalysis]
    ↓
GoalEngine.generate()               ← NEW Engine 6
    → list[HealthGoal]
    ↓
MedicationContextEngine.annotate()  ← NEW Engine 7
    → list[MedicationAnnotation]
    ↓
LifestyleEngine.recommend()         ← NEW Engine 8
    → list[LifestyleRecommendation]
    ↓
HealthStoryGenerator.generate()     ← NEW Engine 3
    → HealthStory (narrative_vi, summary_vi)
    ↓
EvidenceEngine.annotate()           ← Engine 9 (already partial in v2)
    → per-conclusion evidence + confidence
    ↓
PatientInsightReport v3 {
  health_story: HealthStory          ← NEW
  priorities: list[PriorityIssue]    ← NEW (replaces top_priorities list[str])
  insights: list[InsightCard]        ← EXTENDED
  patterns: list[ClinicalPattern]    ← EXTENDED (replaces PatternDetection)
  trends: list[TrendAnalysis]        ← EXTENDED
  goals: list[HealthGoal]            ← NEW
  action_cards: list[ActionCard]
  medication_notes: list[MedicationAnnotation]  ← NEW
  lifestyle_recs: list[LifestyleRecommendation] ← NEW
  overall_status, urgent_alerts, positive_reinforcement, timeline, disclaimer_vi
}
```

---

## 4. Data Models (new entities)

### 4.1 PatientContext (Engine 1)

```python
@dataclass
class PatientContext:
    # Demographics
    age: int | None
    sex: str | None            # "male" | "female"
    
    # Biometrics (from PatientProfile + request)
    height_cm: float | None
    weight_kg: float | None
    bmi: float | None          # computed if height+weight available
    waist_cm: float | None
    
    # Risk factors (from PatientProfile.known_conditions, lifestyle_profile)
    has_diabetes: bool
    has_hypertension: bool
    has_dyslipidemia: bool
    has_cvd_history: bool       # prior MI, stroke, angina
    has_ckd: bool
    has_fatty_liver: bool
    
    # Lifestyle (from PatientProfile.lifestyle_profile JSON)
    is_smoker: bool
    drinks_alcohol: bool
    is_vegetarian: bool
    exercise_level: str        # "none" | "light" | "moderate" | "active"
    
    # Medications (from PatientProfile.lifestyle_profile or dedicated field)
    medications: list[str]     # ["statin", "metformin", "levothyroxine", ...]
    
    # Computed risk category
    cv_risk_category: str      # "low" | "intermediate" | "high" | "very_high"
    
    # Source metadata
    context_completeness: float  # 0.0–1.0 — how complete is the context?
    missing_context: list[str]   # ["waist_cm", "medications"] — what's missing
```

**Build logic:**
- Pull `PatientProfile` from DB (height_cm, weight_kg, waist_cm, gender, known_conditions, lifestyle_profile, family_history)
- Parse `known_conditions` text with keyword matching (no LLM) → set boolean flags
- Parse `lifestyle_profile` JSON → medications, exercise, smoking, diet
- Compute BMI = weight / (height/100)²
- Compute `cv_risk_category` using modified Framingham proxy (age + sex + smoking + known CVD)
- Frontend can also pass context fields directly in request for overrides

### 4.2 ClinicalPattern (Engine 2 — replaces PatternDetection)

```python
@dataclass
class ClinicalPattern:
    pattern_id: str            # "insulin_resistance" | "dyslipidemia" | ...
    display_name_vi: str
    description_vi: str        # What this pattern means
    severity: str              # "info" | "watch" | "warning" | "urgent"
    supporting_findings: list[str]   # canonicals that triggered this
    confidence: str            # "high" | "medium" | "low"
    evidence_based: bool
    evidence_source: str       # "established" | "moderate" | "emerging"
    
    # v3 new fields
    reasoning_vi: str          # Why these markers → this pattern
    clinical_significance_vi: str    # What it means for the patient
    context_modifiers: list[str]     # How patient context changes interpretation
    recommended_additional_tests: list[str]   # "HbA1c", "insulin lúc đói", ...
    limitation_vi: str         # What this pattern cannot tell us
```

**New patterns to add (beyond existing 5):**
- `atherogenic_cholesterol` — LDL↑ + NonHDL↑
- `inflammatory_process` — Ferritin↑ + CRP↑
- `hepatic_metabolic` — ALT↑ + AST↑ + TG↑ + BMI↑ (MAFLD pattern)
- `metabolic_syndrome_full` — HbA1c↑ + TG↑ + HDL↓ (upgrade from existing)
- `thyroid_dysfunction` — TSH↑/↓ + FT4 interpretation
- `anemia_pattern` — Hemoglobin↓ + MCV → classify microcytic/normocytic/macrocytic

### 4.3 PriorityIssue (Engine 4)

```python
@dataclass
class PriorityIssue:
    rank: int                  # 1, 2, 3, ...
    issue_id: str              # card_id or pattern_id
    title_vi: str
    priority_reason_vi: str    # Why this ranked here (context-aware)
    urgency: str               # "routine" | "1_month" | "soon" | "immediately"
    linked_card_id: str | None # for navigation to detail page
```

**Ranking algorithm:**
1. Urgent alerts → always rank 1 (e.g., glucose >22 mmol/L)
2. CV risk × biomarker severity (e.g., LDL↑ in high-CV-risk patient ranks higher)
3. Patterns > isolated findings (multi-marker > single marker)
4. Patient context multipliers (e.g., creatinine↑ in CKD patient → higher priority)
5. Trend worsening > stable (worsening issue ranks higher than stable same-level issue)

### 4.4 HealthStory (Engine 3)

```python
@dataclass  
class HealthStory:
    narrative_vi: str          # 3–5 sentences, coherent narrative, not bullet list
    summary_cards: list[dict]  # [{type: "improved"|"worsened"|"concern"|"goal", text_vi}]
    focus_this_month_vi: str   # One recommended focus
    reading_time_seconds: int  # ~60 target
```

**Generation rules (static, no LLM):**
- Template-based: combine top pattern + trend direction + priority 1 issue
- Use narrative connectors: "Kết hợp lại, những chỉ số này...", "Điều đáng chú ý là..."
- "improved": any biomarker with trend=improving and change_pct > 10%
- "worsened": any biomarker with trend=worsening and change_pct > 10%
- "concern": Priority 1 issue
- "goal": If any goal has progress < 80%

### 4.5 TrendAnalysis (Engine 5 upgrade)

Extend `BiomarkerTrend`:
```python
@dataclass
class TrendAnalysis(BiomarkerTrend):
    # Existing: canonical, display_name_vi, data_points, trend, change_pct, explanation_vi
    
    # v3 new fields
    velocity: str              # "rapid" | "gradual" | "stable" | "fluctuating"
    last_value: float | None
    last_unit: str | None
    last_date: str | None
    target_value: float | None  # from HealthGoal if set
    target_progress_pct: float | None  # current/target progress
    context_note_vi: str       # How patient context affects interpretation of this trend
```

### 4.6 HealthGoal (Engine 6)

```python
@dataclass
class HealthGoal:
    goal_id: str               # "ldl_target" | "hba1c_target" | ...
    canonical: str
    display_name_vi: str
    current_value: float | None
    target_value: float
    unit: str
    progress_pct: float | None  # None if no current value
    direction: str             # "lower_is_better" | "higher_is_better"
    status: str                # "on_track" | "off_track" | "achieved"
    rationale_vi: str          # Why this target (guideline-based)
    evidence_source: str
```

**Auto-generate goals when biomarker is abnormal/borderline:**
- LDL → target based on CV risk category (low: <3.0, high: <1.8 mmol/L)
- HbA1c → <7.0% (diabetic) or <5.7% (pre-diabetic target)
- TG → <1.70 mmol/L
- HDL → >1.0 (male) / >1.3 (female) mmol/L
- Fasting glucose → <5.6 mmol/L
- BMI → <25 if overweight
- Waist → <94cm (male) / <80cm (female) if elevated

### 4.7 MedicationAnnotation (Engine 7)

```python
@dataclass
class MedicationAnnotation:
    medication: str            # "statin" | "metformin" | "levothyroxine"
    affected_biomarkers: list[str]
    annotation_vi: str         # Context note (no prescribing advice)
    # Example: "LDL đang cải thiện — có thể phản ánh đáp ứng điều trị statin."
```

**Rules (static dict — no LLM):**
- statin → affects [ldl, total_cholesterol] → "LDL cải thiện có thể phản ánh đáp ứng với statin."
- metformin → affects [fasting_glucose, hba1c] → "Glucose/HbA1c được kiểm soát — phù hợp với điều trị metformin."
- levothyroxine → affects [tsh, ft4] → "Kết quả tuyến giáp cần xem xét trong bối cảnh đang dùng levothyroxine."
- Never recommend start/stop. Never say "your medication is working" (too clinical).

### 4.8 LifestyleRecommendation (Engine 8)

```python
@dataclass
class LifestyleRecommendation:
    rec_id: str
    category: str              # "diet" | "exercise" | "sleep" | "stress"
    title_vi: str
    detail_vi: str
    rationale_vi: str          # Why this rec for this patient
    priority: int              # 1-3 (1=most urgent)
    context_adaptations: list[str]  # e.g., ["vegetarian_adapted", "low_impact_exercise"]
```

**Context adaptation rules:**
- BMI ≥ 25: prioritize weight loss recs first
- Vegetarian (from lifestyle_profile): exclude red meat recs; add plant protein recs
- Already active (exercise_level="active"): suggest resistance training, not cardio
- Smoker: add smoking cessation rec as priority 1
- Elderly (age ≥ 70): prefer low-impact exercise, avoid aggressive dietary restriction

---

## 5. API Contract Changes

### 5.1 PatientInsightRequest v3

```python
class PatientContextInput(BaseModel):
    """Sent from frontend — supplements data from PatientProfile in DB."""
    sex: str | None = None          # "male" | "female"
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    waist_cm: float | None = None
    medications: list[str] | None = None   # free-text list ["statin", "metformin"]
    exercise_level: str | None = None      # "none"|"light"|"moderate"|"active"
    is_smoker: bool | None = None
    is_vegetarian: bool | None = None

class PatientInsightRequest(BaseModel):  # v3
    batch_id: str | None = None
    lab_result_ids: list[str] | None = None
    include_trends: bool = True
    include_patterns: bool = True
    include_derived: bool = True
    context: PatientContextInput | None = None   # ← NEW, replaces sex/age/waist_cm
    
    # Legacy compat (v1/v2 callers)
    sex: str | None = None
    age: int | None = None
    waist_cm: float | None = None
```

### 5.2 PatientInsightReport v3

```python
@dataclass
class PatientInsightReport:  # v3
    patient_id: str
    generated_at: str
    
    # v1 fields (kept, extended)
    overall_status: str
    overall_status_text_vi: str
    top_priorities: list[str]      # kept as list[str] for backward compat
    insights: list[InsightCard]
    action_cards: list[ActionCard]
    timeline: list[TimelineSummaryItem]
    positive_reinforcement: list[PositiveReinforcement]
    urgent_alerts: list[UrgentAlert]
    ai_draft_contract: str | None
    disclaimer_vi: str
    
    # v3 NEW fields (all optional for backward compat)
    health_story: HealthStory | None = None
    priorities: list[PriorityIssue] = field(default_factory=list)
    patterns: list[ClinicalPattern] = field(default_factory=list)
    trends: list[TrendAnalysis] = field(default_factory=list)
    goals: list[HealthGoal] = field(default_factory=list)
    medication_notes: list[MedicationAnnotation] = field(default_factory=list)
    lifestyle_recs: list[LifestyleRecommendation] = field(default_factory=list)
    context_completeness: float = 0.0
    missing_context: list[str] = field(default_factory=list)
```

---

## 6. DB Migration Requirements

### Required new fields on PatientProfile:
**No new DB migration needed for Phase 1** — existing fields suffice:
- `known_conditions` (EncryptedString) → parse for diabetes, hypertension, CVD flags
- `lifestyle_profile` (EncryptedString) → parse JSON for medications, exercise, diet
- `height_cm`, `weight_kg`, `waist_cm`, `gender` → already exist

**Phase 2 (future):** If we want structured medication storage:
- New table `patient_medications` (patient_id, medication_name, started_at, active)
- Or add `medications_json` column to PatientProfile

### Recommendation:
- **Phase 1:** Use `lifestyle_profile` JSON field + keyword parsing for medications/lifestyle
- This avoids any migration and lets us ship v3 engines without schema changes

---

## 7. File Structure (new files)

```
backend/app/domain/
  patient_context.py          ← Engine 1: PatientContext + PatientContextEngine
  clinical_patterns_v3.py     ← Engine 2: ClinicalPattern (extended PatternDetection)
  health_story.py             ← Engine 3: HealthStoryGenerator
  priority_engine.py          ← Engine 4: PriorityEngine
  longitudinal_v3.py          ← Engine 5: TrendAnalysis (extends BiomarkerTrend)
  health_goals.py             ← Engine 6: GoalEngine + HealthGoal
  medication_context.py       ← Engine 7: MedicationContextEngine
  lifestyle_engine.py         ← Engine 8: LifestyleEngine

backend/app/domain/  (MODIFIED files)
  patient_insight.py          ← Wire all 10 engines; update PatientInsightReport
  derived_metrics.py          ← Pass PatientContext to context-aware thresholds

backend/app/api/v1/routes/
  patient_insight.py          ← Update request/response schema (v3 compat)

frontend/src/lib/api/
  labInsight.ts               ← Extend types for v3 fields

frontend/src/app/(patient)/labs/[batchId]/
  insight/page.tsx            ← Add "My Health Story" section at top
  insight/[cardId]/page.tsx   ← Already v2; extend for goals/medication notes

frontend/src/app/(patient)/
  health-story/page.tsx       ← NEW: standalone Health Story dashboard
  
backend/tests/
  test_patient_context.py     ← Engine 1 tests
  test_clinical_patterns_v3.py ← Engine 2 tests
  test_health_story.py        ← Engine 3 tests
  test_priority_engine.py     ← Engine 4 tests
  test_health_goals.py        ← Engine 6 tests
  test_medication_context.py  ← Engine 7 tests
  test_lifestyle_engine.py    ← Engine 8 tests
```

---

## 8. Build Sequence — PTH APPROVED (2026-06-28)

**Build order = user value, not dependency order.**

### Phase 1 — Personalized Intelligence (Highest ROI)
**Engines:** E1 PersonalContextEngine + E2 CrossMarkerCorrelation + E4 PriorityEngine

1. `patient_context.py` — Engine 1: PatientContext + MedicationContextProvider interface
2. `clinical_patterns_v3.py` — Engine 2: upgraded cross-marker patterns (8+ patterns)
3. `priority_engine.py` — Engine 4: ranked PriorityIssue list with explanation
4. Update `patient_insight.py` + API route to wire E1, E2, E4
5. Tests: E1, E2, E4

**User impact:** Personalized interpretation. Better risk stratification. Top priorities explained.

### Phase 2 — Health Story + Trends
**Engines:** E5 LongitudinalEngine + E3 HealthStoryGenerator

6. `longitudinal_v3.py` — Engine 5: velocity, improvement rate, target_progress_pct
7. `health_story.py` — Engine 3: narrative + summary cards (template-based, no LLM)
8. Frontend: `/health-story` route (standalone, NOT inside insight detail)
9. Tests: E5, E3

**User impact:** Health Story. Trend. Improving/deteriorating at a glance.

### Phase 3 — Goals + Lifestyle
**Engines:** E6 GoalEngine + E8 LifestyleEngine

10. `health_goals.py` — Engine 6: auto-generate personalized targets + progress %
11. `lifestyle_engine.py` — Engine 8: context-adapted recs (vegetarian, BMI, exercise level)
12. Dashboard: Health Story card → `/health-story` (score + priorities + monthly focus)
13. Tests: E6, E8

**User impact:** Goals with progress. Monthly focus. Personalized action plan.

### Phase 4 — Completion + Polish
**Engines:** E7 MedicationContext + E9 Evidence + E10 Explainability + E11 + E12 + E13

14. `medication_context.py` — Engine 7: reads from MedicationContextProvider interface
15. `missing_data_intelligence.py` — Engine 11: "Nếu có HbA1c, AI sẽ..."
16. `preventive_screening.py` — Engine 12: age/sex/condition-based screening reminders
17. `health_confidence.py` — Engine 13: profile completeness score (not health score)
18. Final regression + ruff + TS

**User impact:** Full copilot experience. No unsafe gaps. Motivates data completion.

---

## 8b. UI Routing Decision — PTH APPROVED

| Page | Route | Purpose |
|------|-------|---------|
| Insight Detail | `/labs/[batchId]/insight/[cardId]` | "Tại sao LDL cao?" — single biomarker deep dive |
| **Health Story** | `/health-story` | "Sức khỏe của tôi diễn biến thế nào?" — whole-patient narrative |
| Dashboard card | existing dashboard | Shows: score + #1 priority + improving/worsening; taps → `/health-story` |

**Rationale (PTH decision):** Insight Detail and Health Story answer different mental models. Do NOT combine them. Insight Detail stays biomarker-centric. Health Story is patient-centric narrative.

---

## 8c. Engine Design Principles — PTH APPROVED

1. **No hardcoded per-biomarker logic in engines** — all rules go through engine + rule registry + context provider
2. **MedicationContextProvider interface** — Phase 1 reads from lifestyle_profile JSON; Phase 4 swaps to Medication module DB table. Engine interface unchanged.
3. **Extensible to other modules** — architecture must support: labs, medications, diagnoses, nutrition, wearables, chronic disease monitoring, periodic health checks
4. **Context-first** — every engine receives PatientContext; never operate on raw biomarker values without context

---

## 9. Additional Engines (PTH decision 2026-06-28)

### Engine 11 — Missing Data Intelligence

File: `missing_data_intelligence.py`

AI must know what it doesn't know — and convert missing data into action.

```python
@dataclass
class MissingDataSignal:
    missing_canonical: str           # "hba1c" | "apob" | "waist_cm"
    impact_vi: str                   # "Nếu có HbA1c, AI đánh giá kháng insulin chính xác hơn."
    alternative_used: str | None     # "Đang dùng Non-HDL thay thế ApoB."
    recommended_action_vi: str       # "Xét nghiệm HbA1c lần sau."
    priority: int                    # 1 = critical missing; 3 = nice to have
```

Logic: rule registry keyed by pattern/finding. If pattern `insulin_resistance` fires but `hba1c` missing → emit signal. If `apob` missing → emit "Non-HDL used as proxy".

### Engine 12 — Preventive Screening Engine

File: `preventive_screening.py`

Age/sex/condition-appropriate screening reminders. Only shown when clinically indicated.

```python
@dataclass
class ScreeningReminder:
    screening_id: str                # "colonoscopy" | "psa" | "mammogram" | ...
    title_vi: str
    indication_vi: str               # Why this patient needs it
    frequency_vi: str                # "Mỗi 10 năm"
    urgency: str                     # "routine" | "soon"
```

Rule registry example:
- age ≥ 50 + any sex → colonoscopy
- male ≥ 50 → PSA discussion
- female 40–74 → mammogram
- female 21–65 → Pap smear
- has_diabetes → microalbumin niệu + eye exam
- has_ckd → DEXA if on steroids

### Engine 13 — Health Confidence Score

File: `health_confidence.py`

**Not a health score. A data completeness score.**

```python
@dataclass
class HealthConfidenceReport:
    completeness_pct: float          # 0–100
    grade: str                       # "Cơ bản" | "Tốt" | "Đầy đủ" | "Toàn diện"
    missing_high_value: list[str]    # ["Huyết áp", "Vòng eo", "HbA1c", "ApoB"]
    explanation_vi: str              # "72% — Thêm huyết áp và vòng eo để AI phân tích chính xác hơn."
```

Scoring weights (sum to 100):
- Core lipids (LDL, HDL, TG, TC): 20 pts
- Glucose metabolism (glucose, HbA1c): 20 pts
- Liver (ALT, AST): 10 pts
- Kidney (creatinine, eGFR): 10 pts
- Blood pressure: 10 pts
- Biometrics (weight, height, waist): 10 pts
- Inflammation (CRP, ferritin): 5 pts
- Thyroid (TSH): 5 pts
- Advanced markers (ApoB, Lp(a), insulin): 10 pts

Displayed on: `/health-story` page + dashboard card. Motivates data completion.

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| PatientProfile.lifestyle_profile not populated for most users | High | High | Graceful degradation — context_completeness=0.0 → use v2 defaults |
| known_conditions parsing unreliable (free text) | Medium | Medium | Conservative keyword list; uncertain → treat as not-set; log missing_context |
| CV risk scoring too aggressive | Medium | High | Always use "có thể" / "gợi ý"; never say "bạn có nguy cơ cao" |
| Medication keyword list incomplete | Medium | Low | Whitelist only; unknown → skip (don't annotate) |
| Performance (10 engines × N lab results) | Low | Medium | All engines are O(N) or O(1); no DB calls inside engines; derived already cached |

---

## 11. Acceptance Criteria (from spec)

- [ ] Interpretation changes according to patient context (same LDL → different explanation for 28yo vs 68yo diabetic)
- [ ] AI produces one coherent health story instead of N isolated warnings
- [ ] Clinical patterns detected automatically (at least 8 patterns)
- [ ] Priority ranking generated with explanation
- [ ] Longitudinal trends explained (velocity + direction)
- [ ] Personalized goals generated automatically
- [ ] Recommendations adapt to patient profile (vegetarian, BMI, exercise level)
- [ ] Every conclusion exposes reasoning and evidence
- [ ] No unsafe medical advice (no diagnose, no prescribe, no stop medication)
- [ ] Architecture is modular (each engine independently testable)
- [ ] All tests pass; 0 ruff errors; 0 TS errors

---

*Architecture approved by PTH — 2026-06-28. Implementation begins Phase 1.*
