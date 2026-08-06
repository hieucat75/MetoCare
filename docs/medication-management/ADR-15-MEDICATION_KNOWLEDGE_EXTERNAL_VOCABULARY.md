# ADR-15 — Medication Knowledge External Vocabulary

**Status:** **APPROVED FOR IMPLEMENTATION BY PTH — clinical and legal governance deferred (2026-07-23).** This is a binding governance decision, superseding this ADR's prior "pending sign-off" status: PTH explicitly accepts implementation proceeding **before** formal Clinical Advisor and Legal review is complete. Clinical, legal, and content review are **post-implementation hardening milestones** (§ Release Stages), not coding blockers. Response-field code for `evidence_level`, `theme`, `source_type`, `patient_context`, and `condition_type` is **unblocked for implementation** (§I). `frequency` and `action_level` remain excluded from K2 v1 — a separate scope decision, unrelated to this governance change — unless a separate approved implementation slice explicitly adds them. **No Clinical Advisor, Legal reviewer, or Tech Lead has reviewed or approved anything in this document.** Do not represent otherwise in code comments, response payloads, UI copy, or any downstream document.
**Date:** 2026-07-23 (drafted); **PTH approved for implementation:** 2026-07-23; **Clinical Advisor:** not yet reviewed — recommended future reviewer, non-blocking (§ Recommended Future Reviews); **Legal:** not yet reviewed — recommended future reviewer, non-blocking; **Tech Lead:** not yet reviewed — recommended future reviewer, non-blocking
**Deciders:** PTH (product and governance) — approved for implementation 2026-07-23, and explicitly accepts implementation ahead of clinical/legal governance completion. Clinical Advisor, Legal, and Tech Lead are recommended future reviewers (§ Recommended Future Reviews); their absence does not block coding.

This ADR is the "Phase B" vocabulary ADR that `MEDICATION_K2_KNOWLEDGE_API_IMPLEMENTATION_PLAN.md` (rev 3, §5 lines 273–319) defers to. It supersedes, for the seven fields below, any implicit vocabulary claims made in ADR-10 (`evidence_level` A/B/C list) and in `MEDICATION_KNOWLEDGE_TEMPLATE_V1.md`'s YAML examples where they conflict with the tables in §B–§F.

---

## ADR Metadata

| Field | Value |
|---|---|
| ADR | ADR-15 |
| Status | **Approved for implementation by PTH (2026-07-23) — clinical and legal governance deferred.** Clinical Advisor, Legal, and Tech Lead review are recommended, non-blocking, post-implementation hardening milestones (§ Release Stages). |
| Architecture Version | medication-architecture-v1.1 |
| Implementation Gate | Gate 1 (implementation approval) — **FULLY CLEARED 2026-07-23 by PTH.** Response-field code implementation is unblocked (§I). Clinical Advisor, Legal, and Tech Lead review are Gate 2/Gate 3 milestones (§ Release Stages), not preconditions for writing code. |
| Domain | Medication Knowledge / K2 API contract |
| Supersedes | ADR-10 §"Data Model Impact" `evidence_level` vocabulary (superseded only for the `evidence_level` value list; ADR-10 remains Proposed and otherwise unaffected) |
| Superseded By | None |
| Amends | `MEDICATION_K2_KNOWLEDGE_API_IMPLEMENTATION_PLAN.md` rev 3 (see §I for exact amendments) |

---

## Context

`MEDICATION_K2_KNOWLEDGE_API_IMPLEMENTATION_PLAN.md` rev 3 §5 identifies seven fields on the ADR-13 knowledge tables and `DrugReference` that its response contracts either expose as opaque strings or explicitly withhold, and states that none of them may ship as stable API vocabulary until a dedicated ADR locks: the controlled value set, a named clinical/product owner, explicit source-to-external mapping, unknown-value semantics, versioning, and localization approach — for each field independently. This ADR is that lock.

Research for this ADR surfaced that the seven fields are in materially different states of readiness:

- `frequency` and `action_level` (on `drug_side_effects`) both have DB `CHECK` constraints enforcing a closed value set that matches the authoring template exactly — the most mature of the seven.
- `evidence_level` (on the shared `KnowledgeLifecycleMixin`, all five knowledge tables) has **no DB constraint at all**, and three mutually inconsistent implicit vocabularies exist across the corpus: ADR-10 proposes `A | B | C | expert_opinion | traditional_use`; `MEDICATION_KNOWLEDGE_TEMPLATE_V1.md`'s YAML example uses `moderate`; the K2 plan's own JSON examples use `clinical_guideline` / `product_label`. None of these three lists were ever reconciled.
- `source_type` is a **name shared by three unrelated fields**: `DrugReference.source_type` (DB-enforced, 5 values — the one the K2 plan's `references[]` shape actually uses), `medications.source_type` (ADR-04, reconciliation provenance, unrelated table/domain), and the bare term "`source_type`" used in the K2 plan's §5 discipline list without disambiguation.
- `patient_context` (on `drug_monitoring`) and `condition_type` (on `drug_contraindications`) have **no DB constraint and no enumerated value list anywhere** — only two example `patient_context` values (`baseline`, `renal_impaired`, plus the K2 plan's own `ckd_stage_3_or_worse`) and zero example `condition_type` values have ever been written down. ADR-14 uses the unrelated phrase "Context Engine" / "patient context resolution" for a different concept (ephemeral read-time personalization) — this ADR's `patient_context` is the `drug_monitoring.patient_context` **column**, not ADR-14's Context Engine, and the two must not be conflated in documentation going forward.
- `theme` (on `drug_patient_education`) has the most complete authoring-key list of the seven, but the template document itself contains two internally inconsistent lists (§1's 6-value "Golden Drug Page" list vs. §2.1's stale 8-value table that still includes two themes PTH's 2026-07-16 ruling dropped), is explicitly marked "**Needs PTH confirmation**" (template §9.3), and the K2 plan's own example value `why_this_matters` matches **neither** list.

Given this spread, a single classification cannot apply to all seven fields — this ADR classifies each independently (§A) and defines field-specific rules (§B–§F).

## Problem

Without this ADR, K2 implementation has three bad options: (1) ship all seven fields as opaque strings with no stability contract, silently binding external consumers to today's accidental DB values; (2) block all of K2 on resolving every field's vocabulary, even fields (`patient_context`, `condition_type`, `source_type`) that are either already safely scoped or not yet clinically loaded; or (3) let each field's exposure decision be made ad hoc, per-PR, with no single place recording why. This ADR picks option: classify per-field now, lock what's ready, defer what isn't, and give K2 an explicit, field-by-field green light.

---

## A. Vocabulary Classification

| Field | Classification | Rationale |
|---|---|---|
| `frequency` (`drug_side_effects`) | **Excluded from K2 v1** | DB-enforced vocabulary is mature, but §5's independence-from-`action_level` rule and the dose-schedule-frequency naming collision (see §B) are unresolved; K2 plan already made this call — this ADR affirms it. |
| `action_level` (`drug_side_effects`) | **Excluded from K2 v1** | Safety-relevant axis; must never ship without an explicit escalation-semantics contract and clinical sign-off on display treatment (§C). K2 plan already made this call — this ADR affirms it. |
| `evidence_level` (knowledge mixin) | **External but versioned/experimental** | DB has zero constraint and three conflicting historical vocabularies exist. This ADR locks a canonical v1 list now (§D) but the field stays "experimental" — no compatibility guarantee on the value set — until a DB `CHECK` constraint migration lands (tracked as a K2/K3 follow-up, not part of this ADR). |
| `source_type` (`drug_references` only) | **Stable external coded vocabulary** | Already DB-enforced (5 values), already correctly scoped to `references[]` only in the K2 plan. Locked as-is; the ADR's only addition is a disambiguation rule (§E) preventing this name from being reused for anything else. |
| `patient_context` (`drug_monitoring`) | **Internal authoring key** | No DB constraint, no enumerated list, but the value is load-bearing for clinical correctness (it disambiguates which population a monitoring row applies to) — cannot be omitted from the doctor contract without breaking meaning. Exposed as opaque data, not governed vocabulary. |
| `condition_type` (`drug_contraindications`) | **Internal authoring key** | Same reasoning as `patient_context` — part of the ADR-13 business key, load-bearing for correctness, zero documented values, cannot be safely turned into a governed vocabulary yet. |
| `theme` (`drug_patient_education`) | **External but versioned/experimental** | Best-documented field of the seven, and already patient-facing in the K2 plan's examples, but the authoring template's own value list is internally inconsistent and explicitly marked PTH-pending. Ships in K2 v1 as an experimental-status field (§F). |

**Compatibility consequences by classification:**

- **Stable external coded vocabulary** (`source_type`): value set is a public contract. Adding a value requires an ADR amendment + version bump. Removing or renaming a value is a breaking change requiring a deprecation window (§H).
- **External but versioned/experimental** (`evidence_level`, `theme`): the field's *presence and shape* (`{code, label?}`) is stable, but its *value set* is not — new values may appear without a version bump while status is "experimental"; consumers must fail soft (§G) on unrecognized values. Both fields' v1 code lists are locked by this ADR (§D, §F). Promotion to "stable" additionally requires: a DB `CHECK` constraint following the five-step sequence in §D (`evidence_level`), or a production-data audit plus demonstrated stable patient-UI usage per §F (`theme`) — plus, in both cases, an ADR amendment recording the promotion.
- **Internal authoring key** (`patient_context`, `condition_type`): no compatibility guarantee at the API-contract level. Consumers must treat the string as opaque — safe to display verbatim, unsafe to branch UI logic on specific values, unsafe to assume the value set is finite or enumerable. In practice values change rarely because ADR-13's append-only model treats a `patient_context`/`condition_type` change as creating a new fact-row, not editing an existing one — but that stability is a side effect of the content model, not an API contract.
- **Excluded from K2 v1** (`frequency`, `action_level`): no compatibility surface exists yet; nothing to break. Future exposure requires a new ADR amendment (or this ADR's own re-opening) before any route returns these fields.

---

## B. `frequency`

- **Canonical machine codes (locked, matches existing DB `CHECK`):** `common`, `uncommon`, `rare`, `unknown`.
- **Precise clinical meaning:** how often the described side effect occurs among patients taking this drug — an occurrence-rate classification of the *side effect*, assigned during clinical authoring/review. It carries no instruction about what the patient should do.
- **Permitted display labels:** none locked yet — Vietnamese display labels for `frequency` have never been authored anywhere in the corpus (unlike `action_level`, which has confirmed VN labels in the template). Producing them is a content-team task, tracked as an open question (§ Open Questions), not blocking this ADR's classification decision.
- **Unknown/not-stated semantics:** `unknown` means "the reviewed evidence did not establish an occurrence rate," not "not yet reviewed" (unreviewed content cannot reach `status='approved'` per ADR-13 and therefore cannot reach this API at all) and not "rare." Consumers must render `unknown` as its own distinct state, never collapse it into `rare` or omit the badge.
- **Source-to-canonical mapping:** identity mapping — the DB value already equals the desired external value. No transformation table is needed if/when this field ships.
- **Locale behavior:** the code itself (`common`/`uncommon`/`rare`/`unknown`) is locale-invariant; only the display label varies by locale.
- **Patient sorting/grouping:** **prohibited.** `frequency` must never be used to sort, group, or filter side effects by itself. Per the K2 plan (§5, lines 314–319) and reaffirmed here, only `action_level` may drive severity-oriented grouping — `frequency` is at most a secondary badge inside an `action_level` band.
- **K2 v1 status:** **excluded.** No route may return this field in K2 v1.
- **Naming note for future exposure:** the codebase already uses the bare word "frequency" for an unrelated concept — medication dosing-schedule frequency (e.g. `medications`/dose-schedule fields, referenced in ADR-07's example code as `med.frequency`). To avoid ambiguity for API consumers who may see both concepts in the same client app, **when this field is eventually exposed it must ship under the JSON key `side_effect_frequency`, not bare `frequency`.** This is a naming decision locked now for whenever exposure happens; it requires no code today.
- **Decided (2026-07-23): the physical DB column (`drug_side_effects.frequency`) is not renamed as part of K2.** The `side_effect_frequency` alias above is an API-contract-level rename only. Renaming the underlying DB column is recorded as a **separate, future migration concern**, out of scope for K2, that would require its own consumer inventory (every internal reader of `drug_side_effects.frequency`) and a compatibility period — not undertaken lightly given ADR-13's append-only, business-key-sensitive model.

## C. `action_level`

- **Canonical machine codes (locked, matches existing DB `CHECK`):** `self_monitor`, `contact_clinician`, `urgent_medical_help`.
- **Exact patient-facing meaning:** the recommended patient response to observing this side effect — self_monitor ("this is expected, watch it"), contact_clinician ("raise it with your doctor/pharmacist, not urgent"), urgent_medical_help ("seek medical attention promptly"). This is an instruction axis, distinct from `frequency`'s occurrence-rate axis.
- **Clinical owner:** the Clinical Advisor role defined in ADR-13 (the same role that gates `clinical_review → approved`). No `action_level` value may be authored or changed without going through that same approval gate — it is already covered by ADR-13's lifecycle, this ADR adds no new workflow, only the external-contract rules below.
- **Escalation/urgent-help semantics:** `urgent_medical_help` must never be exposed as a bare code, color, or badge without the accompanying clinically-authored instruction text from the same approved row. This follows directly from `MEDICATION_SAFETY_RULES.md` SR-006 ("interaction warnings MUST include severity + evidence source + evidence quality") and the "never diagnose" doctrine (SR-003, §2.3) — a safety-relevant classification must always travel with its clinical context, never as an isolated signal a client could re-interpret.
- **Unknown semantics:** there is no `unknown` value in the DB `CHECK` for this field — every approved row must have one of the three explicit values. If a persisted value is ever encountered that is not one of the three (e.g., future data-quality bug), the API must treat it as **malformed**, not `unknown` (see §G) — omit the affected knowledge item, and raise a data-quality alert. A safety-instruction field with an unrecognized value is worse than a missing one.
- **Fail-closed scope — item-scoped only, clarified 2026-07-23:** an invalid `action_level` value causes fail-closed omission **only of the single affected medication-knowledge item.** It must never: drop the whole medication from the response, fail the whole request, or affect any other, unrelated knowledge item (including other side-effect rows for the same ingredient that have a valid `action_level`). This mirrors §G's whole-request-fail-closed-is-reserved-for-auth/structural-failures rule — a content-quality problem in one row is never escalated beyond that row.
- **Telemetry (PHI-free, structured, mandatory on every fail-closed omission):** at minimum, `knowledge_vocabulary_version` (§H), the knowledge record identifier (the row's primary key / business key — not any patient- or medication-identifying value), the invalid canonical value observed, and the validation reason (e.g. "value not in locked action_level vocabulary"). **Never log patient free text or any PHI** — the telemetry event describes a vocabulary/data-quality fact about a knowledge row, not anything about the patient who happened to trigger the read.
- **Absence of `action_level` — scoped by item type, not global:** whether a missing `action_level` value causes item omission depends on whether the specific knowledge-item *type* requires `action_level` at all — not every knowledge-item type necessarily does. **Before any route or response-model code implements this field, a field-required-by-item-type matrix must be documented** (which of the five knowledge-item types treat `action_level` as required-for-display vs. not-applicable) so "missing" and "not applicable" are never conflated. Producing that matrix is a K2 implementation-planning task; this ADR requires it to exist before implementation, but does not itself author it.
- **Localization:** VN display labels already exist in `MEDICATION_KNOWLEDGE_TEMPLATE_V1.md` §2.8 (line 82) and are adopted as canonical here:

  | Code | VN display label |
  |---|---|
  | `self_monitor` | "Thường gặp, có thể theo dõi" |
  | `contact_clinician` | "Nên trao đổi với bác sĩ/dược sĩ" |
  | `urgent_medical_help` | "Cần hỗ trợ y tế ngay" |

- **Versioning:** part of the "excluded" set — no external version exists yet. When exposed, this becomes a "stable external coded vocabulary" (not experimental) because the DB constraint and clinical review process already exist; only the API contract itself is missing.
- **Source mapping:** identity mapping, same as `frequency`.
- **K2 v1 status:** **excluded**, same as `frequency`.
- **Independence from `frequency` — stated explicitly, per K2 plan §5:** `action_level` and `frequency` are independent axes describing different things (what to do vs. how often it happens). **No consumer, server-side or client-side, may infer one from the other** (e.g., "rare implies self_monitor" is prohibited). This is the entire reason ADR-13 split the old single `level` enum into these two columns, and this ADR reaffirms that split as permanent, not a temporary modeling artifact.

## D. `evidence_level`

- **Patient exposure form:** **localized label only, backed by a locked code — never the raw code alone, and never omitted.** The K2 plan already exposes `evidence_level` in every patient category; this ADR does not remove it, but requires the patient-facing renderer to always resolve the code to a display label (§ Localization Examples) rather than showing a bare enum string, since raw codes like `peer_reviewed_literature` are not patient-appropriate language.
- **Canonical values and meanings (locked v1 — supersedes ADR-10's A/B/C list and the template's stray `moderate` example):**

  | Code | Meaning |
  |---|---|
  | `clinical_guideline` | Sourced from a recognized clinical practice guideline (e.g. national/international treatment guideline). |
  | `product_label` | Sourced from the approved product label / package insert / SmPC. |
  | `peer_reviewed_literature` | Sourced from peer-reviewed published research. |
  | `expert_consensus` | Sourced from documented expert/specialty-society consensus without a formal guideline. |
  | `traditional_use` | Documented traditional/long-standing clinical use without a formal evidence base (relevant to ADR-06's traditional-medicine content). |
  | `unknown` | Evidence basis was not classified during authoring. |

  This list is deliberately a **source-classification** list, not a GRADE-style quality tier (A/B/C). ADR-10's A/B/C/expert_opinion/traditional_use list is superseded for this field because ADR-10 remains formally Proposed (not Accepted) and its list was never reconciled with the template or the K2 plan's own examples.
- **Decided (2026-07-23): no GRADE-style A/B/C layer inside `evidence_level`.** `evidence_level` remains, permanently, the six-value source-classification vocabulary above — it answers "what kind of source is this," not "how strong is the evidence." **Evidence source classification and evidence certainty/quality are separate dimensions and must not be conflated in one field.** This ADR does not introduce a quality/certainty axis for K2 v1.
- **Reserved future field name: `evidence_quality`.** If MetoCare later wants to express evidence certainty/strength (the GRADE-shaped question), it must be a distinct, separately-named field — `evidence_quality` — not a reinterpretation or extension of `evidence_level`. This ADR reserves the name but does not design or approve the field. Any future `evidence_quality` implementation requires, at minimum:
  1. A Clinical Advisor-approved grading methodology (e.g., adapting GRADE or an equivalent, explicitly chosen, not assumed).
  2. Auditable grading rules — a documented, reviewable procedure for how a row's `evidence_quality` value is assigned, not an ad hoc judgment call per row.
  3. Defined clinical reviewer ownership — a named role (presumably Clinical Advisor, per ADR-13's pattern) accountable for grading decisions.
  4. An explicit mapping from evidence records to displayed conclusions — i.e., a documented rule for how a `evidence_quality` code translates into patient- or doctor-facing text, mirroring this ADR's code/label-separation discipline (§G).
- **Absence allowed?** No — per ADR-13's `_approved_invariants_check()`, `evidence_level` is already required to be non-null for any `status='approved'` row. This ADR does not change that; it only constrains *which* non-null values are valid externally.
- **Unsupported/future values:** fail soft at the field level — omit `evidence_level` from that specific item's response (keep the rest of the item), log a P2 data-quality alert. `evidence_level` is a trust signal, not a safety instruction, so item-level omission (not whole-item exclusion) is acceptable here, unlike `action_level`.
- **Versioning and backward compatibility:** **experimental** status (§A) — the value set may change without an API version bump until (a) a DB `CHECK` constraint enforcing this exact list is migrated in, and (b) a backfill audit confirms no existing approved row uses a value outside this list. Both are tracked as required follow-up work, not part of this ADR (§ Migration/Backfill Impact).
- **Decided (2026-07-23): K2 v1 must not add an `evidence_level` DB `CHECK` constraint yet.** This is a locked sequencing decision, not an oversight — adding a constraint before the value set is proven clean against production data risks either a failed migration (if legacy rows violate it) or a silent narrowing of the "approved" set. The required sequence before any future `CHECK` migration is:
  1. Add application-level validation (reject/flag out-of-vocabulary values at the serialization boundary) and PHI-free telemetry recording validation failures.
  2. Inventory all existing persisted `evidence_level` values across every knowledge table.
  3. Backfill or quarantine (exclude from `approved` exposure) any invalid legacy values found by the inventory.
  4. Validate the proposed constraint against a staging copy of production-shaped data before touching the real schema.
  5. Only then introduce the DB `CHECK` constraint as its own migration.

  This sequence is recorded here as a locked decision on *ordering*; executing any of its five steps remains a future technical task and is explicitly not part of this documentation change.

## E. `source_type`

- **Canonical values (already DB-enforced on `DrugReference`, locked as-is):** `formulary`, `clinical_guideline`, `product_label`, `peer_reviewed`, `other`.
- **External exposure — patient contract:** **not exposed.** The K2 plan's `PatientMedicationKnowledgeOut` contract excludes the entire `references[]` list; `source_type` therefore never reaches the patient response in K2 v1. No change needed.
- **External exposure — doctor contract:** exposed, but **only nested inside `references[]` objects** (`DoctorIngredientKnowledgeOut`, per K2 plan §6.2) — never as a top-level field on a knowledge-row object (usage/side_effects/monitoring/patient_education/contraindications).
- **Localization:** citation metadata is not translated — `source_type` displays as a fixed label set (e.g. "Dược thư" for `formulary`, "Hướng dẫn điều trị" for `clinical_guideline`, etc.); exact VN labels are a content-team task, non-blocking.
- **Unknown handling:** same fail-soft rule as `evidence_level` — omit the malformed reference entry from `references[]`, keep the rest of the list, log a data-quality alert. A citation list missing one bad entry is still useful; failing the whole item over one bad citation is not proportionate.
- **Descriptive-only constraint:** `source_type` classifies *what kind of document* a citation is, not how trustworthy or clinically strong it is. **It must never be interpreted, sorted, or color-coded as a proxy for clinical quality.** That judgment is `evidence_level`'s job (§D), and the two must remain visibly separate in any UI that shows both.
- **Disambiguation rule (new, this ADR's primary contribution for this field):** the bare term "`source_type`" refers, in the K2 API contract, **exclusively** to `DrugReference.source_type`. It must never be confused with, aliased to, or documented near `medications.source_type` (ADR-04's reconciliation-provenance field on a completely different table/domain). Any future PR or doc that introduces a `source_type`-named field outside `DrugReference` must pick a different name and go through its own vocabulary review — this ADR does not pre-approve reuse of the name.

## F. `patient_context`, `condition_type`, `theme`

### `patient_context` (`drug_monitoring`)

- **Classification:** internal authoring key (§A).
- **Naming constraints:** snake_case, ASCII, ≤ 64 chars (already the DB column limit). No enumeration required for K2 v1.
- **Unknown/future value behavior:** N/A in the governed-vocabulary sense — there is no closed set to be "unknown" relative to. Any string the DB contains is, by definition, a valid opaque key. The API returns it verbatim.
- **Doctor exposure in K2 v1:** **yes, but only to authorized doctor-facing consumers when clinically necessary** — unchanged from the K2 plan (`monitoring` rows already include `patient_context`). Required for clinical correctness — a monitoring guidance row without its population qualifier (e.g. `baseline` vs `renal_impaired` vs `ckd_stage_3_or_worse`) is misleading, since ADR-13 treats different `patient_context` values as different facts, not versions of the same fact.
- **Patient exposure:** **never**, full stop, unless a separate ADR justifies it. The K2 plan already excludes it from the patient contract, correctly, because it is "an internal normalized identifier, not patient-meaningful" (K2 plan §6.1). This ADR reaffirms that exclusion as a hard rule, not a stylistic choice.
- **Compatibility/versioning:** **none — carries no guarantee of a stable or enumerable vocabulary.** Opaque, no contract. Doctor-facing UI must render it as plain, unstyled text (e.g. a small caption or tooltip labeled "Bối cảnh lâm sàng (nội bộ)") and must receive **no enum-style badges, colors, filters, or any UI treatment implying a governed value set**, since doing so would imply a stability guarantee this field does not have.
- **Graduation to governed vocabulary:** deferred, with no target date, until an actual product, clinical-logic, analytics, or interoperability requirement exists that specifically needs it — not scheduled as future work by default.
- **Terminology collision warning:** this is the `drug_monitoring.patient_context` **database column**. It is unrelated to ADR-14's "Context Engine" / "Patient Context Resolution," which is a different, ephemeral, read-time personalization concept over `contextual_notes`. Documentation referencing either must name the table/column or the service explicitly to avoid conflation — this ADR does not rename the column, only flags the ambiguity for future writers.

### `condition_type` (`drug_contraindications`)

- **Classification:** internal authoring key (§A) — same treatment as `patient_context`, for the same reason: it is part of the ADR-13 business key (`drug_ingredient_id, condition_type, condition_key`) and load-bearing for disambiguating which contraindication category a row describes.
- **Naming constraints:** snake_case, ASCII, ≤ 64 chars (DB column limit). No enumeration required for K2 v1.
- **Unknown/future value behavior:** same as `patient_context` — opaque, no closed set, returned verbatim.
- **Doctor exposure in K2 v1:** **yes, but only to authorized doctor-facing consumers when clinically necessary** — unchanged from the K2 plan (`contraindications` rows already include `condition_type`). No plan amendment required for this field.
- **Patient exposure:** **never**, full stop, unless a separate ADR justifies it — the K2 plan already excludes it from the patient contract; reaffirmed here.
- **Compatibility/versioning:** **none — carries no guarantee of a stable or enumerable vocabulary.** Opaque — same rendering rule as `patient_context`: plain text only, **no enum-style badges, colors, filters, or UI treatment implying governed values.**
- **Graduation to governed vocabulary:** deferred, with no target date, until an actual product, clinical-logic, analytics, or interoperability requirement exists that specifically needs it.

### `theme` (`drug_patient_education`)

- **Classification:** external but versioned/experimental (§A) — **finalized as of this ADR's approval (2026-07-23)**, superseding the two conflicting provisional lists that previously existed in `MEDICATION_KNOWLEDGE_TEMPLATE_V1.md` (§1's 6-value list vs. §2.1's stale 8-value table) and resolving the mismatch with the K2 plan's own `why_this_matters` example, which is now itself one of the canonical values below.
- **Naming constraints:** snake_case; one of the six closed values below. No open `faq_<slug>` pattern in this canonical list — the template's prior `faq_<slug>` proposal is not adopted here; if a FAQ-shaped content need arises later it requires its own ADR amendment.
- **Canonical `theme` vocabulary (locked, PTH-approved 2026-07-23):**

  | Code | Intent |
  |---|---|
  | `why_this_matters` | Why this medication/step matters for the patient's condition. |
  | `how_to_use_safely` | How to take/use the medication safely (administration guidance). |
  | `what_to_monitor` | What the patient should watch for while on this medication. |
  | `common_side_effects` | Patient-facing framing of commonly expected side effects. |
  | `when_to_seek_help` | When to escalate to a clinician or seek urgent care. |
  | `special_considerations` | Population- or situation-specific caveats not covered by the other five themes. |

- **Doctor exposure in K2 v1:** yes, unchanged from the K2 plan.
- **Patient exposure:** yes, unchanged from the K2 plan — `theme` is the one field of the three in this section that is patient-appropriate, since it is a display-grouping label, not an internal key.
- **Unknown/invalid value behavior:** fail soft **at the field level only** — an unrecognized or invalid `theme` value causes omission of the `theme` field alone. It must never cause the knowledge item, the medication, or the whole request to fail; the item's `content`/`evidence_level`/`last_reviewed_at` are still returned.
- **Safety/authorization boundary:** `theme` is a display-grouping label only. It must never be used to control clinical safety behavior, authorization, data visibility, or access control — no route or client may branch access decisions on a `theme` value.
- **Compatibility/versioning:** remains **experimental** even with the value set locked — new codes may still be added without a major-version bump (§H). Promotion from experimental to **stable** requires two preconditions, both future work, neither performed by this ADR: (1) a production-data audit confirming existing rows conform to this six-value list, and (2) demonstrated stable patient-UI usage of the six values over a full release cycle.

---

## G. API Behavior

- **Unknown persisted value** (a DB value outside this ADR's locked list, for a field with a locked list): fail soft **at the field level** by default — omit the field, keep the rest of the item, emit a structured data-quality log/alert including the row's business key for follow-up. Exception: `action_level`, where an unrecognized value causes the **affected knowledge item only** to be omitted (§C) — never the whole medication, the whole request, or any unrelated item — with mandatory PHI-free structured telemetry (§C: vocabulary version, knowledge record identifier, invalid value, validation reason).
- **Malformed approved row** (e.g., a required field is unexpectedly null despite ADR-13's approved-invariants constraint, or a value fails validation): same fail-soft-at-item-level default as above, with the same structured alert. A single malformed row must never surface as a generic 500 to the caller.
- **Whole-request fail-closed vs. omission:** whole-request failure (4xx/5xx) is reserved **exclusively** for authorization/authentication failures and structural failures (e.g., database unreachable, medication/ingredient not found — the K2 plan's existing 404 case). Content-vocabulary or data-quality issues **never** fail a whole request; the correct behavior is always partial-content success (existing item(s) with the bad field/item omitted) or, in the degenerate case where every item is affected, the K2 plan's existing empty-state `200` response. This protects a doctor's ability to see everything that *is* usable even when one row has a data-quality problem.
- **No route-layer semantic inference:** route handlers must not infer urgency, severity, grouping, or priority from a field's text content, its position in a list, or its absence. All such semantics must come only from the explicit locked codes in §B–§F (where they exist) — never from parsing or pattern-matching a label string.
- **No UI inference from labels or ordering:** clients must not assume alphabetical, insertion, or any other implicit ordering of returned items or field values carries meaning (e.g., "first side effect in the list is most severe" is prohibited). Any severity-relevant grouping must be driven by an explicit code (currently only `action_level`, and only once it ships).
- **Locale behavior:** K1.6's retrieval layer does not filter by locale today (confirmed — no locale filtering exists in `list_current_for_ingredient` or elsewhere), and content is currently authored effectively Vietnamese-only. For K2 v1: **no server-side locale fallback chain is implemented.** The API returns content as authored (Vietnamese), and public codes (§B–§F) are locale-invariant by design so a future client-side or server-side localization layer can be added later without an API contract change. This ADR does not build that layer — it only guarantees the codes are stable inputs to one.
- **Public code vs. localized display label separation:** for every field that carries a locked code (`action_level`, `evidence_level`, `source_type`, and `theme`'s closed values), the API returns the **code**, not a pre-localized string, except where the field's own persisted content *is* the display text (e.g. `drug_patient_education.content`, which is authored prose, not a coded value). Display-label mapping is a client-side responsibility for v1 (tables in §C/§D above are the canonical source clients should use), not a server-computed field. A future `/vocabulary` metadata endpoint is a reasonable K3+ enhancement but is out of scope here.

---

## H. Governance

- **Vocabulary owner:** PTH (product) — accountable for patient-facing meaning, UX treatment, and localization strategy for all seven fields.
- **Clinical approver (recommended, non-blocking as of 2026-07-23):** the Clinical Advisor role (ADR-13) remains the recommended reviewer of record for any change to a clinically-loaded field's meaning or value set: `action_level`, `evidence_level`, `patient_context`, `condition_type`. Per PTH's 2026-07-23 governance decision, Clinical Advisor review is **deferred to post-implementation hardening (§ Release Stages)** and does not block writing or shipping response-field code for these fields — it remains required before any experimental-status field (`evidence_level`, `theme`) is promoted to "stable" (§A) and before Release Stage 3 (broad patient production release). `source_type` and `theme` are not clinically loaded (citation-format and content-grouping respectively) and never required Clinical Advisor sign-off for value-set changes, only PTH's.
- **Change-control process:** adding a new code to a "stable" vocabulary (`source_type`, or `action_level`/`frequency` once they graduate) requires an ADR amendment to this document. Adding a new code to an "experimental" vocabulary (`evidence_level`, `theme`) may happen via a lighter-weight changelog entry appended to this ADR's §J, but still requires the relevant approver from the line above.
- **Backward compatibility policy:** within a stable vocabulary, changes are **additive-only** — existing codes are never renamed or repurposed. Removing or renaming a code is a breaking change requiring the deprecation process below and a version bump (§ Versioning strategy).
- **Deprecation process:** a code being retired is marked `deprecated` in this ADR's tables (not deleted from the doc), continues to be accepted and rendered by the API for a minimum of one full release cycle with a data-quality alert on each occurrence, then is removed from the locked list in a follow-up ADR amendment once no approved rows use it (confirmed by the backfill-audit process in §I).
- **Versioning strategy (locked 2026-07-23):** introduce `knowledge_vocabulary_version` as a **single field placed once at the response-envelope level** of each K2 response — not repeated per knowledge record/item. This is a **new, independent versioning axis** from the existing `/api/v1` URL path version — the backend has no prior art for a second versioning axis, so this is a novel decision, not an extension of an existing pattern (shape precedent for a versioned string: `SafetyNotice.version` in the K2 plan §10).
  - **Initial value: `"1.0"`**, matching this ADR's approval.
  - **Versioning rules:**
    - Translation or display-label changes (e.g. a corrected VN string for an existing code) do **not** increment the vocabulary version — labels are not part of the versioned contract (§G).
    - Backward-compatible canonical-value additions (a new code added to an experimental or stable list, e.g. a future `theme` value) increment the **minor** version (`1.0` → `1.1`).
    - Removal, remapping, or semantic changes to an existing code (a breaking change per §H's backward-compatibility policy) increment the **major** version (`1.0` → `2.0`).
  - This field's exact response placement (e.g. top-level key name) is a K2 implementation decision informed by this ADR, not implemented by this ADR.
- **Required tests and review gates:**
  1. A golden-vocabulary test enumerating every code in §B–§F's locked tables and asserting the corresponding DB `CHECK` constraint (where one exists) is an exact subset match — prevents silent schema drift from this ADR.
  2. A response-contract golden-file test for `PatientMedicationKnowledgeOut` asserting `frequency`, `action_level`, `condition_type`, `patient_context`, `source`, and all governance fields never appear.
  3. A response-contract golden-file test for `DoctorIngredientKnowledgeOut` asserting the allowed set (`evidence_level`, `theme`, `patient_context`, `condition_type`, `source_type` nested under `references[]`) and the still-excluded set (`frequency`, `action_level`, governance fields).
  4. An unknown-value-handling test per field with a locked list, seeding an out-of-vocabulary value and asserting the exact fail-soft/fail-closed behavior specified in §G (per-field omission, per-item omission for `action_level`, never a whole-request failure).
  5. A code-review gate: any PR touching the columns or response models for these seven fields must link to this ADR (or an approved amendment) in its description.

---

## I. K2 Impact

- **Fields remaining omitted from K2 v1, both contracts:** `frequency`, `action_level`. No route may return either in K2 v1 — this is a scope decision independent of the 2026-07-23 governance change, and requires a separate approved implementation slice to lift.
- **Fields with a PTH-decided vocabulary, and whose response-field code is UNBLOCKED FOR IMPLEMENTATION as of PTH's 2026-07-23 governance decision (§ Approval Record, Implementation Gate):**
  - `evidence_level` — patient (as localized label backed by locked code) and doctor, experimental status, per §D.
  - `theme` — patient and doctor, experimental status, per §F.
  - `source_type` — doctor only, nested in `references[]` only, stable status, per §E.
  - `patient_context` — doctor only, internal-key status, per §F.
  - `condition_type` — doctor only, internal-key status, per §F.

  All five fields are cleared for implementation. This list documents PTH's locked *vocabulary content* decision for each, and — as of 2026-07-23 — doubles as the implementation green light; it is no longer gated on Clinical Advisor or Tech Lead sign-off (§ Approval Record). All mandatory reversible controls, provenance, and origin/review-state requirements in the K2 implementation plan's governance section still apply to how these fields are implemented.
- **Plan sections and response examples that must change** (see exact list below):
  1. K2 plan §5 (lines 275–319): update to cite this ADR by exact filename and its current status (APPROVED FOR IMPLEMENTATION BY PTH — clinical and legal governance deferred) instead of "the vocabulary ADR above" / "a dedicated vocabulary ADR," and adopt the `side_effect_frequency` external field name (§B) for whenever `frequency` is eventually exposed.
  2. K2 plan §6.1/§6.2 `evidence_level` treatment: replace the unspecified example values with this ADR's locked v1 list (§D), and add an "experimental — see ADR-15" annotation.
  3. K2 plan §6.1/§6.2 `theme` treatment: replace with the finalized six-value list (§F) and its experimental-status annotation — the prior PTH-confirmation-pending framing and the `why_this_matters`-mismatch gap are both resolved (`why_this_matters` is now itself one of the six canonical values).
  4. K2 plan §6.2 `references[].source_type`: add a footnote disambiguating this from `medications.source_type` (ADR-04), citing this ADR's §E.
  5. K2 plan §6.2 `patient_context` / `condition_type`: add a footnote marking both as opaque internal keys (ADR-15 §F) — no vocabulary stability guarantee, no styling implying enumerability.
  6. K2 plan §16 (open questions, line 769): remove the "exact format of the vocabulary ADR" open question — resolved: standalone ADR, this document.
  7. K2 plan §17 (implementation gates, gate 1): update to reference ADR-15 by number and its actual current status (PTH approved for implementation; Clinical Advisor, Legal, and Tech Lead review deferred as non-blocking post-implementation hardening) — state gate 1 as fully cleared.

  Additionally, the plan must also reflect:

  8. `knowledge_vocabulary_version: "1.0"` as a single field at response-envelope scope (both contracts), per §H — not repeated per knowledge item.
  9. No `evidence_level` DB `CHECK` constraint migration in K2 v1 — the five-step sequence (§D) is future work, not part of K2 v1's implementation.
  10. The finalized six-value `theme` list (§F) replacing any prior placeholder framing.
  11. The item-scoped fail-closed rule for invalid/missing required `action_level` (§C) — never whole-medication or whole-request, always accompanied by the mandatory PHI-free telemetry fields.
  12. A stated requirement (not itself satisfied by the plan document) for a field-required-by-item-type matrix to exist before any `action_level`-bearing response-field code is implemented (§C, Implementation Gate).
  13. That response-field code for all five fields in the bullet above is unblocked for implementation as of PTH's 2026-07-23 governance decision — the plan must describe them as implementation-ready, while continuing to record that Clinical Advisor, Legal, and Tech Lead review have not happened and are deferred to post-implementation hardening (§ Release Stages).
- **Does ADR-15 approval block any K2 coding?** **No.** As of PTH's 2026-07-23 governance decision, nothing in this ADR blocks implementation. K2's ownership, authorization, retrieval (K1.6), provenance, and error-handling implementation may proceed, exactly as before. The serialization/response-model code for `evidence_level`, `theme`, `source_type`, `patient_context`, and `condition_type` is also unblocked — Clinical Advisor, Legal, and Tech Lead review are recommended future reviews (§ Recommended Future Reviews) required before Release Stage 3 (broad patient production release) and before any experimental field graduates to "stable" (§A), but are not preconditions for writing or shipping the code behind mandatory feature flags (§ Mandatory Reversible Controls). `frequency` and `action_level` simply stay absent from response models until a future ADR amendment lifts the exclusion, independent of this decision.

---

## Patient / Doctor Exposure Matrix

| Field | Patient (`PatientMedicationKnowledgeOut`) | Doctor (`DoctorIngredientKnowledgeOut`) | Status |
|---|---|---|---|
| `frequency` | ✗ omitted | ✗ omitted | Excluded from K2 v1 |
| `action_level` | ✗ omitted | ✗ omitted | Excluded from K2 v1 |
| `evidence_level` | ✅ localized label, code-backed | ✅ code + label | Experimental |
| `source_type` | ✗ omitted (no `references[]` at all) | ✅ nested in `references[]` only | Stable |
| `patient_context` | ✗ prohibited | ✅ opaque string | Internal authoring key |
| `condition_type` | ✗ prohibited | ✅ opaque string | Internal authoring key |
| `theme` | ✅ code, fail-soft label | ✅ code, fail-soft label | Experimental |

---

## Candidate Canonical-Code Tables

**`frequency`** (locked, excluded from v1): `common` · `uncommon` · `rare` · `unknown`

**`action_level`** (locked, excluded from v1): `self_monitor` · `contact_clinician` · `urgent_medical_help`

**`evidence_level`** (locked v1, experimental): `clinical_guideline` · `product_label` · `peer_reviewed_literature` · `expert_consensus` · `traditional_use` · `unknown`

**`source_type`** (locked, `DrugReference` only, stable): `formulary` · `clinical_guideline` · `product_label` · `peer_reviewed` · `other`

**`theme`** (locked v1, experimental): `why_this_matters` · `how_to_use_safely` · `what_to_monitor` · `common_side_effects` · `when_to_seek_help` · `special_considerations`

**`patient_context`, `condition_type`:** no canonical table — internal authoring keys, opaque by design (§F).

---

## Localization Examples

```
action_level = "urgent_medical_help"
  → VN label: "Cần hỗ trợ y tế ngay"

action_level = "self_monitor"
  → VN label: "Thường gặp, có thể theo dõi"

evidence_level = "clinical_guideline"
  → VN label: candidate "Theo hướng dẫn điều trị" — non-blocking content-team task, not yet PTH-confirmed

theme = "how_to_use_safely"
  → VN label: candidate "Cách dùng an toàn" — non-blocking content-team task, not yet PTH-confirmed

frequency = <any code>
  → No VN label exists anywhere in the corpus today; must be authored before frequency can ever ship (§ Open Questions)
```

## Invalid / Unknown Value Examples

```
# Case 1: evidence_level outside the locked list (§D) — fail soft, item survives
persisted: evidence_level = "grade_b"          # not in this ADR's list
response:  item returned WITHOUT evidence_level field; content/theme/etc unaffected
side effect: structured alert logged with business key, P2

# Case 2: action_level outside the locked list (§C) — fail soft, item-scoped only
persisted: action_level = "watch_closely"      # not one of the 3 locked codes
response:  the affected drug_side_effects item is omitted; the medication, the rest of the
           response, and every unrelated knowledge item are unaffected
side effect: mandatory PHI-free structured telemetry — knowledge_vocabulary_version,
             knowledge record identifier, invalid value ("watch_closely"), validation reason
             ("value not in locked action_level vocabulary"); no patient free text, no PHI

# Case 3: theme outside the locked list (§F) — fail soft, field-level only
persisted: theme = "unsanctioned_legacy_theme" # not one of the 6 locked codes
response:  item IS returned; only the `theme` field is omitted — content/evidence_level/
           last_reviewed_at are unaffected
side effect: logged as a data-quality note, not an alert — theme is cosmetic, not safety-relevant

# Case 4: whole-request behavior — NEVER triggered by vocabulary issues
persisted: every side_effect row for this ingredient has a malformed action_level
response:  200 OK, side_effects: [] (empty-state, matching K2 plan's existing empty-state convention)
           — NOT a 500, NOT a whole-request failure; only auth/DB/not-found failures produce non-200
```

---

## Migration / Backfill Impact Assessment

This ADR makes no schema changes and authorizes none directly. It identifies follow-up work required before certain classifications can be considered fully load-bearing:

- **`evidence_level`:** **K2 v1 ships with no DB `CHECK` constraint on this field (decided 2026-07-23, §D)** — the five-step sequence (app-level validation + telemetry → inventory → backfill/quarantine → staging validation → constraint migration) must complete, in order, before graduation from "experimental" to "stable" is even eligible. In particular, the template's stray `moderate` example value must be confirmed to be documentation-only and never actually seeded — or, if it was seeded, remapped or excluded — as part of step 2 (inventory). None of the five steps is performed by this ADR.
- **`theme`:** the value list is now locked (§F), removing the PTH-confirmation precondition. Graduation from "experimental" to "stable" still requires (a) a production-data audit confirming existing rows conform to the six-value list, and (b) demonstrated stable patient-UI usage over a full release cycle (§F) — neither performed by this ADR.
- **`frequency` / `action_level`:** already DB-enforced and internally consistent; no backfill required if/when a future ADR amendment lifts their exclusion from K2 — only the `side_effect_frequency` external naming decision (§B) needs to be implemented at that time.
- **`patient_context` / `condition_type`:** no backfill required for K2 v1 (opaque-key classification does not require a closed set). Recommended, non-blocking: a data-inventory ticket to catalog the actual distinct values currently in use, useful groundwork for any future decision to govern these fields (e.g., if ADR-14's K4 Context Engine eventually wants to correlate on them, per the template's §4 forward-looking notes).
- **`source_type`:** no backfill needed — already constrained and consistent.

---

## Test Requirements

See §H "Required tests and review gates" for the five specific test/gate requirements. Summarized:

1. Golden-vocabulary-vs-DB-constraint test (all locked fields).
2. Patient response golden-file test (exclusion assertions).
3. Doctor response golden-file test (inclusion + exclusion assertions).
4. Unknown-value fail-soft/fail-closed behavior test, per field with a locked list, including the `action_level`-drops-whole-item special case.
5. PR-description review gate linking to this ADR for any touching code.

---

## Open Questions

Resolved as of this ADR's approval (2026-07-23) and removed from this list: the `theme` final list (locked, §F), whether to add a GRADE-style tier to `evidence_level` (decided: no, reserved as separate future `evidence_quality`, §D), `evidence_level` DB constraint timing (decided: not in K2 v1, five-step sequence locked, §D), `knowledge_vocabulary_version` scope (decided: response-envelope level, §H), and `frequency`/`action_level` DB column naming (decided: API-level alias only, no DB rename in K2, §B).

Remaining open:

1. **Future governance of `patient_context` / `condition_type`.** The authoring template's §4 flags both as candidate K4 Context Engine inputs. Should either ever graduate from "internal authoring key" to a governed vocabulary? — explicitly **deferred until an actual product, clinical-logic, analytics, or interoperability requirement exists** (§F); not a K2-era decision.
2. **VN display labels for `frequency` and `evidence_level`.** Neither has ever had a Vietnamese label authored. This ADR does not invent them. Labels must be keyed by canonical codes (never a free-text substitute for the code), and patients must never receive a raw evidence-level or frequency code as the primary displayed text. Needed before `evidence_level` can be considered patient-ready beyond "technically renders" and before `frequency` can ever ship. — **Owner: Content/Product team**, explicitly assigned, not scheduled by this ADR.

---

## J. Vocabulary Changelog

- **2026-07-23 — ADR-15's product/vocabulary-direction decisions approved by PTH.** Clinical Advisor and Tech Lead sign-off are pending and not yet recorded (§ Approval Record). Binding product decisions locked by PTH's approval:
  - `theme`: provisional/conflicting lists replaced with the finalized six-value canonical list (`why_this_matters`, `how_to_use_safely`, `what_to_monitor`, `common_side_effects`, `when_to_seek_help`, `special_considerations`); classification remains experimental.
  - `evidence_level`: confirmed as the permanent six-value source-classification vocabulary; no GRADE-style tier added; `evidence_quality` reserved as a distinct future field name for evidence certainty/quality, not yet designed.
  - `evidence_level`: locked the decision not to add a DB `CHECK` constraint in K2 v1, plus the required five-step sequence before any future constraint migration.
  - `knowledge_vocabulary_version`: locked at response-envelope placement (not per-record), initial value `"1.0"`, with minor/major bump rules defined.
  - `patient_context` / `condition_type`: reaffirmed as opaque internal authoring keys with explicit no-badge/no-color/no-filter UI constraints; graduation deferred until an actual requirement exists.
  - `frequency`: confirmed `side_effect_frequency` as the API-level alias; explicitly decided not to rename the underlying DB column as part of K2.
  - `action_level`: clarified that invalid-value fail-closed behavior is scoped to the single affected knowledge item only (never the medication, request, or unrelated items), added mandatory PHI-free structured telemetry fields, and required a field-required-by-item-type matrix to exist before implementation.
- **2026-07-23 (same day, second decision) — PTH changes the governance decision: implementation unblocked ahead of Clinical Advisor/Legal/Tech Lead review (§K).** Status changed from "Approved by PTH — pending Clinical Advisor and Tech Lead sign-off" to "Approved for implementation by PTH — clinical and legal governance deferred." Response-field code for `evidence_level`, `theme`, `source_type`, `patient_context`, and `condition_type` is unblocked (§I, § Implementation Gate). Added §K (mandatory reversible controls, provenance, origin/review-state, safety boundary, release stages). Clinical Advisor and Tech Lead reclassified from blocking sign-offs to recommended, non-blocking future reviews; Legal added as a third recommended future reviewer. `frequency`/`action_level` exclusion from K2 v1 is unaffected — a separate scope decision.

*(Future experimental-list changes to `evidence_level` or `theme`, approved per §H's lighter-weight change-control path, are appended here with date, approver, and diff.)*

---

## K. Governance Decision (2026-07-23) — PTH Accepts Implementation Ahead of Clinical/Legal Governance

**This section is the binding governance decision superseding this ADR's original "pending sign-off" framing.** PTH has decided the product strategy is to build the full AI and medication-knowledge capability using currently available sources, then progressively review, clean, constrain, and govern it — rather than blocking implementation on Clinical Advisor and Legal review completing first. This section applies to this ADR's seven vocabulary fields and, by reference, to the medication knowledge and AI capabilities the K2 implementation plan unblocks (ingestion, AI normalization, AI synthesis, doctor-facing and patient-facing knowledge responses) — the K2 plan's own governance section is the operational home for those, and must not conflict with what is stated here.

### K.1 Mandatory reversible controls (feature flags)

Implementation must include **independently controllable feature flags**, at minimum, for:

- medication knowledge retrieval
- external-source ingestion
- AI synthesis
- doctor-facing AI content
- patient-facing AI content
- experimental vocabulary fields (this ADR's `evidence_level` and `theme`, §A)

**Disabling any one flag must stop new processing and suppress API/UI exposure for that capability, without deleting stored knowledge or provenance.** A flag is a kill switch on new exposure and new processing, never a data-deletion trigger — turning a flag off and back on must not lose or corrupt anything recorded while it was off.

### K.2 Provenance (non-negotiable)

Every knowledge item and every AI-generated output must preserve, at minimum:

- exact source identity
- source URL or stable identifier
- publication date (when available)
- retrieval date
- source/version metadata
- the relevant citation or source span
- normalization version
- model identifier (for AI-generated content)
- prompt/template version (for AI-generated content)
- generation timestamp (for AI-generated content)
- review status
- supersession/deprecation history

**AI-generated content must never overwrite raw source content.** Raw source data, normalized knowledge, AI synthesis, reviewed content, and patient-display content must be kept as separate, distinguishable layers — never collapsed into one mutable field.

### K.3 Origin and review state

Every response and stored record must distinguish, explicitly and machine-readably:

- **Origin:** source-extracted content vs. rule-derived content vs. AI-synthesized content.
- **Review state:** unreviewed vs. reviewed vs. rejected vs. deprecated.

**Experimental or unreviewed AI content must never be represented as clinician-verified**, in code, in API responses, or in UI copy — origin and review state must be visible enough (to the code and, where relevant, to the reader) that this distinction cannot be silently lost.

### K.4 Safety boundary

AI may retrieve, summarize, explain, compare sources, identify conflicts, and generate review suggestions.

**Without a separate, explicit approval, AI must not autonomously:**

- stop or change a medication
- change a dosage
- replace a prescribed medication
- declare a serious interaction safe
- determine that medical evaluation is unnecessary
- suppress or downgrade serious safety warnings

This boundary applies regardless of feature-flag state — enabling AI synthesis or AI content flags never implicitly grants any of the six autonomous actions above.

### K.5 Release stages

Three separate, independently controlled gates govern this program going forward:

1. **Implementation approval** — approved by PTH. This ADR (2026-07-23) and the K2 implementation plan's matching update constitute this gate for the capabilities they cover.
2. **Internal experimental release** — requires technical tests, provenance integrity verification, observability, feature flags, and kill-switch verification, all passing, before any capability is turned on even internally.
3. **Broad patient production release** — separately controlled by PTH. Clinical, legal, and content hardening may be required before expansion to this stage; reaching Stage 2 does not imply Stage 3 is automatically approved.

Clinical Advisor, Legal, and Tech Lead review (§ Recommended Future Reviews) are expected before Stage 3, not before Stage 1.

---

## Approval Record

- [x] **PTH** — approved the product and vocabulary-direction decisions in this ADR on 2026-07-23: field classifications (§A), the finalized `theme` list (§F), the `evidence_level` canonical list and its separation from a future `evidence_quality` (§D), the `patient_context`/`condition_type`/`source_type` treatment (§E/§F), and the `knowledge_vocabulary_version` versioning approach (§H).
- [x] **PTH** — separately approved, 2026-07-23, that **implementation of all five fields above may proceed without waiting for Clinical Advisor, Legal, or Tech Lead review** (§K). PTH explicitly accepts this ordering and its risk; this is a governance decision, not an oversight.

**Recommended Future Reviews (non-blocking).** These reviewers have **not** reviewed or approved anything in this document. Their review is recommended before Release Stage 3 (§K.5, broad patient production release) and before any experimental-status field (`evidence_level`, `theme`) graduates to "stable" (§A) — it is not required to write, merge, or ship the code behind mandatory feature flags (§K.1).

- [ ] **Clinical Advisor** — not yet reviewed. Recommended scope when review happens: clinical vocabulary for `evidence_level` and `action_level` (§C/§D), evidence-source semantics, patient-facing safety interpretation (escalation semantics, §C), and the grading-methodology preconditions for any future `evidence_quality` field (§D).
- [ ] **Legal** — not yet reviewed. Recommended scope when review happens: regulatory and liability exposure of AI-synthesized medication knowledge reaching patients or doctors, the safety-boundary rules in §K.4, and any jurisdiction-specific medical-information-display requirements.
- [ ] **Tech Lead** — not yet reviewed. Recommended scope when review happens: API-envelope versioning for `knowledge_vocabulary_version` (§H), validation semantics and fail-soft/fail-closed rules (§G), mandatory telemetry fields (§C), the field-required-by-item-type matrix requirement (§C), legacy-data/backfill handling (§ Migration/Backfill Impact), and the future DB `CHECK`-constraint migration sequencing (§D).

**No approval is recorded for Clinical Advisor, Legal, or Tech Lead as of 2026-07-23, and none is claimed.** This document must never be read, cited, or displayed as asserting that any of the three has reviewed or approved it. PTH's approval above is sufficient to clear Gate 1 (Implementation Approval, §K.5) on its own.

## Implementation Gate

**Gate 1 (Implementation Approval) — FULLY CLEARED 2026-07-23 by PTH.** This ADR itself performs no migration and changes no code. Two decisions compose this gate, both cleared:

- **PTH product-decision gate: CLEARED (2026-07-23).** The vocabulary classifications, canonical code lists, and versioning/telemetry design in this ADR (§A–§H) are PTH's locked product decisions.
- **PTH implementation-ahead-of-governance gate: CLEARED (2026-07-23, §K).** PTH explicitly accepts implementation proceeding before Clinical Advisor, Legal, or Tech Lead review. Response-field code for `evidence_level`, `theme`, `source_type`, `patient_context`, and `condition_type` may be written now, subject to the mandatory reversible controls, provenance, and origin/review-state requirements in §K.

**Net effect: response-field implementation for `evidence_level`, `theme`, `source_type`, `patient_context`, and `condition_type` is UNBLOCKED.** `frequency` and `action_level` remain excluded from K2 v1 — an independent scope decision, unaffected by this gate — pending a future ADR amendment. Clinical Advisor, Legal, and Tech Lead review are Gate 2/Gate 3 milestones (§K.5): required before broad patient production release and before any experimental field is promoted to "stable," not before writing code. The field-required-by-item-type matrix (§C) remains a required artifact for `action_level`-bearing work specifically, independent of this gate and of `action_level`'s own continued exclusion from K2 v1.
