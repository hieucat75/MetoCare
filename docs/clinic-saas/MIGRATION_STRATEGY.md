# MetoCare Clinic SaaS — Phase C0 Migration Strategy

Author: Agent D. Companion to `DATA_MODEL.md`. **No migration files are
created by this document** — this is the plan for review; actual Alembic
files are a separate, later step pending sign-off.

## 1. Current head (confirmed, not assumed)

```
$ cd backend && source .venv/bin/activate && alembic heads
t13_p0_note_draft_status (head)
```

Single head confirmed — no merge migration needed before starting. All new
revisions below chain linearly onto `t13_p0_note_draft_status`; this batch
introduces **no branching** (no two migrations share the same
`down_revision`), so the repo's single-head discipline
(`CURRENT_ARCHITECTURE_AUDIT.md` §14, precedent: `t12_merge_p0_m1_heads.py`)
is preserved automatically — no merge migration required at the end of this
batch.

Naming convention followed (per `REUSE_AND_GAP_MATRIX.md` "Alembic migration
conventions" row, confirmed by reading `t13_p0_note_draft_status.py` and
`t27_unique_patient_profile_user_id.py`): explicit
`revision`/`down_revision`/`branch_labels`/`depends_on` header, both
`upgrade()`/`downgrade()` always present. New revision ids use the prefix
`c0_mN_` ("Clinic SaaS Phase C0, migration N") — parallel to the existing
`t4_m7_...`/`t12_m1_...` ticket-track convention, since this is a new
bounded-context track rather than a numbered ticket. **Every revision id
below is ≤ 32 characters** (checked explicitly — see table — because of the
PR #93 `alembic_version varchar(32)` incident).

## 2. Ordered migration sequence

| # | Filename | Revision id (len) | down_revision | What it does |
|---|---|---|---|---|
| 1 | `c0_m1_clinic_extend_columns.py` | `c0_m1_clinic_extend_columns` (28) | `t13_p0_note_draft_status` | ALTER `clinics`: add `legal_name`, `tax_code`, `license_no`, `clinic_type`, `status` (NOT NULL, `server_default='trial'`), `branding`, `cancellation_policy`, `queue_config`, `overbooking_policy` (all `JSON`, nullable), `deactivated_at`, `restored_at` (nullable `DateTime`) |
| 2 | `c0_m2_clinic_branches.py` | `c0_m2_clinic_branches` (22) | `c0_m1_clinic_extend_columns` | CREATE TABLE `clinic_branches` + unique `(clinic_id, name)` + index `(clinic_id, status)` |
| 3 | `c0_m3_clinic_membership.py` | `c0_m3_clinic_membership` (24) | `c0_m2_clinic_branches` | CREATE TABLE `clinic_memberships` + unique `(user_id, clinic_id)` + indexes `(clinic_id, status)`, `(user_id, status)` |
| 4 | `c0_m4_clinic_invitation.py` | `c0_m4_clinic_invitation` (24) | `c0_m3_clinic_membership` | CREATE TABLE `clinic_invitations` + unique `token_hash` + CHECK (email or phone) + partial unique `(clinic_id, invited_email)` WHERE `status='pending'` + partial unique `(clinic_id, invited_phone)` WHERE `status='pending'` |
| 5 | `c0_m5_clinic_service.py` | `c0_m5_clinic_service` (21) | `c0_m4_clinic_invitation` | CREATE TABLE `clinic_services` + index `(clinic_id, status)` |
| 6 | `c0_m6_clinic_patient_rel.py` | `c0_m6_clinic_patient_rel` (25) | `c0_m5_clinic_service` | CREATE TABLE `clinic_patient_relationships` + unique `(clinic_id, patient_code)` + unique `(clinic_id, patient_id)` |
| 7 | `c0_m7_subscription_plan.py` | `c0_m7_subscription_plan` (24) | `c0_m6_clinic_patient_rel` | CREATE TABLE `subscription_plans` + unique `code` |
| 8 | `c0_m8_clinic_subscription.py` | `c0_m8_clinic_subscription` (26) | `c0_m7_subscription_plan` | CREATE TABLE `clinic_subscriptions` + partial unique `clinic_id` WHERE `status IN ('trial','active')` |
| 9 | `c0_m9_audit_log_clinic_id.py` | `c0_m9_audit_log_clinic_id` (26) | `c0_m8_clinic_subscription` | ALTER `audit_logs`: add nullable `clinic_id` (`String(36)`) + composite index `(clinic_id, timestamp)` |

**New single head after this batch: `c0_m9_audit_log_clinic_id`.**

Ordering rationale: `clinic_id`-bearing tables are created only after
`clinics` itself has its new columns (though strictly the FK only needs
`clinics.id`, which already exists — the ordering is for doc readability, not
a hard technical dependency). `subscription_plans` (7) is created before
`clinic_subscriptions` (8) because the latter has a hard FK dependency on the
former — this ordering **is** load-bearing. `audit_logs` (9) is last because
it has zero dependency on anything else in this batch and is the lowest-risk
change to land, so any rollback pressure hits the newest, least-depended-on
migration first.

No migration in this batch creates a second head — every `down_revision`
above points at exactly the previous migration in this same list (or, for
#1, at the confirmed current head), so `alembic heads` returns exactly one
row throughout the batch and after it.

## 3. Nullable-first → backfill → enforce-not-null sequencing

**Only one column in this entire batch adds a NOT NULL constraint to an
existing table with live rows: `clinics.status`** (migration #1). Every
other NOT NULL column introduced in this batch is on a **brand-new** table
(no existing rows to backfill — the column is NOT NULL from row zero, which
is safe by construction, not a backfill concern).

For `clinics.status`, the safe pattern used is the **same one-step pattern
already precedented in this repo** (`t13_p0_note_draft_status.py:28-31`,
which added `consultation_notes.status NOT NULL DEFAULT 'finalized'` in a
single `op.add_column` call): because the default value is a static
constant (`'trial'`), not a computed/row-dependent value, Postgres and
SQLite both apply the `server_default` to every existing row in the same
`ALTER TABLE ... ADD COLUMN` statement — there is no window where the column
exists but is NULL on old rows, so a separate three-step
(nullable → `UPDATE` backfill → `ALTER COLUMN SET NOT NULL`) sequence is not
needed here. This is called out explicitly because the task requires
justifying *why* the shorter path is safe, not just asserting it:

```python
op.add_column(
    "clinics",
    sa.Column("status", sa.String(16), nullable=False, server_default="trial"),
)
```

If a future Clinic SaaS phase ever needs a NOT NULL column whose correct
backfill value is *not* a static constant (e.g. derived per-row from other
columns), that migration must use the 3-step pattern instead — flagged here
as guidance for implementers of C1/C2, not something C0 itself needs.

## 4. Explicit additive-only confirmation

Every migration in this batch is additive:

- **No column is dropped.** No table is dropped.
- **No existing column is retyped or renamed.**
- **Every new NOT NULL column has a default** — either a static
  `server_default` (`clinics.status`, and every `status`/`is_primary`-style
  column on the seven new tables, all of which default to their initial
  lifecycle state) or is added to a table with zero existing rows (new
  tables have no pre-existing-row problem by definition).
- **No existing FK, index, or unique constraint is altered or dropped.**
  Every new unique/partial-unique/composite index is additive; none narrows
  or removes an existing one (e.g. `t27`'s
  `uq_patient_profiles_user_id` is untouched).
- **`PatientProfile`'s encrypted PHI columns and `EncryptedString` pattern
  are not touched anywhere in this batch** — confirmed by re-reading
  `patient.py:18-45` line-by-line against every migration above; none of the
  nine migrations references the `patient_profiles` table's own columns,
  only its `id` as a foreign-key target from `clinic_patient_relationships`.

## 5. `upgrade()` / `downgrade()` confirmation

All nine migrations will implement both functions:

- `upgrade()`: the `CREATE TABLE`/`ADD COLUMN`/index/constraint operations
  described above.
- `downgrade()`: the exact inverse — `DROP TABLE` for migrations #2–#8;
  `DROP COLUMN`×11 for #1 (mirroring `t13_p0_note_draft_status.py:41-43`'s
  `drop_column` pattern exactly); `DROP INDEX` + `DROP COLUMN` for #9. Since
  every migration here only *adds* structure, every `downgrade()` is a
  structurally simple, fully symmetric removal — no data-loss ambiguity to
  resolve in the downgrade path (nothing here transforms or destroys
  pre-existing data on the way up, so there is nothing irrecoverable to
  reconstruct on the way down).

## 6. Expensive-migration / production-scale risk assessment

None of the nine migrations is expected to be expensive in production:

- **Migrations #2–#8 (`CREATE TABLE`)**: creating a new, empty table plus
  its indexes is O(1) regardless of the rest of the database's size —
  no existing-table lock or full-table rewrite is involved.
- **Migration #1 (`ALTER TABLE clinics ADD COLUMN ... × 10`)**: `clinics` is
  a low-cardinality table today (the platform has, per the audit, no live
  Clinic SaaS tenants yet — the existing `Clinic`/`DoctorClinic` schema is
  only exercised by one dormant legacy flow, `CURRENT_ARCHITECTURE_AUDIT.md`
  §3/§12). Adding ten nullable-or-defaulted columns to a table with at most
  a handful of rows is negligible even on Postgres's `ADD COLUMN ... DEFAULT`
  path (which historically could rewrite the table for a non-null default
  pre-PG11, but MetoCare's target Postgres versions on Azure are modern
  enough that a constant default is a metadata-only change, not a rewrite —
  flagged for the implementer to confirm the exact Postgres version at
  migration time, since this reasoning depends on it).
- **Migration #9 (`ALTER TABLE audit_logs ADD COLUMN clinic_id` + index)**:
  `audit_logs` is the one table in this batch that plausibly has real
  row-count growth today (every consultation-access check, doctor-review
  decision, and consent action already writes to it per
  `CURRENT_ARCHITECTURE_AUDIT.md` §8). Adding a nullable column with no
  default is a metadata-only change on both Postgres and SQLite (no rewrite,
  no backfill, since `NULL` is the valid existing-row value) — cheap
  regardless of row count. Building the composite index `(clinic_id,
  timestamp)` afterward *does* scan the full table once; on Postgres this
  should use `CREATE INDEX CONCURRENTLY` (outside a transaction block) if
  `audit_logs` has grown large enough by the time this migration actually
  runs, to avoid holding a write lock during index build — called out here
  as an implementation-time decision (Alembic's `op.create_index` can be
  told to run outside a transaction) rather than baked into this design
  doc's fixed plan, since the right choice depends on the row count at
  migration time, which this document cannot predict.

## 7. Summary

- 9 new migration files, all chaining linearly onto the confirmed single
  head `t13_p0_note_draft_status`, ending at a new single head
  `c0_m9_audit_log_clinic_id`.
- 7 new tables, 2 altered tables (`clinics`, `audit_logs`).
- Zero destructive operations; zero non-nullable columns added without a
  default; every migration additive.
- Every migration will carry both `upgrade()` and `downgrade()`.
- No FK/index in this batch is expected to be expensive given current data
  volumes, with one call-out (§6, migration #9's composite index) for the
  implementer to double-check row count / use `CREATE INDEX CONCURRENTLY` if
  `audit_logs` has grown substantially by the time this actually ships.
