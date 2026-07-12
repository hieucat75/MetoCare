# MEDICATION_ADR_DECISION_SUMMARY.md
# MetoCare Medication Platform — Architecture Decision Summary

**Version:** 1.2  
**Date:** 2026-07-11  
**Revision:** 2026-07-11 (v1.2) — `verification_status` value `doctor_confirmed` → `clinician_confirmed` across all ADRs. `source_type` confirmed as independent field (không phải là verification_status). P0 Implementation Plan created.  
**Purpose:** Tóm tắt 12 ADR cho PTH để phê duyệt trước khi bắt đầu implementation.

---

## 1. Một Dòng Verdict Cho Từng ADR

| ADR | Title | Verdict | Recommended Option | Gate |
|-----|-------|---------|-------------------|------|
| ADR-01 | Medication Knowledge Structure | Flat JSON catalog → relational hierarchy | Hybrid: normalized core + JSON extensions | Gate 1 |
| ADR-02 | Drug Interaction Engine | 50 hardcoded pairs → typed clinical rule engine | Typed rules: ingredient/class/route/condition selectors — not class-only | Gate 2 |
| ADR-03 | Medication History & Timeline | `updated_at` only → snapshot + event log | Snapshot-on-write + lightweight event table | Gate 1 |
| ADR-04 | Medication Reconciliation | No reconciliation → provenance-first two-table model | Both tables at P0: `medication_statements` + canonical `medications` from day 1 | Gate 1 |
| ADR-05 | OCR Medication Pipeline | Reuse lab OCR → separate pipeline | Cloud Vision OCR + LLM parse, mandatory human review | Gate 3 |
| ADR-06 | Traditional Medicine & Supplements | Boolean flag → taxonomy enum | `medication_category` 9-value enum, `herb_catalog` at P3 | Gate 3 |
| ADR-07 | AI Knowledge Source | LLM training data → grounded knowledge layer | Structured context injection + explicit uncertainty fallback | Gate 3 |
| ADR-08 | Allergy & Cross-Reactivity | Free-text field → structured allergy + cross-reactivity rules | `patient_allergies` table + cross-reactivity rule table | Gate 2 |
| ADR-09 | CDS Placement | No CDS → domain service | Sync domain service for medication writes, async for lab-drug | Gate 1 |
| ADR-10 | Drug Knowledge Data Sources | Manual 41 drugs → tiered open + licensed | Tier 1: RxNorm + manual; Tier 2: MIMS Vietnam (PTH stop gate) | Gate 2 |
| ADR-11 | Medication Lifecycle | Soft delete only → two-field model | `lifecycle_status` (7 values) + `verification_status` (4 values) — independent fields | Gate 1 |
| ADR-12 | PHI, Privacy & Encryption | Plaintext DB → layered encryption + audit | DB encryption P0, column encryption P1, LLM DPA confirmed | Gate 2 |

---

## 2. Alternatives Rejected (Summary)

| ADR | Option Rejected | Reason |
|-----|-----------------|--------|
| ADR-01 | Graph database (Neo4j) | Over-engineered at current scale. No justification until 50K+ drug entities. |
| ADR-01 | Keep flat JSON catalog | Cannot join, cannot index, dead end for interaction engine. |
| ADR-02 | 50 hardcoded ingredient pairs | Does not scale. Cannot detect class-level interactions. No mechanism data. |
| ADR-02 | External API only (DrugBank/Lexicomp) | Stop gate — licensing cost. Viable at P3+ with PTH approval. |
| ADR-03 | Full Event Sourcing | Adds months of infrastructure complexity. Projection + replay not justified at MetoCare's scale. |
| ADR-03 | `updated_at` only | Loses all clinical history — incompatible with Doctor Portal, AI temporal reasoning. |
| ADR-04 | Auto-merge with confidence scoring | Wrong merge is worse than no merge. Human must confirm all reconciliation decisions. |
| ADR-05 | Reuse lab OCR pipeline | Different domain (table vs narrative). Different accuracy model. Wrong abstraction. |
| ADR-06 | `is_supplement` Boolean | Cannot differentiate clinical behavior between 9 distinct categories. |
| ADR-07 | RAG over vector database | Over-engineered. <1000 drugs in catalog — structured injection is sufficient. |
| ADR-08 | Structured allergy without cross-reactivity | Misses clinically critical Penicillin→Cephalosporin cross-reaction. Unacceptable. |
| ADR-09 | Frontend validation only | Bypassable via direct API call. Not reliable for safety-critical checks. |
| ADR-09 | Database triggers | Untestable, invisible in code review, hard to version. |
| ADR-10 | Assume free sources are sufficient for production | Free sources lack VN localization, interaction completeness. Must evaluate MIMS. |
| ADR-11 | 4 states (active/paused/completed/discontinued) | Missing: planned, on_hold, expired, entered_in_error, unknown. All needed clinically. |
| ADR-12 | No encryption (current state) | Insufficient under Vietnamese privacy law and common-sense security. |

---

## 3. Decision Owner Per ADR

| ADR | Primary Owner | Co-Owner | Requires Clinical Sign-off |
|-----|--------------|----------|---------------------------|
| ADR-01 | PTH (strategy) | Tech Lead (implementation) | Yes — INN as canonical standard |
| ADR-02 | PTH (strategy) | Clinical Advisor (rules) | Yes — MVP rule set |
| ADR-03 | PTH (strategy) | Tech Lead (implementation) | No |
| ADR-04 | PTH (strategy + consent policy) | Clinical Advisor | Yes — verification hierarchy |
| ADR-05 | PTH (scope + PHI risk) | Tech Lead | No |
| ADR-06 | PTH (category policy) | Clinical Advisor | Yes — category clinical behavior |
| ADR-07 | PTH (principle) | Tech Lead | Yes — knowledge format |
| ADR-08 | Clinical Advisor (rules) | PTH (approval) | Yes — cross-reactivity rules |
| ADR-09 | Tech Lead | PTH (approval) | No |
| ADR-10 | PTH (budget + licensing) | Legal Advisor | Partial — source quality |
| ADR-11 | PTH (lifecycle states) | Clinical Advisor (transitions) | Yes — state definitions |
| ADR-12 | PTH (data controller) | Legal Advisor, Tech Lead | No |

---

## 4. Implementation Blockers

### Gate 1 — Blocks ALL code (must resolve before P0 starts)

| ADR | What is blocked if not resolved |
|-----|--------------------------------|
| ADR-01 | Cannot build knowledge structure. Drug catalog stays as dead-end flat table. |
| ADR-03 | History never starts. Cannot retroactively add. Day 1 medication changes lost forever. |
| ADR-04 | `source_type` not on schema. Every P0 record is untagged and cannot be reconciled later. |
| ADR-09 | CDS has no defined home. Every subsequent safety feature has no architectural foundation. |
| ADR-11 | `status` field not on schema. P0 migrations without `status` will need destructive change later. |

**Decision: PTH must approve Gate 1 ADRs before any migration is written.**

### Gate 2 — Blocks Production Safety Features (P3: allergy, interaction, production launch)

| ADR | What is blocked |
|-----|----------------|
| ADR-02 | No interaction engine. Interaction check feature cannot go to production. |
| ADR-08 | No allergy engine. Allergy safety cannot go to production. |
| ADR-10 | No licensed drug data source for VN. Interaction/allergy accuracy insufficient for production. |
| ADR-12 | No PHI encryption, no LLM DPA. Medication data legally exposed. Cannot launch publicly at scale. |

### Gate 3 — Blocks Expansion Features (can defer without blocking P0–P2)

| ADR | What is deferred |
|-----|----------------|
| ADR-05 | OCR prescription capture deferred to P2 |
| ADR-06 | Supplement taxonomy needed at P0 schema (remove `is_supplement`, add `medication_category`) — but `herb_catalog` deferred to P3 |
| ADR-07 | AI medication explanation feature deferred until knowledge layer exists |

---

## 5. Clinical Review Requirements

| Requirement | Who | When | Block |
|-------------|-----|------|-------|
| INN as canonical ingredient standard | Clinical Advisor | Before ADR-01 implementation | ADR-01, ADR-02 |
| MVP interaction rule set review | Clinical Advisor | Before P3 production release | ADR-02 |
| Cross-reactivity rule set review | Clinical Advisor | Before P3 production release | ADR-08 |
| Allergy category clinical behavior | Clinical Advisor | Before P3 design | ADR-06, ADR-08 |
| Medication lifecycle state definitions | Clinical Advisor | Before P0 | ADR-11 |
| Drug data source quality sign-off | Clinical Advisor | Before MIMS contract | ADR-10 |

---

## 6. Unresolved Questions Requiring PTH Decision

These are the **10 actual decisions PTH must make** — not architectural suggestions but yes/no choices:

| # | Question | Impact if not decided |
|---|----------|----------------------|
| 1 | **MIMS Vietnam licensing (~$15-50K/year)?** | Cannot have VN-localized interaction/allergy data at production quality for P3 |
| 2 | **DrugBank Open commercial license?** | Cannot import DrugBank interaction data without license |
| 3 | **WHO ATC commercial use approval?** | Cannot use ATC codes in production without legal clearance |
| 4 | **LLM provider DPA for health data?** (Anthropic/Google) | Cannot inject medication context into LLM at production scale |
| 5 | **Can doctor directly add to patient CML, or must patient always confirm?** | Affects Doctor Portal design and reconciliation architecture |
| 6 | **Include handwritten prescriptions in OCR P2?** | Handwritten accuracy is significantly lower — different UX and pipeline needed |
| 7 | **`on_hold` is doctor-only: patient cannot clear it without doctor.** Confirm this policy? | Affects state machine enforcement and patient UX |
| 8 | **Can patient add medications in `planned` status?** Or only doctor? | Affects P0 form design |
| 9 | **Vietnamese data deletion vs anonymization:** When patient requests deletion, anonymize clinical records (retain structure, remove PII) or full deletion? | Legal compliance, data architecture |
| 10 | **Who is the designated Vietnamese clinical advisor?** | Every clinical sign-off above is blocked without this person identified |

---

## 7. Dependency Map Between ADRs

```
ADR-11 (Lifecycle states)
  └─ must be decided BEFORE ADR-03 (history captures state transitions)
  └─ must be decided BEFORE P0 schema

ADR-01 (Knowledge structure)
  └─ must be decided BEFORE ADR-02 (interaction engine needs ingredient entities)
  └─ must be decided BEFORE ADR-08 (allergy engine needs ingredient/class entities)
  └─ must be decided BEFORE ADR-07 (AI tools read from knowledge tables)

ADR-09 (CDS placement)
  └─ must be decided BEFORE ADR-02 (interaction engine runs inside CDS)
  └─ must be decided BEFORE ADR-08 (allergy engine runs inside CDS)

ADR-04 (Reconciliation — revised: two-table at P0)
  └─ `source_type` field in P0 schema (confirmed)
  └─ `medication_statements` table ALSO at P0 (revised — not deferred to P2)
  └─ `medication_statements` is dependency for ADR-05 (OCR P2 flow)

ADR-10 (Data sources)
  └─ must be decided BEFORE ADR-02 rule set is final (where do rules come from?)
  └─ must be decided BEFORE ADR-08 cross-reactivity rules are finalized

ADR-12 (PHI)
  └─ LLM DPA must be confirmed BEFORE ADR-07 (AI injection) ships to production
  └─ DB encryption must be active BEFORE ADR-08 (allergy) ships (patient_allergies is high-sensitivity)

ADR-03 (History)
  └─ depends on ADR-11 (status transitions are the primary events to log)

ADR-06 (Traditional medicine)
  └─ `medication_category` VARCHAR column is in P0 schema (replaces `is_supplement`)
  └─ Full taxonomy ships at Gate 3 as INSERT into lookup table — zero schema migration needed
  └─ `herb_catalog` deferred to P3 (non-blocking for P0)
  ⚠️ ADR-06 is Gate 3, NOT Gate 1.
```

**Minimum approval sequence for P0 to start:**
```
ADR-11 → ADR-01 → ADR-03 → ADR-04 → ADR-09
```
✅ All 5 Gate 1 ADRs approved (PTH 2026-07-11). ADR-06 NOT required for P0.

**Gate 1 status: ✅ FULLY APPROVED. P0 implementation may begin.**

---

## 7b. PTH Decisions Confirmed (2026-07-11 Review Sessions)

**v1.2 edits:** `doctor_confirmed` → `clinician_confirmed`; `source_type` confirmed as independent field.

**v1.3 Gate 1 Conditional → Full Approval (2026-07-11):**
- ADR-06 removed from Gate 1 (Gate 3 only). `medication_category` uses lookup table, not DB enum.
- M-02 history + M-03 events → merged into `medication_audit_log` (before/after snapshots per row).
- `medication_statements` extended: +`assertion_type`, `related_medication_id`, `effective_from`, `payload_snapshot`.
- Q-OQ-1 (expired re-review) → ✅ RESOLVED: statement-first, 4-case model (Case D = clinician review).

| # | Decision | Status |
|---|---------|--------|
| ADR-01 | Hybrid: normalized core + JSON extensions | ✅ **APPROVED 2026-07-11** |
| ADR-03 | Snapshot-on-write + event log (`medication_audit_log`) | ✅ **APPROVED 2026-07-11** |
| ADR-04 | Two-table at P0: `medication_statements` + canonical `medications` | ✅ **APPROVED 2026-07-11** |
| ADR-04 | Q-OQ-1: expired re-review = statement-first (Case D = clinician) | ✅ **RESOLVED 2026-07-11** |
| ADR-09 | Sync domain service for medication writes, async for lab-drug | ✅ **APPROVED 2026-07-11** |
| ADR-11 | Two-field: `lifecycle_status` (7) + `verification_status` (4) | ✅ **APPROVED 2026-07-11** |
| ADR-11 | `clinician_confirmed` (was `doctor_confirmed`) | ✅ **APPROVED 2026-07-11** |
| ADR-11 | `on_hold` is doctor-only; patient cannot change lifecycle_status | ✅ Confirmed |
| ADR-11 | Patient CANNOT add medication in `planned` state | ✅ Confirmed |
| ADR-11 | Patient reporting non-adherence = event only, NOT lifecycle transition | ✅ Confirmed |
| ADR-05 | Handwritten prescription OCR NOT in P2 default scope | ✅ Confirmed |

**Remaining open decisions: 6** — all Gate 2/3, none block P0:
MIMS licensing · DrugBank license · ATC legal · LLM DPA · data deletion policy · VN clinical advisor identity

---

## 7c. ADRs Revised After PTH Review

| ADR | Change | Reason |
|-----|--------|--------|
| ADR-02 | Class-based → typed clinical rule engine | PTH: class is one selector type, not the full model. Many interactions are ingredient-specific, route-specific, or dose-dependent. |
| ADR-04 | `medication_statements` deferred to P2 → **both tables at P0** | PTH: mixing canonical record with source assertion = destructive migration debt at P2. Must separate from day 1. |
| ADR-11 | 9-state single field → **lifecycle_status + verification_status** | PTH: `planned` and `unknown` are verification concerns, not lifecycle states. Orthogonal fields needed. |

---

## 8. Recommended Approval Order for PTH

| Session | ADRs to Approve | Duration | What Unlocks | Session Status |
|---------|----------------|----------|-------------|---------------|
| **Session 1** | ADR-11 + ADR-09 | 30 min | lifecycle model + CDS placement | Key decisions confirmed in PTH review. ADR-11 revised. Formal sign-off still needed. |
| **Session 2** | ADR-01 + ADR-06 (category only) | 45 min | Knowledge structure + supplement taxonomy | Not yet reviewed |
| **Session 3** | ADR-03 + ADR-04 | 30 min | History + two-table reconciliation | ADR-04 revised: medication_statements now at P0 |
| **Session 4** | ADR-10 + ADR-12 | 60 min | Data licensing + PHI | Bring Legal Advisor. MIMS and LLM DPA are stop gates. |
| **Session 5** | ADR-02 + ADR-08 | 60 min | Typed rule engine + allergy model | ADR-02 revised. Bring Clinical Advisor. |
| **Session 6** | ADR-05 + ADR-07 | 30 min | OCR pipeline + AI knowledge source | Lower urgency, deferred features |

**Estimated remaining: 5 sessions (~4 hours)** after PTH review progress.

---

## 9. P0 Schema Footprint (After Revisions)

After ADR-11 and ADR-04 revisions, P0 foundation migration must include:

```
medications table additions:
  + lifecycle_status    VARCHAR(32) NOT NULL DEFAULT 'active'         [ADR-11]
  + verification_status VARCHAR(32) NOT NULL DEFAULT 'patient_reported' [ADR-11]
  + source_type         VARCHAR(32) NOT NULL DEFAULT 'patient_manual'  [ADR-04]
  + medication_category VARCHAR(32) NOT NULL DEFAULT 'conventional_drug' [ADR-06]
  + drug_product_id     FK nullable                                    [ADR-01]
  + generic_name        VARCHAR(255) nullable                          [ADR-01]
  + status_reason       TEXT nullable                                  [ADR-11]

new tables (all at P0):
  + medication_statements   (ADR-04 — empty table; OCR flow activates at P2)
  + medication_history      (ADR-03 — snapshots on every change)
  + medication_events       (ADR-03 — event log for lifecycle + verification changes)
```

Knowledge, CDS, and allergy tables are later foundation migrations (not P0).

---

## 10. What CAN Start Immediately (Without ADR Approval)

While ADRs are being reviewed, the following work has zero dependency on ADR decisions:

| Work | Why safe to start |
|------|------------------|
| Medication detail page frontend (`/medications/[id]`) | Pure UI, no schema change |
| Fix weekly adherence chart (use real per-day data) | Backend query change, no schema impact |
| Add `medication_reminder` notification type | Safe code addition, no ADR dependency |
| Drug catalog expansion (add more drugs to existing schema) | Additive, no breaking change |
| Write CDS test matrix (unit test cases) | Documentation/test prep, no schema needed |

**What CANNOT start before ADR approval:**
- P0 schema migration (status, source_type, medication_category, knowledge structure)
- Interaction engine (needs ADR-01, ADR-02, ADR-09)
- Allergy engine (needs ADR-01, ADR-08, ADR-09)
- OCR prescription pipeline (needs ADR-04, ADR-05, ADR-12 LLM DPA)
- Any AI medication explanation feature (needs ADR-07)

---

## 11. Risk If ADRs Are Not Resolved Before Coding

| Risk | If Gate 1 ADRs skipped | If Gate 2 ADRs skipped |
|------|----------------------|----------------------|
| Schema refactor cost | HIGH — destructive migration needed to add status, source_type, knowledge structure | MEDIUM — new tables, no existing data broken |
| Clinical safety | HIGH — no history = cannot detect dose changes. No source_type = cannot reconcile | CRITICAL — interaction/allergy features launch without validated rules |
| Legal exposure | HIGH — medication data without PHI policy is regulatory risk from day 1 | CRITICAL — production launch with plaintext PHI |
| Technical debt timeline | 6–9 months to fix if skipped now | 12–18 months to refactor intelligence layer |
| Team alignment | HIGH — without ADRs, different developers will make different assumptions in code | HIGH — clinical features implemented without clinical governance |
