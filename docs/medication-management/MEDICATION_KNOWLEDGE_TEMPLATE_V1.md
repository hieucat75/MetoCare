# Medication Knowledge Template v1.0

**Date:** 2026-07-16
**Author:** Claude Code (session following PR-A1a merge)
**Scope:** Content model design only. No code, no migration, no real clinical content, no citations. Every example below uses a fictional placeholder drug ("ExampleMed") — nothing here is a real medical claim about any real medication.
**Status:** **APPROVED WITH REVISIONS (PTH, 2026-07-16).** Governs Phase B authoring (5 MVP drugs) and every future drug added to the library.
**Related:** `adrs/ADR-13-KNOWLEDGE-CONTENT-LIFECYCLE.md`, `adrs/ADR-01-MEDICATION-KNOWLEDGE-STRUCTURE.md`, `MEDICATION_PHASE_A_PR_A1_IMPLEMENTATION_PLAN.md`, `MEDICATION_PHASE_A_BLOCKING_FINDINGS.md`, [[project_medication_knowledge_phase_ab]] (memory)

**Revision note (2026-07-16, PTH review):** the draft's biggest issue was §9.1/§9.5 — the original `common/uncommon/rare/serious` side-effect model conflated two independent axes: **frequency** (how often) and **action level** (what the patient should do about it). PTH's ruling, applied throughout this revision: split into `frequency ∈ {common, uncommon, rare, unknown}` and `action_level ∈ {self_monitor, contact_clinician, urgent_medical_help}` — a side effect can be simultaneously rare AND urgent, which the old single enum couldn't express. §9.2: keep `food_supplement_interactions` in Phase B; drop `drug_interactions_general` entirely — drug-drug interaction content waits for the real ADR-02 interaction engine, no parallel prose block. §9.3: theme vocabulary trimmed (drop `what_is_this`, redundant with `overview`; drop `drug_interactions_general`). §9.4: approved, `label VARCHAR(80) NOT NULL` (table is empty, no nullable-transition needed). §9.5: resolved by the frequency/action_level split itself — canonical model lives in the DB, frontend updates to match, no lossy 4-to-3 API mapping. New: 15 content types stay independently versioned in the data model, but the Patient App UI groups them into ~7 presentation sections (§11). A1b-F1 (schema completion) and A1b-F2 (specialty seed) are GO; A1b orchestrator itself still waits on both; Phase B content authoring is still NO-GO.

---

## Why this comes before A1b or Phase B content

A1a shipped the *mechanics* (load → validate → resolve identity). It did not settle the *shape* of a drug page — what sections exist, what each section's fields are, which fields the DB already supports vs. which need a schema decision. Authoring 5 real drugs against an unsettled shape risks a rewrite the moment drug #6 needs a section #1-5 didn't anticipate. This document settles the shape first.

Everything here is derived from what already exists (ADR-13's 5 knowledge tables, the Phase A input contract, the real Medication Companion frontend cards) — not invented from scratch. Every place this template needs something the schema doesn't yet support is called out explicitly in **§9 Open Decisions**, not silently assumed.

---

## 1. The Golden Drug Page — full structure

```
<Drug Name>                                                     [presentation group, §11]
├── 1. Overview                         (drug_patient_education, theme="overview")            [1]
├── 2. Why am I taking it?              (drug_patient_education, theme="purpose")              [1]
├── 3. How to take it                   (drug_usage)                                           [2]
├── 4. Missed dose                      (drug_patient_education, theme="missed_dose")          [2]
├── 5. Food & supplement interactions   (drug_patient_education, theme="food_supplement_interactions" — general education, NOT a drug-drug interaction engine, see §9.2) [3]
├── 6. Side effects
│   ├── frequency: common/uncommon/rare/unknown  ×  action_level: self_monitor/contact_clinician/urgent_medical_help
│   └── (drug_side_effects — two independent axes, not one severity enum; see revision note above and §9.1) [4]
├── 7. Monitoring                       (drug_monitoring)                                      [5]
├── 8. Contraindications                (drug_contraindications)                               [6]
├── 9. Patient education (general)      (drug_patient_education, theme="general")               [3]
├── 10. FAQ                             (drug_patient_education, theme="faq_<slug>" — one row per question, see §2.11) [7]
├── 11. References                      (aggregated from every section's `references`, deduped — not its own table, now a real structured relation per A1b-F1, see §2.13) [7]
├── 12. Knowledge metadata              (per-section provenance display — not a page-level rollup, see §2.14) [7]
└── 13. Disclaimer                      (fixed rendering-time constant, not stored — unchanged from Phase A's resolution) [7]
```

**Dropped from the original draft, per PTH's ruling:** "What is this medicine?" (redundant with Overview) and "Drug interactions (general)" (no parallel prose block ahead of the real interaction engine — see §9.2). 13 content-model sections now, not 15.

Sections 1-2, 4-5, 9-10 are all `drug_patient_education` rows distinguished by `theme` — this table is the workhorse of the page, not a single generic "education" blob. Sections 3, 6, 7, 8 map to their own dedicated ADR-13 tables. Sections 11-13 are rendering-layer concerns, not persisted knowledge items. The `[N]` tags map each section to its Patient App presentation group — see §11.

---

## 2. Section-by-section field specification

For each section: which table, which fields, and what's required.

### 2.1-2.3, 2.5-2.7, 2.11 — `drug_patient_education` (themed rows)

| Field | Type | Required | Notes |
|---|---|---|---|
| `theme` | normalized identifier | required | One of: `overview`, `what_is_this`, `purpose`, `missed_dose`, `food_interactions`, `drug_interactions_general`, `general`, or `faq_<slug>` |
| `locale` | `vi` (today) | required | |
| `audience` | `patient` \| `caregiver` | required | |
| `body` | text | required | The section's prose content |

Business key: `(drug_ingredient_id, theme, locale, audience)` — unchanged from ADR-13, already supports this section list without modification since `theme` is free-form (validated against a controlled list at the authoring-tooling layer, not a DB enum — see §9.3).

### 2.4 — `drug_usage`

| Field | Type | Required | Notes |
|---|---|---|---|
| `locale` / `audience` | as above | required | |
| `body` | text | required | Dosing, timing, route — the single canonical "how to take it" narrative. Business key is `(drug_ingredient_id, locale, audience)` — only ONE approved row per ingredient+locale+audience, so this section cannot be split into sub-themes the way patient_education can (this is why "missed dose" lives in patient_education instead, not here). |

### 2.8 — `drug_side_effects` (one row per distinct side effect; grouped by `action_level` for display, per PTH's ruling)

**Two independent axes, not one severity enum** (this was the draft's core error, corrected per PTH's 2026-07-16 review):

| Field | Type | Required | Notes |
|---|---|---|---|
| `frequency` | `common` \| `uncommon` \| `rare` \| `unknown` | required | How often this side effect occurs. Purely epidemiological — carries no instruction about what to do. |
| `action_level` | `self_monitor` \| `contact_clinician` \| `urgent_medical_help` | required | What the patient should do if they notice it. Independent of frequency — a *rare* side effect can still be *urgent*. This is safety information from an authoritative source, not a diagnosis or prescription. |
| `concept_code` | normalized identifier | required | e.g. `nausea`, `dizziness`. **Business key is now `(drug_ingredient_id, concept_code)` alone** — not `(ingredient, level, concept_code)` as in the pre-revision draft. One canonical row per named side effect per drug; frequency and action_level are attributes of that one fact, not partition keys. |
| `label` | `VARCHAR(80)` | **required** | Short chip-style label for `SideEffectsCard`'s `items: string[]` — approved §9.4. |
| `description` | text | required | The full patient-facing explanation. |

**UI grouping** (per PTH): the Patient App groups side effects by `action_level` into three bands — "Thường gặp, có thể theo dõi" (self_monitor), "Nên trao đổi với bác sĩ/dược sĩ" (contact_clinician), "Cần hỗ trợ y tế ngay" (urgent_medical_help) — with `frequency` shown as a secondary badge within each band, not as the primary grouping axis.

### 2.9 — `drug_monitoring`

| Field | Type | Required | Notes |
|---|---|---|---|
| `parameter` | short text | required | e.g. a lab test or vital name |
| `patient_context` | short text | required | e.g. `baseline` vs a specific patient situation |
| `guidance` | text | required | What the monitoring is for, in patient language — never "you should get X test," always framed as "your doctor may monitor X because..." |

### 2.10 — `drug_contraindications`

| Field | Type | Required | Notes |
|---|---|---|---|
| `condition_type` | short text | required | e.g. a category of condition |
| `condition_key` | normalized identifier | required | business-key field |
| `condition_detail` | text | required | Patient-facing explanation, framed as "tell your doctor if..." never "do not take if..." (MetoCare is not a prescribing system) |

### 2.12 — FAQ (`drug_patient_education`, `theme="faq_<slug>"`)

Each FAQ question is its own `drug_patient_education` row, themed `faq_<slug>` (e.g. `faq_can_i_take_with_food`). This reuses the existing schema with zero new fields — no new "FAQ table" or "array of Q&A pairs" field needed. Rationale: each FAQ answer can then be independently versioned/reviewed (one wrong FAQ answer doesn't force re-review of the whole FAQ set), and the `theme` field already supports unlimited rows per ingredient.

`body` for an FAQ row should itself contain the question as a leading line, then the answer — see §6 example.

### 2.13 — References

Not a section with its own knowledge rows. At render time, the page aggregates the `references` list from every section actually shown on the page, deduplicates by `(publisher, title, publication_date)`, and renders one combined bibliography. This is exactly the `references:` structure already built in Phase A's `schema.py` — **persistence of this list is Finding 1, still open** (see `MEDICATION_PHASE_A_BLOCKING_FINDINGS.md`). Until Finding 1 resolves, references exist in the versioned authoring source files but are not queryable from the live repository.

### 2.14 — Knowledge metadata

Displayed **per section**, not as one page-level rollup — different sections legitimately have different `source`/`version`/`reviewed_at` values, and collapsing them to a single date would misrepresent whichever section is actually stale. Rendered from each row's existing provenance fields (`source`, `version`, `evidence_level`, `last_reviewed_at`) — no new fields needed.

### 2.15 — Disclaimer

Unchanged from Phase A: a fixed constant, appended at render time, never stored per-row, never author-editable. See Phase A plan §3 for the exact required text.

---

## 3. Required vs optional — summary matrix

| Field (applies to every knowledge row, any table) | Required? |
|---|---|
| Content field (`body`/`description`/`guidance`/`condition_detail`) | **Required** |
| `source`, `version`, `evidence_level`, `reviewed_at`, `authored_by` | **Required** (already enforced structurally by Phase A's `schema.py`) |
| `references` (min 1 structured citation) | **Required** |
| `ai_generated: false` | **Required, fixed value** |
| `disclaimer.acknowledged: true` | **Required, fixed value** |
| `specialty_codes` | Optional (empty unless a section genuinely needs specialist sign-off) |
| Side effect `label` (§9.4) | **Required once the field exists** — currently a schema gap |

No section in the Golden Page is itself optional at the *template* level — but a specific drug's *page* can omit a section if there's genuinely nothing to say (e.g. a drug with no notable food interactions can skip section 6 entirely rather than authoring a placeholder "none known" row).

---

## 4. Patient-facing vs internal vs future-Meto/Context-Engine fields

**Read this section as forward-looking design classification, not a current wiring plan.** Per K1's dormancy discipline (still in force — A1b-F1/F2 unresolved, no Knowledge API exists), **zero fields are readable by any AI system today.** This table exists so that when K2 (Knowledge API) and K4 (Context Engine) eventually get their own separate GO, the access boundary is already thought through rather than improvised under time pressure.

| Field category | Patient-facing (K2, future) | Internal only, never rendered/read | Meto Insight / Context Engine candidate (K4, future — NOT live) |
|---|---|---|---|
| Content (`body`/`description`/`guidance`/`condition_detail`) | ✅ | | Usage/education narrative: low value as a structured AI signal (it's prose, not data) — not a strong K4 candidate |
| `level` / `concept_code` (side effects) | ✅ | | ✅ — candidate for future symptom-correlation insight (e.g. patient logs a symptom that matches a known side effect of a drug they're on) — correlation only, never a recommendation to stop/change |
| `parameter` / `patient_context` (monitoring) | ✅ | | ✅ — candidate for correlating a patient's lab trends with what their medication's monitoring guidance says matters |
| `condition_key` / `condition_type` (contraindications) | ✅ | | ✅ — candidate for a future "worth discussing with your doctor" flag, never an autonomous safety block |
| `references` | ✅ (citation display) | | Low value as an AI signal — citation metadata, not clinical content |
| `source`, `version`, `evidence_level`, `last_reviewed_at` | ✅ (shown per-section) | | Could inform Meto's confidence framing ("based on guidance last reviewed in 2026") if K4 ever explains its own sourcing — speculative |
| `authored_by`, `status_changed_by`, `status_changed_at`, row `id` | | ✅ | |
| `specialty_codes`, specialty review records | | ✅ | |
| `ai_generated`, `disclaimer.acknowledged` | | ✅ (validation-only flags, never rendered as content) | |

**Non-negotiable restated for this table specifically:** even in the K4-candidate column, nothing here authorizes AI to recommend starting, stopping, or changing a medication. The strongest future use is *correlation and surfacing*, never *instruction*.

---

## 5. JSON/YAML authoring template (canonical)

This extends Phase A's already-built `schema.py` input contract (`metadata` / `content` / `references` / `review_metadata` / `disclaimer`) with the Golden Page's `theme` vocabulary and the new `label` field for side effects. No field here is new relative to Phase A except `label` (§9.4, flagged) and the closed `theme` vocabulary (§9.3, flagged).

```yaml
metadata:
  knowledge_type: patient_education        # usage | patient_education | side_effect | monitoring | contraindication
  medication_identity:
    name_inn: examplemed                   # placeholder — resolves to a real drug_ingredients row
  locale: vi
  audience: patient

content:
  theme: purpose                           # only for patient_education rows — closed vocabulary, §9.3
  body: >
    [PLACEHOLDER — patient-facing prose explaining why this medicine is prescribed.
    No real clinical content in this template document.]

references:
  - publisher: "[Placeholder Publisher]"
    title: "[Placeholder Reference Title]"
    source_type: formulary
    url: "https://example.invalid/placeholder-reference"
    publication_date: "2024-01-01"
    source_version: "2024"
    accessed_at: "2026-07-01"

review_metadata:
  source: "[Placeholder Source Name]"
  version: "1.0.0"
  evidence_level: moderate
  reviewed_at: "2026-07-01"
  authored_by: "content-team@metocare.me"
  ai_generated: false
  specialty_codes: []

disclaimer:
  acknowledged: true
```

For a `side_effect` row, `content` becomes:

```yaml
content:
  level: common                            # common | uncommon | serious (rare exists in DB, folded into uncommon for display — §9.1)
  concept_code: placeholder_symptom        # normalized identifier
  label: "[Placeholder short label]"       # NEW field, not yet in DB — §9.4
  description: >
    [PLACEHOLDER — full patient-facing explanation of this side effect.]
```

---

## 6. Complete placeholder example — "ExampleMed"

A fictional drug, used only to show the full page assembled from its constituent authoring files. No real medical facts anywhere below.

```yaml
# examplemed__patient_education__purpose.yaml
metadata:
  knowledge_type: patient_education
  medication_identity: { name_inn: examplemed }
  locale: vi
  audience: patient
content:
  theme: purpose
  body: >
    [PLACEHOLDER] ExampleMed is prescribed to help manage [placeholder condition].
    Your doctor has chosen this specific medicine based on your individual health needs.
references:
  - publisher: "[Placeholder Publisher]"
    title: "[Placeholder Formulary Entry]"
    source_type: formulary
    url: "https://example.invalid/examplemed"
    publication_date: "2024-01-01"
    source_version: "2024"
    accessed_at: "2026-07-01"
review_metadata:
  source: "[Placeholder Source]"
  version: "1.0.0"
  evidence_level: moderate
  reviewed_at: "2026-07-01"
  authored_by: "content-team@metocare.me"
  ai_generated: false
  specialty_codes: []
disclaimer: { acknowledged: true }

---
# examplemed__usage.yaml
metadata:
  knowledge_type: usage
  medication_identity: { name_inn: examplemed }
  locale: vi
  audience: patient
content:
  body: >
    [PLACEHOLDER] Take ExampleMed as directed by your doctor, generally at the same
    time each day. [Placeholder timing/route detail.]
references: [ ... same shape as above ... ]
review_metadata: { ... }
disclaimer: { acknowledged: true }

---
# examplemed__patient_education__missed_dose.yaml
content:
  theme: missed_dose
  body: >
    [PLACEHOLDER] If you miss a dose, [placeholder guidance]. Do not take a double
    dose to make up for a missed one. If you're unsure, contact your pharmacist or
    doctor rather than guessing.
# (rest of file same shape)

---
# examplemed__side_effect__placeholder_symptom_a.yaml
content:
  level: common
  concept_code: placeholder_symptom_a
  label: "[Placeholder symptom A]"
  description: >
    [PLACEHOLDER] Some people notice [placeholder symptom A] when starting this
    medicine. This is usually mild and improves over time.
# (rest of file same shape)

---
# examplemed__monitoring__placeholder_parameter.yaml
content:
  parameter: "[Placeholder lab parameter]"
  patient_context: baseline
  guidance: >
    [PLACEHOLDER] Your doctor may check [placeholder parameter] periodically while
    you're taking this medicine, to make sure it's working well for you.
# (rest of file same shape)
```

**Rendered page (patient-facing, illustrative only):**

```
ExampleMed
──────────
Overview: [placeholder]
What is this medicine?: [placeholder]
Why am I taking it?: [PLACEHOLDER — purpose text above]
How to take it: [PLACEHOLDER — usage text above]
Missed dose: [PLACEHOLDER — missed-dose text above]
Food & supplement interactions: [placeholder, if authored]
Drug interactions (general): [placeholder, if authored]
Side effects
  Common: [Placeholder symptom A] — [PLACEHOLDER description]
  Uncommon: [placeholder, if authored]
  Serious: [placeholder, if authored]
Monitoring: [PLACEHOLDER parameter] — [PLACEHOLDER guidance]
Contraindications: [placeholder, if authored]
Patient education (general): [placeholder, if authored]
FAQ: [placeholder, if authored]
References: [Placeholder Publisher] — [Placeholder Formulary Entry] (2024) [+ others, deduped]
Last reviewed: 2026-07-01 (Purpose section) · 2026-07-01 (Usage section) · ...
Disclaimer: [fixed constant text — see Phase A plan §3]
```

---

## 7. Mapping to existing Medication Companion cards

Grounded in the actual frontend components (`frontend/src/components/patient/medications/`, PRs #119-122), not assumed:

| Companion card | Current state | Golden Template field(s) it will eventually consume |
|---|---|---|
| `UsageInstructionsCard` (`usage-instructions.tsx`) | Real `note` (patient-authored) rendered; `guidance` section is a **hardcoded empty-state constant** — the component's own comment says "DrugEntry has no structured dosing-instructions field" | Section 4 (`drug_usage.body`) is exactly what fills that gap once K2 exists. `note` stays patient-authored and separate — the template does not touch it. |
| `SideEffectsCard` (`side-effects-card.tsx`) | `groups: MedicationSideEffectGroup[]` hardcoded to `[]` ("structure only"). Expects `{ level, items: string[], evidenceLabel? }` | Section 8. **Vocabulary mismatch found**: card's `SideEffectLevel` is `common \| uncommon \| urgent`; DB's is `common \| uncommon \| rare \| serious`. `items: string[]` wants short labels — matches the new `label` field proposed in §9.4, not the DB's long-form `description`. Both gaps are flagged in §9, not silently papered over. |
| `InteractionsCard` (`interactions-card.tsx`) | `interactions: MedicationInteraction[]` hardcoded to `[]`. Expects `{ severity: 'high'\|'moderate'\|'low', interactingSubstance, mechanism?, effect?, recommendation?, evidenceLabel?, evidenceUrl? }` — a fully structured interaction-rule shape | This card's shape is **not** satisfied by section 6/7's general-education content — it expects the real structured interaction engine (severity, mechanism, a specific interacting substance). That engine is `drug_interactions`, explicitly deferred past K1 to a future ADR-02-compliant phase (K5 per roadmap). Sections 6/7 of the Golden Page are a *different, narrower* thing (general prose education) that this card cannot render as-is — a future PR would need either a second, simpler card for general interaction education, or to wait for the real engine. |
| `TodayStatusCard` (`today-status.tsx`) | Real data, adherence-only | No overlap — this card is patient's own adherence tracking, not drug reference knowledge. Out of this template's scope entirely. |
| Medication Hero (inline in `page.tsx`) | Real data, action hierarchy | No overlap — same reasoning as above. |

**Key finding for Phase B and beyond:** authoring "Drug interactions (general)" content (section 7) does **not** unblock the `InteractionsCard` as it exists today — that card is purpose-built for the structured engine, not prose. This should be flagged to whoever scopes K5, not solved here.

---

## 8. Scaling to 500+ drugs without a schema change

The structural scaling story is already sound — every mechanism below already exists in the shipped K1 schema or Phase A tooling, none of it needs a new table to go from 5 to 500 drugs:

1. **Identity resolution scales linearly.** `drug_ingredients`/`drug_classes`/`drug_products` are just more rows; `provenance.resolve_medication_identity`'s exact-match-or-fail-closed lookup (Phase A) doesn't degrade with row count (indexed FK lookup).
2. **Authoring throughput is a tooling problem, already being solved.** A1b's orchestrator (batch import, transactional validate-then-write) is exactly what makes authoring hundreds of files tractable instead of one-by-one manual entry.
3. **Business-key + content-hash idempotency (Phase A §4) prevents duplicate/conflicting versions from accumulating as more drugs and more content-update cycles pile up** — this was designed generally, not per-drug.
4. **`concept_code`/`condition_key`'s normalized-identifier pattern** (added during A1a's Codex review fix) keeps side-effect/contraindication vocabularies from drifting into near-duplicate strings as more authors contribute across more drugs. Recommend a periodic (not per-PR) cross-drug audit query — "list all distinct `concept_code` values, flag near-duplicates" — as a lightweight process addition once past ~50 drugs, not a schema addition.
5. **`drug_classes.parent_class_id` (self-referential hierarchy) already supports class-level grouping** (e.g., every drug in a class sharing a common side-effect profile). At 500 drugs, this becomes genuinely useful — a future enhancement (not required now) could let a knowledge row's business key optionally scope to `drug_class_id` instead of `drug_ingredient_id` for content that's truly class-wide, avoiding N copies of identical class-level content across N ingredients. This is a **future optimization idea, not a current requirement** — flagged for awareness, not proposed as a change to make now.
6. **`locale` already supports multi-language expansion** without a schema change (currently `vi`-only by validator choice, not by column constraint).
7. **Specialty review routing** (`drug_classes.required_specialties` → `knowledge_review_specialties`) already scales as a data-driven config, not code — adding a new class's required specialties is a data change, not a schema change.

**What does NOT scale for free, and needs a process decision (not a schema decision) before 500 drugs:** clinical review throughput. The template and tooling can ingest content fast; a Clinical Advisor's ability to review it before anything reaches `approved` is a human bottleneck this document cannot solve. Flagging this as a known constraint for whoever plans K1.5/K2 capacity, not proposing a fix here.

---

## 11. UI presentation grouping (Patient App)

13 content-model sections stay independently versioned/reviewed in the data model — that granularity is for content governance, not for the patient's eyes. Per PTH's ruling, the Patient App groups them into **7 presentation sections**:

1. Tổng quan (Overview + Purpose)
2. Cách sử dụng (Usage + Missed dose)
3. Thực phẩm và sản phẩm cần lưu ý (Food/supplement interactions + General patient education)
4. Tác dụng phụ (Side effects, grouped by `action_level` per §2.8)
5. Theo dõi (Monitoring)
6. Điều cần báo cho bác sĩ (Contraindications)
7. FAQ, nguồn và thông tin cập nhật (FAQ + References + Knowledge metadata)

This is a rendering-layer grouping only — no schema or content-model change. A future frontend PR (out of scope here) implements this grouping; this document just fixes the mapping so content authors and frontend engineers build against the same plan.

---

## 9. Open decisions — RESOLVED (PTH, 2026-07-16)

Original open questions and their resolutions, kept for record:

### 9.1 — Is "Emergency" a real severity tier, or does "Serious" cover it?

The original Golden Page sketch had `Common / Serious / Emergency`. The shipped DB schema has `common / uncommon / rare / serious` (4 tiers, no "emergency"). Recommend **not** adding an "Emergency" tier: MetoCare is explicitly not a prescribing/triage system, and a formal "this is an emergency" classification edges toward clinical instruction-giving territory that should get its own compliance review before it exists anywhere in the schema. Proposed resolution: "serious" side effects' `description` text can include "seek care promptly" framing *within the prose*, without a separate DB-level emergency category. **Needs PTH confirmation** — this is a content-policy call, not just a technical one.

### 9.2 — "Food interactions" / "Drug interactions (general)" vs. the real interaction engine

The Golden Page sketch's "Food interactions" and "Drug interactions" sections are, in the current schema, general educational prose (`drug_patient_education` themes) — **not** connected to any structured interaction-rule engine (that's `drug_interactions`, deferred to K5). This template treats them as two genuinely different things sharing a page position. **Needs PTH confirmation** that general educational prose about interactions is an acceptable Phase B deliverable even though it won't power the `InteractionsCard`'s structured UI (§7) — or whether Phase B should skip these sections entirely until K5 exists, to avoid two visually-similar-but-functionally-different "interaction" surfaces confusing patients later.

### 9.3 — `theme` is a closed vocabulary for `drug_patient_education`, but the DB doesn't enforce it

The DB column is free-text `String`. This template proposes a closed set (`overview`, `what_is_this`, `purpose`, `missed_dose`, `food_interactions`, `drug_interactions_general`, `general`, `faq_<slug>`) — enforcement of this list belongs in the authoring-tooling validator (A1b, when it's built), not the DB schema, matching this project's established pattern (DB enforces invariants, application enforces authorship rules). **Needs PTH confirmation** on the exact theme list before A1b's validator hardcodes it.

### 9.4 — Side effects need a short `label` field the DB doesn't have yet

`SideEffectsCard`'s `items: string[]` wants short chip-style labels; the DB only has long-form `description`. This is a genuine, small schema gap (one new nullable-or-required `label VARCHAR(~80)` column on `drug_side_effects`) — **not solved in this document**, since this document is design-only. Recommend folding this into the same A1b-F1 migration PR that adds structured reference persistence, since both are schema additions to the same table family and doing them in one migration is more efficient than two. **Needs PTH confirmation** before that migration is scoped.

### 9.5 — Side-effect severity vocabulary mismatch (DB vs. frontend)

DB: `common / uncommon / rare / serious`. Frontend (`SideEffectsCard`): `common / uncommon / urgent`. These need to converge before section 8 can actually render through the existing card. Two options: (a) a future frontend PR renames `urgent` → `serious` and adds `rare` (mapped to `uncommon` for display, per §9.1's "fold rare into uncommon" recommendation) to match the DB exactly; (b) a future K2 API-layer mapping translates DB's 4 values down to the frontend's 3 at read time. **Needs PTH confirmation** on which side changes — flagged here so it's a conscious decision when K2 gets scoped, not a surprise integration bug.

---

## 10. Explicit restatement of scope

This document designs a content model. It does not:
- Write any migration (§9.4's proposed `label` column is a *recommendation for a future PR*, not built here).
- Author any real drug content (every example above is fictional/placeholder).
- Cite any real medical source.
- Wire anything to an API, frontend, or AI system.
- Authorize starting A1b, A1b-F1, A1b-F2, or Phase B. Those each still need their own explicit GO per the existing governance pattern.
