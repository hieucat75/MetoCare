# ADR-02 — Drug Interaction Engine

**Status:** PROPOSED — Gate 2 (blocks production safety features)  
**Date:** 2026-07-11  
**Revision:** 2026-07-11 (PTH review — typed clinical rules, not class-only)  
**Deciders:** PTH, Clinical Advisor, Tech Lead  
**Depends on:** ADR-01 (ingredient entities must exist before this is meaningful)

---

## Context

MetoCare cần detect drug-drug interactions khi patient thêm thuốc. Hiện tại: zero implementation. Tài liệu P0-P4 đề xuất "50 hardcoded interaction pairs" dưới dạng `drug_interaction_rules` table với `ingredient_a`, `ingredient_b` string fields.

Câu hỏi kiến trúc: hardcoded pairs, rule engine, pathway-based engine, hay external API?

---

## Problem

**Hardcoded 50 pairs là dead end vì:**
1. Không scale: bệnh nhân metabolic trung bình dùng 6–8 drugs → n*(n-1)/2 pairs cần check. 50 pairs cover < 5% clinically relevant interactions cho population này.
2. Không maintainable: mỗi drug mới thêm vào catalog, team phải manually identify và add tất cả pairs với existing drugs.
3. Không có mechanism: "warfarin + aspirin = HIGH severity" là verdict, không phải explanation. AI không thể explain tại sao nếu không có mechanism.
4. Ingredient string matching: nếu `ingredient_a = "warfarin"` nhưng patient medication có `active_ingredient = "Warfarin sodium"`, pair không match.
5. Class-level interactions bị miss: tất cả NSAIDs tương tác với warfarin — nhưng nếu chỉ có pairs, phải add 15+ rows (ibuprofen, naproxen, diclofenac...).

---

## Decision Drivers

- Patient safety: false negatives (missed interactions) là unacceptable
- MetoCare không xây hệ thống kê đơn tự động — CDS là warning/advisory, không phải block
- Must work with existing PostgreSQL/SQLite — no new infrastructure
- Vietnamese metabolic patient population: ~100 drugs cover 95% of use cases
- AI Copilot cần mechanism data để explain interactions in plain Vietnamese
- Evidence must be citable — cannot hallucinate interaction severity
- Vietnamese MoH does not publish structured interaction database publicly
- Budget: licensed commercial DB (DrugBank Enterprise, Lexicomp) = stop gate for PTH approval

---

## Options Considered

### Option A — Hardcoded pair table (ingredient_a, ingredient_b, severity)
Simple. Dead end. Already rejected above.

### Option B — Structured rule engine with ingredient-based and class-based rules (original)
`interaction_rules` table where rules can be:
- `ingredient_pair`: exact ingredient match
- `drug_class_pair`: any drug in class A + any drug in class B

**PTH review note:** "Class-based interaction là hữu ích, nhưng không thể là mô hình duy nhất." Class-based là một *selector* trong typed rule model, không phải toàn bộ model. Option B như mô tả ban đầu vẫn thiếu typed rule selectors, route-specific rules, và dose-dependent rules.
- `ingredient_class`: specific ingredient + any drug in a class

### Option C — Pathway/mechanism-based engine
Model CYP enzyme pathways. Detect interactions transitively: if Drug A inhibits CYP3A4 and Drug B is CYP3A4 substrate, flag interaction.

### Option D — External API (DrugBank, Lexicomp, MIMS Vietnam)
Real-time or batch lookup. Accurate. Licensed.

### Option E — Hybrid: Option B + pathway extension hooks (original)
Build Option B first. Design schema to add pathway data later without rewrite.

### Option F — Typed clinical rule engine (revised per PTH review)
Rule schema supports multiple subject types (not just class-based). Each rule has:
- `subject_a_type` / `subject_b_type`: `ingredient | drug_class | medicinal_product | route | patient_condition | lab_threshold`
- `subject_a_id` / `subject_b_id`: FK to corresponding entity table
- Rule can be bidirectional or directional (A affects B, not necessarily B affects A)
- `condition_expression` (nullable JSON): optional clinical precondition (e.g., dose > 10mg, eGFR < 45)
- Pathway hooks: `cyp_enzyme` field for CYP pathway data when available

This is functionally a superset of Option E. The difference: class-based is ONE selector type among several, not the primary organizing concept.

---

## Trade-off Table

| Criterion | A (pairs) | B (rule engine) | C (pathway) | D (external API) | E (hybrid B+C hooks) |
|-----------|-----------|-----------------|-------------|------------------|----------------------|
| Coverage for 100-drug catalog | ❌ Low | ✅ High | ✅ Very high | ✅ Comprehensive | ✅ High |
| Maintainability | ❌ Manual | ⚠️ Moderate | ❌ Complex | ✅ Outsourced | ✅ Moderate |
| Class-level interaction | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Mechanism data for AI | ❌ No | ✅ Yes (structured) | ✅ Yes | ✅ Yes | ✅ Yes |
| Infrastructure | ✅ None | ✅ None | ✅ None | ⚠️ API dependency | ✅ None |
| Licensing cost | ✅ Free | ✅ Free (curated) | ✅ Free | ❌ Paid | ✅ Free initially |
| Time to implement | ✅ Days | ⚠️ 2–3 weeks | ❌ Months | ⚠️ Integration work | ⚠️ 3–4 weeks |
| Clinical accuracy | ❌ Poor | ⚠️ Depends on curation | ✅ High | ✅ High | ✅ Good |

---

## Recommended Decision

**Option F — Typed clinical rule engine with multi-subject selectors.**

Build now: typed rule engine where class-based is ONE selector type among several.  
Design schema to add pathway/condition data later without schema change.  
External API: evaluate at 400+ drug scale, treat as stop gate for PTH decision.

---

## Why This Option (revised per PTH review)

**PTH's critique is correct:** "Class-based interaction rất hữu ích nhưng không thể là mô hình duy nhất." Many interactions are:
- `ingredient–ingredient` only (e.g., warfarin + metronidazole)
- `ingredient–class` (e.g., warfarin + any NSAID)
- `class–class` (e.g., any sulfonamide + any sulfonamide-diuretic)
- route-specific (e.g., only for IV, not oral)
- dose-dependent (e.g., only when Colchicine > 0.5mg/day)
- lab-dependent (e.g., only when eGFR < 45)
- patient condition-dependent (e.g., only when patient has G6PD deficiency)

A class-only engine would need to create artificial "classes" to capture ingredient-level specificity, which is wrong abstraction.

Typed rule selectors solve this cleanly: each rule declares its subject types, and the engine resolves the appropriate entity IDs at check time. Class-based remains the most common selector for MVP rules — but not the only one.

Option C (pathway) still not feasible without licensed metabolic pathway data.  
Option D still a stop gate — but Option F schema is compatible with importing DrugBank data into the same structure.

---

## Consequences

**Typed Clinical Rule Schema (revised):**
```sql
CREATE TABLE drug_interaction_rules (
    id                  UUID PRIMARY KEY,

    -- Subject A: who/what this rule applies to (one side of the interaction)
    subject_a_type      VARCHAR(32) NOT NULL,
    -- Values: ingredient | drug_class | medicinal_product | route | patient_condition | lab_threshold
    subject_a_id        UUID nullable,
    -- FK to drug_ingredients, drug_classes, or medicinal_products depending on subject_a_type
    -- NULL when subject_a_type = patient_condition or lab_threshold (use condition_json instead)

    -- Subject B: the other side of the interaction
    subject_b_type      VARCHAR(32) NOT NULL,
    subject_b_id        UUID nullable,

    -- Directionality
    is_bidirectional    BOOLEAN NOT NULL DEFAULT TRUE,
    -- FALSE: A affects B only (e.g., drug A reduces absorption of drug B, not vice versa)

    -- Optional clinical precondition (structured JSON, nullable)
    condition_json      JSONB nullable,
    -- Examples:
    -- {"type": "dose_threshold", "subject": "a", "operator": ">", "value": 0.5, "unit": "mg"}
    -- {"type": "lab_value", "lab": "eGFR", "operator": "<", "value": 45, "unit": "mL/min"}
    -- {"type": "route", "route": "IV"}  -- only applies for IV route
    -- {"type": "patient_condition", "icd10": "D55.0"}  -- G6PD deficiency
    -- NULL = rule applies unconditionally

    -- Interaction outcome
    severity            VARCHAR(16) NOT NULL,
    -- Values: contraindicated | major | moderate | minor

    -- Mechanism (for AI explanation and clinical advisor review)
    mechanism_type      VARCHAR(32) nullable,
    -- Values: pharmacokinetic | pharmacodynamic | additive | unknown
    mechanism_subtype   VARCHAR(64) nullable,
    -- For pharmacokinetic: CYP3A4_inhibition | CYP2C9_substrate | P_glycoprotein | absorption | etc.
    mechanism_detail    TEXT nullable,  -- plain English/Vietnamese explanation
    cyp_enzyme          VARCHAR(32) nullable,  -- e.g., CYP3A4, CYP2C19 (for pathway extension)

    -- Clinical outcomes (in Vietnamese for patient-facing display)
    clinical_effect     TEXT NOT NULL,     -- what can happen
    management          TEXT NOT NULL,     -- recommended action
    patient_message     TEXT nullable,     -- simplified patient-language version

    -- Evidence and governance
    evidence_level      VARCHAR(16) NOT NULL,
    -- Values: A | B | C | expert_opinion | traditional_use
    source              VARCHAR(255) NOT NULL,
    -- e.g., "curated:metocare-v1.0" | "drugbank-open:v5" | "mims-vn:2026-q1"
    rule_set_version    VARCHAR(16) NOT NULL,  -- bump for re-evaluation
    approved_by         VARCHAR(255) nullable,  -- clinical advisor who signed off
    approved_at         DATETIME nullable,
    valid_from          DATE nullable,
    valid_until         DATE nullable,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,

    created_at          DATETIME NOT NULL,
    updated_at          DATETIME NOT NULL,

    -- Soft constraint via application: subject_a_id and subject_b_id must match their _type
    -- Cannot use DB FK without polymorphic FK support — enforce at service layer
    INDEX (subject_a_type, subject_a_id),
    INDEX (subject_b_type, subject_b_id),
    INDEX (severity, is_active)
);
```

**Engine Resolution Logic (typed, runs at service layer):**
```python
def check_interactions(
    patient_medication_ids: list[str],
    patient_condition_codes: list[str],  # ICD-10 codes from patient profile
    recent_labs: dict[str, float],        # lab code → most recent value
    db: Session
) -> list[InteractionAlert]:

    # 1. Resolve patient's ingredient_ids and drug_class_ids from medication list
    patient_ingredients = resolve_ingredients(patient_medication_ids, db)
    patient_classes = resolve_drug_classes(patient_medication_ids, db)
    patient_routes = resolve_routes(patient_medication_ids, db)

    # 2. Query rules: subject_a or subject_b matches patient's ingredients/classes
    # This is a broader query — then condition_json evaluated in Python
    candidate_rules = query_candidate_rules(
        ingredients=patient_ingredients,
        drug_classes=patient_classes,
        db=db
    )

    # 3. Evaluate condition_json for each candidate rule
    triggered_rules = []
    for rule in candidate_rules:
        if evaluate_condition(rule.condition_json, recent_labs, patient_condition_codes):
            triggered_rules.append(rule)

    # 4. Map triggered rules → InteractionAlert (include involved medication IDs)
    # 5. Deduplicate by (medication_a_id, medication_b_id, rule_type)
    # 6. Return sorted by severity DESC
    return build_alerts(triggered_rules, patient_medication_ids)
```

**Condition evaluation examples:**
```python
def evaluate_condition(condition_json, labs, patient_conditions) -> bool:
    if condition_json is None:
        return True  # unconditional rule always triggers

    match condition_json["type"]:
        case "dose_threshold":
            # Evaluate if patient's dose of subject drug exceeds threshold
            # If dose unknown: return True (conservative — assume condition met)
            ...
        case "lab_value":
            lab_value = labs.get(condition_json["lab"])
            if lab_value is None:
                return False  # cannot evaluate — do not trigger without evidence
            return eval_operator(lab_value, condition_json["operator"], condition_json["value"])
        case "patient_condition":
            return condition_json["icd10"] in patient_conditions
        case "route":
            return condition_json["route"] in patient_routes
```

**Note on MVP rules:** All MVP rules will use `condition_json = NULL` (unconditional). The condition evaluation engine exists to handle future rules without schema change.

**Severity mapping to clinical action:**
| Severity | Display | Patient action | Doctor action |
|----------|---------|----------------|---------------|
| contraindicated | 🔴 Không nên dùng chung | Phải hỏi bác sĩ ngay | Review required |
| major | 🟠 Nguy cơ cao | Hỏi bác sĩ trước lần uống tiếp | Flag for review |
| moderate | 🟡 Cần theo dõi | Thông báo cho bác sĩ biết | Informational |
| minor | ⚪ Thông tin | Tham khảo | No action needed |

**Initial curated rule set (MVP):**
Priority: drugs in current 41-drug catalog. Class-based rules preferred where applicable.
- Anticoagulant class + Antiplatelet class = major (bleeding risk)
- Statin class + Fibrate class = moderate (myopathy risk)
- SGLT2i class + Loop diuretic class = moderate (dehydration)
- ACEi/ARB class + K-sparing diuretic class = major (hyperkalemia)
- Metformin (ingredient) + iodine contrast (note: not in catalog — flag as informational only)
- Levothyroxine (ingredient) + Calcium/Iron/Antacid class = moderate (absorption)
- Warfarin (ingredient) + NSAID class = major
- Colchicine (ingredient) + Strong CYP3A4 inhibitors class = major
- Sulfonylurea class + Fluoroquinolone class = moderate (dysglycemia)
- Beta-blocker class + Non-DHP calcium channel blocker class = major (heart block)

Estimated: ~20 class-based rules cover ~80% of clinically relevant interactions for MetoCare patient population.

---

## Data Model Impact

- ADR-01 ingredient entities are prerequisite
- `drug_interactions` replaces `drug_interaction_rules` (not yet created)
- Patient medication record needs `drug_ingredient_ids` resolvable from `drug_product_id` FK

---

## API Impact

- No new public endpoints needed in MVP
- CDS engine calls this internally
- Future: `GET /patients/{id}/medications/interactions` — surface current active interactions

---

## Security and Privacy Impact

- `drug_interactions` is reference data, not PHI
- Interaction check result (alert) is PHI-adjacent: derived from patient's medication list
- Alerts stored in `medication_alerts` table: patient_id-scoped, access-controlled

---

## Clinical Safety Impact

**If class-based rules are wrong (false positive):** Patient unnecessarily alarmed. Doctor clarifies. Acceptable.  
**If rule is missing (false negative):** Patient not warned. This is the main risk.

Mitigation:
- All rules have `evidence_level` — LOW evidence rules shown with explicit disclaimer
- Missing coverage disclaimer: "Hệ thống chỉ kiểm tra tương tác trong danh mục thuốc MetoCare. Hỏi dược sĩ để kiểm tra đầy đủ hơn."
- Vietnamese doctor must review MVP rule set before production (stop gate)

---

## Migration Impact

No existing data to migrate. New table. Safe.

---

## Operational Ownership

- Clinical Advisor owns rule set content
- Tech team owns rule schema and engine code
- Rule set updates: PR review → clinical sign-off → version bump → re-evaluate existing alerts for affected patients

---

## Open Questions

1. **MIMS Vietnam:** Does MetoCare have budget/license to use MIMS Vietnam interaction database? This would provide authoritative VN-localized interaction data. **[PTH decision required — stop gate if yes]**
2. **DrugBank Open:** Free tier provides basic interaction data with attribution. Legal for commercial use? **[Legal review required before import]**
3. **Clinical review timeline:** Who is the designated Vietnamese clinical advisor to sign off on MVP rule set? **[PTH must identify before P3 start]**

---

## Approval Required From

- [ ] PTH — engine strategy (class-based rule engine vs external API)
- [ ] PTH — budget decision on MIMS Vietnam or DrugBank licensed tier
- [ ] Clinical Advisor — review and sign off on MVP rule set before production
- [ ] Tech Lead — engine placement (domain service, not frontend)

## Implementation Gate

**Gate 2 — blocks production safety features (P3).**  
ADR-01 must be approved and ingredient entities must exist before this ADR can be implemented.  
Clinical advisor sign-off required before any interaction rule goes to production users.
