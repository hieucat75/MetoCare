# ADR-13 — Knowledge Content Lifecycle

**Status:** ✅ ACCEPTED (PTH, 2026-07-15). History: Proposed (2026-07-15) → approved in substance after K0 review round 1 (2026-07-15) → **Accepted** after K1 Pre-Validation update, following the business-key policy and test-fixture-removal revisions in round 2 (2026-07-15). See `MEDICATION_K1_PRE_VALIDATION.md` for the gate record.
**Date:** 2026-07-15 (revised twice same day per PTH review rounds 1 and 2; Accepted same day)
**Deciders:** PTH (product), Tech Lead, Clinical Advisor

---

## ADR Metadata

| Field | Value |
|-------|-------|
| ADR | ADR-13 |
| Status | Accepted |
| Architecture Version | medication-architecture-v1.1 |
| Implementation Gate | Gate 1 — cleared. K1 schema/migration work may proceed on this ADR's basis. |
| Domain | Knowledge Governance |
| Supersedes | None (extends ADR-01's provenance columns) |
| Superseded By | None |

---

## Context

ADR-01 gave every knowledge table (`drug_usage`, `drug_side_effects`, `drug_monitoring`, `drug_contraindications`, `drug_interactions`, and the newly proposed `drug_patient_education` — see the K0 architecture doc revision) a provenance mixin: `source`, `version`, `evidence_level`, `reviewed_by`, `last_reviewed_at`. That answers **who last touched this row and how trustworthy is it**, but not **is this row safe to show a patient right now**.

PTH's K0 review flagged this gap directly: content needs a `status` field, not just a reviewer name.

## Problem

Without an explicit lifecycle status:

1. There is no way to author a row (e.g. a newly-curated `drug_usage` entry) without it being immediately visible via `GET /medications/{id}/knowledge` — `reviewed_by` NOT NULL only proves *someone* touched it, not that clinical review is complete.
2. There is no safe way to **update** approved content. Editing an approved row in place destroys the audit trail of what patients actually saw on a given date — unacceptable for a clinical-safety-adjacent feature.
3. There is no way to **retire** outdated guidance (e.g. a monitoring parameter that changes after a clinical guideline update) without hard-deleting history.
4. `reviewed_by` alone doesn't route review by specialty — a Clinical Pharmacy reviewer signing off on an Endocrinology-specific Levothyroxine caution is a real risk PTH called out separately (see the K0 doc's Knowledge Source revision, `review_specialty`).

## Options Considered

### Option A — Keep only `reviewed_by` + `last_reviewed_at` (status quo from K0 v1.0)
No explicit state machine; "reviewed" is inferred from a non-null reviewer.

### Option B — Single boolean `is_approved`
Binary gate: content is either live or not.

### Option C — Full lifecycle enum with append-only versioning
`draft → clinical_review → approved → deprecated → retired`. Editing approved content always creates a new row; the old row transitions to `deprecated` rather than being mutated or deleted.

### Option D — External CMS/workflow tool owns lifecycle, DB just mirrors final state
A separate content-management system outside the app database drives review state.

---

## Trade-off Table

| Criterion | A (status quo) | B (boolean) | C (full enum, append-only) | D (external CMS) |
|-----------|-----------------|-------------|------------------------------|-------------------|
| Prevents unreviewed content reaching patients | ❌ No enforced gate | ✅ Yes | ✅ Yes | ✅ Yes |
| Preserves what-patient-saw-when audit trail | ❌ No | ❌ Overwrites in place | ✅ Append-only | ✅ (if CMS versions) |
| Supports specialty-routed review | ❌ No | ❌ No | ✅ Yes (paired w/ `review_specialty`) | ✅ Yes |
| Safe content updates without downtime/data loss | ❌ Risky | ⚠️ Risky (still mutates) | ✅ Safe | ✅ Safe |
| Infra/ops cost | ✅ None | ✅ None | ✅ None (just a column + service rule) | ❌ New system, new integration |
| Migration friction | ✅ None | ⚠️ Small | ⚠️ Small (one column + service logic) | ❌ Large |
| Matches existing codebase idiom | — | — | ✅ Yes — mirrors `Medication` notes' append-only pattern already used elsewhere | ❌ No precedent |

---

## Recommended Decision

**Option C — Full lifecycle enum, append-only versioning.**

## Why This Option

The append-only pattern is not new to this codebase — `Medication` notes already preserve history rather than overwriting (per existing product conventions this session has repeatedly observed). Applying the same idiom to knowledge content keeps behavior consistent and auditable: a patient who was shown a since-corrected side-effect warning can always be traced back to exactly what version they saw and when.

A boolean (Option B) would stop unreviewed content from leaking, but the moment content needs correcting, it either mutates history (audit gap) or forces a parallel versioning scheme to be bolted on later — better to build it in at K1 than retrofit after real content exists.

## Consequences

**Schema — add to the shared provenance mixin (applies to every knowledge table from ADR-01 §2.2 plus the new `drug_patient_education` table):**

```
status              VARCHAR(16) NOT NULL DEFAULT 'draft'
                     -- CHECK IN ('draft','clinical_review','approved','deprecated','retired')
status_changed_at   TIMESTAMPTZ NOT NULL
status_changed_by   VARCHAR(255) NOT NULL
authored_by         VARCHAR(255) NOT NULL   -- distinct from status_changed_by at approval time — see self-approval rule below
```

**`review_specialty` is NOT a free-text column** (revised per PTH review round 1 — see addendum). It is a controlled vocabulary plus a many-to-many join, since one knowledge item can require sign-off from more than one specialty:

```
clinical_specialties (
    id, code VARCHAR(32) UNIQUE,   -- 'clinical_pharmacy' | 'endocrinology' | 'cardiology' |
                                    -- 'internal_medicine' | 'nephrology' | 'obstetrics' | 'pediatrics' | ...
    display_name_vi, display_name_en, is_active
)

knowledge_review_specialties (
    id,
    knowledge_table   VARCHAR(32),   -- 'drug_usage' | 'drug_patient_education' | 'drug_side_effects' |
                                       -- 'drug_monitoring' | 'drug_contraindications' | 'drug_interactions'
    knowledge_row_id  UUID,          -- FK target resolved by knowledge_table, not a single physical FK
                                       -- (polymorphic association — acceptable here because this table
                                       -- is metadata-about-review, never joined for clinical content itself)
    specialty_id      → clinical_specialties.id,
    reviewed_by        VARCHAR(255) NOT NULL,
    reviewed_at         TIMESTAMPTZ NOT NULL
)
-- A knowledge row only reaches 'approved' once EVERY required specialty for its drug_class
-- (a separate, small config table: drug_classes.required_specialties[]) has a row here.
```

**Transition rules (enforced in the service layer, not left to the client):**
- `draft → clinical_review`: any authenticated content author.
- `clinical_review → approved`: only a role-scoped Clinical Advisor action; requires a `knowledge_review_specialties` row for every specialty the drug's class requires. **Self-approval is blocked at the service layer:** `status_changed_by` (the approver) may never equal `authored_by` (who wrote/last edited the row) for a `clinical_review → approved` transition. The only exception is a logged, PTH-approved override for cases where MetoCare has exactly one advisor covering a specialty and no second reviewer exists yet — the override reason and PTH's sign-off are stored on the transition row itself, not silently allowed.
- `approved → deprecated`: automatic when a newer `approved` row exists for the same `(drug_ingredient_id, knowledge table)` — the old row is never deleted or edited.
- `deprecated → retired`: manual, after a grace period (exact period is a K1.5 operational decision, not architectural).
- No transition ever skips `clinical_review` — a `draft` row can never become `approved` directly, even by an admin.

**API impact:** `GET /medications/{id}/knowledge` (per the K0 API design) filters `status = 'approved'` unconditionally at the query layer — this is not a parameter clients can override. Draft/in-review content is visible only through an internal authoring/QA surface, out of scope for K0–K3.

**Migration impact:** additive columns only, default `'draft'`. Existing seed/migrated content (the 41-drug catalog carryover) must be explicitly walked through `clinical_review → approved` by the Clinical Advisor before K1 is considered complete — it does not inherit `approved` status automatically just because it migrated cleanly.

## Per-Table Business Key & Uniqueness Policy (PTH review round 2, 2026-07-15)

The transition rules above establish that at most one `approved` row may be active "for a given unit of knowledge" — but "unit of knowledge" is not the same shape for every table, and a single generic `(drug_ingredient_id)` uniqueness key is wrong: a single ingredient legitimately has *many* concurrently-approved rows in most of these tables (multiple side effects, multiple monitoring parameters, multiple interaction partners). The uniqueness constraint must be scoped to each table's actual business key — the thing that, when a new version replaces it, is genuinely "the same fact being updated" rather than "a different fact being added."

| Table | Business key (unique among `status='approved'` rows) | Why |
|-------|--------------------------------------------------------|-----|
| `drug_usage` | `(drug_ingredient_id, locale, audience)` | One usage narrative per ingredient per language/audience variant — genuinely a single fact being versioned. |
| `drug_patient_education` | `(drug_ingredient_id, theme, locale, audience)` | Multiple education messages coexist per ingredient (per `theme`, e.g. `hormone_replacement`, `chronic_disease_context`) — `theme` scopes each to its own independently-versioned slot, `locale`/`audience` as usage. |
| `drug_side_effects` | `(drug_ingredient_id, level, concept_code)` | Many side effects coexist per ingredient+level (nausea, headache, dry mouth are all independently `common`). `concept_code` is a new short normalized identifier (distinct from the free-text `description`) so "update the description of nausea" doesn't collide with "add a new common side effect." |
| `drug_monitoring` | `(drug_ingredient_id, parameter, patient_context)` | The same `parameter` (e.g. "eGFR") can need different monitoring guidance under different `patient_context` (e.g. `baseline` vs `renal_impaired`) — those are different facts, not versions of the same fact. |
| `drug_contraindications` | `(drug_ingredient_id, condition_type, condition_key)` | Multiple contraindications can share a `condition_type` (e.g. two different renal thresholds). `condition_key` is a new short normalized identifier (e.g. `egfr_lt_30`) distinct from the free-text `condition_detail`. |
| `drug_interactions` | `(canonical_pair_key)` — a computed, normalized key over `(subject_a_type, subject_a_id, subject_b_type, subject_b_id)`, sorted so a bidirectional rule for A↔B produces the same key regardless of insert order | Matches ADR-02's existing rule identity; prevents the same interaction pair from having two independently-approved rows that could disagree. |

**Schema impact:** `drug_side_effects` and `drug_contraindications` each gain one new short-code column (`concept_code`, `condition_key` respectively) beyond what K0 §7 specified — these are controlled, normalized identifiers, not free text, and are what the uniqueness index actually keys on (the human-readable `description`/`condition_detail` fields remain free text for display). `drug_interactions` gains a computed `canonical_pair_key` column populated at write time by the service layer (never client-supplied). The partial unique index in every case is `WHERE status = 'approved'` over the table's business key, not over `drug_ingredient_id` alone.

## Production Schema Must Not Encode "Test Data" (PTH review round 2, 2026-07-15)

The database schema enforces approval **invariants**, not environment provenance:
- an `approved` row must have `reviewed_by` set
- an `approved` row must have a `knowledge_review_specialties` row for every specialty its drug's class requires (per `drug_class_required_specialties`)
- `authored_by` must differ from `status_changed_by` at approval (except the logged PTH-approved override)
- `evidence_level`, `source`, `version`, `last_reviewed_at` must be present

The schema does **not** know what "test fixture" means, and no CHECK constraint may reference `source` patterns, environment names, or any other "this is test data" marker. Keeping test content out of `approved` is enforced entirely outside the database:
- **Seed convention:** fixture-loading scripts only ever call the draft-insert path (Section on transition rules) and never have credentials capable of performing a `clinical_review → approved` transition.
- **CI guard:** a pipeline check fails the build if a migration or seed diff introduces any `status='approved'` row outside of an explicit, reviewed content-release step.
- **Environment-scoped permission:** the service-layer role capable of approving content does not exist in test/CI environments at all — there is no reviewer identity to invoke the transition with, independent of any schema-level marker.

## PTH Review Round 1 Addendum (2026-07-15)

PTH approved this ADR's substance in the K0 review round, with two required refinements, both now incorporated above:

1. **`review_specialty` must be a controlled vocabulary with many-to-many support**, not free text — a knowledge item can require more than one specialty's sign-off (e.g. a drug relevant to both endocrinology and nephrology). Resolved via `clinical_specialties` (lookup) + `knowledge_review_specialties` (join), see Consequences.
2. **Authors may not approve their own content**, except via a logged, PTH-approved exception. Resolved via the `authored_by` vs `status_changed_by` distinction in the transition rules.

PTH's explicit condition for this ADR to move from "approved in substance" to formally **Accepted**: it must reach that status *before K1 creates production schema* — this is a K1 pre-validation gate, not a documentation formality. See the K1 Implementation Plan + Pre-Validation doc for how this gate is tracked.

## Approval Required From

- [ ] PTH — lifecycle states and transition rules (substance approved 2026-07-15; formal Accepted status still pending)
- [ ] Clinical Advisor — confirms `clinical_review → approved` is a role they can gate, and that specialty routing is workable given how many advisors MetoCare has access to (ties to OQ-7 / OQ-8, see index)

## Implementation Gate

**Gate 1 — blocks all knowledge-table writes.** No `drug_usage`/`drug_side_effects`/`drug_monitoring`/`drug_contraindications`/`drug_patient_education`/`drug_interactions` row may be created without the `status` column existing and the API-layer `status='approved'` filter in place. This must land in K1, not be retrofitted after content exists.
