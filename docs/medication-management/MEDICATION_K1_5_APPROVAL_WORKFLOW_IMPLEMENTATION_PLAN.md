# K1.5 — Clinical Review & Approval Write Path — Implementation Plan

**Date:** 2026-07-17
**Author:** Claude Code (planning session following A1b orchestrator merge, PR #132)
**Status:** **PLANNING — REVISED PER PTH REVIEW (2026-07-17), STILL NOT YET GO FOR CODING.** This document proposes the next Medication Knowledge slice and specifies it in implementable detail. It does not itself authorize implementation; per this program's established governance pattern (A1a/A1b/K1-S2/K1-S3 all separated "planning GO" from "implementation GO"), a human (PTH) must explicitly approve this plan before any code is written. PTH reviewed the original version of this plan and agreed with its overall conclusion (K1.5 before Phase B, no migration, dormancy preserved) subject to 3 additions, all applied in this revision — see §3.5 (non-negotiable invariants) and the updated §3.4/§4.1/§4.2. PTH's review closed with: *"Nếu ba invariant này được bổ sung vào implementation plan, tôi đánh giá K1.5 đã sẵn sàng để bước vào giai đoạn coding"* — i.e. conditional readiness, contingent on these edits, which this revision makes. Coding itself was still explicitly out of scope for the planning session that produced this document.
**Scope:** Planning and design only. No code, no migration, no real clinical content in this document.
**Related:** `adrs/ADR-13-KNOWLEDGE-CONTENT-LIFECYCLE.md` (the ADR this slice executes — already Accepted, no new ADR needed), `MEDICATION_K1_S3_COMPLIANCE_REVIEW.md` (documents the gap this closes), `MEDICATION_PHASE_A1B_ORCHESTRATOR_IMPLEMENTATION_PLAN.md` (A1b, merged 2026-07-17, prerequisite), `MEDICATION_KNOWLEDGE_TEMPLATE_V1.md` (content model — uncommitted draft, see §0.3), `[[project_medication_knowledge_k1]]` / `[[project_medication_knowledge_phase_ab]]` (memory)

---

## 0. Baseline this plan was written against

### 0.1 Verified facts (2026-07-17)

- `main` HEAD = `988e8f85cfd8a93819165fdc0f42fb44c8dfc683` ("feat(medication): A1b orchestrator implementation (#132)"), verified via a clean `git worktree` at `origin/main` — working tree clean, no divergence.
- Single Alembic head: `k1_a1b_artifact_hash` (verified by parsing all 65 files under `backend/alembic/versions/` for `revision`/`down_revision` pairs — exactly one revision is not referenced as anyone's `down_revision`).
- A1b orchestrator (`backend/app/services/medication_knowledge_import/orchestrator.py`) is implemented, merged, and — per its own module docstring and every compliance review read — **draft-only, dormant**: no API route, frontend screen, or AI wiring imports it (verified directly: `grep` across `backend/app/api`, `backend/app/ai` for any of the 5 knowledge-table model names or `knowledge_repository` returns zero hits).

### 0.2 Ambiguity resolved by direct source-code inspection, not inference

The user asked that "Phase B" not be inferred from its name. Cross-referencing the ADRs, the K1/Phase-A/A1b planning docs, and actual code confirms: **"Phase B"** in this doc set means one specific, narrow thing — *the later, separately-PTH-gated act of authoring real clinical content for a 5-drug MVP set (levothyroxine, metformin, aspirin, warfarin, calcium) through the already-built A1b import pipeline, landing only in `draft`/`clinical_review` status* — and multiple docs state explicitly that **the approval workflow itself is out of scope for Phase B** (`MEDICATION_PHASE_A_PR_A1_IMPLEMENTATION_PLAN.md:63`: *"The actual approve workflow (Clinical Advisor role, K1.5+) is out of scope for both Phase A and Phase B"*). This plan is that named **K1.5** slice — it is a prerequisite the docs already anticipated, not a phase I invented.

### 0.3 A flag, not a blocker: `MEDICATION_KNOWLEDGE_TEMPLATE_V1.md` is uncommitted

This file (dated 2026-07-16, marked "APPROVED WITH REVISIONS (PTH, 2026-07-16)") exists only as an **untracked file in the live working directory**, not on `main`. Its content is already substantively reflected in code — the `drug_side_effects.label`/`frequency`/`action_level` split it describes is already live in `backend/app/models/drug_knowledge_content.py` via migration `k1_a1b_f1_schema_complete` — but the document itself was never committed. This plan does not depend on that document (K1.5 is pure lifecycle/RBAC work, not content-model work), but it should be committed to `main` before or alongside Phase B (§2, Phase 4) since Phase B's authors will need it as their spec-of-record. Flagged here so it isn't lost; not part of this slice's scope.

---

## 1. Gap analysis

Built from direct inspection of `backend/app/services/knowledge_repository.py`, `backend/app/models/drug_knowledge_*.py`, `backend/app/core/rbac.py`, and `backend/tests/test_knowledge_repository.py` — not from doc claims alone.

| Capability | State | Evidence | Risk if left as-is | Migration need | Recommended phase |
|---|---|---|---|---|---|
| `draft` → `clinical_review` transition | **Have** — real, atomic, race-safe DB write (`submit_for_review`) | `knowledge_repository.py:180-220`, tested incl. concurrency (`test_concurrent_submit_for_review_only_one_wins`) | None | None | Done (K1-S3) |
| `clinical_review` → `approved` transition rule | **Have** as a pure function only | `validate_transition()` implements self-approval block + specialty-completeness gate + illegal-transition block; unit-tested in isolation (`TestTransitionValidation`) | Rule is correct but unreachable | None | — |
| `clinical_review` → `approved` **write path** | **Missing entirely** | `grep -rn "def approve" backend/app` — zero hits outside unrelated domains (care_plans, doctor_verification); module docstring states this explicitly: *"There is no function anywhere in this module that can set a row's status to 'approved'"* | Content authored in Phase B has nowhere to go past `clinical_review` — forces either scope creep into Phase B's own PR, or content stalls indefinitely | **None** — all columns already exist | **This slice (K1.5)** |
| `approved` → `deprecated` automatic transition | **Missing** | Explicitly named as deferred in `MEDICATION_K1_S3_COMPLIANCE_REVIEW.md:54` | Two "approved" rows for the same business key would require this to reconcile; currently only the partial unique index prevents it at the DB layer, with no service-layer path to resolve a legitimate content update | None | **This slice (K1.5)** |
| `deprecated` → `retired` transition | **Missing** | No `def retire` anywhere in the module | Old content accumulates in `deprecated` with no lifecycle terminus; grace period explicitly deferred as "a K1.5 operational decision" (ADR-13) | None | **This slice (K1.5)** |
| Specialty review recording | **Have** | `record_specialty_review()`, tested | — | — | Done (K1-S3) |
| Specialty completeness check | **Have**, read-only, fails closed | `check_specialty_completeness()`, tested incl. dangling-reference case | — | — | Done (K1-S3) |
| `zero-approved-row` invariant | **Have**, enforced by absence of a write path + regression-tested | `test_zero_approved_rows_exist_anywhere` (scoped to each test's own isolated transaction, not a global lock — confirmed by reading the fixture) | — | — | Continues to hold after this slice: the test doesn't need to change, since it only asserts no *orchestrator-driven* import ever produces `approved` rows, and this slice's `approve_row` is never called by the orchestrator |
| `artifact_hash` / append-only versioning | **Have**, robustly implemented | `versioning.py` — full-artifact SHA-256 hash (not content-only), fails closed on NULL legacy hash, batch-local + DB-seeded fold logic, unit-tested extensively | — | — | Done (A1b) |
| Reference identity/conflict handling | **Have** | `references.py`, `drug_knowledge_references.py` — two-tier citation identity (document_identifier-first, publisher/title/date fallback), conflict detection tested | — | — | Done (A1b-F1) |
| Legacy NULL artifact_hash remediation | **Detected**, not **remediated** | `LegacyArtifactHashUnavailableError` fails closed and says "manual remediation required" — no script/runbook exists to perform that remediation | Low today (no legacy rows exist — K1 dormancy guarantees 0 rows in all 5 tables); becomes relevant only once real content exists | N/A now | Defer until it's an actual incident, not before |
| Duplicate/concurrent import (same batch, same run) | **Have**, well-tested | Batch-local fold in `orchestrator._resolve_phase1`, `known_versions_for` DB fold | — | — | Done (A1b) |
| Concurrent import (two orchestrator runs at once) | **Untested gap**, low severity | No test found exercising two simultaneous `import_batch` calls against the same business key | Low — worst case is a spurious `REJECT_VERSION_CONFLICT` or duplicate draft version, not data corruption (partial unique index still caps `approved` rows at 1) | None | Nice-to-have, not blocking |
| Audit trail | **Have** | `status_changed_by`/`status_changed_at`/`authored_by` on every row; append-only design means row history *is* the audit trail, no separate log table needed | — | — | Done |
| RBAC: who may approve | **Missing** | `MEDICAL_REVIEWER` (the only review-flavored role that exists) is explicitly documented in `rbac.py:7` as *"read-only — bypass read checks, blocked on writes elsewhere"* — reusing it for approval writes would silently grant a write capability to a role never audited for one | Building `approve_row` without resolving this either (a) reuses `MEDICAL_REVIEWER` incorrectly, or (b) invents a role without an explicit decision | None | **This slice must make an explicit, flagged interim choice (§3.4)** |
| Real Clinical Advisor identity | **Missing**, PTH-pending | `ARCHITECTURE_DECISION_INDEX.md` OQ-7: "designated VN clinical advisor identity... Pending PTH" | Cannot be resolved by code — this is a staffing/business decision | N/A | Out of scope for K1.5; K1.5's RBAC gate is deliberately role-based (any user holding the interim role), not identity-based, so it doesn't block on OQ-7 |
| Specialty-to-drug-class roster | **Partially have** | `drug_classes.required_specialties` column exists (JSON list); actual roster content (which specialty reviews which class) is OQ-8, "Pending PTH" | `check_specialty_completeness` works correctly against whatever roster exists — an empty roster means every class trivially passes (`if not required_codes: return True`, `knowledge_repository.py:273-274`) | N/A | Out of scope for K1.5 — orthogonal, does not block approval-path code |
| Content licensing / Tier-1 sourcing confirmation | **Open**, PTH-pending | ADR-10 OQ-2/OQ-3/OQ-4 | Blocks *real content*, not the approval mechanism | N/A | Blocks Phase B, not K1.5 |
| Calcium ingredient identity | **Missing** | `MEDICATION_PHASE_A_BLOCKING_FINDINGS.md:79-82` — no generic "Calcium" `drug_ingredients` row exists; needs a `K1-S2b` PR | Blocks one of Phase B's 5 target drugs | New data-only migration (adds 2 rows: calcium carbonate, calcium citrate) | Blocks Phase B, not K1.5 |
| PHI boundary | **N/A — correctly out of scope** | ADR-01: knowledge content is "Public reference data. Không cần encrypt" — verified no `drug_ingredient_id`-keyed table joins to any patient/PHI table | — | — | No action needed |
| Tenant/clinic scoping | **N/A — correctly out of scope** | No `clinic_id` column on any of the 5 knowledge tables or their governance tables — knowledge content is platform-global by design | — | — | No action needed |
| AI consumption without bypassing approval | **Safe by construction, still fully dormant** | `list_published()` already filters `status='approved'` unconditionally (ADR-13's binding rule); zero AI code imports any knowledge-table model today | — | — | Ready whenever K2/K4 gets its own GO; not this slice |
| Self-approval override (single-advisor-per-specialty case) | **Explicitly not built anywhere, and not part of this slice** | ADR-13 describes "a logged, PTH-approved override... reason and PTH's sign-off stored on the transition row itself" — no schema field or code exists for this | Cannot yet handle the case where MetoCare has exactly one advisor for a specialty | Would need a new column (e.g. `approval_override_reason`) if ever built | Deliberately deferred (§2.2) |

---

## 2. Roadmap — next 5 phases, gated and independently reviewable

Each phase below is scoped to be small enough to review and roll back independently. None of phases 2-5 are authorized by this document — only Phase 1 (K1.5) is specified to implementation-ready detail (§3 onward); phases 2-5 are included so the recommendation in §2.1 can be judged against real alternatives, per the request.

### Phase 1 — K1.5: Clinical Review & Approval Write Path — **RECOMMENDED NEXT (this document, §3-9)**

- **Objective:** Give ADR-13's already-designed `clinical_review → approved`, `approved → deprecated`, `deprecated → retired` rules a real, tested, race-safe database write path, so content authored in a future Phase B has somewhere to go.
- **Scope:** `backend/app/services/knowledge_repository.py` additions only (`approve_row`, `retire_row`, an interim RBAC gate). Synthetic fixtures only in every test.
- **Out of scope:** Real clinical content, self-approval override mechanism, API routes, frontend, AI wiring, a dedicated Clinical Advisor role/table.
- **Schema/data changes:** None.
- **Migration:** None.
- **Security/clinical review gate:** Codex review rounds to 0 P0/P1 (this program's standing convention) + explicit PTH GO before merge — same two-step pattern as every prior slice.
- **Entry criteria:** This plan approved by PTH.
- **Exit criteria:** See §9.

### Phase 2 — K1-S2b: Calcium Ingredient Identity Fix

- **Objective:** Resolve the one named, concrete Phase B blocker in `MEDICATION_PHASE_A_BLOCKING_FINDINGS.md` — no `drug_ingredients` row exists for calcium (PTH ruling: no generic "Calcium" row; must be salt-specific).
- **Scope:** One data-only Alembic migration adding `calcium carbonate` and `calcium citrate` as distinct `drug_ingredients` rows (with their `drug_class_id`), following the exact idempotent-seed pattern already used by `k1_a1b_f2_specialty_seed.py`.
- **Out of scope:** Any knowledge content about calcium; any other new ingredient.
- **Schema/data changes:** 2 new rows in `drug_ingredients` (and possibly 1 new row in `drug_classes` if no existing mineral-supplement class fits — needs a Tech Lead check against the existing 41-drug catalog's class taxonomy before scoping the migration for real).
- **Migration strategy:** Idempotent `INSERT ... WHERE NOT EXISTS`, matching `k1_a1b_f2_specialty_seed.py`'s convention exactly. Downgrade deletes exactly those 2 rows by a specific filter, never a blanket delete.
- **Security/clinical review gate:** Low — this is identity/taxonomy data, not clinical content (no dosing, no side effects, no claims). Still requires the standing Codex-review-to-0-P0/P1 gate for any migration PR in this program.
- **Entry/exit:** Entry — none (fully independent of Phase 1). Exit — `provenance.resolve_medication_identity(db, "calcium carbonate")` and `"calcium citrate"` both resolve; existing 41-drug catalog identity resolution unaffected (regression test).
- Can run in parallel with Phase 1 — no shared files, no ordering dependency.

### Phase 3 — Knowledge Template Formalization (docs-only)

- **Objective:** Commit `MEDICATION_KNOWLEDGE_TEMPLATE_V1.md` to `main` (currently uncommitted, §0.3) and resolve its remaining "needs PTH confirmation" items (§9.1 "Emergency" tier rejection, §9.2 general-education-vs-interaction-engine framing, §9.3 closed `theme` vocabulary enforcement point).
- **Scope:** Documentation only. No code.
- **Out of scope:** Any code change implied by the resolutions (e.g., if PTH wants `theme` enforced as a DB CHECK instead of an authoring-tooling validator, that becomes its own future migration PR, not part of this phase).
- **Migration/rollback:** N/A (docs).
- **Gate:** PTH sign-off on the 3 open items; no Codex review needed (no code).
- Can run in parallel with Phases 1-2.

### Phase 4 — Phase B: Real Content Authoring (5-drug MVP)

- **Objective:** Author real clinical content (patient education, usage, side effects, monitoring, contraindications) for levothyroxine, metformin, aspirin, warfarin, calcium, through the already-merged A1b pipeline.
- **Scope:** Authoring files only (YAML/JSON per the input contract in `schema.py` + the Golden Page template from Phase 3), run through `import_batch()`. Lands in `draft`/`clinical_review` — per the docs, **not required to reach `approved`** even after Phase 1 ships, though PTH may choose to pilot a small number of rows through the real approval path once Phase 1 exists.
- **Out of scope:** API, frontend, AI wiring (K1 dormancy still holds until K2 gets its own GO).
- **Hard entry criteria (all must be true, none satisfied by this plan):** Phase 2 merged (calcium resolvable); Phase 3 merged (template is the spec-of-record); a real, named Clinical Advisor identity confirmed (OQ-7); ADR-10 Tier-1 sourcing confirmed usable without a licensing blocker (OQ-2/3/4); **explicit, separate PTH GO** — every doc that mentions Phase B says this is "a separate, later, PTH-gated decision," never inferred from an earlier GO.
- **Security/clinical review gate:** Highest of any phase in this roadmap — this is the first point real medical claims (even in draft state) enter the system. Recommend a Vietnamese-doctor spot-check of the first batch before it's considered a template for the rest, independent of whether it ever reaches `approved`.
- Not further specified in this document — it needs its own planning pass once its entry criteria are met, and explicitly is not authorized here.

### Phase 5 — K2: Knowledge API Exposure

- **Objective:** First wiring of a public/internal read endpoint (`GET /medications/{id}/knowledge`) that reads `status='approved'` rows only, per ADR-13's binding, non-overridable filter rule.
- **Scope:** New API route(s) + schema(s) reading via `knowledge_repository.list_published()` (already exists, already tested, currently unused by anything).
- **Out of scope:** Frontend consumption, AI wiring (still separate, later GOs per ADR-07/ADR-14's own gating).
- **Dependency:** Needs *some* `approved` rows to be meaningful in staging (Phase 1 + Phase 4, at least a pilot), though the endpoint itself could be built and tested against fixtures before real content exists — flagging this as a valid sequencing choice, not a hard blocker on Phase 4 completing first.
- **Migration:** None expected (pure read API over existing tables).
- **Security/clinical review gate:** Standard API review (auth, rate limiting, response shape) — the clinical-content gate was already paid at Phase 1/4.
- Its own separate K1 Exit Criteria (EC-08) explicitly requires this to be a distinct, later GO — not bundled with K1.

---

## 2.1 Recommended decision

**Build Phase 1 (K1.5 — Clinical Review & Approval Write Path) next.**

**Why this and not the alternatives:**

- **Vs. Phase 4 (Phase B real content):** Every doc that names "Phase B" is explicit that it is a separate, later, PTH-gated decision — never inferred from A1b merging. Phase B also has *unresolved business decisions* no plan can close by writing code: a real Clinical Advisor identity (OQ-7) and Tier-1 sourcing confirmation (ADR-10 OQ-2/3/4) are both still "Pending PTH." Starting Phase 4 next would mean either stalling mid-implementation on those same open questions, or authoring real content under a placeholder identity — exactly the "silently AI-assisted... ultimate responsibility sits with whoever authors Phase B content" risk `MEDICATION_PHASE_A_PR_A1_IMPLEMENTATION_PLAN.md:242` already warns about. K1.5 has no such external dependency: every column and table it needs already exists, and it can be fully built and tested against synthetic fixtures.
- **Vs. Phase 2 (Calcium fix):** Real, useful, and narrow — but it only unblocks one specific drug for a phase (Phase B) that isn't ready to start yet for the reasons above. It's a good parallel-track pick, not a better *primary* pick, since on its own it doesn't close any capability gap in the lifecycle model itself.
- **Vs. Phase 3 (Template formalization):** Pure documentation — valuable, cheap, but doesn't reduce engineering risk the way exercising the untested approve/deprecate/retire write path does.
- **The concrete, code-level reason:** `validate_transition()` already encodes the full ADR-13 rule set (self-approval block, specialty-completeness gate, illegal-transition rejection) and is unit-tested — but **zero code path in the entire repository ever calls it with a target of `'approved'` against a real row.** This is the single largest gap between "ADR-13 is Accepted" and "ADR-13 is actually enforced by running code." Building and hardening this now, against synthetic data, while nothing depends on it working correctly yet, is safer than building it later under the time pressure of real content already piling up in `clinical_review` with nowhere to go — a bottleneck the Knowledge Template itself already names as a known future constraint (§8: *"a Clinical Advisor's ability to review it before anything reaches `approved` is a human bottleneck this document cannot solve"*).

**Risk level:** Low. No migration, no schema change, no new external dependency, no real clinical content, no change to any existing dormant/wired boundary (still zero API/frontend/AI wiring after this slice ships). The main risk is entirely internal-design: the RBAC interim-role decision (§3.4) must be explicit and reviewable, not silently assumed.

**Migration:** None required.

**Real clinical content:** **Not permitted in this slice** — every test uses synthetic fixture data (the existing `_make_ingredient()`-style helpers already used throughout `test_knowledge_repository.py`), matching the "no real content" discipline every K1/A1a/A1b slice has held to.

---

## 3. K1.5 — exact scope

### 3.1 In scope

- `backend/app/services/knowledge_repository.py`: two new public functions (`approve_row`, `retire_row`), one new authorization helper (`assert_can_approve_knowledge`), one new internal helper (`_deprecate_superseded`), one new error class (`KnowledgeApprovalAuthorizationError`).
- `backend/tests/test_knowledge_repository.py`: new test classes covering the above (SQLite, via the existing `db` fixture).
- One new Postgres integration test file: `backend/tests/integration/test_medication_k1_5_approval_workflow_postgres.py` (concurrency + DB-level partial-unique-index backstop).
- A compliance review doc at `docs/medication-management/MEDICATION_K1_5_COMPLIANCE_REVIEW.md`, written after implementation, following this program's established post-merge pattern (see `MEDICATION_K1_S3_COMPLIANCE_REVIEW.md` for the template).

### 3.2 Explicitly out of scope

- Any new Alembic migration (no schema change is needed — see §3.3).
- The self-approval override mechanism ADR-13 describes for the single-advisor-per-specialty case (§1, last row) — flagged as a future, separately-scoped PR requiring its own PTH-approved design (likely a new nullable column pair, e.g. `approval_override_reason` / `approval_override_approved_by`).
- Any API route, frontend screen, or AI wiring (K1 dormancy discipline continues to hold — this is still a service-layer-only module).
- A dedicated `CLINICAL_ADVISOR` role or any change to `app/models/user.py`'s `UserRole` enum (§3.4 explains why).
- Real clinical content of any kind.
- Enforcing a minimum grace period between `deprecated` and `retired` (ADR-13 explicitly calls the exact period "a K1.5 operational decision, not architectural" — this plan treats it as a *process* convention for callers to observe, not a code-level constraint, since no PTH-specified duration exists to encode).
- Changing `test_zero_approved_rows_exist_anywhere` or any other existing test's behavior (verified: it operates on each test's own isolated, rolled-back transaction via the `db` fixture, so it is unaffected by this slice's new tests creating `approved` rows in their own separate test transactions).

### 3.3 Schema / data changes

**None.** Every column this slice needs already exists on all 5 knowledge tables via `KnowledgeLifecycleMixin` (`status`, `status_changed_at`, `status_changed_by`, `authored_by`) and on `knowledge_review_specialties`/`clinical_specialties` (both already populated with the 7-code seed from `k1_a1b_f2_specialty_seed.py`). This is confirmed by direct inspection of `backend/app/models/drug_knowledge_content.py` and `drug_knowledge_governance.py` — not assumed.

### 3.4 RBAC decision — must go through a single abstraction (PTH review, 2026-07-17)

No dedicated Clinical Advisor role exists yet (OQ-7/OQ-8 both "Pending PTH"). `MEDICAL_REVIEWER` is documented in `rbac.py:7` as strictly read-only platform-wide. This plan's default, implementable-without-guessing choice: gate `approve_row`/`retire_row` on `actor_role in {"internal_admin", "super_admin"}`. This is an interim policy default, not a technical inevitability — PTH may prefer a different interim role set later, and this is exactly why the check must live behind one abstraction rather than being reimplemented per caller.

**PTH's explicit requirement (2026-07-17 review):** the role check must be a named, reusable predicate — `can_approve_knowledge(actor_role) -> bool` — not an inline `if actor_role in {...}` scattered across `approve_row`/`retire_row`/any future caller. §4.1 implements this as two functions: `can_approve_knowledge()` (pure boolean predicate, the one place the interim role set is named) and `assert_can_approve_knowledge()` (raises `KnowledgeApprovalAuthorizationError` if the predicate fails — used inside the write paths). The predicate function exists separately from the assert wrapper so a future read-only caller (e.g. a K2+ API route deciding whether to render an "Approve" button) can query capability without triggering an exception. **When a real Clinical Advisor role is established (OQ-7), only `can_approve_knowledge`'s body changes — `approve_row`, `retire_row`, and every other caller are untouched.** This is the concrete acceptance test for "went through the abstraction correctly": grep for `actor_role` outside `can_approve_knowledge`'s own body should show zero direct role-set comparisons.

### 3.5 Non-negotiable invariants (PTH review, 2026-07-17)

Three invariants were already designed into §4.1's code in the original draft of this plan, but PTH's review correctly flagged that they must be stated explicitly as **non-negotiable, testable requirements** — not left implicit in a helper function's docstring — so an implementer cannot quietly weaken them under time pressure. All three must hold after this slice ships, verified by the specific tests named in §4.2:

1. **At most one `approved` row per business key, at any instant.** A new approval must deprecate the prior approved row for the same business key **in the same transaction** — never as a separate follow-up write, never eventually-consistent. This is enforced two ways, independently: (a) `approve_row`'s own logic (`_deprecate_superseded`, called before `db.commit()`, §4.1), and (b) the DB-level partial unique index (`uq_drug_usage_approved_key` etc., `postgresql_where="status = 'approved'"`, already shipped in K1-M01) as a backstop if (a) is ever bypassed or buggy. §4.3's `test_partial_unique_index_backstop_rejects_second_approved_row` exists specifically to prove backstop (b) independently of trusting (a).
2. **All approve/retire authorization routes through one predicate, `can_approve_knowledge()`.** No inline role comparison anywhere else in this module or any future caller (§3.4). This is a code-review-time invariant (grep-verifiable), not just a runtime one.
3. **The lifecycle is a strict DAG with no cycles or skips, and every illegal edge is explicitly tested, not just implicitly excluded by an allowlist.** In particular: `approved → approved` (re-approving an already-approved row) and `retired → approved` (resurrecting retired content) must both be rejected, with a named test proving each (§4.2, `TestApproveRow.test_rejects_double_approval` and `test_rejects_approval_of_retired_row`). `validate_transition`'s existing `_ALLOWED_TRANSITIONS` allowlist already rejects both cases correctly today (neither pair is a member of the set) — PTH's point is that this must be *proven by an explicit test naming the exact scenario*, not left as an unverified consequence of the allowlist's shape.

---

## 4. File-by-file changes

### 4.1 `backend/app/services/knowledge_repository.py`

Add, after the existing `submit_for_review` function and before `record_specialty_review` (keeping the file's existing top-to-bottom lifecycle ordering: create → submit → review-record → completeness-check → **approve/retire (new)** → list):

```python
# --- Interim RBAC gate (K1.5) -----------------------------------------
#
# No dedicated Clinical Advisor role exists yet (ADR-13 OQ-7/OQ-8 both
# "Pending PTH" per ARCHITECTURE_DECISION_INDEX.md). MEDICAL_REVIEWER is
# deliberately NOT used here: app/core/rbac.py documents it as
# "read-only — bypass read checks, blocked on writes elsewhere"
# (rbac.py:7) — reusing it for an approval WRITE would silently grant a
# capability that role was never audited for, platform-wide. This
# constant is the single place that decision lives; revisit it the
# moment a real Clinical Advisor role/identity is established (OQ-7).
_APPROVAL_CAPABLE_ROLES = frozenset({"internal_admin", "super_admin"})


class KnowledgeApprovalAuthorizationError(ValueError):
    """Raised when actor_role lacks approve/retire capability. Distinct
    from TransitionError (an illegal *state* transition) so a future API
    layer can map this to 403 and TransitionError to 409/400 separately."""


def can_approve_knowledge(actor_role: str) -> bool:
    """The ONE place the interim approval-capable role set is named
    (PTH review, 2026-07-17, non-negotiable invariant #2 — see
    MEDICATION_K1_5_APPROVAL_WORKFLOW_IMPLEMENTATION_PLAN.md §3.4/§3.5).
    No other function in this module, and no future caller (a K2+ API
    route, a script, anything), may inline its own
    `actor_role in {...}` comparison — always call this predicate (or
    assert_can_approve_knowledge below) instead. When a real Clinical
    Advisor role is established (ADR-13 OQ-7), only this function's body
    changes; approve_row/retire_row/every other caller stay untouched.

    A pure boolean predicate (not just the raising assert below) so a
    future read-only caller — e.g. an API route deciding whether to show
    an "Approve" button — can query capability without triggering an
    exception."""
    return actor_role in _APPROVAL_CAPABLE_ROLES


def assert_can_approve_knowledge(actor_role: str) -> None:
    if not can_approve_knowledge(actor_role):
        raise KnowledgeApprovalAuthorizationError(
            f"actor_role={actor_role!r} is not authorized to approve or "
            f"retire knowledge content. Allowed: {sorted(_APPROVAL_CAPABLE_ROLES)}."
        )


# --- Business-key lookup for auto-deprecation ---------------------------
#
# Mirrors medication_knowledge_import/versioning.py's _BUSINESS_KEY_FIELDS
# exactly (ADR-13 "Per-Table Business Key & Uniqueness Policy"). Kept as
# this module's own copy, same convention as KNOWLEDGE_TABLE_NAME above
# (the two files can't share a live import without a circular dependency;
# keep in sync by hand if either ever changes).
_BUSINESS_KEY_FIELDS: dict[type, tuple[str, ...]] = {
    DrugUsage: ("drug_ingredient_id", "locale", "audience"),
    DrugPatientEducation: ("drug_ingredient_id", "theme", "locale", "audience"),
    DrugSideEffect: ("drug_ingredient_id", "concept_code"),
    DrugMonitoring: ("drug_ingredient_id", "parameter", "patient_context"),
    DrugContraindication: ("drug_ingredient_id", "condition_type", "condition_key"),
}


def _deprecate_superseded(
    db: Session, row: KnowledgeModel, *, actor_user_id: str, now: dt.datetime
) -> int:
    """ADR-13: "approved -> deprecated: automatic when a newer approved
    row exists for the same business key — the old row is never deleted
    or edited." This is non-negotiable invariant #1 (PTH review,
    2026-07-17, plan §3.5): at most one approved row per business key at
    any instant. Must be called only from inside approve_row's own
    transaction (no independent commit here) so a crash between approving
    the new row and deprecating the old one is impossible — either both
    happen or neither does. The partial unique index on `status='approved'`
    is a second, independent backstop if this function is ever bypassed
    (verified directly by test_partial_unique_index_backstop_rejects_
    second_approved_row, plan §4.3 — the invariant is enforced twice, not
    trusted to one layer). Expected rowcount is 0 or 1 (the unique index
    caps live approved rows at 1 per business key); if it is ever >1
    (e.g. a pre-existing integrity violation), this still correctly
    deprecates all of them — fail-open here is safe, since deprecating
    extra approved rows only reduces exposure, never increases it."""
    model_cls = type(row)
    fields = _BUSINESS_KEY_FIELDS[model_cls]
    key_filters = [getattr(model_cls, f) == getattr(row, f) for f in fields]
    result = db.execute(
        update(model_cls)
        .where(model_cls.status == "approved", model_cls.id != row.id, *key_filters)
        .values(status="deprecated", status_changed_by=actor_user_id, status_changed_at=now)
    )
    return result.rowcount


def approve_row(
    db: Session,
    row: KnowledgeModel,
    *,
    actor_user_id: str,
    actor_role: str,
) -> KnowledgeModel:
    """clinical_review -> approved (ADR-13). Atomically approves this row
    AND deprecates any prior approved row sharing its business key, in one
    transaction — see _deprecate_superseded's docstring for why these must
    not be split across two commits.

    Specialty completeness is re-checked against the DB at write time
    (never trusts a caller-supplied bool) — the same reasoning as every
    other check in this module: a stale or spoofed value must not be able
    to force an approval.
    """
    assert_can_approve_knowledge(actor_role)
    specialty_complete = check_specialty_completeness(db, row)
    validate_transition(
        row.status,
        "approved",
        authored_by=row.authored_by,
        actor_user_id=actor_user_id,
        specialty_complete=specialty_complete,
    )
    model_cls = type(row)
    now = dt.datetime.now(dt.UTC)
    try:
        result = db.execute(
            update(model_cls)
            .where(model_cls.id == row.id, model_cls.status == "clinical_review")
            .values(status="approved", status_changed_by=actor_user_id, status_changed_at=now)
        )
        if result.rowcount != 1:
            raise TransitionError(
                f"Row {row.id!r} was not in 'clinical_review' status at commit "
                "time — another transition won the race. Re-fetch and re-check "
                "before retrying."
            )
        _deprecate_superseded(db, row, actor_user_id=actor_user_id, now=now)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return row


def retire_row(
    db: Session,
    row: KnowledgeModel,
    *,
    actor_user_id: str,
    actor_role: str,
) -> KnowledgeModel:
    """deprecated -> retired (ADR-13, manual). The exact grace period
    between deprecation and retirement is an operational/process decision,
    not a code constraint ("a K1.5 operational decision, not architectural"
    per ADR-13) — this function does not check how long the row has been
    deprecated; if PTH wants a minimum-wait policy enforced later, that is
    a follow-up change to this function, not assumed here.
    """
    assert_can_approve_knowledge(actor_role)
    validate_transition(
        row.status, "retired", authored_by=row.authored_by, actor_user_id=actor_user_id
    )
    model_cls = type(row)
    now = dt.datetime.now(dt.UTC)
    try:
        result = db.execute(
            update(model_cls)
            .where(model_cls.id == row.id, model_cls.status == "deprecated")
            .values(status="retired", status_changed_by=actor_user_id, status_changed_at=now)
        )
        if result.rowcount != 1:
            raise TransitionError(
                f"Row {row.id!r} was not in 'deprecated' status at commit time "
                "— another transition won the race. Re-fetch and re-check "
                "before retrying."
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return row
```

Note on `validate_transition`'s existing `_ALLOWED_TRANSITIONS` set (`{("draft","clinical_review"), ("clinical_review","approved"), ("approved","deprecated"), ("deprecated","retired")}`): **no change needed** — `retire_row`'s call with `("deprecated", "retired")` is already legal, and since `new_status != "approved"` in that call, the self-approval/specialty branch inside `validate_transition` is correctly skipped. Zero modifications to `validate_transition` itself.

### 4.2 `backend/tests/test_knowledge_repository.py`

Add two new test classes after the existing `TestSpecialtyCompleteness` class (keeping the file's existing grouping: creation → transitions → specialty checks → **approve/retire (new)** → rollback atomicity):

**`TestApproveRow`** (SQLite, `db` fixture):
1. `test_happy_path_approves_and_records_actor` — create draft → `submit_for_review` → `approve_row` with a different `actor_user_id` and an authorized `actor_role`, no `required_specialties` on the test ingredient's class (empty list trivially satisfies completeness per existing `check_specialty_completeness` behavior) → assert `status == "approved"`, `status_changed_by == actor_user_id`.
2. `test_rejects_self_approval_at_write_time` — same author and actor → expect `TransitionError` (not just the existing pure-function test — this proves the real write path enforces it too).
3. `test_rejects_incomplete_specialty_at_write_time` — ingredient's class has `required_specialties=["cardiology"]`, no `knowledge_review_specialties` row recorded → expect `TransitionError`.
4. `test_rejects_unauthorized_role` — valid actor, valid specialty completeness, `actor_role="patient"` → expect `KnowledgeApprovalAuthorizationError`, and assert the row's status is unchanged (still `clinical_review`) afterward.
5. `test_rejects_from_draft_status` — row still in `draft` (never submitted) → expect `TransitionError` (illegal transition, matches existing `test_draft_to_approved_directly_rejected` but through the real write path).
6. `test_auto_deprecates_prior_approved_row_same_business_key` — approve one `DrugUsage` row for `(ingredient, "vi", "patient")`, then create + submit + approve a **second** row for the exact same business key → assert the first row is now `status="deprecated"` with its own `status_changed_by`/`status_changed_at` updated, and the second row is `status="approved"`.
7. `test_concurrent_approve_only_one_wins` — mirrors `test_concurrent_submit_for_review_only_one_wins` exactly (two `SessionLocal()` sessions, both read the row while `clinical_review`, both attempt `approve_row`) — one succeeds, one raises `TransitionError`.
8. `test_rejects_double_approval` — **non-negotiable invariant #3 (§3.5).** Approve a row once (reaches `approved`), then call `approve_row` on it a second time → expect `TransitionError` (`("approved","approved")` is not in `_ALLOWED_TRANSITIONS`), and assert the row's `status_changed_at` is unchanged from the first approval (proves the second call had zero effect, not just that it raised).
9. `test_rejects_approval_of_retired_row` — **non-negotiable invariant #3 (§3.5).** Build a row through to `retired` (draft → clinical_review → approved → deprecated via a superseding approval → retired via `retire_row`), then call `approve_row` on the retired row → expect `TransitionError` (`("retired","approved")` is not in `_ALLOWED_TRANSITIONS`) — retired content can never be resurrected directly to `approved`; the only way old content becomes current again is authoring a brand-new draft and taking it through the full lifecycle from the top.

**`TestRetireRow`** (SQLite, `db` fixture):
1. `test_happy_path_retires_deprecated_row` — build a row already at `deprecated` (via the approve-then-superseding-approve pattern from `TestApproveRow.test_auto_deprecates...`, or directly via `build_draft`+manual status set in the test's own fixture setup — implementer's choice, whichever is less test-fixture code) → `retire_row` → assert `status == "retired"`.
2. `test_rejects_from_non_deprecated_status` — attempt `retire_row` on a `draft`/`clinical_review`/`approved` row → expect `TransitionError` for each (parametrized).
3. `test_rejects_unauthorized_role` — same pattern as approve.

### 4.3 New file: `backend/tests/integration/test_medication_k1_5_approval_workflow_postgres.py`

Follow the existing real-Postgres integration test convention (see `backend/tests/integration/test_medication_a1b_orchestrator_postgres.py` for the fixture/connection pattern already established in this repo).

1. `test_concurrent_approve_race_under_real_postgres_isolation` — same shape as the SQLite concurrency test, but against a real Postgres connection, to prove the atomic `UPDATE ... WHERE status = 'clinical_review'` pattern holds under Postgres's actual transaction isolation semantics, not just SQLite's (the existing `test_concurrent_submit_for_review_only_one_wins` runs wherever `SessionLocal()` points, which may be SQLite in unit-test config — this test makes the Postgres case explicit and unambiguous).
2. `test_partial_unique_index_backstop_rejects_second_approved_row` — bypass the service layer entirely: directly `INSERT` a second row with `status='approved'` for a business key that already has one approved row → expect a Postgres `IntegrityError` from the partial unique index (`uq_drug_usage_approved_key` or equivalent, `postgresql_where=text("status = 'approved'")`). This proves the DB-level backstop actually works, independent of trusting the service-layer code to be bug-free — the same "two independent enforcement layers" philosophy ADR-13 itself specifies for the approved-invariants CHECK constraint.

### 4.4 New file: `docs/medication-management/MEDICATION_K1_5_COMPLIANCE_REVIEW.md`

Written **after** implementation, following the exact structure of `MEDICATION_K1_S3_COMPLIANCE_REVIEW.md` (the most directly comparable prior slice — also service-layer-only, no migration, no API wiring). Must document: which of this plan's invariants were verified, what changed (if anything) during Codex review rounds, and explicit confirmation that `test_zero_approved_rows_exist_anywhere` still passes unmodified.

---

## 5. Transaction ownership

- `approve_row` and `retire_row` each own their own transaction end-to-end, identical in shape to the existing `submit_for_review`/`record_specialty_review`/`create_draft` convention in this module: single-row operation, caller passes an already-open `Session`, the function itself calls `db.commit()` (success) or `db.rollback()` (any failure) and never leaves the session mid-transaction either way.
- `approve_row` specifically owns **two** UPDATE statements (the approval itself + `_deprecate_superseded`) inside **one** transaction — this is the one place this slice's transaction scope is wider than the existing single-statement pattern, and it's the reason the whole body is wrapped in one `try/except Exception: db.rollback(); raise` rather than only wrapping the final `db.commit()` the way `submit_for_review` does — a failure in the second UPDATE must not leave the first one committed.
- Neither function is ever called from inside `orchestrator.import_batch`'s own transaction (the orchestrator only ever calls `build_draft`/`add_draft`, never these) — the two call graphs (batch import vs. individual review actions) stay fully separate, matching the orchestrator's own documented invariant ("no file under `medication_knowledge_import/` may be imported by anything under `backend/app/api/`... " — this slice lives in `knowledge_repository.py`, not that package, and does not change that boundary).

---

## 6. State transitions (complete picture after this slice)

| Transition | Write path | Guard | Atomic? |
|---|---|---|---|
| `draft → clinical_review` | `submit_for_review` (existing) | any authenticated author | Yes (`UPDATE...WHERE status='draft'`) |
| `clinical_review → approved` | `approve_row` (**new**) | role check + self-approval block + specialty completeness | Yes (`UPDATE...WHERE status='clinical_review'`) |
| `approved → deprecated` (automatic) | `_deprecate_superseded`, called only from inside `approve_row` (**new**) | none beyond business-key match — this is a system-driven side effect, not an independently authorized action | Yes, same transaction as the triggering approval |
| `deprecated → retired` | `retire_row` (**new**) | role check only (no specialty/self-approval — those only gate the approval step) | Yes (`UPDATE...WHERE status='deprecated'`) |
| Any other pair | Rejected | `validate_transition`'s `_ALLOWED_TRANSITIONS` allowlist (unchanged) | N/A — never reaches a DB statement |

No standalone "deprecate an approved row without replacing it" path exists after this slice, matching ADR-13's own wording exactly (deprecation is described only as automatic-on-supersession, never as an independent action).

---

## 7. Error taxonomy

| Error | Raised by | Meaning | Suggested future HTTP mapping (K2+, not built here) |
|---|---|---|---|
| `TransitionError` (existing, `ValueError` subclass) | `validate_transition`, `submit_for_review`, `approve_row`, `retire_row` | Illegal state transition, self-approval, incomplete specialty review, or a lost optimistic-concurrency race | 409 Conflict (state) or 400 (illegal transition) |
| `KnowledgeApprovalAuthorizationError` (**new**, `ValueError` subclass) | `assert_can_approve_knowledge` | Actor's role lacks approve/retire capability | 403 Forbidden |
| (unchanged) `LegacyArtifactHashUnavailableError` | `versioning.known_versions_for` | Not touched by this slice — listed for completeness since it's in the same domain | N/A |

Two distinct exception types (not one) so a future API layer (K2+) can map authorization failures to 403 and state-machine failures to 409/400 without string-matching error messages.

---

## 8. Idempotency & concurrency

- **Idempotency:** Neither `approve_row` nor `retire_row` is idempotent by design intent, but both **fail safely on repeat calls** — calling `approve_row` twice on an already-approved row hits `validate_transition`'s illegal-transition check (`("approved","approved")` is not in `_ALLOWED_TRANSITIONS`) before any DB statement runs. Same for `retire_row` on an already-retired row.
- **Concurrency:** Both functions use the same atomic `UPDATE ... WHERE id = ... AND status = '<expected>'` pattern already proven in `submit_for_review` (and its existing concurrency test) — a losing concurrent caller gets `rowcount != 1` and raises `TransitionError`, never silently no-ops or double-applies.
- **Cross-batch concurrency (two orchestrator imports running at once):** Explicitly out of scope for this slice (§1 gap analysis notes this as a low-severity, untested gap in the *existing* A1b code, not something K1.5 introduces or is responsible for fixing).

---

## 9. Test matrix, CI gates, migration/rollback, merge policy

### 9.1 Test matrix

| Layer | File | New tests | DB |
|---|---|---|---|
| Unit | `backend/tests/test_knowledge_repository.py` | `TestApproveRow` (7 cases), `TestRetireRow` (3 cases) | SQLite (`db` fixture) |
| Integration | `backend/tests/integration/test_medication_k1_5_approval_workflow_postgres.py` (**new**) | Concurrent-approve race under real Postgres isolation; DB-level partial-unique-index backstop | Real PostgreSQL (matches this repo's existing integration-test convention, e.g. `test_medication_a1b_orchestrator_postgres.py`) |
| Regression | `backend/tests/test_medication_knowledge_import_orchestrator.py` | None changed — `test_zero_approved_rows_exist_anywhere` verified to still pass unmodified (§3.2) | Both (existing parametrization) |

### 9.2 Migration strategy

**No migration in this slice.** All required columns/tables pre-exist (§3.3). The Alembic head remains `k1_a1b_artifact_hash` after this PR merges.

### 9.3 Rollback strategy

- **Code rollback:** Revert the PR. Since no migration exists, there is nothing to downgrade — a plain `git revert` fully removes the capability with zero data-layer cleanup needed.
- **If `approve_row` is ever called against real content in a later phase and produces a wrong approval:** the row is never deleted or edited (ADR-13 append-only) — correction means authoring a new version and running it through `approve_row` again, which automatically deprecates the wrong one via `_deprecate_superseded`. This is the same correction model every other knowledge-content mistake in this system already uses; this slice doesn't need a special-case "undo approval" function.

### 9.4 CI gates / Codex review gates

Matches this program's standing convention (every K1/A1a/A1b slice): Codex review rounds until 0 unresolved P0/P1 findings; full backend suite green (unit + Postgres integration); single Alembic head confirmed (trivially true — no migration added); explicit PTH GO recorded before merge to `main`.

### 9.5 Merge/deploy policy

Same as every prior K1/A1a/A1b slice: PR merges to `main` only after Codex + PTH sign-off; no direct deploy action implied by merging (this module has no API/frontend/AI consumer, so a merge is inert in production until some future phase wires a consumer — matching K1's dormancy discipline, which this slice fully preserves).

### 9.6 Entry criteria

- This plan document approved by PTH (explicit GO, per this program's two-step planning/implementation pattern).

### 9.7 Exit criteria

- [ ] `approve_row`, `retire_row`, `can_approve_knowledge`, `assert_can_approve_knowledge`, `_deprecate_superseded` implemented exactly as specified in §4.1 (or with any deviation documented and justified in the compliance review).
- [ ] All tests in §4.2/§4.3 passing, SQLite and Postgres — including the 3 non-negotiable-invariant tests added per PTH's 2026-07-17 review: `test_auto_deprecates_prior_approved_row_same_business_key` + `test_partial_unique_index_backstop_rejects_second_approved_row` (invariant #1), `test_rejects_double_approval` + `test_rejects_approval_of_retired_row` (invariant #3).
- [ ] `grep -n "actor_role" backend/app/services/knowledge_repository.py` shows role-set comparisons only inside `can_approve_knowledge`'s own body (invariant #2, §3.4/§3.5) — no inline `actor_role in {...}` anywhere else in the file.
- [ ] `test_zero_approved_rows_exist_anywhere` (5 parametrized cases) still passes unmodified.
- [ ] No new Alembic revision created; head remains `k1_a1b_artifact_hash`.
- [ ] `grep` confirms zero API/frontend/AI imports of `knowledge_repository` (dormancy preserved).
- [ ] `MEDICATION_K1_5_COMPLIANCE_REVIEW.md` written and merged alongside the code.
- [ ] Codex review: 0 unresolved P0/P1.
- [ ] PTH final sign-off recorded (including explicit confirmation of the `_APPROVAL_CAPABLE_ROLES` interim choice, §3.4 — this is a real policy decision this plan defaults but does not unilaterally finalize).

---

## 10. Explicit restatement of scope

This document plans a service-layer write path. It does not:

- Write any migration.
- Author any real drug content.
- Add or change any RBAC role in `app/models/user.py`.
- Build the self-approval override mechanism ADR-13 describes for the single-advisor case.
- Wire anything to an API, frontend, or AI system.
- Authorize starting Phase 2, 3, 4, or 5 above. Each needs its own explicit GO, per this program's existing governance pattern.
- Authorize its own implementation. That is a separate PTH decision this document requests, not assumes.
