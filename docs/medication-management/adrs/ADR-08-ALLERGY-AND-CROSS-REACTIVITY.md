# ADR-08 — Allergy and Cross-Reactivity

**Status:** PROPOSED — Gate 2 (blocks production safety features — P3)  
**Date:** 2026-07-11  
**Deciders:** PTH, Clinical Advisor  
**Depends on:** ADR-01 (ingredient entities needed for linking)

---

## Context

Allergy data hiện tại trong MetoCare: `allergies` field trên `patient_profiles` — free text String. "Penicillin, dust mites, shellfish" lưu như một chuỗi văn bản.

Tài liệu P0–P4 đề xuất `patient_allergies` table mới với các fields: allergen_name, drug_catalog_id, active_ingredient, drug_class, reaction_type, severity, verified_by_doctor.

---

## Problem

Allergy data cần đủ để:
1. **Hard-stop check:** patient đang uống thuốc A, vừa thêm thuốc B có chứa allergen → CRITICAL warning
2. **Cross-reactivity check:** patient dị ứng Penicillin → system biết Cephalosporin có cross-reactivity risk
3. **Class-level allergy:** patient dị ứng "sulfonamides" (class) → tất cả sulfonamide drugs bị flagged
4. **Certainty tracking:** dị ứng đã được bác sĩ xác nhận vs bệnh nhân tự báo cáo → khác nhau về clinical action
5. **Reaction type:** IgE-mediated (anaphylaxis) vs non-IgE (rash, GI) → khác nhau về severity of warning

Nếu cross-reactivity không được model, system sẽ bỏ qua: patient dị ứng Penicillin nhưng được kê Amoxicillin → không alert.

---

## Decision Drivers

- Clinical safety: false negative allergy alert = potentially life-threatening
- Cross-reactivity must be modeled — not optional
- Certainty/source must be tracked for clinical decision
- IgE vs non-IgE distinction matters for severity
- Must work without external allergy DB initially (curated cross-reactivity rules)
- Vietnamese patient population: most common allergies = drug allergies (antibiotics, NSAIDs, sulfonamides, iodine contrast)
- Patient self-report ≠ verified allergy — UI must clearly differentiate

---

## Options Considered

### Option A — Free text only (current state)
Allergen as string. Cannot match algorithmically. Not viable.

### Option B — Structured allergy table, no cross-reactivity
`patient_allergies` with ingredient/class fields. Match directly. Misses cross-reactivity.

### Option C — Structured allergy table + cross-reactivity rule table
Allergy table + `allergy_cross_reactivity_rules` table with documented cross-reactivity pairs.

### Option D — Structured allergy table + external allergy API
Outsource cross-reactivity checking to clinical API (DrugBank, etc.).

---

## Trade-off Table

| Criterion | A (free text) | B (structured, no cross) | C (structured + cross rules) | D (external API) |
|-----------|---------------|--------------------------|------------------------------|-----------------|
| Direct allergy check | ❌ | ✅ | ✅ | ✅ |
| Cross-reactivity | ❌ | ❌ | ✅ | ✅ |
| IgE vs non-IgE | ❌ | ✅ | ✅ | ✅ |
| Certainty tracking | ❌ | ✅ | ✅ | ✅ |
| Infrastructure | ✅ None | ✅ None | ✅ None | ❌ API dependency |
| Clinical accuracy | ❌ Poor | ⚠️ Partial | ✅ Good for common pairs | ✅ Comprehensive |
| Licensed cost | ✅ Free | ✅ Free | ✅ Free (curated) | ❌ Paid |

---

## Recommended Decision

**Option C — Structured allergy table + curated cross-reactivity rules table.**

External API (Option D) is a stop gate for PTH budget decision, same as interaction engine.  
Without cross-reactivity (Option B), system would miss the clinically most important allergy scenarios.

---

## Consequences

**`patient_allergies` table (full schema):**
```sql
CREATE TABLE patient_allergies (
    id                      UUID PK,
    patient_id              VARCHAR(36) NOT NULL REFERENCES patient_profiles(id),

    -- Allergen identification
    allergen_type           VARCHAR(32) NOT NULL,
      -- drug_ingredient | drug_class | food | environmental | other
    allergen_name           VARCHAR(255) NOT NULL,  -- canonical name (INN for drugs)
    drug_ingredient_id      FK → drug_ingredients.id nullable,   -- ADR-01 dependency
    drug_class_id           FK → drug_classes.id nullable,        -- ADR-01 dependency

    -- Reaction characterization
    reaction_type           VARCHAR(64) nullable,
      -- anaphylaxis | urticaria | angioedema | rash | gi_reaction | respiratory | unknown
    reaction_mechanism      VARCHAR(32) nullable,
      -- ige_mediated | non_ige | cell_mediated | unknown
      -- IgE = higher severity, faster onset, anaphylaxis risk
    severity                VARCHAR(32) NOT NULL DEFAULT 'unknown',
      -- life_threatening | severe | moderate | mild | unknown

    -- Evidence and verification
    certainty               VARCHAR(32) NOT NULL DEFAULT 'suspected',
      -- confirmed | probable | suspected | unlikely | entered_in_error
    source                  VARCHAR(32) NOT NULL DEFAULT 'patient_reported',
      -- patient_reported | clinician_confirmed | hospital_record | lab_test | ocr_extracted
    verified_by_user_id     VARCHAR(36) nullable REFERENCES users(id),
    verified_at             DATETIME nullable,

    -- Temporal
    onset_date              DATE nullable,       -- when allergy first occurred
    last_occurrence_date    DATE nullable,       -- most recent reaction
    status                  VARCHAR(32) NOT NULL DEFAULT 'active',
      -- active | resolved | unknown | entered_in_error

    -- Documentation
    notes                   TEXT nullable,
    evidence_ref            VARCHAR(255) nullable,  -- e.g., hospital record ID, lab result ID

    created_at              DATETIME NOT NULL,
    updated_at              DATETIME NOT NULL,
    deleted_at              DATETIME nullable,

    INDEX (patient_id, allergen_type),
    INDEX (patient_id, drug_ingredient_id),
    INDEX (patient_id, drug_class_id)
);
```

**`allergy_cross_reactivity_rules` table:**
```sql
CREATE TABLE allergy_cross_reactivity_rules (
    id                    UUID PK,
    -- Allergen: patient is allergic to this
    source_ingredient_id  FK → drug_ingredients.id nullable,
    source_drug_class_id  FK → drug_classes.id nullable,
    -- Cross-reactive: system should warn about these
    target_ingredient_id  FK → drug_ingredients.id nullable,
    target_drug_class_id  FK → drug_classes.id nullable,
    -- Risk level
    cross_reactivity_type VARCHAR(32) NOT NULL,
      -- definite | probable | possible | theoretical
    mechanism             TEXT nullable,
    recommendation        TEXT NOT NULL,  -- what to tell patient/doctor
    evidence_level        VARCHAR(8) NOT NULL,
    source                VARCHAR(255) NOT NULL,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    rule_version          VARCHAR(16) NOT NULL
);
```

**MVP cross-reactivity rules (curated, clinically critical for VN metabolic patients):**

| Source allergy | Cross-reactive with | Type | Clinical importance |
|----------------|---------------------|------|---------------------|
| Penicillin (class) | Cephalosporins (class) | probable | IgE-mediated cross-reaction ~1-2% |
| Penicillin (class) | Carbapenems (class) | possible | Lower but significant |
| Sulfonamide antibiotic (class) | Sulfonamide diuretics (furosemide) | theoretical | Debated, include as warning |
| Aspirin (ingredient) | Other NSAIDs (class) | probable | COX-1 mechanism |
| Iodine/contrast (ingredient) | Shellfish allergy | theoretical | Common belief, limited evidence — include with disclaimer |
| Codeine (ingredient) | Other opioids (class) | possible | Cross-reactivity via pseudo-allergy |

**Warning level matrix based on allergy attributes:**

| certainty | reaction_mechanism | severity | → Warning level |
|-----------|-------------------|----------|----------------|
| confirmed | ige_mediated | life_threatening/severe | CRITICAL — hard stop |
| confirmed | any | severe/moderate | HIGH |
| probable | any | any | HIGH |
| suspected | any | any | MEDIUM |
| suspected + cross_reactivity_type=possible | | | LOW/informational |
| unlikely | any | any | Informational only |

**Hard stop vs soft warning:**
- CRITICAL: drug matches allergen, certainty=confirmed, severity=life_threatening → cannot be dismissed by patient, must require doctor acknowledgment
- HIGH: cannot be silently dismissed; requires "Tôi đã thông báo cho bác sĩ" button
- MEDIUM/LOW: dismissible with one tap, logged

**Check execution sequence:**
```
1. Direct ingredient match: patient_allergies.drug_ingredient_id IN medication.ingredients
2. Direct class match: patient_allergies.drug_class_id = medication.drug_class_id
3. Cross-reactivity lookup: for each patient allergy, query cross_reactivity_rules for targets
4. Generate ClinicalAlert per match
5. Deduplicate by (medication_id, allergen_id)
```

---

## Data Model Impact

- New: `patient_allergies` table (replaces free-text `allergies` field on patient_profiles)
- New: `allergy_cross_reactivity_rules` table
- Modify: `patient_profiles` — migrate free-text `allergies` → `patient_allergies` (data migration required)
- Requires ADR-01 `drug_ingredients` and `drug_classes` entities

**Free-text migration:**
- Existing `patient_profiles.allergies` text → parse → attempt catalog matching → insert as `patient_allergies` with `certainty='suspected'`, `source='patient_reported'`
- Patient prompted to review and confirm migrated allergies on first app open after migration

---

## API Impact

- `POST /patients/{id}/allergies` — create allergy (PATIENT, DOCTOR)
- `GET /patients/{id}/allergies` — list allergies (PATIENT, DOCTOR)
- `PATCH /patients/{id}/allergies/{aid}` — update (PATIENT, DOCTOR — doctor can set verified_by)
- `DELETE /patients/{id}/allergies/{aid}` — soft delete (PATIENT only)
- DOCTOR can set `certainty='confirmed'` and `source='clinician_confirmed'` — auto-sets `verified_by_user_id`

---

## Security and Privacy Impact

`patient_allergies` is highly sensitive PHI — reveals medical history.  
Access: PATIENT (own), DOCTOR (consent only), ADMIN.  
CAREGIVER: NO access (allergy information is clinical PHI, not appropriate for general caregiver).  
Audit log: all allergy write actions.

---

## Clinical Safety Impact

This is the highest-impact safety feature. Cross-reactivity for Penicillin → Cephalosporin alone covers a major patient safety risk. IgE distinction drives different clinical urgency.

Critical rule: `certainty='suspected'` patient-reported allergy must NOT be treated as "no allergy." It must trigger a warning at MEDIUM severity minimum. Clinician can downgrade to "unlikely" after review.

---

## Migration Impact

`patient_profiles.allergies` free-text → structured migration required. Plan:
1. Parse existing allergy text per patient (heuristic: comma-separated items)
2. Attempt catalog match per item (drug_ingredient or drug_class)
3. Insert with `certainty='suspected'`, `source='patient_reported'`
4. Patient sees "Xác nhận lại thông tin dị ứng" banner on next login
5. After confirmation period: deprecate `allergies` column on patient_profiles

---

## Operational Ownership

Cross-reactivity rules: Clinical Advisor owns content.  
Rule version bumps trigger re-evaluation of all patient allergies vs all active medications.

---

## Open Questions

1. **Penicillin allergy labeling:** Many patients in VN report "penicillin allergy" that may have been mislabeled (childhood reaction may be viral rash, not drug reaction). Should MetoCare include a "clarification prompt" encouraging patients to discuss with doctor? **[Clinical advisor recommendation needed]**
2. **Data migration of existing free-text allergies:** Patient population size and current allergy data quality? **[Tech Lead to assess before migration planning]**
3. **CAREGIVER allergy access:** Is there a case where caregiver should see allergy information? **[PTH product policy decision]**

---

## Approval Required From

- [ ] PTH — allergy table schema approval
- [ ] Clinical Advisor — cross-reactivity rule set (MVP list) sign-off before production
- [ ] Clinical Advisor — IgE mechanism distinction in warning severity
- [ ] Tech Lead — free-text allergy migration plan

## Implementation Gate

**Gate 2 — blocks production allergy safety features (P3).**  
ADR-01 must be approved first (need drug_ingredient_id and drug_class_id for allergy linking).  
Cross-reactivity rules require Clinical Advisor sign-off before production.
