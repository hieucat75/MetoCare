# Medication Knowledge — Phase A, PR-A1 Implementation Plan

**Date:** 2026-07-16
**Author:** Claude Code (session following K1-S4 exit review)
**Scope:** Planning only. No code, no migration, no API, no frontend, no AI wiring, no clinical content, no new ADR.
**Related:** `MEDICATION_K1_EXIT_CRITERIA.md` (all 10 PASS, staging live), `adrs/ADR-13-KNOWLEDGE-CONTENT-LIFECYCLE.md`, `MEDICATION_PHASE_A_BLOCKING_FINDINGS.md`, [[project_medication_knowledge_phase_ab]] (memory)

This plan answers PTH's 10-point brief for PR-A1 ("Knowledge Import Framework"). It is grounded in the actual merged K1 code (`git show origin/main:...`), not a re-statement of the spec.

**Revision note (2026-07-16, post-PTH-review):** PTH reviewed the original version of this plan and made three decisions, incorporated below: (1) **rejected** "references live only in the source file" — structured reference persistence is required, a real schema gap that blocks A1b (not A1a) until resolved; (2) **approved** disclaimer-as-rendering-constant unchanged; (3) Calcium and `clinical_specialties` findings upgraded from "flagged, low severity" to explicit blockers with concrete next steps. See `MEDICATION_PHASE_A_BLOCKING_FINDINGS.md` for the two findings PTH asked to be tracked separately. **A1a is GO; A1b is blocked pending the reference-persistence schema gap and specialty seed.**

---

## 1. Current-state audit

### Reusable from K1-S3 (`backend/app/services/knowledge_repository.py`, commit `002e90a`)

| Function | Signature | Reuse in Phase A |
|---|---|---|
| `create_draft(db, model_cls, *, authored_by, **fields)` | Always INSERT, status forced to `'draft'` | **Reuse directly.** This is the only write path Phase A's orchestrator should call. |
| `submit_for_review(db, row, *, actor_user_id)` | Atomic `UPDATE...WHERE status='draft'`, `draft→clinical_review` only | **Reuse directly.** This is the only status transition Phase A's orchestrator may trigger. |
| `validate_transition(...)` | Pure function, full ADR-13 rule set incl. self-approval block + specialty gate | **Do not call with `new_status="approved"` anywhere in Phase A.** Not even in tests against a real write path — K1-S3's own scope lock stays in force. |
| `check_specialty_completeness` / `record_specialty_review` | Specialty sign-off bookkeeping | **Out of scope for Phase A.** Only matters for the `clinical_review→approved` leg, which Phase A never reaches. |
| `list_published` | Read-only, `status='approved'` filter | Not needed — Phase A produces no approved rows to list. |

Phase A's importer is therefore an **orchestration layer on top of `knowledge_repository`**, not a replacement for it. **Superseded by `MEDICATION_PHASE_A1B_ORCHESTRATOR_IMPLEMENTATION_PLAN.md` §2a/§14:** that plan's round-2/round-3 review found `create_draft` cannot be called directly from a multi-file batch (it commits internally, breaking one-commit-per-batch) — A1b does add two small, backward-compatible write primitives to `knowledge_repository.py` (`build_draft`/`add_draft`), with `create_draft` itself becoming a thin wrapper over them for existing callers. Treat this paragraph as historical context for A1a's scope, not as A1b's actual design.

### The 5 knowledge tables in scope (confirmed against `backend/app/models/drug_knowledge_content.py`)

`drug_usage`, `drug_patient_education`, `drug_side_effects`, `drug_monitoring`, `drug_contraindications`. `drug_interactions` remains excluded (no table exists). This matches the spec's list of "Patient Education / Usage / Side Effects / Monitoring / Contraindications" exactly.

**Gap — "Drug References" (spec's 6th knowledge type) has no backing table, and PTH rejected the source-file-only resolution.** There is no `drug_references` table anywhere in the schema, and no `references: list[...]` column on any of the 5 tables — each row has exactly one `source: VARCHAR(255)` string. The original version of this plan proposed keeping the full reference list only in the versioned YAML source file; **PTH rejected this** — provenance that only lives in a source file is lost the moment that file is renamed/moved/deleted, can't be queried, can't back a future patient-facing "where did this come from" API, and doesn't support many-to-many (one item citing multiple sources, one source backing multiple items). **This is now a real schema gap that must be resolved (a `drug_references` table + join, added via migration) before A1b can persist anything.** A1a is unaffected — it validates the `references:` field's structure in the input file regardless of where it eventually persists. Tracked as Finding 1 in `MEDICATION_PHASE_A_BLOCKING_FINDINGS.md`.

**Gap — no `disclaimer` column anywhere. PTH approved treating this as a rendering-time constant** (not clinical content, not per-row, not author-editable) — see §3 for the unchanged resolution.

**Gap — Calcium is not in the relational core, and "just add Calcium" is not an acceptable resolution.** Checked the 41-entry catalog seed (`backend/app/services/drug_catalog.py`) against Phase B's 5 target drugs: `levothyroxine`, `metformin`, `aspirin`, `warfarin` are present (so `drug_ingredients` rows exist for them after K1-S2). **`calcium` is absent** — zero `drug_ingredients` row. Since every knowledge row has `drug_ingredient_id NOT NULL, ondelete=RESTRICT` FK, no Calcium knowledge content can be imported until a `drug_ingredients` row exists. **PTH's explicit ruling: no generic "Calcium" ingredient row** — calcium is administered as distinct salts (carbonate, citrate, acetate) with different absorption/dosing/interaction profiles, and this codebase's own existing convention (K1-S2's ingredient dedup is keyed on the verbatim salt-form INN string, e.g. `insulin aspart` vs `insulin glargine` as separate ingredients, never collapsed to a generic "insulin") already supports salt-specific identity — a generic "Calcium" row would be the first ingredient in the catalog to break that convention. This remains a **Phase B blocker, not a Phase A blocker** (Phase A's tests use synthetic ingredients only). Resolution is a small, separate, real PR (`K1-S2b — add Calcium to relational drug catalog`) with an explicit salt-identity proposal — see Finding-adjacent audit output in `MEDICATION_PHASE_A_BLOCKING_FINDINGS.md`. Not started as part of this plan.

**Gap — `clinical_specialties` is structurally created but has zero seeded rows.** PTH's ruling: **not fully harmless** — A1a's own "invalid specialty code" validation rule needs *something* to validate against; with an empty table, either every specialty reference gets rejected (as originally proposed) or the check has to be silently bypassed — both bad. Resolution: seed a minimal controlled vocabulary (7 specialty codes PTH specified) before A1b's integration tests run — data-only, idempotent, no migration required (the table and its unique constraint already exist). A1a's own validator still only checks *structural* shape (is this a plausible code, from a hardcoded Python-level allowlist) without needing the DB seed; the DB-existence check lives in `provenance.py` and its integration test is the part that needs real seed data. See Finding 2 in `MEDICATION_PHASE_A_BLOCKING_FINDINGS.md`.

### No API / frontend / AI consumer will be touched

Re-confirmed from this session's K1-S4 exit review (EC-08/09/10, all PASS): no router imports `knowledge_repository` or any of the 12 K1 model classes; `frontend/` diff for K1 is empty; Meto's `ContextBuilder` has zero references to the new schema.

**New finding this session, important for Phase A specifically:** the codebase already has an *unrelated* `app/knowledge/` package (`backend/app/knowledge/registry.py`, `schema.py`) — a `KnowledgeRegistry`/`KnowledgeCard` system loading YAML "medical knowledge cards" (biomarker/disease/lifestyle explainers) with its **own, different** status enum (`draft/internal_review/medical_review/approved/deprecated` — not ADR-13's `draft/clinical_review/approved/deprecated/retired`). This is consumed by `backend/app/services/medical_narrative.py`, which is wired into live patient-facing routes (`backend/app/api/v1/routes/narrative.py`, `patient_insight.py`). **This is a live, already-approved, AI-narrative-adjacent system — completely separate from K1.** Phase A's new module must not live under `app/knowledge/`, must not be named anything that greps ambiguously against `KnowledgeRegistry`/`KnowledgeCard`, and this plan explicitly does not touch that package. See §9 (Risks).

---

## 2. Module boundaries

Proposed package: **`backend/app/services/medication_knowledge_import/`** (new subpackage, not a single file — the K1-S3 precedent of one flat service file doesn't scale to 6+ concerns without exceeding the project's file-size guideline). Named `medication_knowledge_import`, deliberately distinct from the pre-existing `app/knowledge/` package to avoid the collision described above.

| File | Responsibility | Notes |
|---|---|---|
| `loader.py` | Read a `.yaml`/`.json` file from disk → raw `dict`. No validation, no DB. | Uses `yaml.safe_load` (PyYAML already a transitive dependency via `app/knowledge/registry.py`, confirmed importable) or `json.load`. Rejects anything but `.yaml`/`.yml`/`.json` by extension. |
| `schema.py` | Pydantic v2 models (project already depends on `pydantic>=2.7`) defining the exact input contract from §3. One model per knowledge type + a shared metadata/provenance model. | Structural validation only (types, required/optional) — Pydantic's own `ValidationError` on load. |
| `validators.py` | Business-rule validation beyond structural typing: controlled-vocabulary checks (locale, audience, status), forbidden-AI-source check, malformed-reference check. Pure functions, no DB writes (may read reference tables e.g. `clinical_specialties`). | Returns a list of validation errors rather than raising on the first one, so a single import attempt reports everything wrong at once (matches K1-S2 migration's own "validate everything before writing anything" convention). |
| `provenance.py` | Checks specifically for source/version/reviewed_at/disclaimer-flag presence, and resolves `medication identity → drug_ingredient_id` (fail closed if the ingredient doesn't exist — this is exactly where the Calcium gap surfaces at Phase-B time). | Separated from `validators.py` because provenance/identity resolution needs a DB session; the rest of validation doesn't. |
| `versioning.py` | Business-key computation per knowledge type (mirrors ADR-13's per-table key), content hashing, and the idempotency/version-conflict decision (§4). | Pure logic + read-only DB queries. No writes. |
| `orchestrator.py` | Ties it together: `loader → schema → validators → provenance → versioning → knowledge_repository.build_draft/add_draft [→ references.find_or_create_reference/link_reference_to_row]`, one transaction per batch, `orchestrator.import_batch` as the sole commit/rollback owner (superseded from `create_draft` — see `MEDICATION_PHASE_A1B_ORCHESTRATOR_IMPLEMENTATION_PLAN.md` §2a; `create_draft` commits internally and cannot participate in a shared batch transaction). **This is the only file that calls `knowledge_repository` write functions.** | Never calls `validate_transition(..., new_status="approved")`. Never calls anything that could reach `approved`. |
| `preview.py` | Draft preview (render one knowledge item to Markdown), diff preview (render a content diff between two versions of the same business key). Sanitizes Markdown (no raw HTML passthrough). | Pure rendering — no DB writes, adds no clinical claims (renders exactly what's in the row, no synthesis). |
| `publish_prep.py` | "Publish pipeline" reinterpreted per the note below — a dry-run validation summary over a batch of already-imported `clinical_review` rows, answering "is this batch ready for a future human approval step," producing a report. **Does not transition anything.** | This satisfies the spec's "publish pipeline" deliverable without building an approve path. |

**Explicit reinterpretation (per PTH's own note in the request):** "Publish pipeline" in the original spec is implemented as **publish preparation**, not publish execution. It stages/validates a batch and produces a report; it never calls `create_draft`/`submit_for_review` with a target beyond `clinical_review`, and never touches `approved`. The actual approve workflow (Clinical Advisor role, K1.5+) is out of scope for both Phase A and Phase B.

Tests live flat under `backend/tests/`, matching existing convention (`test_knowledge_repository.py` precedent): `test_medication_knowledge_import_loader.py`, `test_medication_knowledge_import_validators.py`, `test_medication_knowledge_import_versioning.py`, `test_medication_knowledge_import_orchestrator.py`, `test_medication_knowledge_import_preview.py`.

---

## 3. Input contract — Knowledge Authoring Template

One file = one knowledge item (one row in one of the 5 tables). A drug's full page is many files (one per section × locale/audience).

```yaml
metadata:
  knowledge_type: patient_education        # required | enum: usage | patient_education | side_effect | monitoring | contraindication
  medication_identity:                     # required
    name_inn: levothyroxine                # required | must resolve to an existing drug_ingredients.name_inn (fail closed if not found)
  locale: vi                               # required | enum, currently only "vi" supported (matches DrugUsage.locale default)
  audience: patient                        # required | enum: patient | caregiver (matches existing `audience` column convention)

content:                                   # required | shape depends on knowledge_type (see per-type fields below)
  # patient_education: { theme: str, body: str }
  # usage:              { body: str }
  # side_effect:        { frequency: enum(common|uncommon|rare|unknown), action_level: enum(self_monitor|contact_clinician|urgent_medical_help), concept_code: str, label: str, description: str }
  # monitoring:         { parameter: str, patient_context: str, guidance: str }
  # contraindication:   { condition_type: str, condition_key: str, condition_detail: str }

references:                                # required, min 1 item — see "Drug References" resolution below. Fields per PTH's minimum spec.
  - publisher: "Vietnam Ministry of Health"
    title: "Vietnam National Drug Formulary 2024, Levothyroxine monograph"
    source_type: "formulary"               # required | controlled vocab: formulary | clinical_guideline | product_label | peer_reviewed | other
    url: null                              # optional — document identifier required if url is null (see below)
    document_identifier: null              # optional if url present, required otherwise (e.g. ISBN, DOI, internal doc ref)
    publication_date: "2024-01-01"
    source_version: "2024"                 # the *reference document's* version, distinct from review_metadata.version (the knowledge item's own version)
    accessed_at: "2026-07-01"              # when the author actually consulted this source

review_metadata:                           # required
  source: "MOH Vietnam Formulary 2024"     # required, <=255 chars — becomes DrugXxx.source (DB column)
  version: "1.0.0"                         # required — becomes DrugXxx.version (DB column); see §4 for version-conflict rules
  evidence_level: moderate                 # required | enum: strong | moderate | emerging | expert_opinion (matches existing AI knowledge card's EvidenceLevel vocabulary for consistency, even though these are separate systems)
  reviewed_at: "2026-07-01"                # required — becomes DrugXxx.last_reviewed_at
  authored_by: "content-team@metocare.me"  # required — becomes DrugXxx.authored_by / status_changed_by at draft creation
  ai_generated: false                      # required, MUST be false — see validation rules
  specialty_codes: []                      # optional, defaults to empty — see Finding 2 (clinical_specialties seed); validated structurally against the 7-code allowlist regardless of DB seed state

disclaimer:
  acknowledged: true                       # required, MUST be true — see resolution below
```

### Resolution: "Drug References" (spec type #6) and `references:` field — REVISED per PTH decision

**Original proposal (source-file-only persistence) was rejected by PTH.** Structured references must be queryable from the repository, not just present in a versioned YAML file — needed for a future patient-facing "source" API, reviewer traceability, monthly-update source/version comparison, and because one knowledge item can cite multiple sources and one source can back multiple items (a many-to-many the single `source: VARCHAR(255)` column cannot express).

- `references:` is a **required structured list on every knowledge file** (schema in the template above — `publisher`, `title`, `source_type`, `url` or `document_identifier`, `publication_date`, `source_version`, `accessed_at`). A1a validates this structure regardless of the persistence question below.
- **Persistence requires a schema addition** — a `drug_references` table (or equivalent structured relation) plus a join between it and each of the 5 knowledge tables (a knowledge row can cite N references; a reference can be cited by N rows — the same polymorphic-association pattern ADR-13 already uses for `knowledge_review_specialties`, since references, like specialty reviews, span all 5 knowledge tables without a single physical FK target). **This is a real schema gap, tracked as Finding 1** (`MEDICATION_PHASE_A_BLOCKING_FINDINGS.md`) — it needs its own small migration PR before A1b can persist knowledge content, since A1b's persistence must write real reference rows, not skip them.
- The existing `source: VARCHAR(255)` column is retained unchanged (still useful as a short canonical citation for at-a-glance display / the approved-invariants CHECK) — it is now a *summary* field, not the only place provenance lives.
- "Drug References" as a standalone spec type #6 is still not a separate persisted *knowledge type* parallel to the other 5 (no `drug_references` *page*, no `drug_ingredient_id`-scoped row of its own) — it is the bibliography attached to every item of the other 5 types. This part of the original interpretation stands; only the "where does it persist" half was rejected.

### Resolution: `disclaimer:`

No DB column exists for this. The exact Vietnamese disclaimer text from Phase B's spec is a **fixed constant** (legally significant, must not vary per drug or be re-typed by content authors — retyping risks a typo in a compliance-critical string). Recommend: the disclaimer constant lives once in `preview.py` (or a small `disclaimer.py` constant module) and is appended at render time by the preview/markdown renderer, never stored per-row. The `disclaimer.acknowledged: true` field in the input file is a validation gate only — the importer rejects any file where it's missing or `false` — not content that gets written anywhere.

### Required / optional / controlled-vocabulary / AI-forbidden fields

| Field | Required? | Controlled vocabulary | AI may not generate |
|---|---|---|---|
| `metadata.knowledge_type` | required | yes — 5 values, matches the 5 tables | — |
| `metadata.medication_identity.name_inn` | required | must exist in `drug_ingredients` | — |
| `metadata.locale` | required | yes — currently `vi` only | — |
| `metadata.audience` | required | yes — `patient`, `caregiver` | — |
| `content.*` | required, shape varies by type | `frequency`, `action_level`, `condition_type` are controlled vocab; `concept_code`/`condition_key` are free-form normalized identifiers (author-chosen, validated for format not membership) | **the entire `content` block — clinical facts must be authored by a human, never AI-generated** |
| `references` | required, min 1 | — | — |
| `review_metadata.source/version/reviewed_at/authored_by` | all required | `evidence_level` is controlled vocab (4 values) | — |
| `review_metadata.ai_generated` | required, must be `false` | boolean | this field is the explicit machine-checkable gate for the "no AI-generated clinical facts" non-negotiable |
| `disclaimer.acknowledged` | required, must be `true` | boolean | — |

---

## 4. Transaction and idempotency

**Business key per knowledge type** (from ADR-13, re-derived per table, resolved via `medication_identity.name_inn → drug_ingredient_id`):

| Type | Business key |
|---|---|
| `usage` | `(drug_ingredient_id, locale, audience)` |
| `patient_education` | `(drug_ingredient_id, theme, locale, audience)` |
| `side_effect` | `(drug_ingredient_id, concept_code)` |
| `monitoring` | `(drug_ingredient_id, parameter, patient_context)` |
| `contraindication` | `(drug_ingredient_id, condition_type, condition_key)` |

**Re-importing the same file twice:** `create_draft` always INSERTs (append-only, per K1-S3's own design — there is no UPDATE path). A naive re-import would therefore create a duplicate draft with identical content. `versioning.py` prevents this: before writing, look up the most recent (non-`retired`) row for the same business key.

- **Same business key, same `version` string, identical content hash → no-op.** Log "already imported, skipped," write nothing. This is the idempotency guarantee.
- **Same business key, same `version` string, *different* content hash → reject.** A version string is a promise that its content is fixed; two different contents claiming the same version is a version-integrity violation, not a new version. Surfaces as a validation error, not a silent overwrite.
- **Same business key, new `version` string, different content → create a new draft row** (new version, exactly ADR-13's append-only model — the old row is untouched, never mutated).
- **Same business key, new `version` string, but content hash equal to a version that already exists (case-insensitive whitespace-normalized comparison) → warn, but proceed** (a legitimate case: re-approving the same wording under a new formulary edition/date). Not an error.

**Content hash** = SHA-256 over the type-specific content fields only (not provenance/metadata) — same technique used in this session's own EC-04 checksum verification of the K1-S2 catalog migration.

**Partial import failure → whole-batch rollback.** One importer invocation processes a batch (e.g., all files for one drug, or a directory). `orchestrator.py` runs the full loader→schema→validators→provenance→versioning pipeline for **every file in the batch first (pure, no DB writes)**, collects all errors, and only if the entire batch is error-free does it write every item, committing once at the end. **Superseded (this paragraph is now historical context, not the locked design):** `MEDICATION_PHASE_A1B_ORCHESTRATOR_IMPLEMENTATION_PLAN.md` §2a/§2b lock the exact mechanics — Phase 1 and Phase 2 share one already-open `Session` transaction (not "opens one DB transaction" after Phase 1 ends), writes go through `build_draft`/`add_draft` (not committing `create_draft`) with `import_batch` as the sole commit/rollback owner, and any Phase 2 failure returns `BatchResult(success=False, ...)` rather than propagating an exception. Zero partial rows survive a failed batch either way — that outcome is unchanged; only the mechanics of how it's guaranteed were corrected. This two-phase "validate everything, then write everything" design is the same pattern K1-S2's catalog migration already used successfully.

**Concurrency:** two importer invocations targeting the *same business key* at the same time have a TOCTOU race between the idempotency lookup and the insert (same class of race K1-S3's Codex review caught in `submit_for_review`, fixed there with an atomic `UPDATE...WHERE`). Recommend **not** building distributed locking for this: Phase A/B's importer is an authoring tool run by a human or a CI job, not a concurrent multi-user API — document "single-writer per business key at a time" as an accepted operational constraint. Worst-case failure mode if violated is two draft rows with identical content (harmless, cleanable), never data corruption, since nothing here ever reaches `approved`. The test matrix (§7) includes a concurrency test to *prove* that bound, not to eliminate the race.

---

## 5. Validation rules

All of the spec's required rules, plus two resolved above:

| Rule | Where enforced | Notes |
|---|---|---|
| Missing `source` | `provenance.py` | Stricter than the DB — the DB's `ck_*_approved_invariants` CHECK only requires this at `approved`; Phase A requires it at draft-creation time. Deliberately earlier/stronger gate. |
| Missing `version` | `provenance.py` | Same as above. |
| Missing `reviewed_at` | `provenance.py` | Same as above. |
| Missing `disclaimer` (acknowledgment) | `validators.py` | No DB column exists — see §3 resolution; validated against the file's `disclaimer.acknowledged` flag. |
| Duplicate `concept_code` (within `side_effect`) / `condition_key` (within `contraindication`) | `versioning.py`, as part of business-key resolution | A duplicate at the *same* business key with different content is the "duplicate concept_code" case from §4. |
| Duplicate approved version | N/A in Phase A/B (nothing reaches `approved`) | Kept as a validator rule for forward-compatibility (checked against `status='approved'` rows, which will always be zero today) — inert but present, since building it now is trivial and it's needed the moment K1.5 activates. |
| Invalid `specialty` code | Two-tier, per PTH's ruling: `validators.py` (structural — checked against a hardcoded Python allowlist of the 7 PTH-specified codes, no DB needed) + `provenance.py` (DB-existence — checked against real `clinical_specialties` rows) | The DB-existence tier is real but its integration test needs the table actually seeded (Finding 2, `MEDICATION_PHASE_A_BLOCKING_FINDINGS.md`) — not built as a silent bypass. Phase B's 5-drug content is not required to declare specialties (specialty-completeness only gates the out-of-scope `approved` transition). |
| Malformed reference entry | `validators.py` (schema.py Pydantic model) | Every entry in `references:` must have `publisher`, `title`, `source_type` (controlled vocab), `publication_date`, `source_version`, `accessed_at`, and either `url` or `document_identifier`. |
| Invalid lifecycle status | N/A — the importer never accepts a `status` field from the input file at all. `create_draft` always forces `'draft'`; `submit_for_review` is the only other transition and is orchestrator-controlled, not file-controlled. This removes an entire class of "invalid status" input by construction. |
| Duplicate active version | Same mechanism as "duplicate concept_code" (§4) — a business-key + version collision with differing content. |
| Forbidden AI-generated source | `validators.py` | Hard-reject if `review_metadata.ai_generated != false`. This is the one machine-checkable proxy for "no AI-generated clinical facts" — Phase A cannot verify a human actually wrote the prose, but it can refuse to import anything that self-declares as AI-generated. |
| Malformed references | `validators.py` | Pydantic structural validation (§3) — missing `citation`/`organization`/`publication_date`, empty list, or non-list `references` value. |
| Unsupported locale | `validators.py` | Only `vi` accepted today (matches every existing `locale` column's default and K1's Vietnamese-first product scope) — anything else is a hard reject, not silently coerced. |

---

## 6. Preview design

- **Draft preview**: renders one knowledge item (already-loaded/validated, in-memory or already-persisted-as-draft) to Markdown using the type-specific template, plus the disclaimer constant appended at the end (matching Phase B's exact required text). Renders *only* what's in the row/file — no synthesis, no filling gaps, no AI.
- **Diff preview**: given two versions of the same business key (old row, new row), renders a content-only diff (unified-diff-style over the content fields) plus a metadata diff (version, source, reviewed_at changes). Provenance/audit fields (`authored_by`, `status_changed_at`, id) are shown as context, not diffed as "changes" (they always differ trivially between any two rows).
- **No clinical claims added by the renderer**: enforced by construction — the renderer is a pure function over already-validated content, has no LLM/AI call anywhere in its dependency graph, and every string in its output traces to either the input row or the fixed disclaimer constant.
- **Markdown sanitization**: strip/escape raw HTML tags from any free-text field before rendering (defense against a compromised or careless authoring file injecting markup) — a simple allowlist sanitizer (headers, bold, italic, lists, links) is sufficient; no need for a full HTML sanitizer library given the trusted-author threat model.
- **No patient-facing UI**: preview output is Markdown text (rendered to a file, terminal, or a future internal review tool) — explicitly not a route, not a frontend component, not anything reachable by the patient app. This is the same boundary EC-08/EC-09 already established for K1's repository layer; Phase A's preview must not become a de facto Knowledge API by being exposed through any route.

---

## 7. Test matrix

| Test | File | Notes |
|---|---|---|
| Valid import | `test_medication_knowledge_import_orchestrator.py` | End-to-end: valid YAML file → draft row created with correct fields. |
| Invalid import (each validation rule from §5) | `test_medication_knowledge_import_validators.py` | One test per rule — missing source, missing disclaimer ack, `ai_generated=true`, unsupported locale, malformed references, etc. |
| Duplicate import (same file twice) | `test_medication_knowledge_import_versioning.py` | Asserts idempotent no-op — row count unchanged, no duplicate. |
| Version bump | `test_medication_knowledge_import_versioning.py` | Same business key, new version, new content → new draft row; old row untouched (content + id unchanged). |
| Version conflict (same version, different content) | `test_medication_knowledge_import_versioning.py` | Asserts rejection, zero rows written. |
| Rollback (partial batch failure) | `test_medication_knowledge_import_orchestrator.py` | Batch of N files where file K is invalid → asserts zero rows written for the *entire* batch, not just file K. |
| Concurrency | `test_medication_knowledge_import_orchestrator.py` | Two importer calls against the same business key at once (mirrors K1-S3's own two-session concurrency test pattern) — asserts the worst case is a harmless duplicate draft, not a crash or corrupted row. |
| Malformed YAML/JSON | `test_medication_knowledge_import_loader.py` | Syntactically broken file → clean validation error, not an unhandled parser exception. |
| Prohibited status | `test_medication_knowledge_import_validators.py` | Input file attempting to set `status` directly is ignored/rejected — importer only ever produces `draft`/`clinical_review`. |
| Prohibited AI source | `test_medication_knowledge_import_validators.py` | `ai_generated: true` → hard reject (also listed under "invalid import" — called out separately since it's the one direct check for the non-negotiable "no AI-generated clinical facts" rule). |
| Zero approved rows after tests | `test_medication_knowledge_import_orchestrator.py` (assertion added to every test, matching K1-S3's `test_zero_approved_rows_exist_anywhere` convention) | Every test in this suite asserts `status='approved'` count is 0 across all 5 tables at teardown, regardless of what else it tests. |
| No API/frontend/AI changes | Not a runtime test — a **CI/PR-diff check**, same as EC-08/09/10 in this session's K1-S4 review: `git diff` for the PR must touch zero files under `frontend/`, zero files under `backend/app/api/`, zero files under `backend/app/ai/`, and zero files under the pre-existing `backend/app/knowledge/` package. |

Test DB: unit-style tests (loader, validators, versioning-logic) run against the existing SQLite `db` fixture (`tests/conftest.py`), matching K1-S3's own convention. Anything asserting real Postgres-specific behavior (partial unique index interaction, concurrent transaction behavior) runs as a `pytest.mark.integration` test against `POSTGRES_TEST_URL`, matching K1-S1/S2's convention — this session's own scratch-Postgres rehearsal setup (homebrew Postgres 17, CI-matching `mcp`/`mcp_test_ci`/`mcp_test` credentials) is directly reusable for local iteration on these tests.

---

## 8. PR split

Recommend **3 sequential PRs**, mirroring K1's own S1/S2/S3 rationale (each has a genuinely different risk profile and reviewer focus — not splitting for its own sake):

- **PR-A1a — Loader + schema + validation** (`loader.py`, `schema.py`, `validators.py`, `provenance.py`). Pure functions, no DB writes except the read-only `drug_ingredients`/`clinical_specialties` lookups in `provenance.py`. Lowest risk, reviewable in isolation, unblocks writing real Phase B content files for review even before A1b lands.
- **PR-A1b — Versioning + orchestrator** (`versioning.py`, `orchestrator.py`, plus structured reference persistence). The only PR that touches `knowledge_repository`'s write path (`create_draft`/`submit_for_review`) and owns transaction/rollback/idempotency semantics — the highest-risk, highest-review-attention piece, same category as K1-S2's migration PR. Depends on A1a. Finding 1 (reference-persistence schema, #128) and Finding 2 (specialty seed, #129) are both **✅ resolved** — A1b planning is now GO; see `MEDICATION_PHASE_A1B_ORCHESTRATOR_IMPLEMENTATION_PLAN.md` for the locked design. Implementation itself still awaits plan approval (not GO yet).
- **PR-A1c — Preview + diff renderer** (`preview.py`, `publish_prep.py`, the disclaimer constant). Independent of A1b's DB-writing logic (only needs A1a's validated schema shape) — could in principle land in parallel with A1b, but sequencing after keeps review load manageable and lets A1c's tests use real drafted rows from A1b instead of only in-memory fixtures.

A single combined PR is viable if PTH prefers fewer review cycles — the three pieces are not so large individually that splitting is mandatory, only recommended for the same reason K1 split its schema/data/service concerns.

---

## 9. Risks and stop gates

| Risk | Category | Mitigation / stop gate |
|---|---|---|
| Confusion/collision with the pre-existing `app/knowledge/` package (KnowledgeRegistry, live AI-narrative-adjacent, different status enum) | **Technical + governance** | New package named `app/services/medication_knowledge_import/`, never `app/knowledge/*`. PR review must explicitly confirm zero files under `backend/app/knowledge/` or `backend/app/services/medical_narrative.py` are touched. |
| "Drug References" and "disclaimer" have no DB column — risk of someone "just adding a column" mid-PR to make the spec literally match | **Governance** | This plan's resolution (§3) is the agreed interpretation; any deviation requiring a new column/table is a schema change and needs its own ADR + PTH sign-off, out of scope for Phase A. |
| Calcium has no `drug_ingredients` row — Phase B cannot import Calcium content without a prerequisite data step | **Technical, Phase-B-blocking** | Flagged now (§1); resolution (a small data-only insert, not a migration) is explicitly deferred to whoever starts Phase B, not built in Phase A. |
| Idempotency/versioning race on concurrent same-business-key imports | **Technical, low severity** | Documented as an accepted single-writer operational constraint (§4); test proves the failure mode is bounded (harmless duplicate), not corruption. |
| `clinical_specialties` unseeded — specialty validation is currently inert | **Governance** | Rule implemented per spec for forward-compatibility; Phase B content should not declare specialties (not required while nothing reaches `approved`). |
| A future contributor extends `orchestrator.py` to call `validate_transition(..., "approved")` "just to see if it works" | **Clinical misinformation risk** | This is the actual mechanism that would let unreviewed content reach patients. Stop gate: PR review (Codex + compliance + architecture, all mandatory) must explicitly grep for any `"approved"` string literal or `validate_transition` call with a non-`clinical_review` target anywhere in the diff, same check this session's own EC-07 verification used. |
| Phase B content authored without real, checkable references (silently AI-assisted despite the `ai_generated` flag) | **Clinical misinformation risk** | Out of Phase A's ability to fully prevent (it's a process/authorship question, not a code question) — the `ai_generated` flag and mandatory `references` list are the only automatable proxies; ultimate responsibility sits with whoever authors Phase B content, per PTH's own "do not invent medical facts" instruction. |
| Scope creep: Phase A's preview renderer becomes a stepping-stone someone wires into a route "since it's basically an API already" | **Governance** | Stop gate: no file under `medication_knowledge_import/` may be imported by anything under `backend/app/api/`. Same CI/PR-diff check as the "no API changes" test in §7. |

**Stop gates before merge (per PTH's own instruction — non-negotiable, not new process):** Codex review, compliance review, architecture-compliance review, all green. No merge otherwise.

---

## 10. Output

### File/module map
```
backend/app/services/medication_knowledge_import/
  __init__.py
  loader.py
  schema.py
  validators.py
  provenance.py
  versioning.py
  orchestrator.py
  preview.py
  publish_prep.py

backend/tests/
  test_medication_knowledge_import_loader.py
  test_medication_knowledge_import_validators.py
  test_medication_knowledge_import_versioning.py
  test_medication_knowledge_import_orchestrator.py
  test_medication_knowledge_import_preview.py
```

### Implementation order
1. PR-A1a: `schema.py` → `loader.py` → `validators.py` → `provenance.py` (+ their tests)
2. PR-A1b: `versioning.py` → `orchestrator.py` (+ their tests, incl. concurrency + rollback)
3. PR-A1c: `preview.py` → `publish_prep.py` (+ their tests)

### Test plan
Per §7 — unit tests on SQLite (`db` fixture) for pure logic, `pytest.mark.integration` on real Postgres for anything DB-behavior-sensitive, every test asserts zero approved rows at teardown, plus a CI/PR-diff check gating zero touches to `frontend/`, `backend/app/api/`, `backend/app/ai/`, `backend/app/knowledge/`.

### Acceptance criteria
- All 3 PRs merged, each with Codex + compliance + architecture review green.
- `SELECT COUNT(*) FROM drug_usage WHERE status='approved'` (and the same for the other 4 tables) is 0 on staging after Phase A merges — same live-verification method this session used for K1-S4.
- No new route, no frontend diff, no AI-context-builder diff, no touch to `app/knowledge/` or `medical_narrative.py` — verifiable by the same grep/diff method used for EC-08/09/10.
- Importer successfully round-trips a synthetic test fixture end-to-end (load → validate → draft → submit_for_review → preview) with zero manual SQL involved anywhere in the path.

### Explicit out-of-scope (for this plan and for Phase A itself)
- Any schema migration (new column/table for references or disclaimer).
- Any API route, any frontend change, any AI/context-builder change.
- Any transition to `approved`, any Clinical Advisor role/permission system.
- Seeding `clinical_specialties` or creating the missing Calcium `drug_ingredients` row (both deferred to whoever starts Phase B).
- Authoring any real clinical content (Phase A's tests use only synthetic fixtures).
- New ADRs — this plan resolves the "Drug References"/"disclaimer" schema gaps by keeping them out of the DB entirely (versioned source file + rendering-time constant, respectively), not by proposing new schema.

### Verdict (updated post-PTH-review, 2026-07-16)

| Item | Status |
|---|---|
| A1a — loader/schema/validation/provenance | ✅ **GO** — no persistence, no migration, proceed now |
| A1b — orchestrator + persistence | 🟡 **Blocked** until structured reference persistence exists (Finding 1) |
| A1c — preview/diff | ✅ Can proceed after A1b, or partially in parallel (schema-shape-only work) |
| Calcium content (Phase B) | 🔴 **Blocked** until salt-specific catalog identity is resolved (separate small PR, see findings doc) |
| Specialty validation | 🟡 Structural check buildable now in A1a; DB-existence check's integration test needs real seed (Finding 2) before A1b |
| Disclaimer constant | ✅ Approved, unchanged |

**No part of A1a requires a migration, an API, a frontend change, an AI wiring change, or new clinical content.** A1b will require one small migration (`drug_references` + join) before it can proceed — tracked as Finding 1, not started as part of this plan or A1a.
