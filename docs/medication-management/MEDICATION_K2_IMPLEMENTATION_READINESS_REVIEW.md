# MetoCare Medication — K2 Implementation Readiness Review

**Status:** REVIEW ONLY — no route, schema, service, migration, frontend, or test code written
by this document. This is the final gate PTH reads before issuing explicit GO to code, per
PTH's own instruction. No commit, no PR from this document.

**Date:** 2026-07-23
**Scope:** `MEDICATION_K2_KNOWLEDGE_API_IMPLEMENTATION_PLAN.md` (as governance-updated the same
day) and the wider capability set that PTH's 2026-07-23 governance decision unblocked:
medication knowledge retrieval, external-source ingestion, AI normalization, AI synthesis,
doctor-facing AI content, patient-facing AI content, experimental vocabulary fields.
**Method:** direct inspection of the current backend — `app/models/drug_knowledge_content.py`,
`app/models/drug_knowledge_governance.py`, `app/models/drug_knowledge_references.py`,
`app/services/knowledge_repository.py`, `app/services/medication_knowledge_import/schema.py`,
`app/core/feature_flags.py`, `app/api/deps_clinic_saas.py`, `app/models/care.py`, and the
current Alembic head — not re-derived from the plan documents alone.

---

## 0. Bottom line

| Slice | Ready for PTH GO now? | Why |
|---|---|---|
| **Slice 0 — Provenance/origin foundation** | **No — needs its own short implementation plan first** (§1, §2) | No `origin` field exists on any knowledge table today; this is a real schema gap, not paperwork. |
| **Slice 1 — K2 retrieval API (this plan's 2 endpoints)** | **Yes, once Phase C (Codex review) and gate 6 (explicit PTH GO) close** — unchanged from the K2 plan's own §17 | Zero new tables, zero new write paths, zero AI. Fully speced, fully audited against `app/models/`. |
| **Slice 2 — External-source ingestion** | **No implementation plan exists** | `find app -iname "*ingest*"` returns nothing. Governance unblocks it; nothing designs it yet. |
| **Slice 3 — AI normalization** | **No implementation plan exists; also blocked by a live code constraint** | `medication_knowledge_import/schema.py` hard-types `ai_generated: Literal[False]` today — AI-authored import content is rejected by the type system, not just policy. |
| **Slice 4 — Doctor-facing AI content** | **No implementation plan exists** | Depends on Slice 3. |
| **Slice 5 — Patient-facing AI content** | **No implementation plan exists** | Depends on Slice 4. Must be the most conservative, last-shipped surface. |

**Recommendation: PTH's explicit GO should be issued per-slice, not once for the whole
program.** Slice 1 can be GO'd on the existing K2 plan almost as-is. Slices 0, 2, 3, 4, 5 each
need a short, focused implementation plan of their own — this review identifies what each plan
must contain, it does not author them.

---

## 1. Slice ordering — what builds first, and why

```
Slice 0: Provenance/origin schema + flag registration   (foundation, no visible behavior change)
   │
   ├──► Slice 1: K2 retrieval API (patient + doctor read endpoints)   ─── ships independently
   │
   └──► Slice 2: External-source ingestion (raw capture, origin=source_extracted)
            │
            └──► Slice 3: AI normalization (draft rows, origin=ai_synthesized)
                     │
                     └──► Slice 4: Doctor-facing AI content exposure
                              │
                              └──► Slice 5: Patient-facing AI content exposure
```

**Slice 0 must land before Slices 2-5, but not before Slice 1.** Slice 1 (retrieval) reads only
already-`approved` rows through `knowledge_retrieval.py`, which does not touch `origin` at all —
it has no dependency on Slice 0. Building Slice 1 first, in parallel with drafting Slice 0's own
plan, is safe and matches the K2 plan's existing "Slice 1 has zero unresolved gaps" state.

**Why Slice 1 (retrieval) goes before any AI/ingestion slice, not after:** it is the only slice
with zero new write paths — it cannot corrupt data, cannot mis-attribute AI content as
clinician-verified, and cannot violate the safety boundary (§4), because it never constructs a
knowledge row, only reads existing `approved` ones. It is also the only slice with a complete,
audited implementation plan today. Shipping it first proves the retrieval contract, the
feature-flag gate pattern (§3), and the audit/caching discipline (K2 plan §11) on live traffic
before any AI-authored content exists to flow through it.

**Why ingestion goes before normalization, and normalization before synthesis (not
collapsed into one slice):** each stage has an independently disable-able failure mode
(mandatory reversible controls, §3) — a bad ingestion source must be killable without also
killing already-normalized content; a bad normalization pass must be killable without deleting
raw ingested source; a bad synthesis prompt must be killable without touching either. Collapsing
them into one slice would make the flags perform the same job at three different layers,
defeating the point of independent kill switches.

**Why doctor-facing AI content ships before patient-facing:** doctors are professionally
equipped to catch a bad AI output that a patient is not; this is the same precedent already
encoded in this codebase's own flag list (`CLINICAL_COPILOT` is doctor-facing and still defaults
OFF — `app/core/feature_flags.py:34,60`). Patient-facing AI content should not ship until
doctor-facing AI content has been live through at least one full Release Stage 2 (internal
experimental) cycle with clean provenance/observability results (ADR-15 §K.5).

---

## 2. Mandatory migrations

**Slice 1 (K2 retrieval): zero migrations.** Verified directly — `drug_usage`,
`drug_patient_education`, `drug_side_effects`, `drug_monitoring`, `drug_contraindications`
(`app/models/drug_knowledge_content.py`) already carry every column both endpoints need:
`locale`, `audience`, `status`, `evidence_level`, `source`, `version`, `last_reviewed_at`, the
per-table business-key partial-unique indexes, and (for the doctor contract) `DrugReference` /
`KnowledgeReferenceLink` for citations. This matches the K2 plan's own §2.1 claim ("Migration:
None") — confirmed against the live model file, not just the plan's assertion.

**Slice 0 (provenance/origin foundation): one mandatory migration, before any AI-touching
slice.** Two concrete gaps, both verified by absence:

1. **No `origin` column exists anywhere.** `grep` across `app/models/` and
   `app/services/medication_knowledge_import/` for `origin_type`/`content_origin` found no
   knowledge-row-level origin field. `KnowledgeLifecycleMixin`
   (`app/models/drug_knowledge_content.py:59-92`) has provenance and lifecycle columns but no
   way to say "this row is source-extracted, rule-derived, or AI-synthesized." **Recommended
   shape:** add `origin: Mapped[str]` (CHECK-constrained to `source_extracted` /
   `rule_derived` / `ai_synthesized`, `NOT NULL`, default `source_extracted` for backward
   compatibility with every row written before this migration) directly to
   `KnowledgeLifecycleMixin`, following the same "add one column to the shared mixin, migrate
   all five tables in one revision" shape already used by `k1_a1b_artifact_hash.py`. Every row
   has exactly one origin — this belongs on the core table, not a side table.
2. **No AI-generation metadata storage exists.** No `model_identifier`,
   `prompt_template_version`, `generation_timestamp`, or `normalization_version` column or table
   exists anywhere in `app/models/`. **Recommended shape:** a new polymorphic side table,
   `knowledge_ai_generation_metadata`, keyed by `(knowledge_table, knowledge_row_id)` exactly
   like the existing `knowledge_review_specialties`
   (`app/models/drug_knowledge_governance.py:61-86`) and `knowledge_reference_links`
   (`app/models/drug_knowledge_references.py:88-113`) — same polymorphic-association rationale
   both docstrings already give ("metadata-about-X, never joined for clinical content itself").
   Populated only for `origin='ai_synthesized'` rows; absent for the other two origins. This
   avoids adding four mostly-`NULL` columns to five hot, high-traffic tables.

**Slice 0 also requires one non-migration code change, equally mandatory:**
`app/services/medication_knowledge_import/schema.py:171` currently declares
`ai_generated: Literal[False]` — a Pydantic type that makes any AI-authored import payload fail
validation before it reaches the database. This must become a real `bool` (or be superseded by
the new `origin` field) before Slice 3 (AI normalization) can ingest anything. Flag this
explicitly in whichever plan authors Slice 0/3 — it is not covered by a database migration and
would otherwise be missed.

**Slice 2 (ingestion): at least one migration, not yet designed.** No ingestion table or module
exists (`find app -iname "*ingest*"` returns nothing). Whether raw ingested content lands in a
new dedicated table or as `status='draft', origin='source_extracted'` rows in the existing five
tables is an open design question for Slice 2's own plan — this review does not decide it, but
flags that assuming "no new table needed" would be premature; the current schema was designed
for manually-authored content only (`KnowledgeLifecycleMixin`'s docstring: "No clinical content
is authored by this migration").

**Citation/reference provenance: no migration needed anywhere.** `DrugReference` +
`KnowledgeReferenceLink` (`app/models/drug_knowledge_references.py`) already cover source
identity, URL/stable identifier (`document_identifier`), publication date, retrieval date
(`accessed_at`), and source/version metadata (`source_version`) for both source-extracted and
future AI-synthesized citations. Reuse as-is.

**Pre-flight, unrelated to K2 but must be checked before any of the above:** local dev DB is
currently at revision `1ec6f403fced`, behind the actual migration head
(`k1_a1b_artifact_hash`). Confirm staging/production are at head before Slice 0 work starts;
this is an environment-hygiene check, not a K2-specific blocker.

---

## 3. Feature-flag architecture

**Do not invent a new mechanism — extend the existing one.** `app/core/feature_flags.py`
already implements exactly the architecture PTH's decision calls for: a `FeatureFlag` `StrEnum`,
a `_DEFAULTS` dict, and `is_enabled()`, which reads `FEATURE_<NAME>` or the `MCP_FEATURE_<NAME>`
alias from the environment, **fails closed on any unrecognized flag**, and falls back to the
coded default otherwise. It already has the exact precedent this program needs:
`CLINICAL_COPILOT` (doctor-facing AI over PHI, default OFF) and `CLINIC_SAAS` (new module,
default OFF, gated at the router level) are structurally identical to what medication knowledge
AI needs.

**Recommended new flags (6, matching PTH's mandated list 1:1):**

| Flag | Default | Precedent |
|---|---|---|
| `MEDICATION_KNOWLEDGE_RETRIEVAL` | `False` | new capability — off until Slice 1 ships |
| `MEDICATION_KNOWLEDGE_INGESTION` | `False` | mirrors `CLINIC_SAAS` — new module, fail-closed |
| `MEDICATION_KNOWLEDGE_AI_SYNTHESIS` | `False` | mirrors `CLINICAL_COPILOT` — real LLM, fail-closed |
| `MEDICATION_KNOWLEDGE_DOCTOR_AI_CONTENT` | `False` | gates exposure, independent of synthesis running |
| `MEDICATION_KNOWLEDGE_PATIENT_AI_CONTENT` | `False` | most conservative — independent of doctor-facing flag |
| `MEDICATION_KNOWLEDGE_EXPERIMENTAL_VOCAB` | `False` (or `True`, PTH's call) | gates `evidence_level`/`theme` while ADR-15 §A status is "experimental" |

**Enforcement pattern — copy `app/api/deps_clinic_saas.py` exactly.** That module is a
20-line, single-purpose router dependency: `require_clinic_saas_enabled()` raises `503` when
`is_enabled(FeatureFlag.CLINIC_SAAS)` is `False`, mounted via
`APIRouter(dependencies=[Depends(...)])` so the entire route surface fails closed before any
handler code runs. A new `app/api/deps_medication_knowledge.py` with one such dependency per
flag above is the correct, minimal shape — not a new abstraction. **503, not 404** — signals
"temporarily unavailable," matching `_FEATURE_UNAVAILABLE_DETAIL`'s existing convention, and
distinguishes "flag off" from "resource doesn't exist" for the retrieval endpoints' own 404
semantics (K2 plan §8).

**Reversibility requirement, stated as an architecture property, not just a rule:** because
`is_enabled()` reads flags from environment variables at call time with no caching layer this
review found, flipping a flag is a deploy-config change, not a data mutation — disabling
`MEDICATION_KNOWLEDGE_INGESTION` mid-flight stops new ingestion calls from passing the router
gate on the very next request; it never touches rows already written. This satisfies "stop new
processing... without deleting stored knowledge or provenance" by construction, provided (and
only provided) every write path is gated at the router/dependency layer, never inside a
service function that could be reached by another, un-gated caller. Each slice's own plan must
name every entry point into its write path and confirm all of them sit behind the gate.

---

## 4. Provenance data model

**Already sufficient — reuse without change:**

- **Source identity, source/version metadata, review status:** `KnowledgeLifecycleMixin`
  (`source`, `version`, `evidence_level`, `reviewed_by`, `last_reviewed_at`, `status`,
  `status_changed_at`, `status_changed_by`, `authored_by`, `artifact_hash`) already covers this
  for all five knowledge tables.
- **Source URL/stable identifier, publication date, retrieval date, citation span, source
  version:** `DrugReference` (`publisher`, `title`, `source_type`, `url`,
  `document_identifier`, `publication_date`, `source_version`, `accessed_at`) plus
  `KnowledgeReferenceLink`'s polymorphic many-to-many already cover every one of these fields
  for citation-level provenance, for any origin.
- **Supersession/deprecation history:** `_deprecate_superseded()`
  (`app/services/knowledge_repository.py:334-365`) already flips the previous `approved` row
  for the same business key to `deprecated` atomically inside `approve_row`'s own transaction,
  never deletes it, and the partial-unique-index backstop
  (`test_partial_unique_index_backstop_rejects_second_approved_row`) already guarantees at most
  one live `approved` row at a time. This satisfies "supersession/deprecation history" today,
  for every origin, with no new code.

**Missing — requires Slice 0 (§2):**

- **Origin classification** (source-extracted / rule-derived / AI-synthesized) — does not
  exist on any table today. New `origin` column on `KnowledgeLifecycleMixin` (§2).
- **AI-generation-specific fields** (model identifier, prompt/template version, generation
  timestamp, normalization version) — no storage exists. New `knowledge_ai_generation_metadata`
  side table (§2).
- **"Never overwrite raw source content" as an enforced invariant, not just a rule:** the
  existing schema already enforces the analogous invariant for reviewed content
  (approve/deprecate is append-only, never an in-place edit — see `_deprecate_superseded`
  above). The same discipline must extend to raw ingested source content once Slice 2 exists:
  normalization and synthesis must always **write new rows**, never `UPDATE` a raw-capture row
  in place. This is a service-layer discipline for Slice 2/3's own plans to encode as a test
  (§5), not a schema constraint this review can add today, since the raw-capture table doesn't
  exist yet.

**Enforcement precedent to copy directly:** `app/models/care.py`'s `CarePlan` model
(`ai_generated: Mapped[bool]`, lines ~206-253) already implements, for a different domain,
exactly the rule ADR-15 §K.3 requires: `@validates` hooks that reject constructing an
AI-generated row in a forbidden status (`ai_generated=True` may only ever be created at
`status=DRAFT`; flipping `ai_generated` to `True` later re-checks the current status and rejects
if it's already past the allowed point). **Recommendation: apply the identical `@validates`
pattern to `KnowledgeLifecycleMixin`'s new `origin` field** — reject, at the ORM layer, any
attempt to construct or transition a row to `origin='ai_synthesized'` with
`status != 'draft'` except through the existing `approve_row`/`retire_row` functions, which
already enforce role-gated (`can_approve_knowledge`), non-self-approval, specialty-review-gated
transitions. This makes "AI content must go through the same human review lifecycle, never
self-approve" a code-level invariant identical in mechanism to a precedent already shipped and
tested in this codebase, not a new pattern.

---

## 5. Tests and rollback gate

**Flag kill-switch tests (one per new flag, §3):** mirroring the existing `CLINIC_SAAS`/
`CLINICAL_COPILOT` flag-off regression coverage already in this suite —
(a) flag off → every gated route returns `503`, and no write-path function is reachable through
any other entry point (grep-guard, same convention as K2 plan §13's "No AI/frontend
regression" test); (b) flag off → zero new DB rows are written, ever, from a request that
reaches the gate; (c) flag flipped back on → previously stored rows are immediately servable
again with no reprocessing step required — proves "disabling never deletes" is actually true,
not merely intended.

**Origin/review-state invariant tests:** a schema-introspection or service-level test proving no
code path can construct `origin='ai_synthesized', status='approved'` directly — every
AI-authored row must transit `draft → clinical_review → approved` through the existing
`approve_row` function, with the same `authored_by != status_changed_by` self-approval block
already enforced for human authors. This is the direct test of the `@validates` enforcement in
§4.

**Provenance completeness tests:** before an `origin='ai_synthesized'` row may reach
`approved`, assert every field in the governance decision's non-negotiable list (§K.2 of
ADR-15) is present: the existing `_approved_invariants_check` DB `CHECK` already enforces
`source`/`version`/`evidence_level`/`reviewed_by`/`last_reviewed_at` for every origin; a new
service-level check (the AI metadata lives in a side table, not enforceable by a single-table
`CHECK`) must additionally assert `knowledge_ai_generation_metadata` has a matching row with
non-null `model_identifier`, `prompt_template_version`, and `generation_timestamp` before
`approve_row` will accept an AI-originated row.

**Safety-boundary regression tests:** one named test per each of ADR-15 §K.4's six prohibited
autonomous actions (stop/change medication, change dosage, replace medication, declare a
serious interaction safe, declare evaluation unnecessary, suppress/downgrade a safety warning),
asserting the AI synthesis service cannot produce output that reaches a route response without
a human `approve_row` call in between. The exact mechanism (contract test on synthesis service
output shape vs. a lint-style grep-guard) is Slice 3/4's own implementation-planning decision —
this review requires the test to exist, not how it's built.

**Rollback gate — three parts:**

1. **Every Slice 0 migration must have a tested, working `downgrade()`** — the existing
   convention for every migration already in `backend/alembic/versions/`. No exception for a
   "just add a column" migration.
2. **Additive-only schema changes.** The new `origin` column and
   `knowledge_ai_generation_metadata` table must not be required by any currently-running code
   path (K1.5's `approve_row`/`retire_row`, K1.6's `knowledge_retrieval.py`) — those must keep
   working unmodified whether or not Slice 0's migration has run. This makes Slice 0 safely
   forward- and backward-deployable independent of every other slice.
3. **Behavioral rollback is a flag flip, not a deploy revert**, for every slice except Slice 0's
   own schema change. This is the entire point of §3's mandatory reversible controls — verify it
   with the kill-switch tests above before treating any slice as "shippable."

**Unchanged, standing program convention:** Codex review rounds to 0 P0/P1 before merge (K2
plan §14/§17) applies to every slice in this document, not only Slice 1.

---

## 6. Absolute scope boundaries — must not creep, in any slice

- **Slice 1 stays read-only, `approved`-only, zero write path, ever.** No AI, ingestion, or
  approval-workflow call from either retrieval endpoint. This is the K2 plan's own §2.2/§3/§12
  boundary — reaffirmed, not relitigated.
- **`frequency`/`action_level` stay excluded from K2 v1 in every slice above**, unaffected by
  the 2026-07-23 governance update. Lifting this requires its own future ADR amendment
  (ADR-15 §B/§C).
- **No AI code may call `approve_row`/`retire_row` or any other status-mutating function on
  itself.** Every AI-authored row enters the same human review lifecycle as manually authored
  content — `origin='ai_synthesized'` is a label, not a bypass. No "auto-approve above a
  confidence threshold" path, ever, without a separate, explicit, named approval distinct from
  this governance decision (ADR-15 §K.4).
- **Patient-facing AI content (Slice 5) must not ship ahead of doctor-facing AI content
  (Slice 4)** having been live through at least one full Release Stage 2 cycle. This is a
  sequencing rule this review locks, not something inspection alone proves — treat it as a
  hard gate on Slice 5's own GO.
- **No patient-specific doctor lookup**, in any slice — K2 plan §2.2 already excludes combining
  a doctor's consented-patient relationship with medication knowledge content; AI synthesis
  output must stay ingredient/drug-scoped and generic, never patient-instance-scoped, until a
  separate, later authorization design is built and reviewed on its own.
- **No new PHI exposure.** Ingestion, normalization, and synthesis operate on generic
  drug/ingredient knowledge only — never on a specific patient's data. Nothing in the governance
  update licenses touching patient-instance data; this stays exactly as scoped in the current K2
  plan (§3 Consumers, §12) and ADR-15.
- **`app/ai/*` must still never import `knowledge_retrieval.py` or the knowledge tables
  directly**, bypassing whatever sanctioned service boundary Slice 3 defines. The existing
  grep-guard test convention (K2 plan §13) must be extended to cover the new AI modules once
  they exist, never dropped.
- **Endpoint #2 caching stays OFF** (K2 plan §11) until version-supersession soundness is
  separately proven — untouched by this review or the governance update.
- **This review authors no code and settles no open design question for Slices 2-5** — raw
  ingestion table shape, the exact synthesis-service contract test mechanism, and the
  precise doctor/patient AI content route shapes are explicitly left to each slice's own
  implementation plan, which must pass the same review gates (route/schema approval, response
  examples, error mapping — K2 plan §17 gates 2-4 shape) this K2 plan itself passed, before
  requesting its own PTH GO.

---

## 7. What this review recommends PTH actually do next

1. **Issue explicit PTH GO for Slice 1 (K2 retrieval API)** once Phase C (Codex review of the
   K2 plan document itself) closes — nothing in this review found a new blocker for Slice 1; it
   was already fully audited against the live schema.
2. **Request a short Slice 0 implementation plan** (provenance/origin schema + the 6 feature
   flags, §2-§4 above) before authorizing any ingestion/AI code — this is schema-and-flags only,
   no product behavior, and is the natural next planning artifact.
3. **Do not GO on ingestion, AI normalization, AI synthesis, or AI content exposure yet** — none
   of the four has an implementation plan today; this review defines what each plan must contain
   (§1-§6) but does not substitute for one.

**No route, schema, service, migration, frontend, or test code was written as part of this
review. No commit, no PR.**
