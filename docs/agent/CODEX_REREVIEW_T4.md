# T4 P0 Re-Review — C1 / C2 / C5 / C6
> Reviewer: Claude Code (claude-opus-4-8) · Date: 2026-06-17 · Branch: feature/t4-medical-domain (commit fb12a47)
> Mode: READ-ONLY re-review of P0 fixes. No source modified.

=== CODEX_REREVIEW_T4_START ===
## T4 P0 Re-Review

### C5 FK Ordering: PARTIAL — one BLOCKING gap remains
The three enumerated fixes are correct, but an identical FK-ordering bug was **not** fixed in M3.

Verified chain (linear, no branches):
`a1b2c3d4e5f6 → t4_m0_role → m1 → m2 → m3 → m4 (encounters) → m4b (enc FK) → m5 → … → m9`

- ✅ M4b `down_revision = t4_m4_add_encs` — runs after `encounters` is created. Correct.
- ✅ M5 `down_revision = t4_m4b_enc_fk`. Correct.
- ✅ M2 no longer creates the `encounter_id` FK — adds the column + index only; encounter FK deferred to M4b. Correct. Downgrade order (M4b drops FK before M2 drops the column) is sound.
- ✅ M0 `userrole` constraint name confirmed against the initial schema (`name='userrole'`, `native_enum=False`).

**🔴 REMAINING FK ORDERING RISK (BLOCKING for Postgres):**
`t4_m3_add_recs` creates `ai_clinical_recommendations` with an inline
`sa.ForeignKeyConstraint(['encounter_id'], ['encounters.id'], name='fk_clinical_recs_encounter_id')`
(M3 line 44). M3 runs **before** M4, which is the only migration that creates `encounters`.
On Postgres, `CREATE TABLE ai_clinical_recommendations` will fail (referenced table absent) —
the exact failure mode C5 was raised to fix. It only "passes" on SQLite because SQLite does not
validate the referenced table at table-creation time (and FK enforcement is off by default), so
the suite's SQLite roundtrip does not catch it.

`test_migration_chain_order` checks only down_revision wiring; it does not detect this because the
FK is inside the table-create DDL, not a separate `create_foreign_key` step.

**Fix:** remove the `encounters` FK from M3's `create_table` and add it (like the ai_sessions FK)
in a post-M4 step — either extend M4b to also add `fk_clinical_recs_encounter_id`, or add an M4c.
Until then the Postgres migration chain is broken at M3.

### C6 ai_service Constraint: PARTIAL
Logic is correct for the common incremental-deploy path; the discovery mechanism is fragile.

- ✅ Adds `AI_SERVICE` to the recreated CHECK (`_NEW_ROLES`), correct VALUES list, correct
  `sa.column('role').in_(...)` predicate. Constraint name `'userrole'` matches the initial schema.
- ✅ SQLite is correctly a no-op (VARCHAR, no CHECK).
- ✅ Downgrade rediscovers the current name, drops, recreates with `_OLD_ROLES`. Symmetric.
- ✅ "Constraint not found" is handled (skips the drop).

**⚠️ Concerns (should fix before relying on a from-base Postgres run):**
1. **Separate connection for discovery.** `with bind.connect() as conn:` opens a *new* connection
   scope rather than using the migration's own connection. Two problems:
   (a) The project pins `SQLAlchemy>=2.0`; in 2.0 "branched" connections were removed, so
   `Connection.connect()` is not the safe shared-DBAPI call it was in 1.4 — behavior is
   version-dependent.
   (b) On a fresh DB, `alembic upgrade head` from base runs all migrations in **one transaction**
   (Alembic default). The `users.role` CHECK is created by the initial-schema migration earlier in
   that same uncommitted transaction. A separate/pooled connection will not see uncommitted DDL →
   `_get_constraint_name()` returns `None` → the drop is skipped → `create_check_constraint('userrole')`
   then collides with the still-present (but invisible) `userrole` constraint →
   "constraint already exists". The incremental path (DB already at `a1b2c3d4e5f6`, constraint
   committed) works fine, which is why this is latent.
   **Fix:** query via `op.get_bind()` (the active migration connection), not a new `bind.connect()`.
2. **Name-only discovery.** Discovery matches a hardcoded 2-name set (`userrole`, `users_role_check`)
   instead of inspecting which CHECK references `role`. If a future SA version emits a different
   auto-name, the old constraint is silently left in place and AI_SERVICE inserts still fail.
3. Unverified by CI: SQLite skips M0; the Postgres migration test is `skipif` unless
   `MCP_TEST_POSTGRES_URL` is set, so neither path exercises M0 against real Postgres.

### C1 Recommendation Creation Guard: PASS
The guard is structural at the ORM layer and the service path is correct.

- ✅ `@validates("status")` fires on **every** attribute assignment, not just `__init__`.
  Post-construction `rec.status = "accepted"` raises `ValueError` — cannot bypass after construction.
- ✅ Forbidden set `{accepted, reviewed, superseded}` is enforced **unconditionally** (no dependence
  on any other attribute), so there is no ordering/race bypass. `pending_review`/`rejected`/`None`
  allowed at construction, as intended.
- ✅ `@validates("safety_cleared")` rejects `True` at any assignment time. `safety_cleared=True`
  is genuinely blocked at the model layer.
- ✅ `DoctorReviewService.review()` sets `ACCEPTED`/`safety_cleared=True` via Core `update()`
  (SQL UPDATE), not ORM attribute assignment — correctly bypasses the validator. Supersede of prior
  accepted recs also uses `update()`. Confirmed in `doctor_review.py:135-161`.
- ✅ `create_from_ai()` hardcodes `status=PENDING_REVIEW, safety_cleared=False`; accepts no status param.
- ✅ Tests assert the right things and the messages line up (StrEnum formats to its value, so
  `match="cannot be set to 'accepted'"` matches). `test_doctor_review_service_can_set_accepted`
  is a real end-to-end check of the SQL-UPDATE path.

Residual (acceptable, inherent to `@validates`): Core/bulk inserts (`bulk_insert_mappings`, raw
`insert()`) bypass validators. Only a DB CHECK would be fully insert-proof, but a validator is what
C1 asked for and AI write paths go through the ORM/factory. Note it for defense-in-depth.

### C2 CarePlan Status Machine: PARTIAL
Factory is correct; the validator is order-dependent and bypassable — weaker than C1.

- ✅ `create_from_ai()` passes `ai_generated=True` **before** `status=DRAFT` and hardcodes both —
  correct, and DRAFT is allowed anyway, so the factory is safe regardless of ordering.
- ✅ Doctor/human path (`ai_generated=False`) may use any status (`test_doctor_careplan_can_have_any_status`).
- ⚠️ **The guard depends on attribute init order.** `_validate_status` only blocks forbidden states
  `if getattr(self, "ai_generated", False)`. SQLAlchemy's declarative `__init__` applies `**kwargs`
  via `setattr` in **caller-supplied order**. So:
  - `CarePlan(ai_generated=True, status="ACTIVE", …)` → blocked ✅ (the tests use this order).
  - `CarePlan(status="ACTIVE", ai_generated=True, …)` → **NOT blocked** ❌. When `status` is set,
    `ai_generated` is not yet assigned, `getattr(..., False)` is False, so `ACTIVE` is accepted; then
    `ai_generated` becomes True. Result: an AI-generated CarePlan with `status=ACTIVE`, guard bypassed.
- ⚠️ Post-construction: `plan.ai_generated = True; plan.status = "ACTIVE"` **is** blocked (validator
  re-fires on the status set with ai_generated now True) ✅. But `CarePlan(...); plan.status="ACTIVE"`
  while `ai_generated` stays default-False is allowed (treated as human plan) — only the AI flag matters.
- ✅ `create_from_ai()` itself correctly enforces DRAFT + ai_generated=True.

Contrast with C1, which is unconditional and therefore robust. **Fix:** make the guard
order-independent — either set `ai_generated` first inside a custom `__init__`, or, more robustly,
re-validate on the `ai_generated` setter too (add `@validates("ai_generated")` that rejects a flip to
True when `status` is already a forbidden value), or enforce via a DB CHECK. As written, only the
sanctioned factory path is safe; ad-hoc construction can bypass it.

## Verdict: BLOCKED
The C1 fix is solid. But two conditions are not closed and one is a hard Postgres blocker:

| # | Condition | Severity |
|---|---|---|
| **C5-bis** | `t4_m3_add_recs` still creates `ai_clinical_recommendations` with an inline FK to `encounters.id` before `encounters` exists (created in M4). Move this FK to a post-M4 step (extend M4b or add M4c). **The Postgres migration chain fails at M3 until fixed.** | **BLOCKING** |
| **C6-hardening** | Use `op.get_bind()` (active migration connection) for constraint discovery instead of a fresh `bind.connect()`, so a from-base single-transaction `upgrade head` sees the uncommitted `userrole` constraint and avoids a duplicate-constraint error on Postgres. | **BLOCKING for from-base PG run** |
| **C2-hardening** | Make the CarePlan status guard order-independent (it is bypassable via `CarePlan(status=..., ai_generated=True)` kwarg ordering). | **Should-fix** |

C1: closed. C5: not closed (equivalent bug migrated to M3). C6: works incrementally but fragile from base. C2: factory safe, guard weak.

**Recommendation:** add a contract test that runs the full chain against real Postgres (or at least
asserts no `create_table`/`ForeignKeyConstraint` references a table created in a later revision) so
C5-class bugs cannot pass on SQLite again.
=== CODEX_REREVIEW_T4_END ===

*End of CODEX_REREVIEW_T4.md — Claude Code, 2026-06-17. No source files modified.*
