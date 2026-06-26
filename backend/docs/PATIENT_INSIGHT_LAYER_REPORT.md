# Patient Insight Layer — Phase E Report

## Status

COMPLETE

---

## Architecture

```
Verified LabResult rows (DB)
        ↓
[Lab Intelligence Pipeline]
  • assess_biomarker()      → list[ClinicalFinding]
  • compute_all_derived()   → dict[str, DerivedMetricResult]
  • detect_patterns()       → list[PatternDetection]
  • compute_trends()        → list[BiomarkerTrend]
        ↓
[Patient Insight Layer]   app/domain/patient_insight.py
  generate_patient_insight()
  • _build_urgent_alerts()        → UrgentAlert[]
  • _derive_overall_status()      → str (good/attention/action_required/urgent)
  • _build_insight_cards()        → InsightCard[] (max 5, sorted by importance)
  • _build_action_cards()         → ActionCard[]
  • _build_timeline()             → TimelineSummaryItem[]
  • _build_positive_reinforcement() → PositiveReinforcement[]
        ↓
[API Route]               app/api/v1/routes/patient_insight.py
  POST /api/v1/patients/{patient_id}/patient-insight
  → dataclasses.asdict(PatientInsightReport) → JSON
```

### Design Principles Applied
- **Rule-based only** — zero LLM calls, fully deterministic
- **Mobile-first Vietnamese** — all user-facing text in Vietnamese
- **Safety-first** — disclaimer always present; no diagnosis language in alerts
- **Verified-only** — only processes `verified_by_user=True` OR `verified_by_doctor=True` records (enforced upstream)
- **Graceful degradation** — never crashes on empty input; returns valid minimal report
- **Extensible** — `ai_draft_contract: None` slot reserved for Phase 2 LLM drafting

---

## API

| Property | Value |
|---|---|
| **Method** | POST |
| **Endpoint** | `/api/v1/patients/{patient_id}/patient-insight` |
| **Auth** | Bearer token; roles: PATIENT, DOCTOR, INTERNAL_ADMIN |
| **Patient restriction** | Patients may only access their own records (403 otherwise) |
| **Doctor/Admin** | Requires `consent.require_access(scope="lab")` |

### Request Body (`LabIntelligenceRequest` — reused from lab_intelligence)
```json
{
  "lab_result_ids": null,
  "include_trends": true,
  "include_patterns": true,
  "include_derived": true,
  "age_years": 58,
  "is_male": true,
  "waist_cm": null
}
```

### Response Shape
JSON-serialized `PatientInsightReport` (via `dataclasses.asdict`).

---

## Sample Output

Realistic JSON for a patient with mixed findings (high fasting glucose, elevated LDL, improving trend):

```json
{
  "patient_id": "patient-abc-123",
  "generated_at": "2026-06-26T16:45:00+00:00",
  "overall_status": "action_required",
  "overall_status_text_vi": "Cần hành động — có mẫu hình đáng lo ngại.",
  "top_priorities": [
    "insight_fasting_glucose_high",
    "insight_ldl_high",
    "pattern_dyslipidemia"
  ],
  "insights": [
    {
      "card_id": "insight_fasting_glucose_high",
      "title_vi": "Đường huyết lúc đói đang cao hơn mức bình thường",
      "explanation_vi": "Đường huyết đang cao và cần bác sĩ xem xét thêm.",
      "importance": "high",
      "supporting_biomarkers": ["fasting_glucose"],
      "trend": "improving",
      "recommended_action": "discuss_with_doctor",
      "action_text_vi": "Trao đổi với bác sĩ trong lần khám tới."
    },
    {
      "card_id": "insight_ldl_high",
      "title_vi": "LDL Cholesterol đang cao hơn mức bình thường",
      "explanation_vi": "LDL đang cao, có thể làm tăng nguy cơ tim mạch.",
      "importance": "high",
      "supporting_biomarkers": ["ldl"],
      "trend": "stable",
      "recommended_action": "discuss_with_doctor",
      "action_text_vi": "Trao đổi với bác sĩ trong lần khám tới."
    },
    {
      "card_id": "pattern_dyslipidemia",
      "title_vi": "Rối loạn lipid máu",
      "explanation_vi": "Có mẫu hình rối loạn lipid máu.",
      "importance": "medium",
      "supporting_biomarkers": ["ldl_friedewald", "triglyceride"],
      "trend": "stable",
      "recommended_action": "repeat_lab",
      "action_text_vi": "Nên xét nghiệm lại theo lịch định kỳ."
    }
  ],
  "action_cards": [
    {
      "action_id": "repeat_glucose",
      "title_vi": "Xét nghiệm đường huyết lại",
      "detail_vi": "Kiểm tra lại đường huyết lúc đói và HbA1c sau 1 tháng.",
      "interval_days": 30,
      "action_type": "repeat_lab"
    },
    {
      "action_id": "repeat_lipid_panel",
      "title_vi": "Xét nghiệm lipid định kỳ",
      "detail_vi": "Kiểm tra lại bộ mỡ máu (LDL, HDL, Triglyceride) sau 3 tháng.",
      "interval_days": 90,
      "action_type": "repeat_lab"
    }
  ],
  "timeline": [
    {
      "canonical": "fasting_glucose",
      "display_name_vi": "Đường huyết lúc đói",
      "trend": "improving",
      "trend_text_vi": "Đang cải thiện",
      "change_pct": -10.0
    }
  ],
  "positive_reinforcement": [
    {
      "message_vi": "Đường huyết lúc đói đã cải thiện so với lần đo trước. Hãy duy trì lối sống lành mạnh!",
      "biomarkers": ["fasting_glucose"]
    }
  ],
  "urgent_alerts": [],
  "ai_draft_contract": null,
  "disclaimer_vi": "Đây là thông tin tham khảo từ kết quả xét nghiệm đã được xác nhận. Không phải chẩn đoán y khoa. Luôn tham khảo ý kiến bác sĩ trước khi thay đổi chế độ điều trị."
}
```

---

## Tests

**File:** `tests/test_patient_insight.py`  
**Count:** 37 tests, all passed

| Test | Coverage |
|---|---|
| `test_overall_status_urgent` | critical → "urgent" |
| `test_overall_status_action_required` | warning pattern → "action_required" |
| `test_overall_status_attention` | abnormal finding → "attention" |
| `test_overall_status_good` | all normal → "good" |
| `test_overall_status_good_empty` | no findings → "good" |
| `test_urgent_alert_generated` | critical finding → len(urgent_alerts) >= 1 |
| `test_no_urgent_alert_on_warning` | warning → no alert |
| `test_multiple_critical_findings_produce_multiple_alerts` | 2 critical → 2 alerts |
| `test_insight_cards_max_5` | 10 findings → max 5 cards |
| `test_insights_sorted_by_importance` | high before medium before low |
| `test_normal_info_findings_produce_no_insight_cards` | normal findings → 0 cards |
| `test_pattern_produces_insight_card` | pattern → card with pattern_* id |
| `test_abnormal_derived_produces_insight_card` | abnormal derived → card |
| `test_action_cards_doctor_visit_on_critical` | critical → doctor_visit, interval=0 |
| `test_action_cards_lipid_panel_on_lipid_abnormal` | LDL warning → repeat_lipid_panel |
| `test_action_cards_continue_monitoring_when_all_normal` | all normal → continue_monitoring |
| `test_action_cards_glucose_on_glucose_abnormal` | glucose abnormal → repeat_glucose |
| `test_action_cards_kidney_on_kidney_abnormal` | creatinine → repeat_kidney |
| `test_timeline_conversion` | BiomarkerTrend → TimelineSummaryItem 1:1 |
| `test_timeline_trend_text_vi` | trend text Vietnamese strings |
| `test_timeline_change_pct_preserved` | change_pct passthrough |
| `test_positive_reinforcement_on_improving` | improving trend → positive message |
| `test_no_positive_reinforcement_on_stable` | stable → no message |
| `test_no_positive_reinforcement_on_worsening` | worsening → no message |
| `test_disclaimer_always_present` | disclaimer always non-empty |
| `test_disclaimer_content` | disclaimer contains "tham khảo" + "bác sĩ" |
| `test_no_lapse_on_empty_inputs` | empty inputs → no crash, valid report |
| `test_ai_draft_contract_null` | ai_draft_contract == None |
| `test_ai_draft_contract_null_with_findings` | None even with real data |
| `test_top_priorities_max_3` | top_priorities len <= 3 |
| `test_top_priorities_are_card_ids` | all priority IDs in insights |
| `test_top_priorities_empty_when_no_abnormal` | normal → empty priorities |
| `test_report_patient_id_preserved` | patient_id passthrough |
| `test_report_generated_at_is_iso8601` | generated_at parseable |
| `test_insight_card_fields` | all required fields, correct types |
| `test_urgent_alert_never_diagnoses` | "chẩn đoán" not in action_vi |
| `test_asdict_serializable` | dataclasses.asdict runs without error |

**Full suite (excl. migrations):** 1310 passed, 1 pre-existing failed (`test_lab_reference::test_catalog_covers_all_ocr_canonicals` — calcium missing from catalog, unrelated to Phase E).

---

## Known Limitations

1. **No diagnosis gap explanation** — InsightCards reuse `patient_explanation_vi` directly from `ClinicalFinding`. Future versions could add more layered explanations per card_id.
2. **Pattern-level trend is aggregate** — `_collective_trend()` across supporting biomarkers is heuristic; per-pattern longitudinal tracking would require dedicated pattern history.
3. **`dataclasses.asdict` serializes `datetime.date` objects inside `BiomarkerTrend.data_points`** — these are nested as raw `date` objects, which are not JSON-serializable by default. The API layer would need a custom encoder if `timeline` items include data_points (currently omitted from `TimelineSummaryItem`).
4. **No unit test for the API route HTTP layer** — the domain function is fully tested; route-level integration tests would require DB fixtures.
5. **Derived metric card deduplication with biomarker card** — if both a biomarker finding AND a derived metric produce a card for the same organ system, both appear. Max-5 cap provides natural mitigation.

---

## Next Phase

**Phase F — Personalized Health Goals**

Build a `PatientGoalEngine` that:
- Accepts `PatientInsightReport` + patient's personal health goals (weight, glucose target, etc.)
- Generates `GoalProgress` objects showing % toward each goal
- Tracks 3-month rolling window of goal adherence
- Produces a `GoalSummaryCard` (top of dashboard, above InsightCards)
- Integrates with Action Cards to suggest goal-aligned lifestyle reminders
- Remains rule-based; LLM coaching text deferred to Phase G

This would complete the "See → Understand → Act → Track" loop for MetoCare patients.
