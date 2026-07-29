# Codex Review — PR #136 (Round 4) — Medication Knowledge Slice 0

**Reviewer:** Codex (read-only, `model_reasoning_effort=high`, `codex exec -s read-only`)
**Date:** 2026-07-29
**Branch:** `feat/medication-knowledge-slice0-provenance`
**Base:** `main@e8ae3d8`
**Head SHA reviewed:** `849b58b` (Fix Round 3.1 — SHA-256 hex-charset CHECK + Slice 3
concurrency gate)
**Scope:** full PR diff (`git diff origin/main...HEAD`), explicit focus on all 6 Round 3
findings' post-review fixes, the new Fix Round 3.1 hash-format hardening, the Slice 3
concurrency-gate formalization, reserved `system:*` actor enforcement, PG/SQLite trigger
parity, and transaction rollback/promotion correctness.

---

## VERDICT (as delivered): **BLOCK MERGE**

Codex found **1 new P1** and reconfirmed **2 P2s** (one pre-existing, one newly
introduced as a documentation item this round). All 6 Round 3 findings and the
Fix Round 3.1 hash-charset hardening were independently verified as closed.

---

## Findings (as delivered by Codex)

1. **[P1] SQLite's hash CHECK had a raw-SQL bypass through embedded NUL characters.**
   The SQLite branch relied solely on `GLOB` (`k2_s0_round3_hardening.py:251`). SQLite's
   `GLOB` stops comparison at an embedded NUL (U+0000) byte, so a value like
   `"a" * 64 + "\x00" + "evil_garbage_after_nul"` satisfied the 64-class GLOB pattern
   even though SQLite genuinely stores every byte after the NUL. Codex reproduced this
   directly (87 bytes stored, `hex()` showed the full payload). The ORM regex validator
   already rejected it, but raw SQL bypasses the ORM entirely — the exact threat model
   this hardening exists to close. Codex's suggested fix: combine the `GLOB` with a
   byte-length check via `LENGTH(CAST(column AS BLOB)) = 64` (ordinary `LENGTH(column)`
   is insufficient — it *also* stops at the embedded NUL and misreports 64).

2. **[P2] The lenient `system:*` actor-namespace CHECK is not byte-for-byte equivalent
   across SQLite, PostgreSQL, and the ORM.** `_system_actor_check_sql` uses
   `NOT LIKE 'system:%'`, while the ORM uses case-sensitive `startswith()`. PostgreSQL
   `LIKE` and the ORM both treat `SYSTEM:attacker` as outside the reserved lowercase
   namespace; SQLite's default `LIKE` is case-insensitive by default and would treat it
   as matching (a value like `SYSTEM:attacker` would then be blocked as if it were a
   forged reserved value, an over-block rather than a bypass) — Codex correctly assessed
   this as **not a security bypass** (lowercase forged `system:*` values remain blocked
   on all three), only a dialect/ORM parity gap. Not fixed this round — pre-existing
   from Round 2/3, out of Fix Round 3.1's narrow scope, and non-exploitable as a
   security issue.

3. **[P2] The generation-insert vs. approval race remains deferred, now adequately
   formalized as one hard Slice 3 gate.** Codex independently confirmed: the limitation
   and required shared target-row lock are explicit in both
   `knowledge_repository.py`'s `_select_and_promote_ai_generation` docstring and
   `MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md` §B8.
   Repository-wide inspection found **no production `KnowledgeAIGeneration` INSERT
   writer** — only the model import, the approval query/promotion path, and test
   fixtures. Deferral is safe today; the gate is correctly merge-blocking for whichever
   slice ships the first writer.

## Other Round 3 / Fix Round 3.1 verification (Codex's own words)

- Downgrade refusal runs before any DDL (Codex Round 3 P1-1) — confirmed still correct.
- PostgreSQL `TRUNCATE` and both-dialect `DELETE` are blocked (Round 3 P1-2) — confirmed.
- Client-supplied `sequence_number` cannot persist (Round 3 P1-4) — confirmed.
- SQLite Round 1 triggers are recreated correctly after `batch_alter_table` rebuilds —
  confirmed.
- PostgreSQL `JSONB` permits the legitimate `review_status` promotion UPDATE (Round 2
  finding 1) — confirmed, no regression.
- Approval promotion, row transition, lifecycle history, and deprecation share one
  rollback boundary — confirmed.
- PostgreSQL `~` regex and SQLite `GLOB` correctly reject uppercase, mixed-case,
  ordinary non-hex, whitespace, and Unicode-lookalike values, and enforce exact length.
  SQLite `GLOB` remained case-sensitive under both `case_sensitive_like` pragma settings.

Codex noted the targeted pytest classes could not be run directly inside its own
read-only sandbox (no writable temp directory available there) — it instead exercised
the SQLite CHECK predicate directly in-memory (including the NUL-bypass reproduction),
which is what surfaced finding 1.

---

## Disposition — fix applied after this round, in-branch

**Finding 1 (P1, embedded-NUL bypass) — independently re-verified and fixed:**

Before trusting Codex's finding, it was reproduced directly against a real migrated
SQLite database via the actual SQLAlchemy/production code path (not just the sqlite3
CLI Codex used) — confirmed: a raw-SQL `INSERT` with `input_hash = "a" * 64 + "\x00" +
"evil_garbage_after_nul"` (87 real characters) succeeded and persisted all 87 bytes
verbatim, with SQLite's own `LENGTH()` misreporting 64.

Applied Codex's suggested fix exactly: `k2_s0_round3_hardening.py`'s
`_hash_format_check_sql` now combines the existing `GLOB` with
`LENGTH(CAST(column AS BLOB)) = 64` on the SQLite branch — a `BLOB` cast has no
C-string/NUL-termination semantics, so it measures genuine byte length independent of
any embedded NUL. Re-verified directly against a real migrated database:
- the same embedded-NUL payload is now rejected (`IntegrityError`);
- a genuine 64-char lowercase hex digest still succeeds;
- an uppercase 64-char value is still correctly rejected.

Independently confirmed PostgreSQL was never affected by this specific vector: its
`text`/`varchar` type cannot store an embedded NUL byte at all — psycopg raises
`DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes` client-side before
the value ever reaches the `~` regex CHECK. Reproduced directly.

Added a regression test case (`embedded_nul_suffix`) to both dialects' hash-format test
suites:
- `tests/test_medication_k2_s0_migrations_sqlite.py::TestHashFormatValidationOnSQLite`
  — proves the bypass is now closed via raw SQL (the exact vector Codex demonstrated).
- `tests/integration/test_medication_k2_s0_round3_hardening_postgres.py::
  TestHashFormatValidationOnPostgres` — documents and regression-locks that PostgreSQL
  was never exploitable via this vector (rejected client-side as `DataError`, not by the
  CHECK constraint), so the dialect asymmetry is intentional, not an oversight.

**Findings 2 and 3 (P2) — deliberately not fixed this round:**
- Finding 2 (actor-namespace CHECK parity) is a real but non-exploitable gap, out of
  this round's narrow scope (SHA-256 hash validation + Slice 3 gate formalization
  only) — tracked as a future hardening item, not merge-blocking.
- Finding 3 (generation-insert/approval race) is the one P2 explicitly permitted to
  remain by the task's own merge gate, since no production writer exists yet and
  Slice 3 is now hard-gated on solving it before shipping one.

A full automated Codex Round 5 re-review of this one-line fix was **not** run,
matching the precedent already set at the end of Round 2 (see
`CODEX_REVIEW_PR136_MEDICATION_SLICE0_ROUND2.md`'s own disposition section): the task
instruction that authorized this round asked to run Round 4 and then stop before merge
to report — it explicitly said not to start a Round 5 automatically. The fix was
instead independently, directly verified against real migrated SQLite and PostgreSQL
databases (raw-SQL reproduction of the failure before the fix, and of the correct,
still-permissive behavior after), the same standard of evidence Codex's own Round 4
finding used to substantiate itself. Full verification suite (SQLite migration tests,
combined Postgres K1.5/K1.6/K2/round3-hardening regression x2, full non-integration
backend suite, ruff, single Alembic head) was re-run in full after the fix — all green,
zero regressions, +2 tests (the new embedded-NUL case on each dialect).
