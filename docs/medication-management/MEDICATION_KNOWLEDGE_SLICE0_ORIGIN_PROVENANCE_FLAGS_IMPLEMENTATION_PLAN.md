# Medication Knowledge — Slice 0: Origin, Provenance & Capability-Flag Foundation

**Status:** PLANNING ONLY — no route, schema, service, or migration code is written by this
document. This is the "short Slice 0 implementation plan" that
`MEDICATION_K2_IMPLEMENTATION_READINESS_REVIEW.md` (2026-07-23, §7 recommendation 2) called for
before any ingestion/AI-normalization/AI-synthesis code may be authorized.

**Date:** 2026-07-24
**Author context:** written immediately after K2 Slice 1 (PR #135, `e8ae3d8`) merged to `main`,
read-only and dormant behind `MEDICATION_KNOWLEDGE_RETRIEVAL=False`.
**Method:** direct inspection of the live backend at this commit — every claim below cites an
exact file/line, not a re-statement of an earlier planning doc's assertion. Where this plan
extends, corrects, or narrows a suggestion from the Readiness Review, that is called out
explicitly (see §0.2).

---

## 0. Bottom line

**Verdict: CONDITIONAL — implementation-ready pending PTH sign-off on 4 named decisions (§0.3).**
**Update 2026-07-27:** all 4 original decisions plus a 5th (added retroactively — see §0.3 item 5)
have since been made by PTH at the Slice 0 final implementation checkpoint. This section is left
as the historical planning record, not rewritten in place.

Slice 0 is schema-and-flags-only: one new column family, one new table, one new status value,
seven capability flags, and two small service-layer guards. No product behavior changes, no AI
code, no ingestion code. It does not touch K1.5's or K1.6's existing call paths — every existing
test in `test_medication_knowledge_routes.py`, `test_knowledge_retrieval.py`, and the K1.5
compliance-review suite must continue passing unmodified against this plan.

### 0.1 What Slice 0 adds, in one sentence each

1. An `origin` column on all 5 ADR-13 knowledge tables — the fact a row has always structurally
   lacked (§B2.2).
2. A `rejected` terminal status, closing a real gap: today a `clinical_review` row that a
   reviewer declines has no modeled destination at all (§B2.3).
3. An append-only `knowledge_ai_generations` table recording every AI generation attempt, not
   just the latest (§B2.4).
4. A service-layer guard so `approve_row` refuses to promote an `ai_synthesized` row unless a
   matching successful generation record exists (§B2.3, §B4).
5. Seven independently-toggleable capability flags, extending (not replacing)
   `app/core/feature_flags.py` (§B2.1).
6. A grep-guard test family proving the six ADR-15 §K.4 prohibited actions are structurally
   unreachable, not just policy (§B2.7).
7. An append-only `knowledge_lifecycle_transitions` table recording every status transition —
   actor, timestamp, reason code, PHI-free rationale — added and PTH-authorized 2026-07-27, after
   this document's original drafting (§B3 Migration 3, §0.3 item 5).

### 0.2 Where this plan departs from the Readiness Review, and why

| Readiness Review said (§2, §3) | This plan does instead | Why |
|---|---|---|
| `origin` default `source_extracted` for backward compatibility | Default **`human_authored`** | Verified directly: every row ever written through this codebase's only real write path (`create_draft`, fed exclusively by the A1b importer, which hard-types `ai_generated: Literal[False]` at `medication_knowledge_import/schema.py:171`) is human-authored. `source_extracted` would be **factually false** for 100% of legacy rows — no ingestion pipeline (Slice 2) has ever run. Backfilling to `source_extracted` would itself violate this plan's own "do not silently classify legacy content as AI-generated [or any other origin it wasn't]" instruction. |
| One `MEDICATION_KNOWLEDGE_AI_SYNTHESIS` flag covering both normalization and synthesis | **Two separate flags**: `MEDICATION_KNOWLEDGE_AI_NORMALIZATION` and `MEDICATION_KNOWLEDGE_AI_SYNTHESIS` | The Review's own §1 argues normalization and synthesis need *independent* kill switches ("a bad normalization pass must be killable without deleting raw ingested source; a bad synthesis prompt must be killable without touching either... Collapsing them into one slice would make the flags perform the same job at three different layers, defeating the point of independent kill switches") — then its own §3 flag table collapses them into one flag anyway. This plan resolves that internal inconsistency in the Review's own favor. |
| `knowledge_ai_generation_metadata`, one row per knowledge row (1:1 side table) | `knowledge_ai_generations`, **append-only, many rows per knowledge row** | The Review's brief sketch stores only the latest generation. This plan's mandate is explicit: "Do not store only 'latest model' metadata... if outputs can be regenerated" — retries, regenerations, and prompt-version changes must each leave their own immutable record (§B2.4). |
| Flag names `MEDICATION_KNOWLEDGE_INGESTION` / `..._AI_SYNTHESIS` / `..._DOCTOR_AI_CONTENT` / etc. | Bare `MEDICATION_` prefix (`MEDICATION_EXTERNAL_SOURCE_INGESTION`, `MEDICATION_AI_SYNTHESIS`, `MEDICATION_AI_DOCTOR_CONTENT`, etc.) — **corrected 2026-07-27**: this row originally argued for a `MEDICATION_KNOWLEDGE_` prefix, but that is not what was implemented, and at the Slice 0 final checkpoint PTH's own preferred-names list confirmed the bare `MEDICATION_` prefix (matching the one pre-existing flag, `MEDICATION_KNOWLEDGE_RETRIEVAL`, kept as-is since it predates this plan) as correct going forward. No code change was needed — implementation already matched PTH's decision; this document's stated rationale was what was wrong. | Naming-convention alignment only — verified against `app/core/feature_flags.py`, no functional difference either way. |

### 0.3 Decisions this plan needs PTH to make explicitly before coding starts

1. **`rejected` status** (§B2.3): adding a 6th lifecycle value is a real ADR-13 amendment, not
   just a Slice 0 implementation detail. Needs the same sign-off tier as the original 5-value
   enum did.
2. **`MEDICATION_KNOWLEDGE_EXPERIMENTAL_VOCABULARY` default**: this plan recommends `False`
   (fail-closed, consistent with every other new flag in this codebase's history), but the
   Readiness Review left this explicitly open ("PTH's call") and this plan does not have
   standing to close it unilaterally.
3. **Reserved system-actor identity strings** for non-human `authored_by`/`created_by` values
   (§B2.4, §B7): this plan proposes literal strings (`"system:ai-synthesis"`,
   `"system:rule-engine"`) with no dedicated `Actor`/`ServiceAccount` table backing them — PTH
   should confirm this is acceptable for Slice 0, or request a real service-identity table
   (larger scope, likely its own follow-up).
4. **Whether Slice 0's `approve_row` extension (§B4) ships now or is deferred to Slice 3**: this
   plan recommends shipping it in Slice 0 (the `knowledge_ai_generations` table it depends on is
   also a Slice 0 artifact, and the invariant is cheap to enforce even before any AI content
   exists), but it is defensible to defer it to Slice 3 if PTH prefers Slice 0 to touch zero
   existing service functions.
5. **`knowledge_lifecycle_transitions`** (added retroactively, not in this document's original
   §B3): a 4th migration, plus unconditional new call sites in the already-live K1.5 functions
   `submit_for_review`/`approve_row`/`retire_row`/`_deprecate_superseded`, was implemented without
   appearing in this section and without going through this same PTH sign-off gate. Flagged at the
   Slice 0 final-checkpoint review (2026-07-27). **PTH decision, same day: KEEP.** The later,
   binding PTH implementation instruction explicitly required lifecycle transition history with
   actor/reviewer identity, timestamp, reason code, and PHI-free rationale, plus preservation of
   all previous lifecycle history — superseding this document's original 3-migration scope for
   this one item. See ADR-13 Amendment 1 for the full authorizing record and design rationale;
   §B3 Migration 3 for the schema-level documentation.

---

## B1. Live-codebase findings

Every finding below was verified directly against the current backend at `main@e8ae3d8`, not
re-derived from a planning document. File:line citations point at the exact evidence.

### B1.1 The five knowledge models + shared mixin

`app/models/drug_knowledge_content.py`. `KnowledgeLifecycleMixin` (lines 59–95) is inherited by
`DrugUsage`, `DrugPatientEducation`, `DrugSideEffect`, `DrugMonitoring`, `DrugContraindication`.
Existing columns: `drug_ingredient_id`, `source`, `version`, `evidence_level` (widened to
VARCHAR(32) by K2 Slice 1's own migration), `reviewed_by`, `last_reviewed_at`, `status`
(`draft|clinical_review|approved|deprecated|retired`), `status_changed_at`, `status_changed_by`,
`authored_by`, `artifact_hash` (nullable, A1b orchestrator idempotency). **No `origin` column
exists.** `_status_check()` / `_approved_invariants_check()` (lines 43–56) build per-table CHECK
constraints from a single `STATUS_VALUES` tuple (line 40) — the exact mechanism Slice 0 extends
for the new `rejected` value.

### B1.2 `DrugReference` / `KnowledgeReferenceLink`

`app/models/drug_knowledge_references.py`. `DrugReference` (lines 34–85): `publisher`, `title`,
`source_type`, `url`, `document_identifier`, `publication_date`, `source_version`, `accessed_at`
— already covers every citation-level provenance field this plan's §B2.5 needs (source
identity, URL/stable id, publication date, retrieval date, source version). `KnowledgeReference
Link` (lines 88–113) is a polymorphic association keyed by `(knowledge_table, knowledge_row_id)`
— **this exact shape is the precedent Slice 0's new `knowledge_ai_generations` table copies.**
Reused as-is; zero changes needed.

### B1.3 K1.5 approval workflow — `app/services/knowledge_repository.py` (781 lines, read in full)

- Transition table (`_ALLOWED_TRANSITIONS`, lines 63–68): exactly
  `draft→clinical_review→approved→deprecated→retired`. **No `reject_row` exists** — a
  `clinical_review` row a reviewer declines has no modeled destination today. This is a real gap,
  not an oversight this plan can route around (§B2.3).
- `can_approve_knowledge`/`assert_can_approve_knowledge` (lines 243–266): the **entire**
  approval-capable role set is `frozenset({"internal_admin", "super_admin"})` — a closed,
  hardcoded set with a single named call site. As long as no AI/system actor is ever granted
  either role, `approve_row`/`retire_row` are already structurally unreachable by AI code with
  **zero new code** — this is the load-bearing fact behind "AI may never call or bypass
  `approve_row` on itself" (§B2.3, §B6).
- Self-approval block (`validate_transition`, lines 93–102): `actor_user_id == authored_by` at
  approval time raises `TransitionError`. Extends to AI content automatically, provided AI-
  authored rows use a reserved, non-human `authored_by` identity (§0.3 item 3) that never
  collides with a real approver's `actor_user_id`.
- **No audit/history row is written on any transition** — `submit_for_review`/`approve_row`/
  `retire_row`/`_deprecate_superseded` mutate only the row's own `status`/`status_changed_by`/
  `status_changed_at` via direct `UPDATE` (lines 204–208, 546–550, 639–643, 360–365). There is no
  separate lifecycle-history table today. This is exactly the gap `knowledge_ai_generations`
  fills for AI-authored rows (§B2.4) — it does **not** retrofit history for human-authored rows,
  which is out of Slice 0's scope.
- `_lock_canonical_row` (lines 368–412) and `_reject_if_pending_delete` (415–463): re-fetch the
  canonical row by id with `populate_existing=True, with_for_update=True` before every check —
  never trusts a caller-supplied object's fields. Slice 0's `approve_row` extension (§B4) must
  read `canonical.origin`, never a caller-supplied `row.origin`, for the same reason.

### B1.4 K1.6 retrieval — `app/services/knowledge_retrieval.py`

Confirmed `list_current_for_ingredient`/`get_current_batch`/`list_references_for_batch` all
filter `status="approved"` unconditionally; `list_references_for(_batch)` is identity-based, not
approved-gated (caller's responsibility). **None of these functions read `origin` today, and
none need to** — Slice 1's contracts intentionally never expose governance/origin metadata to
patients or doctors (K2 plan §6, reaffirmed in §B4 below). Adding `origin` to the schema does not
change K1.6's behavior at all — this is the "additive, not required by any running code path"
property the rollback gate (§B8) depends on.

### B1.5 `medication_knowledge_import` package (A1b orchestrator)

- **The exact `Literal[False]` restriction:** `app/services/medication_knowledge_import/
  schema.py:171–173`, on `ReviewMetadata.ai_generated`. Pydantic rejects any authoring file with
  `ai_generated: true` before it reaches the database. **There is no `ai_generated` (or any
  origin-like) column on the ORM models at all** — the field exists only in this input contract,
  and is folded into `artifact_hash`'s payload (`versioning.py:168`) but never persisted as its
  own column anywhere. This is the single fact that makes "no `origin` field exists on any
  knowledge table today" (Readiness Review §0) true, and confirms every row this importer has
  ever written is unambiguously human-authored.
- `orchestrator.py` imports only `build_draft`/`add_draft` (line 31) — **never** `create_draft`,
  **never** `approve_row`/`retire_row`. It writes `status='draft'` rows and stops; it has no
  lifecycle-advancement capability at all today.
- `versioning.py`'s `artifact_hash()` (lines 133–172) hashes the **full** authored artifact
  (content + references + provenance + `ai_generated` + disclaimer), explicitly chosen over a
  content-only hash after a prior incident where a content-only hash let an author silently
  change a reference/provenance field under an unchanged version. `knowledge_ai_generations`'
  `input_hash`/`output_hash` (§B2.4) follow this same full-payload-hash discipline, not an
  identity-fields-only shortcut.
- No `supersede`/`superseded_by` terminology exists anywhere in this package. Supersession is
  handled entirely by `knowledge_repository._deprecate_superseded` (§B1.3), which this package
  never calls (it only ever writes drafts).

### B1.6 `CarePlan.ai_generated` pattern, and a stricter sibling

`app/models/care.py:178–290`. `ai_generated: Mapped[bool]` (line 206), enforced by **dual
`@validates` hooks** (lines 234–264, `_validate_status`/`_validate_ai_generated`) that are
order-independent (either attribute can be set first) and a `create_from_ai()` factory (line
266) that is "the ONLY constructor AI service code paths should call." This is the direct
precedent Slice 0's `origin` field copies (§B2.2).

**Important asymmetry found:** `CarePlanCreate` (`app/schemas/care.py:185`) declares
`ai_generated: bool = False` — a **plain bool, not `Literal[False]`**. The API schema layer does
*not* block a client from POSTing `ai_generated=True` directly; only the ORM-level `@validates`
hooks (which fire on attribute assignment, not on Pydantic validation) provide the real guard,
and only when combined with a forbidden `status`. **A stricter sibling precedent exists in the
same codebase:** `AIClinicalRecommendation` (`app/models/ai.py:65–170`) rejects
`safety_cleared=True` **unconditionally at construction**, regardless of any other field's
value — not just in combination with a forbidden status. Slice 0's `origin` validation copies
**the stricter `AIClinicalRecommendation` pattern**, not the looser `CarePlan` one (§B2.2), and
this plan's future Slice 2/3 schemas should use `Literal[False]`-style API-layer restrictions
(matching `medication_knowledge_import/schema.py`'s own precedent) rather than relying on the
ORM layer alone, closing the exact gap `CarePlanCreate` leaves open.

### B1.7 Audit log infrastructure

`app/services/audit.py` (44 lines) / `app/models/governance.py:55–85`. `AuditLog` fields:
`actor_type, actor_id, action, resource_type, resource_id, outcome, severity, ip_address,
device, timestamp, clinic_id, details:JSON`. Append-only by convention ("No update/delete in
application code"), no dedicated soft-delete. **No automated PHI-scrubbing exists** — the
`details` field's PHI-free discipline is enforced by comment and call-site field selection only,
not by any redaction function. Concrete precedent already in this exact domain:
`medication_knowledge.py:79–89`'s patient-endpoint audit call passes only
`{"drug_ingredient_ids": ingredient_ids}` — ids, never knowledge content. Slice 0's own new
audit touchpoints (§B4) must follow this identical discipline: ids and enum values only, never
knowledge-row content, never prompt text, never raw AI output.

### B1.8 Background-job / worker patterns

**No persistent, retryable, or scheduled job-queue framework exists anywhere in this backend** —
confirmed by grep (no Celery/RQ/arq/dramatiq/APScheduler). The only "background" primitives are
FastAPI's request-scoped `BackgroundTasks` (fire-and-forget, no retry/persistence) and one
homegrown `asyncio.Queue` + `threading` pipeline specific to lab-document OCR
(`app/services/lab_pipeline.py`). One real precedent for a flag check *inside* a
service-layer function reached from a job-like path exists: `app/services/ocr_engine.py:424`,
`if not is_enabled(FeatureFlag.OCR_CLOUD_FALLBACK): return None`. **This plan's own live
experience during staging verification (Part A of this session) directly exercised the actual
mechanism this codebase already uses for one-off, longer-running backend work: Azure Container
Apps Jobs** (`caj-metocare-migrate`, `caj-metocare-seed-demo`) — not a Python task queue. §B2.1
recommends this same mechanism for Slice 2/3's ingestion/normalization/synthesis runs, with the
flag check as the literal first statement in the job's entrypoint script.

### B1.9 Model/prompt/version metadata precedent elsewhere

No `model_version`/`prompt_version`/`model_id` field exists anywhere in this codebase today.
Established naming convention for "what produced this": `provider: String(32)` +
`model: String(64)` as two separate columns (`MetoMessage`, `app/models/meto.py:83-84`), or a
single `model_used: String(64)` (`AISession`, `app/models/ai.py:50`), plus a separate
`ai_confidence: float | None` where confidence is tracked at all
(`AIClinicalRecommendation`, `app/models/ai.py:101`) — never a combined field, never an
enum-based version scheme. `knowledge_ai_generations` (§B2.4) follows this `provider`+`model`
naming/width convention for consistency with the rest of the codebase.

### B1.10 Soft-delete / supersession / version-history conventions

Three genuinely distinct conventions co-exist in this codebase:

1. `SoftDeleteMixin` (`deleted_at`+`deleted_by`, `_mixins.py:34-36`) — `CarePlan`, `Encounter`,
   `AISession`, `AIClinicalRecommendation`.
2. Status-enum-encoded supersession + an integer `version` counter — `CarePlan`
   (`SUPERSEDED` status value + `version: int`).
3. Status-enum-encoded lifecycle with **no** soft-delete mixin and a partial unique index
   enforcing "at most one current" — the ADR-13 knowledge tables (`retired` is a terminal status
   value, not a `retired_at` timestamp; no `deleted_at`/`deleted_by` anywhere on these 5 tables).

**Slice 0 uses convention 3, unchanged** — the knowledge tables' own existing `status` lifecycle
already *is* their supersession/version-history mechanism (`_deprecate_superseded`,
`knowledge_repository.py:334-365`, already atomic, already never deletes). This satisfies the
"supersession/deprecation history" requirement with zero new schema on the knowledge tables
themselves; Slice 0 adds `origin` (§B2.2) and `rejected` (§B2.3) to this same convention, not a
4th one.

### B1.11 Alembic conventions

Current head: `k2_s1_widen_evidence_level` (confirmed live on staging in Part A of this
session). Revision-id convention: filename stem = `revision` value, `<phase>_<slice>_<tag>`
shape (`k1_m01_...`, `k2_s1_...`). SQLite/Postgres parity for partial unique indexes uses
`postgresql_where=`/`sqlite_where=` at both the ORM level (`drug_knowledge_content.py`) and the
migration level (`k1_m01_knowledge_schema.py:245-252` and 3 more identical blocks). `ALTER
COLUMN` operations use `op.batch_alter_table(...)` (required for SQLite; harmless no-op wrapper
on Postgres) — confirmed in `k2_s1_widen_evidence_level.py:95,132`. **Downgrade-guard precedent**
(same file, lines 104-138): before any narrowing/destructive downgrade, run a plain-SQL
pre-check across every affected table and raise a named `RuntimeError` on any violation,
performed identically regardless of dialect rather than trusting either engine's own
constraint enforcement. **Every migration in this plan (§B3) follows this exact guard idiom.**

### B1.12 Doc-vs-code conflicts found

1. **`MEDICATION_ROADMAP.md`/`MEDICATION_SAFETY_RULES.md` describe an entirely different,
   older P0–P4 program** (medication CRUD, scheduling, OCR prescription capture, drug-drug
   interactions) — not this K-track (K0→K1→K1.5→K1.6→K2→Slice 0-5, ADR-13 knowledge tables).
   They are useful *precedent* for safety-rule phrasing (SR-001/002/003 map almost verbatim onto
   ADR-15 §K.4's six prohibited actions) but must not be confused with this program's own scope
   or migration numbering.
2. **The Readiness Review's own §1 and §3 self-contradict** on whether normalization and
   synthesis share one flag or two — resolved in §0.2 above, in favor of the user's (and the
   Review's own §1 reasoning's) two-flag design.
3. **The Readiness Review's suggested `origin` default (`source_extracted`) is inconsistent with
   its own evidence** — it correctly identifies that `ai_generated: Literal[False]` blocks
   AI-authored imports, which by itself proves every existing row is human-authored, yet
   recommends backfilling to a value that means "raw-ingested," which has never happened.
   Corrected in §0.2/§B2.2.

---

## B2. Slice 0 design

### B2.1 Central capability controls

**Extend `app/core/feature_flags.py` — do not invent a new mechanism.** Confirmed precedent:
`FeatureFlag` `StrEnum` + `_DEFAULTS` dict + `is_enabled()` (reads `FEATURE_<NAME>` /
`MCP_FEATURE_<NAME>`, fails closed on unrecognized flag). `CLINICAL_COPILOT`/`CLINIC_SAAS`/
`MEDICATION_KNOWLEDGE_RETRIEVAL` are the structural precedent for every flag below.

| User's requested name | This plan's `FeatureFlag` member | String value | Default | Maps to |
|---|---|---|---|---|
| `MEDICATION_KNOWLEDGE_RETRIEVAL` | `MEDICATION_KNOWLEDGE_RETRIEVAL` | `medication_knowledge_retrieval` | `False` | Unchanged — already exists (K2 Slice 1) |
| `MEDICATION_EXTERNAL_SOURCE_INGESTION` | `MEDICATION_KNOWLEDGE_INGESTION` | `medication_knowledge_ingestion` | `False` | Slice 2 |
| `MEDICATION_AI_NORMALIZATION` | `MEDICATION_KNOWLEDGE_AI_NORMALIZATION` | `medication_knowledge_ai_normalization` | `False` | Slice 3a |
| `MEDICATION_AI_SYNTHESIS` | `MEDICATION_KNOWLEDGE_AI_SYNTHESIS` | `medication_knowledge_ai_synthesis` | `False` | Slice 3b |
| `MEDICATION_AI_DOCTOR_CONTENT` | `MEDICATION_KNOWLEDGE_DOCTOR_AI_CONTENT` | `medication_knowledge_doctor_ai_content` | `False` | Slice 4 |
| `MEDICATION_AI_PATIENT_CONTENT` | `MEDICATION_KNOWLEDGE_PATIENT_AI_CONTENT` | `medication_knowledge_patient_ai_content` | `False` | Slice 5 |
| `MEDICATION_EXPERIMENTAL_VOCABULARY` | `MEDICATION_KNOWLEDGE_EXPERIMENTAL_VOCABULARY` | `medication_knowledge_experimental_vocabulary` | `False`* | Any slice reading experimental `evidence_level`/`theme` values |

*Recommended, not decided — see §0.3 item 2.

**Naming rationale:** every sibling flag in this domain shares the `MEDICATION_KNOWLEDGE_`
prefix, matching the one flag that already exists — not a bare `MEDICATION_` prefix, which would
be self-inconsistent the moment two flags from this same family sat side by side in the enum.

**Enforcement per layer:**

| Layer | Mechanism | Precedent copied |
|---|---|---|
| Router/API | `require_<capability>_enabled()` dependency, `APIRouter(dependencies=[Depends(...)])`, 503 before any handler runs | `deps_medication_knowledge.py:23-32` (already shipped, Slice 1) |
| Service | Capability check as the first statement of the service's public entry function (e.g. `ingest_batch()`, `normalize_batch()`, `synthesize()`) — never assume the router gate is the only entry point | New for Slice 2/3; same principle as `ocr_engine.py:424`'s in-service check |
| Background-job/worker | No job-queue framework exists (§B1.8) — the mechanism is an **Azure Container Apps Job**, same as `caj-metocare-migrate`. The flag check must be the literal first statement the job's entrypoint script executes, before any DB connection is opened for writing | This session's own direct verification of the container-apps-job mechanism (Part A) |
| Scheduler/queue-consumer | Not applicable yet — no scheduler exists. If Slice 2+ introduces a cron-triggered job, the same "check first, before any write" rule applies at the cron entrypoint | N/A — flagged as a gap to close in Slice 2's own plan, not assumed solved here |
| Response serialization | Origin/review-state/generation-history fields are **never** serialized into any K2 Slice 1 response today, and must not be added to `PatientXOut`/`DoctorXOut` without a separate, explicit product decision (§B4) | K2 schemas already exclude all governance metadata (`medication_knowledge.py` docstring) |
| Frontend capability exposure | Out of scope for Slice 0 (no frontend code touched) — future slices must read the *same* flags via a whitelisted `/config`-style endpoint, never hardcode capability assumptions client-side | Deferred, named for Slice 4/5's own plans |
| Cache | No caching exists for any of these endpoints today (K2 plan §11, endpoint #2 caching explicitly OFF). A disabled flag must never be masked by a stale cached "enabled" response — since no cache exists, this is satisfied vacuously today; any future cache layer must key on flag state or bypass cache entirely for gated routes | N/A yet — named so Slice 1's own "endpoint #2 caching stays OFF until version-supersession soundness is proven" gate isn't accidentally reopened by a later slice |

**Reversibility property:** because `is_enabled()` reads env vars at call time with no caching
layer (confirmed, §B1.8/§B1.11 context), flipping a flag is a deploy-config change, not a data
mutation — disabling any of these flags stops new processing on the very next request/job
invocation and never touches rows already written, **provided every entry point into that
slice's write path sits behind the gate**. Each of Slice 2/3/4/5's own plans must enumerate every
entry point into its write path and confirm all of them check the flag — Slice 0 defines the
pattern, it does not audit slices that don't exist yet.

### B2.2 Row-level content origin

**Add `origin: Mapped[str]` directly to `KnowledgeLifecycleMixin`** (`drug_knowledge_content.py`,
alongside `artifact_hash`) — not a shared mixin, not a separate version/entity model. Every row
has exactly one origin; this is a first-class fact about the row itself, following the exact
"add one column to the shared mixin, migrate all five tables in one revision" shape already used
for `artifact_hash` (`k1_a1b_artifact_hash.py`).

```python
# CHECK-constrained, matches _status_check()'s existing shape (drug_knowledge_content.py:43-46)
ORIGIN_VALUES = ("source_extracted", "rule_derived", "ai_synthesized", "human_authored")

origin: Mapped[str] = mapped_column(
    String(24), nullable=False, server_default=text("'human_authored'")
)
```

**Default: `human_authored`, not `source_extracted`** — see §0.2 for the full justification.
Every row written before this migration went through `create_draft`, fed exclusively by the A1b
importer's `ai_generated: Literal[False]`-enforced input contract; there is no ingestion or
rule-engine path that has ever produced a row. Backfilling to anything else would be exactly the
"silently classify legacy content" error this plan is required to avoid.

**Enforcement — copy `AIClinicalRecommendation`'s stricter unconditional-reject pattern, not
`CarePlan`'s combined-check one** (§B1.6): dual `@validates` hooks on `KnowledgeLifecycleMixin`
itself (validators are collected across the MRO, so adding them to the mixin covers all 5
tables uniformly, same as every other shared invariant in this file):

```python
_AI_SYNTHESIZED_FORBIDDEN_STATUSES = frozenset(
    {"clinical_review", "approved", "deprecated", "retired"}
)

@validates("origin")
def _validate_origin(self, key, value):
    if value == "ai_synthesized":
        status_val = self.__dict__.get("status")
        if status_val in self._AI_SYNTHESIZED_FORBIDDEN_STATUSES:
            raise ValueError(
                "origin='ai_synthesized' may only be constructed with status='draft'. "
                "Use the sanctioned AI draft factory; never construct a reviewed/approved "
                "row directly."
            )
    return value

@validates("status")
def _validate_status_against_origin(self, key, value):
    if self.__dict__.get("origin") == "ai_synthesized" and value in self._AI_SYNTHESIZED_FORBIDDEN_STATUSES:
        raise ValueError(
            "A row with origin='ai_synthesized' cannot be constructed at status="
            f"{value!r}. Only draft is allowed at construction; promotion happens "
            "exclusively through approve_row."
        )
    return value
```

This is **defense-in-depth against direct ORM construction/mutation** — it does not, by itself,
stop the service-layer `UPDATE ... WHERE status = ...` calls `submit_for_review`/`approve_row`
already use (those are SQLAlchemy Core statements, which do not trigger ORM `@validates` hooks).
The real backstop against an `ai_synthesized` row skipping review is §B2.3's `approve_row`
extension, not this hook alone — the hook exists to catch the same accidental/malicious
direct-construction risk `CarePlan`/`AIClinicalRecommendation` already guard against for their
own domains, nothing more and nothing less.

### B2.3 Review state

**Do not add a second, parallel `review_state` field on the knowledge tables.** The existing
`status` enum (`draft/clinical_review/approved/deprecated/retired`) already *is* the row-level
review-state lifecycle — adding a parallel field on the same row would create exactly the "two
contradictory approval systems" this plan must avoid. Instead, map the requested 4-state
vocabulary onto the existing (extended) lifecycle:

| Requested state | Existing/extended `status` mapping |
|---|---|
| `unreviewed` | `status IN ('draft', 'clinical_review')` |
| `reviewed` | `status == 'approved'` |
| `rejected` | **New status value** — see below |
| `deprecated` | `status == 'deprecated'` — already exists, unchanged |

**Gap found and closed:** today, a `clinical_review` row a reviewer declines has no modeled
destination — `_ALLOWED_TRANSITIONS` (§B1.3) has no `("clinical_review", "rejected")` pair, and
no `reject_row` function exists. This plan adds:

1. A 6th value to `STATUS_VALUES`/the CHECK constraint on all 5 tables: `rejected` (this is the
   one genuine ADR-13 amendment in this plan — flagged for its own sign-off, §0.3 item 1).
2. `("clinical_review", "rejected")` added to `_ALLOWED_TRANSITIONS`.
3. A new `reject_row(db, row, *, actor_user_id, actor_role) -> KnowledgeModel` function in
   `knowledge_repository.py`, structurally identical to `retire_row` (same canonical-row
   resolution, same transaction-boundary discipline, same `assert_can_approve_knowledge` gate —
   no partial-unique-index interaction needed, since a rejected row was never approved).

**Mandatory invariant — extend `approve_row`, not a new parallel function:**
`approve_row` (§B1.3) currently has no origin-awareness at all. This plan adds one guard, at the
top of `approve_row`'s existing transaction, immediately after `_lock_canonical_row`:

```python
if canonical.origin == "ai_synthesized":
    generation = (
        db.query(KnowledgeAIGeneration)
        .filter_by(
            knowledge_table=KNOWLEDGE_TABLE_NAME[model_cls],
            target_row_id=canonical.id,
            generation_status="succeeded",
        )
        .filter(KnowledgeAIGeneration.superseded_by_generation_id.is_(None))
        .first()
    )
    if generation is None or not (
        generation.model_identifier and generation.prompt_template_id
        and generation.prompt_template_version
    ):
        raise AIProvenanceIncompleteError(
            f"Row {canonical.id!r} has origin='ai_synthesized' but no complete, "
            "non-superseded successful generation record exists — refusing to approve."
        )
```

This is the concrete mechanism behind "AI-generated content may not be created directly in an
approved/reviewed state" and "only an authorized human workflow may promote AI-generated content
to reviewed/approved status" — the *human* part is already enforced by
`assert_can_approve_knowledge`'s closed role set (§B1.3); this guard adds the *provenance-
completeness* part specific to AI-authored rows. **`reject_row` needs no equivalent guard** —
rejecting is always safe regardless of origin.

**"AI may never call or bypass `approve_row` on itself":** already true today by construction
(§B1.3 — the closed 2-role set), **provided no AI/system actor is ever added to
`_APPROVAL_CAPABLE_ROLES`.** Slice 0 adds one regression test asserting this set's exact
membership never changes without an explicit, reviewed diff (§B5), plus a grep-guard test
(mirroring the existing "`app/ai/*` must never import `knowledge_retrieval.py`" convention,
Readiness Review §6) asserting no module under a future AI-authoring package ever imports
`approve_row`/`retire_row`/`reject_row` directly.

### B2.4 AI generation history

**New table: `knowledge_ai_generations`** (`app/models/drug_knowledge_ai_generation.py`, new
file — keeps this codebase's "many small files" convention, one new model concern per file,
matching how `drug_knowledge_references.py`/`drug_knowledge_governance.py` are already split
out from `drug_knowledge_content.py`). Polymorphic association, same shape and rationale as
`KnowledgeReferenceLink`/`KnowledgeReviewSpecialty` (§B1.2/B1.3): "metadata-about-provenance,
never joined for clinical content itself."

**Append-only in practice, with two narrow, explicitly-justified mutable fields** — mirrors this
codebase's own convention (the knowledge row's own `status`/`status_changed_by` mutate in place
while `artifact_hash`/`authored_by` never do): every field describing *what was generated* is
set once at insert and never changes; `review_status` and `superseded_by_generation_id` describe
the generation's *current disposition* and may be updated exactly once each, by exactly one
sanctioned caller.

```python
class KnowledgeAIGeneration(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "knowledge_ai_generations"

    knowledge_table: Mapped[str] = mapped_column(String(32), nullable=False)
    target_row_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # polymorphic, no FK — nullable: a failed
        # generation may have no draft row to point at yet

    model_provider: Mapped[str] = mapped_column(String(32), nullable=False)          # matches MetoMessage.provider (§B1.9)
    model_identifier: Mapped[str] = mapped_column(String(64), nullable=False)        # matches MetoMessage.model
    model_version_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)

    prompt_template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_pipeline_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    input_source_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # DrugReference ids AND/OR
        # other knowledge_row ids this generation consumed (e.g. a source_extracted draft row)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)    # sha256 hex, full-payload (artifact_hash discipline)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # null iff generation_status='failed'
    generation_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # temperature/top_p/seed/etc, where material

    generation_status: Mapped[str] = mapped_column(String(16), nullable=False)   # 'succeeded' | 'failed'
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)       # only when generation_status='failed'

    review_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
        # 'pending' | 'promoted' | 'rejected' | 'superseded' — mutable, exactly once, by the sanctioned promoter/rejecter
    superseded_by_generation_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_ai_generations.id", ondelete="RESTRICT"), nullable=True
    )  # self-referential, forward-pointing only — never delete the old row

    created_by: Mapped[str] = mapped_column(String(255), nullable=False)  # reserved system-actor string (§0.3 item 3),
        # never a real human user id

    __table_args__ = (
        CheckConstraint(
            "knowledge_table IN (" + ",".join(f"'{t}'" for t in KNOWLEDGE_TABLES) + ")",
            name="ck_knowledge_ai_generations_table",
        ),
        CheckConstraint(
            "generation_status IN ('succeeded','failed')",
            name="ck_knowledge_ai_generations_status",
        ),
        CheckConstraint(
            "review_status IN ('pending','promoted','rejected','superseded')",
            name="ck_knowledge_ai_generations_review_status",
        ),
        Index("ix_knowledge_ai_generations_row", "knowledge_table", "target_row_id"),
        Index("ix_knowledge_ai_generations_review_status", "review_status"),
    )
```

**Retries/regeneration/supersession, explicitly:** a retry after a transient failure is a
**new row** (`generation_status='failed'` on the first, `'succeeded'` on the second) — never an
update of the failed row. A regeneration that produces a materially different output for the
same target is also a **new row**; if the earlier generation had already been `promoted`, the
new row's write path sets the earlier row's `superseded_by_generation_id` to the new row's id
and flips its `review_status` to `'superseded'` — the only two fields ever mutated, and only by
Slice 3's own promotion/supersession service function (not built in Slice 0; the column and its
constraint exist so Slice 3 has a correct place to write into without another migration).
**Nothing in this table is ever deleted or content-mutated.**

### B2.5 Provenance

**Reuse `DrugReference`/`KnowledgeReferenceLink` as-is — no duplication.** Already covers, for
any origin: source URL/stable identifier (`url`, `document_identifier`), publication date
(`publication_date`), retrieval date (`accessed_at`), source version (`source_version`),
citation relationship (`KnowledgeReferenceLink`). Confirmed by direct inspection (§B1.2) — zero
schema changes needed here.

**What remains missing, and is what Slice 0 actually adds:** AI-generation-specific fields
(model identity, prompt/template version, generation timestamp, normalization version, input/
output hashes) — covered entirely by `knowledge_ai_generations` (§B2.4). `DrugReference` was
never meant to carry these; conflating "what source was cited" with "what AI process produced
this" would be exactly the kind of duplication this plan must not introduce.

**Provenance completeness rules, by origin** (enforced by the existing
`_approved_invariants_check` DB CHECK for the first two, and by §B2.3's new service-layer guard
for the third):

| Origin | Required before `approved` | Enforcement |
|---|---|---|
| `human_authored` | `source`, `version`, `evidence_level`, `reviewed_by`, `last_reviewed_at` | Existing DB CHECK (`_approved_invariants_check`) — unchanged |
| `source_extracted` | Same as above, plus at least one `KnowledgeReferenceLink` row (Slice 2's own plan must add this — not enforceable by a single-table CHECK, same reasoning as the AI case) | Deferred to Slice 2's plan |
| `rule_derived` | Same base fields; `source`/`version` should identify the rule/ruleset, not a document | Existing DB CHECK suffices; no new enforcement needed |
| `ai_synthesized` | Same base fields, **plus** a complete, non-superseded `knowledge_ai_generations` row | New service-layer guard, §B2.3 |

**No AI-generated output may overwrite or replace raw source data destructively:** already
structurally true — `create_draft`/`build_draft` are always an INSERT (§B1.3, §B1.5's own
docstring: "editing existing content means calling this again... producing a second row, never
an UPDATE"). Slice 2/3's own plans must preserve this discipline for whatever raw-capture
representation they design; Slice 0 does not create that representation, only the origin/
generation-history scaffolding it will need to record its own provenance correctly once it
exists.

### B2.6 Content-layer separation

**Layers are represented as `origin` + `authored_by` values on the same append-only row family,
not as separate physical tables** — verified as sufficient, not assumed:

- The partial-unique-index (`uq_*_approved_key`) only constrains `status='approved'` rows
  (§B1.1) — multiple non-approved drafts **already can coexist** for the same business key today
  (e.g. a raw `source_extracted` draft and a later `ai_synthesized` refinement of it), with only
  one ever allowed to reach `approved`. This was verified directly against the index definition,
  not assumed — it is the structural reason Slice 0 does not need a separate "raw" vs. "refined"
  table.
- **Raw source content / extracted content** (Slice 2) and **rule-derived facts** — no table
  exists yet, and Slice 0 does not create one (out of its scope, §B6). Slice 0 only reserves the
  `source_extracted`/`rule_derived` values in the `origin` CHECK constraint now, so Slice 2, when
  designed, has a place to land its classification without a further migration.
- **AI synthesis** = `origin='ai_synthesized'` rows + their `knowledge_ai_generations` history
  (§B2.4).
- **Human-reviewed content** = `status='approved'`, regardless of origin — reviewed-ness is
  orthogonal to origin by design (an `ai_synthesized` row becomes "human-reviewed" the same way
  a `human_authored` one does: by passing through `approve_row`).
- **Patient-display content is not a separate persisted layer today, and should not become one.**
  Verified directly: `medication_knowledge_response.py` builds `PatientXOut`/`DoctorXOut` objects
  at request time from the same underlying approved rows, filtered by audience/locale — it is a
  real-time projection, not a materialized copy. This is correct and must stay this way: a
  separate stored "patient-display" table would be a second place the same fact could drift from
  its source of truth.

**How this prevents destructive cleanup:** because every stage writes a new row rather than
mutating a prior one (append-only, verified above), and `knowledge_ai_generations` records every
attempt rather than only the latest, a future cleanup pass has no code path that can destroy an
earlier stage's evidence without an explicit, separate, and reviewed deletion — which this plan
does not authorize anywhere.

### B2.7 Safety boundary

The six prohibited actions in this task's brief match, 1:1, ADR-15 §K.4's own list (Readiness
Review §5) — this plan does not invent a new list, it locks the existing one:

1. Stop/change medication
2. Change dosage
3. Replace prescribed medication
4. Declare a serious interaction safe
5. Declare medical evaluation unnecessary
6. Suppress/downgrade a serious warning

**Structural enforcement, verified directly, not assumed:** the 5 ADR-13 knowledge tables
(`drug_usage`, `drug_patient_education`, `drug_side_effects`, `drug_monitoring`,
`drug_contraindications`) are exclusively informational-content tables — none of them, and
nothing this plan or Slice 2/3/4/5 touches, has any column representing an active prescription's
state. Medication start/stop/dose changes live entirely in the separate `medications`/
`medication_statements` tables (a different bounded context, `app/models/clinical.py`), which
`create_draft`/`build_draft`/the entire `medication_knowledge_import` package have **no import
of, and no write path to** (confirmed: `orchestrator.py`'s only model imports are the 5 knowledge
models + `DrugReference`/`KnowledgeReferenceLink`). **The six prohibited actions are therefore
already structurally impossible for any code this plan scaffolds to perform** — not because of a
prompt-level policy, but because the write path has no table to perform them on.

**Test mechanism (not code, per this plan's own scope):** a grep-guard test, mirroring the
existing "`app/ai/*` must never import `knowledge_retrieval.py`" convention (Readiness Review
§6), asserting:
- No file under `app/services/medication_knowledge_import/` (or any future Slice 2/3 AI module)
  imports `app.models.clinical.Medication`, `app.models.clinical.MedicationStatement`, or
  `app.services.medication`.
- This test is named and required now (§B5); it passes trivially today (zero such imports exist)
  and becomes a real regression guard the moment Slice 2/3 code is added.

### B2.8 PHI boundary

Slice 0 introduces no patient-specific knowledge surface — every table it touches
(`drug_usage`, ..., `knowledge_ai_generations`) is keyed by `drug_ingredient_id`, never by
`patient_id`. Concretely:

- **PHI-free metadata:** `origin`, `status`, every `knowledge_ai_generations` column — all
  describe an ingredient-scoped knowledge fact or an AI process, never a patient.
- **Actor/user identifiers in audit logs:** unchanged from existing convention (§B1.7) —
  `actor_id` is a real user id for human actions; `knowledge_ai_generations.created_by` uses a
  reserved system-actor string (§0.3 item 3), never conflated with a real user id.
- **What must never reach an external AI provider:** any patient-instance data at all — Slice 0
  does not call any AI provider itself, but the boundary it locks for Slice 3+ is: synthesis
  input is `input_source_ids` (ingredient-scoped references/rows) only, never anything resolved
  from a `patient_id`. This is the same boundary the Readiness Review §6 already states ("AI
  synthesis output must stay ingredient/drug-scoped and generic, never patient-instance-scoped")
  — Slice 0 gives it a concrete schema-level anchor (`knowledge_ai_generations` has no
  `patient_id` column, and cannot acquire one without a further, separately-reviewed migration).
- **Future patient context isolation:** deferred entirely to whatever later design lets a
  patient-facing AI surface (Slice 5) reference a specific patient's medications — explicitly
  not designed here, and this plan's schema gives it nothing to accidentally piggyback on.
- **Log discipline:** identical to §B1.7's existing convention — ids and enum values in
  `details`, never row content, never prompt text, never raw model output.

---

## B3. Migration design

**Four** additive-only migrations, chained off the current head (`k2_s1_widen_evidence_level`).
Naming follows this codebase's own convention (§B1.11): `k2_s0_<tag>`. (Corrected 2026-07-27: this
section originally specified three migrations. The fourth — `k2_s0_lifecycle_transitions` — was
implemented without being named here, flagged at the Slice 0 final-checkpoint review, and then
explicitly authorized by PTH the same day as a required part of Slice 0, per the binding PTH
implementation instruction requiring lifecycle transition history with actor/reviewer identity,
timestamp, reason code, and PHI-free rationale — see §0.3 item 5 and
`docs/medication-management/adrs/ADR-13-KNOWLEDGE-CONTENT-LIFECYCLE.md` Amendment 1 for the full
authorizing record and design rationale. It is documented here at the same level of detail as the
other three, not narrated as an afterthought.)

### Migration 1 — `k2_s0_knowledge_origin`

**Revises:** `k2_s1_widen_evidence_level`

| | |
|---|---|
| Table/column | `origin` on `drug_usage`, `drug_patient_education`, `drug_side_effects`, `drug_monitoring`, `drug_contraindications` |
| PostgreSQL type | `VARCHAR(24)` |
| SQLite parity | `op.batch_alter_table(table, schema=None)` per table (required for SQLite `ADD COLUMN ... NOT NULL` with a default; harmless on Postgres) |
| Nullable/default | `NOT NULL`, `server_default='human_authored'` — backfills every existing row atomically as part of the `ADD COLUMN`, no separate `UPDATE` needed |
| Indexes/uniqueness | None — `origin` is not part of any business key or partial unique index |
| FKs/delete behavior | None |
| CHECK constraints | `origin IN ('source_extracted','rule_derived','ai_synthesized','human_authored')`, one per table, named `ck_<table>_origin` |
| Backfill strategy | Server-default backfill at `ADD COLUMN` time (see above) — every pre-Slice-0 row becomes `human_authored` |
| Upgrade ordering | First of the three |
| Downgrade behavior | **Guarded, not unconditional.** Refuse if any row has `origin <> 'human_authored'` on any of the 5 tables (i.e., real classification has already happened) — raise a named `RuntimeError` listing offending tables/counts, same idiom as `k2_s1_widen_evidence_level.py:104-138`. If all rows are still at the default, drop the column + CHECK constraint on all 5 tables. |
| Legacy-row interpretation | Every row becomes `human_authored` — justified in §0.2/§B2.2, not `source_extracted` as the Readiness Review's brief sketch suggested. |

### Migration 2 — `k2_s0_ai_generation_history`

**Revises:** `k2_s0_knowledge_origin`

| | |
|---|---|
| Table | `knowledge_ai_generations` (new) |
| Columns | Per §B2.4's model definition — `id` (UUID PK), `knowledge_table`, `target_row_id`, `model_provider`, `model_identifier`, `model_version_snapshot`, `prompt_template_id`, `prompt_template_version`, `normalization_pipeline_version`, `input_source_ids` (JSON), `input_hash`, `output_hash`, `generation_params` (JSON), `generation_status`, `failure_reason`, `review_status`, `superseded_by_generation_id`, `created_by`, `created_at`, `updated_at` |
| PostgreSQL types | `String→VARCHAR(n)` per §B2.4; `JSON` (plain `JSON`, not `JSONB` — matches this table's own dialect-neutral convention already used for `meto.py`'s JSON columns on SQLite test runs; upgrade to `JSONB` is a separate, later optimization, not needed for Slice 0's write volumes) |
| SQLite parity | Plain `create_table` — no `batch_alter_table` needed (new table, not an ALTER) |
| Nullable/default | `target_row_id`, `model_version_snapshot`, `normalization_pipeline_version`, `output_hash`, `failure_reason`, `superseded_by_generation_id` nullable; `review_status` `NOT NULL DEFAULT 'pending'`; every other column `NOT NULL` |
| Indexes/uniqueness | `ix_knowledge_ai_generations_row (knowledge_table, target_row_id)` — mirrors `ix_knowledge_reference_links_row`'s exact shape; `ix_knowledge_ai_generations_review_status (review_status)` for the ops query "what's pending review." No uniqueness constraint — many generations may legitimately target the same row. |
| FKs/delete behavior | `superseded_by_generation_id` self-referential FK, `ondelete="RESTRICT"` (never allow a referenced generation to be deleted while superseded rows still point at it — though nothing in this plan ever deletes a row from this table at all) |
| CHECK constraints | `knowledge_table IN (...)` (5 values, same list as `KnowledgeReferenceLink`'s own check); `generation_status IN ('succeeded','failed')`; `review_status IN ('pending','promoted','rejected','superseded')` |
| Backfill strategy | None — table starts empty, same discipline as every other migration in this codebase ("no clinical content is authored by this migration") |
| Upgrade ordering | Second of the three |
| Downgrade behavior | **Guarded.** Refuse (raise `RuntimeError`) if the table is non-empty — by definition every row in it is a real generation record, never a backfilled default. If empty, `op.drop_table(...)`. |
| Legacy-row interpretation | N/A — no legacy rows possible, table did not exist before |

### Migration 3 — `k2_s0_lifecycle_transitions`

**Revises:** `k2_s0_ai_generation_history`

Added 2026-07-27, PTH-authorized (see the correction note at the top of this section and ADR-13
Amendment 1) after the original three-migration plan was found not to include it.

**Why current-state fields alone are insufficient for auditability:** before this migration, a
knowledge row's own `status`/`status_changed_by`/`status_changed_at` were the *only* record of a
transition — each new transition overwrites the previous one's actor/timestamp in place. That
answers "what is this row's state right now," never "who approved it the first time and why," nor
"was this row ever rejected before a later version was approved." For clinical-safety-adjacent
content that second class of question is exactly what an audit needs.

| | |
|---|---|
| Table | `knowledge_lifecycle_transitions` (new) |
| Purpose | One immutable row per lifecycle transition (draft→clinical_review, clinical_review→approved, clinical_review→rejected, approved→deprecated, deprecated→retired) — history, never a duplicate source of truth for current state (that remains the knowledge row's own `status` column) |
| Relationship model | Polymorphic association keyed by `(knowledge_table, knowledge_row_id)` — no physical FK to any of the 5 content tables, same shape and rationale as `KnowledgeReferenceLink`/`KnowledgeReviewSpecialty`/`knowledge_ai_generations`: metadata-about-history, never joined for clinical content itself |
| Columns | `id` (PK), `knowledge_table`, `knowledge_row_id`, `from_status`, `to_status`, `actor_id`, `actor_role` (nullable), `reason_code`, `rationale`, `transitioned_at`, `created_at`/`updated_at` |
| PostgreSQL types | `String→VARCHAR(n)`, `rationale` as `TEXT`, `transitioned_at`/`created_at`/`updated_at` as `TIMESTAMPTZ` |
| SQLite parity | Plain `create_table` — no `batch_alter_table` needed (new table) |
| Nullable/default | `actor_role` nullable; every other column `NOT NULL` |
| Indexes/uniqueness | `ix_knowledge_lifecycle_transitions_row (knowledge_table, knowledge_row_id)`. No uniqueness constraint — a row legitimately accumulates many transitions over its lifetime |
| FKs/delete behavior | None (polymorphic, see above) |
| CHECK constraints | `knowledge_table IN (...)` (5 values); `from_status`/`to_status` constrained to the 6 canonical lifecycle values (added retroactively at the 2026-07-27 checkpoint — see §C addendum below) |
| Actor semantics | `actor_id` is always the real identity responsible for the transition — for every transition a human directly requests, the real human `actor_user_id`, never a fabricated system identity. The one *automatically triggered* transition (`_deprecate_superseded`, fired when approving a newer row for the same business key deprecates an older one) also records the real human approver's `actor_user_id`, since their approval action is what caused it — not a reserved `SystemActor` string. `SystemActor` identities are reserved for a future automated process (ingestion/normalization/AI synthesis) that writes to this table on its own initiative with no human in the loop; none exists yet, so none has ever been written here |
| Append-only enforcement | No code path issues `UPDATE`/`DELETE` against this table — every write is a single `INSERT` inside the same transaction as the status transition it records. Enforced today by absence of any other write path, not a DB trigger |
| Backfill strategy | None — table starts empty, same discipline as `knowledge_ai_generations` |
| Upgrade ordering | Third of the four |
| Downgrade behavior | **Guarded.** Refuse (raise a named `RuntimeError`) if the table is non-empty — any row in it is real transition history, never a reconstructable default. This makes downgrade past this migration **intentionally unavailable** once the approval workflow has genuinely been used, until that history is explicitly remediated (exported/archived) first — the same operational property this plan already accepts for `knowledge_ai_generations` and for approved knowledge content never being deleted (ADR-13). If empty, `op.drop_table(...)` |
| Legacy-row interpretation | N/A — no legacy rows possible, table did not exist before |

### Migration 4 — `k2_s0_add_rejected_status`

**Revises:** `k2_s0_lifecycle_transitions`

| | |
|---|---|
| Table/column | `status` CHECK constraint on the same 5 knowledge tables — widen the allowed-value list, not the column itself (still `VARCHAR(16)`, `rejected` fits) |
| PostgreSQL type | Unchanged (`VARCHAR(16)`) |
| SQLite parity | `op.batch_alter_table` per table, dropping and recreating the named CHECK constraint (SQLite has no `ALTER TABLE ... DROP CONSTRAINT`; recreate via batch mode, same mechanism `k2_s1_widen_evidence_level` already uses for column-type changes) |
| Nullable/default | Unchanged |
| Indexes/uniqueness | Unchanged — `rejected` is never part of the `approved`-only partial unique index |
| FKs | None |
| CHECK constraints | `ck_<table>_status` widened from 5 to 6 values: adds `'rejected'` |
| Backfill strategy | None — additive value, no existing row is reclassified |
| Upgrade ordering | Fourth of the four (independent of the other three migrations' content, ordered last only to keep this plan's own migration sequence linear) |
| Downgrade behavior | **Guarded.** Refuse if any row has `status = 'rejected'` (narrowing the CHECK back to 5 values would make such a row invalid/unreadable under the old constraint). If none exist, recreate the 5-value CHECK. |
| Legacy-row interpretation | No existing row is ever `rejected` before this migration exists — trivially safe |

**No migration in this plan is required by K1.5's or K1.6's existing code paths** — `approve_row`
(pre-Slice-0), `submit_for_review`, `list_current_for_ingredient`, and every K2 Slice 1 route
continue to work unmodified whether or not these four migrations have run, satisfying the
rollback gate's "additive-only, not required by any currently-running code path" property
(Readiness Review §5) — with the one documented exception that `knowledge_lifecycle_transitions`'s
own downgrade becomes unavailable, not that any *upgrade path* is required by existing code.

---

## B4. API and service impact

- **K2 response contracts (`PatientXOut`/`DoctorXOut`) do not change.** `origin`, `status`
  extensions, and generation-history metadata are never serialized into either contract — this
  matches K2 Slice 1's own existing exclusion of every governance/workflow field (schema
  docstring: "still no workflow/governance metadata"). Exposing origin/review-state to doctors
  or patients is a separate, later product decision (plausibly Slice 4's own plan, for doctor-
  facing provenance transparency) — Slice 0 does not decide it.
- **Origin/review metadata stays internal** — visible only through direct DB/admin tooling until
  a future slice explicitly designs an exposure surface for it.
- **`knowledge_vocabulary_version` is unaffected** — confirmed it's a hardcoded module constant
  (`medication_knowledge_response.py:47`, `"1.0"`), not derived from any row; Slice 0 does not
  touch it.
- **Services gaining capability checks:** none yet exist to gate, since Slice 2/3/4/5's own
  service modules aren't built. Slice 0's only service-layer change is the `approve_row`
  extension (§B2.3) and the new `reject_row` function — both in `knowledge_repository.py`.
- **Interfaces Slice 0 prepares but does not implement:** the `origin`/`knowledge_ai_generations`
  schema Slice 2/3 will write into; the `MEDICATION_KNOWLEDGE_*` flags Slice 2/3/4/5 will check;
  the grep-guard test pattern Slice 3+ must extend to cover its own new modules.
- **Compatibility with K1.5/K1.6/K2 Slice 1:** verified exhaustively in §B1.3/§B1.4/§B3 — every
  existing function either ignores the new column entirely (K1.6) or gains one new, additive
  guard clause that only activates for `origin='ai_synthesized'` rows, which cannot exist until
  Slice 3 ships (`approve_row`, K1.5).

---

## B5. Testing strategy

| Area | Concrete test(s) |
|---|---|
| Flag fail-closed — router | `test_<flag>_off_returns_503` per new flag, mirroring existing `TestFeatureFlagOff`-style tests for `MEDICATION_KNOWLEDGE_RETRIEVAL`/`CLINIC_SAAS` |
| Flag fail-closed — service | Once Slice 2/3 exist: assert the service entry function itself raises/no-ops when its flag is off, called directly (not just through the router), proving the gate isn't router-only |
| Flag fail-closed — worker/job | Once Slice 2/3 exist: assert the job entrypoint script exits before any DB write when its flag is off (integration test against the actual container image, same style as this session's own live Part A verification) |
| Kill-switch with queued/pending jobs | No job queue exists (§B1.8) — N/A for Slice 0; Slice 2/3's own plan must define this once a real job mechanism exists |
| No data deletion when flag disabled | `test_disabling_flag_does_not_delete_existing_rows` — write a row with the flag on, disable it, assert the row (and its `knowledge_ai_generations` history) is unchanged and still readable once re-enabled |
| Origin vocabulary constraints | `test_origin_check_constraint_rejects_invalid_value` (Postgres integration, mirrors `k2_s1`'s own CHECK-violation tests); one test per `@validates` guard in §B2.2 |
| Legacy-row backfill | `test_existing_rows_backfilled_to_human_authored` — Postgres integration test, seed rows pre-migration, run `k2_s0_knowledge_origin` upgrade, assert every row's `origin == 'human_authored'` |
| AI content cannot be born approved | `test_construct_ai_synthesized_row_at_approved_status_raises` — direct ORM construction attempt, both attribute-assignment orders (origin-then-status, status-then-origin), asserting `ValueError` both ways (mirrors `CarePlan`'s own dual-order test convention) |
| AI cannot approve itself | `test_ai_actor_role_never_in_approval_capable_roles` (regression-locks `_APPROVAL_CAPABLE_ROLES`'s exact membership) + `test_approve_row_rejects_ai_synthesized_without_generation_record` (the §B2.3 guard) + grep-guard test asserting no future AI module imports `approve_row`/`retire_row`/`reject_row` |
| Generation history is append-only | `test_knowledge_ai_generations_never_updates_immutable_fields` — attempt to mutate `input_hash`/`model_identifier`/etc. on a persisted row via a raw `UPDATE`, assert this plan's own service layer (once Slice 3 exists) never does so; for Slice 0 itself, a schema-level test that only `review_status`/`superseded_by_generation_id` are ever targeted by any `UPDATE` statement in the codebase (grep-guard) |
| Retries don't overwrite prior records | `test_second_generation_attempt_creates_new_row_not_update` — two `KnowledgeAIGeneration` inserts for the same `target_row_id`, assert both persist independently |
| Source provenance intact across normalization/synthesis | Deferred to Slice 2/3's own plans (no normalization/synthesis code exists yet) — named here so it isn't dropped later |
| Row/generation/reference mapping integrity | `test_generation_target_row_id_resolves_to_real_row_when_present` — `target_row_id`, when non-null, must resolve to an actual row in the table named by `knowledge_table` (service-level test, since this is a polymorphic association with no physical FK, same testing convention already used for `KnowledgeReferenceLink`) |
| PHI-free telemetry | `test_knowledge_ai_generations_has_no_patient_id_column` (schema-introspection test, cheap and permanent) + audit-detail tests following the existing `medication_knowledge.py:79` convention |
| PostgreSQL and SQLite parity | Every migration test runs on both a SQLite dev DB and the real Postgres integration suite (`POSTGRES_TEST_URL`), matching this session's own Part A verification method exactly |
| Migration upgrade/downgrade | One test per migration (3 total) proving upgrade succeeds, and **two** downgrade tests per guarded migration: (a) downgrade succeeds when the guard condition is unmet (no real data), (b) downgrade refuses with the named `RuntimeError` when it is met — mirrors `k2_s1_widen_evidence_level`'s own existing test file shape exactly |
| Rollback with existing K1.5/K1.6/K2 data | `test_full_downgrade_then_upgrade_roundtrip_preserves_existing_knowledge_rows` — seed real K1.5-style approved rows first, then exercise all 4 migrations' upgrade→downgrade→upgrade cycle, assert the original rows are untouched throughout |
| Six prohibited autonomous actions | One named test per action (§B2.7) asserting the underlying import/write-path boundary — e.g. `test_medication_knowledge_import_never_imports_medication_models` (grep-guard); full behavioral tests on AI *output* are Slice 3/4's own responsibility, since no AI output exists yet |
| No regression to K2 Slice 1 | Full existing suite (`test_medication_knowledge_routes.py`, `test_knowledge_retrieval.py`, `test_medication_k2_slice1_postgres.py`, `test_medication_k2_widen_evidence_level_migration.py`) must pass unmodified — this is a gate condition, not new test content |

**No silent caps in this test matrix** — every area the user's brief named has either a concrete
test or an explicit "deferred to Slice N's own plan" note; nothing is dropped without saying so.

---

## B6. Slice boundaries and sequence

```
Slice 0 (this plan): origin + rejected status + knowledge_ai_generations + 7 flags
   │  (schema + flags only, no product behavior, no AI, no ingestion)
   │
   ├──► Slice 1: K2 retrieval API — ALREADY MERGED (PR #135), independent of Slice 0
   │
   └──► Slice 2: External-source ingestion
            — raw capture representation (own migration, not designed here)
            — origin='source_extracted' rows
            — NOT in Slice 0's scope: ingestion table shape, source connectors, rate limits
            │
            └──► Slice 3: AI normalization (3a) + AI synthesis (3b) — 2 independent flags
                     — origin='ai_synthesized' rows, populate knowledge_ai_generations
                     — NOT in Slice 0's scope: prompt design, model selection, the actual
                       normalization/synthesis service code, promotion/supersession service logic
                     │
                     └──► Slice 4: Doctor-facing AI content exposure
                              — NOT in Slice 0's scope: doctor route/schema design
                              │
                              └──► Slice 5: Patient-facing AI content exposure
                                       — must not ship ahead of Slice 4 having been live
                                         through one full Release Stage 2 cycle (Readiness
                                         Review §1/§6 — this plan does not relitigate that gate)
```

**What belongs to Slice 0:** everything in §B2/§B3/§B4/§B5 above — the origin column, the
rejected status, the generation-history table, the 7 flags and their enforcement pattern, the
`approve_row` provenance-completeness guard, the grep-guard test family.

**What is explicitly deferred:**
- Slice 2: raw-ingestion table design, source connectors, ingestion rate/volume limits,
  `source_extracted` provenance-completeness enforcement (the "at least one reference link"
  rule named in §B2.5 is Slice 2's to build, not Slice 0's).
- Slice 3: the actual normalization/synthesis service code, prompt templates, model selection,
  the promotion/supersession service function that mutates `review_status`/
  `superseded_by_generation_id`, the contract test proving synthesis output can't reach a route
  without a human `approve_row` call (Readiness Review §5 — this plan names the requirement,
  Slice 3 builds the mechanism).
- Slice 4/5: route/schema design for doctor/patient AI content exposure, the decision of whether
  origin/review-state ever becomes visible to either audience.

**Prevention of accidental Slice 3+ implementation during Slice 0:** Slice 0 contains zero AI
provider calls, zero prompt code, and zero new API routes. The `knowledge_ai_generations` table
exists and is schema-valid before any code writes to it — this is deliberate (same "additive,
not yet exercised" discipline the K1-M01 migration itself used when it created the 5 knowledge
tables empty, §B1.11) and is proven, not assumed, by the empty-table downgrade guard in
Migration 2 (§B3): if Slice 0's own test suite ever left a row in this table, the downgrade test
would fail loudly.

---

## B7. File-level implementation map

| File | Action | Why |
|---|---|---|
| `backend/app/models/drug_knowledge_content.py` | **Modify** | Add `origin` column + `ORIGIN_VALUES` tuple + `_origin_check()` helper + dual `@validates` hooks (§B2.2) to `KnowledgeLifecycleMixin`; extend `STATUS_VALUES` to include `'rejected'` (§B2.3) |
| `backend/app/models/drug_knowledge_ai_generation.py` | **Create** | New `KnowledgeAIGeneration` model (§B2.4) — kept in its own file, matching this codebase's existing split of `drug_knowledge_references.py`/`drug_knowledge_governance.py` out of the same content file |
| `backend/app/services/knowledge_repository.py` | **Modify** | Add `reject_row()` (§B2.3, mirrors `retire_row`'s shape); add the origin-awareness guard + `AIProvenanceIncompleteError` to `approve_row()` (§B2.3); add `("clinical_review", "rejected")` to `_ALLOWED_TRANSITIONS` |
| `backend/app/core/feature_flags.py` | **Modify** | Add 6 new `FeatureFlag` members + their `_DEFAULTS` entries (§B2.1) — `MEDICATION_KNOWLEDGE_RETRIEVAL` itself is unchanged |
| `backend/alembic/versions/k2_s0_knowledge_origin.py` | **Create** (not authored in this task) | Migration 1, §B3 |
| `backend/alembic/versions/k2_s0_ai_generation_history.py` | **Create** (not authored in this task) | Migration 2, §B3 |
| `backend/alembic/versions/k2_s0_add_rejected_status.py` | **Create** (not authored in this task) | Migration 3, §B3 |
| `backend/tests/test_knowledge_repository.py` (or equivalent existing K1.5 test file) | **Modify** | Add tests for `reject_row`, the `approve_row` provenance guard, the `@validates` hooks (§B5) |
| `backend/tests/test_medication_knowledge_ai_generation.py` | **Create** | New model's own test file — append-only behavior, CHECK constraints, polymorphic row-resolution tests (§B5) |
| `backend/tests/integration/test_medication_k2_s0_origin_migration.py` | **Create** | Postgres migration tests for all 4 new migrations — upgrade/downgrade/guard behavior, mirrors `test_medication_k2_widen_evidence_level_migration.py`'s own shape exactly |
| `backend/tests/test_medication_knowledge_scope_guard.py` (or extend the existing K2 scope-guard test) | **Modify** | Extend the grep-guard convention (§B2.7, §B5) to assert no AI-authoring module imports `Medication`/`MedicationStatement`/`approve_row`/`retire_row`/`reject_row` |
| `backend/app/api/deps_medication_knowledge.py` | **Left untouched** | Slice 0 adds no new routes; `require_medication_knowledge_read_enabled` is unchanged |
| `backend/app/schemas/medication_knowledge.py`, `backend/app/services/medication_knowledge_response.py` | **Left untouched** | Confirmed no serialization changes needed (§B4) |
| `backend/app/services/knowledge_retrieval.py` | **Left untouched** | Confirmed no read-path changes needed (§B1.4) |
| `backend/app/services/medication_knowledge_import/*.py` | **Left untouched** | The `Literal[False]` restriction in `schema.py:171` is explicitly **not** relaxed by Slice 0 — that change belongs to Slice 3's own plan, the moment AI-authored import content is actually being designed (Readiness Review §2 already flags this correctly as a Slice-3-not-Slice-0 change) |

---

## B8. Risk register and gates

| Risk | Mitigation in this plan |
|---|---|
| Provenance loss | Append-only discipline throughout (§B2.4, §B2.6); no migration in §B3 is destructive without a guard |
| AI self-approval | Closed 2-role `_APPROVAL_CAPABLE_ROLES` set (already exists) + new regression-locking test + grep-guard (§B2.3, §B5) |
| Incorrect legacy backfill | `human_authored` default, justified by direct evidence (§0.2/§B2.2), not `source_extracted` |
| Duplicate/conflicting review state | Explicitly rejected a parallel `review_state` field (§B2.3) — extends the existing `status` enum instead |
| Feature-flag inconsistency across layers | Explicit per-layer table (§B2.1) naming the mechanism at each layer, including the two layers (worker, scheduler) that don't exist yet — named as gaps, not silently skipped |
| Queued jobs continuing after kill switch | No job queue exists today (§B1.8) — risk is currently N/A; flagged as a **mandatory** requirement for whichever of Slice 2/3 introduces the first real job mechanism |
| PHI leakage | No `patient_id` anywhere in Slice 0's schema (§B2.8); audit discipline unchanged from existing convention |
| Migration rollback failure | Every migration has a tested, guarded downgrade (§B3, §B5) — no exception, matching this codebase's own standing convention |
| Generation-history overwrite | Schema only allows `review_status`/`superseded_by_generation_id` to be mutable; every other column has no code path that ever issues an `UPDATE` against it (§B2.4, enforced by a grep-guard test) |
| Model/prompt version ambiguity | `model_provider`+`model_identifier`+`model_version_snapshot`+`prompt_template_id`+`prompt_template_version` as 5 distinct fields, not one overloaded string (§B2.4) |
| Patient-facing exposure of unreviewed AI content | K2 response contracts unchanged (§B4); no route in Slice 0 or Slice 1 can read `origin`/`review_status` at all |
| Generation-insert vs. in-flight approval race | Not mitigated in Slice 0 — no production writer exists yet (`knowledge_ai_generations` stays empty through Slice 0, no AI provider calls). Formalized as a **hard Slice 3 entry gate**, not a soft follow-up — see the Gates subsection immediately below |

### Gates

- **Implementation gate:** the 4 items in §0.3 must be explicitly decided by PTH before any of
  §B3's migrations are authored (not just before they're applied — the `rejected` status value
  in particular is a real ADR-13 amendment and needs the same review tier the original 5-value
  enum received).
- **Staging gate:** every migration in §B3 must pass its Postgres integration test (upgrade,
  downgrade-refuses, downgrade-succeeds) against a real Postgres instance before merge — same
  bar this session's own Part A verification just held K2 Slice 1's migration to.
- **Patient/production gate:** not reached by Slice 0 at all — Slice 0 ships no patient-visible
  behavior change, and this plan does not request or need a production activation decision.
  Clinical/legal review of the eventual AI-authored *content* is explicitly out of Slice 0's
  scope (Slice 3+'s own gate) — this plan's job is only to make sure the data model can carry
  whatever policy that later review imposes, without needing to be rebuilt.
- **Slice 3 entry gate (hard — PR #136 Fix Round 3.1, 2026-07-29):** `approve_row`'s
  `_select_and_promote_ai_generation` (knowledge_repository.py) selects the single most recent
  non-superseded `KnowledgeAIGeneration` by `sequence_number DESC`, locked `FOR UPDATE` — but
  that lock is only ever acquired against rows that already exist at the moment the `SELECT ...
  FOR UPDATE` runs. A concurrent `INSERT` of a NEW, more-authoritative generation (a later,
  successful retry superseding an earlier failed or incomplete one) is not covered by that lock
  and could commit either just before or just after the approval transaction's own read,
  non-deterministically, if the two ever race against the same `target_row_id`. Slice 0 defers
  this entirely because **no code path in this codebase inserts a `KnowledgeAIGeneration` row
  today** — the table is schema-valid and permanently empty through Slice 0 (no AI provider
  calls, no synthesis code, no caller). This is acceptable ONLY as long as that remains true.
  **Slice 3 — the first slice to introduce any `KnowledgeAIGeneration` INSERT path — must NOT
  ship that writer until:**
  1. generation-creation and `approve_row`'s generation-selection both acquire the SAME
     target-row-scoped lock/serialization protocol before either reads or writes any
     `KnowledgeAIGeneration` row for that `(knowledge_table, target_row_id)` pair (e.g. locking
     the target knowledge row itself — already done via `_lock_canonical_row` in the approval
     path — as the shared serialization point for both operations, so a concurrent insert and a
     concurrent approval can never interleave unlocked); and
  2. a PostgreSQL concurrency test (not SQLite — SQLite's serialized single-writer model cannot
     construct this race at all, see `k2_s0_round3_hardening_postgres.py`'s own module docstring
     for why generation-ordering/concurrency claims require real Postgres) proves directly that
     an approval running concurrently with a new, more-authoritative generation INSERT for the
     same target row can never miss that newly-authoritative attempt — i.e. either the approval
     correctly waits and picks it up, or it correctly fails closed (`AIProvenanceIncompleteError`)
     rather than silently approving against a now-stale "latest" generation.
  This is a merge-blocking precondition for Slice 3's writer, not an optional follow-up item —
  Slice 3's own implementation plan must show this test passing before that PR can merge.

---

## Summary — required output recap

- **Plan file path:** `docs/medication-management/MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md` (this file).
- **Direct live-code findings:** §B1 (12 subsections, all file/line-cited).
- **Proposed data model:** §B2.2 (`origin`), §B2.3 (`rejected` status), §B2.4
  (`knowledge_ai_generations`).
- **Proposed migrations:** §B3 (4 migrations, none authored in this task — the fourth,
  `k2_s0_lifecycle_transitions`, was added and authorized after this document's original drafting;
  see the correction note at the top of §B3).
- **Capability/feature-flag architecture:** §B2.1 (7 flags, per-layer enforcement table).
- **Provenance and generation-history design:** §B2.4, §B2.5.
- **Test matrix:** §B5.
- **File-level implementation map:** §B7.
- **Slice boundaries:** §B6.
- **Risks and unresolved technical decisions:** §B8, §0.3.
- **Explicit verdict: CONDITIONAL** — implementation-ready pending PTH's decision on the 4 items
  in §0.3. Nothing in this plan blocks on missing information; everything blocks on a decision
  only PTH can make (a genuine ADR-13 amendment, an explicitly-deferred default, a
  service-identity design choice, and a scope-sequencing preference).
