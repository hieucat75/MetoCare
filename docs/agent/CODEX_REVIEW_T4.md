# T4 Code Review — RBAC / Consent / AI Safety / Medical Governance
> Reviewer: Claude Code (claude-opus-4-5) · Date: 2026-06-17 14:00 GMT+7
> Branch: feature/t4-medical-domain (commit 195ffde)
> Mode: READ-ONLY review — no source files modified
> Verdict: **APPROVED_WITH_CONDITIONS**

---

## Scope note

This branch implements models + two write-side services + migration files. API endpoints and
read-path RBAC are explicitly deferred to T5 (per the Antigravity report). Reviewed the four
mandated areas against that scope. Tests pass on SQLite via `create_all`, **not** via the migration
chain — so migration correctness is unverified by the suite.

---

## 1. RBAC — MEDICAL_SAFETY_PACKAGE §1.5 invariants

| Invariant | Status | Evidence |
|---|---|---|
| **Inv.1** AI creates rec only `pending_review`/`safety_cleared=False`; else hard-block + audit | ⚠️ **NOT STRUCTURALLY ENFORCED** | No recommendation-creation factory/guard. `AIClinicalRecommendation(...)` is constructed freely via the ORM with no validator, DB CHECK, or service gate. `submit_for_review` only *flips an existing row* to `pending_review`; it does not gate creation. The "any other status → hard-block + AuditLog(deny, high)" requirement is absent. |
| **Inv.2** AI_SERVICE uses same ConsentGuard, no bypass | ✅ **HOLDS** | `consent_guard.py:62-70` — self-access branch skipped for `actor_type=="ai_service"`, so AI always requires explicit consent. Verified by integration test. |
| **Inv.3** CLINIC_ADMIN / INTERNAL_ADMIN never see clinical body | ❌ **UNIMPLEMENTED** | No read services/endpoints exist; no field-level RBAC projection. Cannot be enforced or tested in T4. Deferred to T5. |
| **Inv.4** SUPER_ADMIN cannot review/accept | ✅ **HOLDS (service layer)** | `review()` hard-blocks any non-DOCTOR actor (`doctor_review.py:93`). |
| **Inv.5** Every DENY writes AuditLog(deny) | ✅ **HOLDS** for implemented paths | ConsentGuard deny (`:100`, severity=warning); review deny (`:94`, warning); submit deny (`:46`, severity=high). |

**CarePlan hard-block:** ❌ **UNIMPLEMENTED.** `CarePlan` is a bare model with free-text `String(32)` status, no status machine, no service, no guard. Safe only because no write path exists. Must be fixed before T5.

---

## 2. Consent — ConsentGuard

**Correct for what it covers:**
- AI cannot self-bypass (`:63`); only explicit `granted_to==actor_id` consent passes.
- `Consent.is_active` checks revoked/from/until/scope. All four negative cases tested.
- `CONSENT_GATE` flag: default True, fail-closed on unknown.

**Production foot-gun:** `FEATURE_CONSENT_GATE=false` silently disables all PHI consent enforcement. Should be guarded against production (refuse to start, or env-allowlist).

**B3 / `ai_use`:** ⚠️ Vacuously satisfied. M1 adds no DDL — `consent_type` is `String(48)` with no CHECK. No allowed-value validation anywhere. A typo'd `consent_type` silently never matches. Functional for now; flag for T5.

**Not yet wired:** Guard is standalone; no model/endpoint calls it. Enforcement reach is zero until T5 — acceptable for scope.

---

## 3. AI Safety — feature flags

**PTH conditions 1 & 5:** ⚠️ **Vacuously satisfied — flags are inert.** `AI_TRIAGE`, `AI_LAB_INTERPRET`, `AI_CARE_PLAN_DRAFT`, `AI_SAFETY_LAYER` are referenced **nowhere** outside their definition. `is_enabled()` is only consulted for `CONSENT_GATE` and `DOCTOR_REVIEW_GATE`. The existing `triage.py`/`guardrails` code does NOT check these flags. When AI features land in T5, nothing currently forces them behind these gates.

**Can AI write diagnosis/prescription/approved careplan?** Today: no such path exists. Structurally: the L2 capability deny-list is NOT implemented — `PROHIBITED_ACTIONS` in `policies.py` is data only; no enforcement engine blocks Medication/CarePlan/diagnosis writes by `actor_type`. Defense is currently "absence of a code path," not a structural block.

Flag defaults, fail-closed, and env override: correctly implemented and tested.

---

## 4. Medical Governance — AIClinicalRecommendation status machine

- `RecommendationStatus` enum: correct.
- `review()` enforces transitions only from `PENDING_REVIEW` → `ValueError` otherwise. ✅
- `accept` → `ACCEPTED + safety_cleared=True` + supersede of prior accepted same-type/patient. ✅
- `reject` → `REJECTED, safety_cleared=False`. ✅
- **Can AI set ACCEPTED via services?** No (submit forces pending_review; review is doctor-gated). ✅
- **Can AI set ACCEPTED via direct ORM?** Yes — no constraint prevents `AIClinicalRecommendation(status=ACCEPTED, safety_cleared=True)`. Same root gap as Inv.1.
- **Can admin approve?** Via services: no (role-gated to DOCTOR). ✅
- **Deviation:** `REVIEWED` state is dead — `pending_review` jumps straight to `accepted/rejected`. The MEDICAL_REVIEWER "review queue (not accept)" capability is not implemented. Minor, but narrower than safety package §1.4.

---

## Migration Defects (real, Postgres-affecting)

### 🔴 BLOCKING — FK ordering bug in M2

M2 (`down_revision=t4_m1`) creates `fk_ai_sessions_encounter_id → encounters`, but `encounters`
is created in M4 (`down_revision=t4_m3`), which runs *after* M2. On Postgres this FK creation
**will fail** (table absent). It only "passes" because it's skipped on SQLite. The Antigravity
report's risk #2 mischaracterizes this as safe "if all four run together" — Alembic runs
sequentially, so M2 fails regardless.

**Fix required:** Move the `encounter_id` FK creation from M2 to a step that runs after M4, or
reorder the migration chain.

### ⚠️ WARNING — `UserRole.AI_SERVICE` enum constraint

`User.role` uses `Enum(UserRole, native_enum=False)` → CHECK-constrained VARCHAR. No migration
alters the constraint to admit `ai_service`. On Postgres, inserting an AI_SERVICE user will
violate the existing CHECK constraint.

---

## Verdict: APPROVED_WITH_CONDITIONS

The implemented pieces — `ConsentGuard`, `DoctorReviewService`, recommendation status enforcement
in `review()`, soft-delete mixin, config-driven thresholds, and flag defaults — are **correct and
well-tested** for a models-plus-write-services branch. No PTH hard constraint is *violated* (the
AI write paths that could violate them don't exist yet). Mergeable to the feature branch as a
foundation, **but the following must be closed before any AI write path ships or any Postgres
migration runs.**

---

## Conditions before T5 / AI write path

| # | Item | Priority |
|---|---|---|
| **C1** | Recommendation creation guard — factory/service/validator so AI_SERVICE can only create `status=pending_review, safety_cleared=False`; else hard-block + AuditLog(deny, high) | **BLOCKING** |
| **C2** | CarePlan governance — status machine + AI guard (ai_generated=True, force PENDING_REVIEW, block DRAFT→ACTIVE and AI-set APPROVED/ACTIVE) | **BLOCKING** |
| **C3** | Wire the 4 AI feature flags — `AI_TRIAGE/LAB_INTERPRET/CARE_PLAN_DRAFT/SAFETY_LAYER` must be checked in the actual AI execution path and L2 capability deny-list | **BLOCKING** |
| **C4** | Read-path RBAC — Inv.3 (admins see metadata only) and patient `pending_review` non-visibility must be implemented when read endpoints land in T5 | **BLOCKING for T5** |

## Conditions before any Postgres migration run

| # | Item | Priority |
|---|---|---|
| **C5** | Fix M2→M4 FK ordering bug — move `encounter_id` FK to after M4 or reorder chain | **BLOCKING** |
| **C6** | Add `ai_service` to `users.role` CHECK constraint via migration | **BLOCKING** |

## Recommended (non-blocking)

| # | Item |
|---|---|
| **R1** | Guard `FEATURE_CONSENT_GATE=false` against production (silently disables all PHI consent enforcement) |
| **R2** | Add allowed-value validation for `Consent.consent_type` (B3 currently satisfied vacuously) |
| **R3** | Restore/document the `REVIEWED` state and MEDICAL_REVIEWER review-queue, or formally drop from §1.4 |
| **R4** | Add contract test asserting `clinical_thresholds.yml` symptom keys match `triage.py` (report risk #4) |

---

*End of CODEX_REVIEW_T4.md — Claude Code, 2026-06-17 14:00 GMT+7*
*No source files modified. Awaiting PTH approval to proceed with C1-C6 fixes.*
