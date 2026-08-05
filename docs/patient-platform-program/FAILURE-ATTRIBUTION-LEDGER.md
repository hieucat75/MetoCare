# Failure-attribution ledger — integration candidate vs `origin/main`

**Candidate:** `feat/patient-platform-journey2`
**Baseline:** `origin/main` @ `99a3616`
**Date:** 2026-08-05

Every row below was produced by running the **same command**, on the **same
PostgreSQL server**, with a **freshly created database**, the **same environment
variables**, the **same collection order**, and the **same dependency lock** —
once in an isolated `origin/main` worktree and once on the candidate. The earlier
comparison was not like-for-like (two files at baseline vs the full suite on the
candidate) and its conclusions are superseded here.

---

## 1. What "the full suite" means

There are three distinct commands, and conflating them caused the earlier
confusion:

| # | Command | Who runs it |
|---|---|---|
| **CI-1** | `pytest tests/ -m "not integration"` | `test-backend` job |
| **CI-2** | `pytest <5 named integration files> -m integration` | `test-backend-postgres` job |
| **AD-HOC** | `pytest` (everything, one process, one database) | nobody — used only during this investigation |

**CI never runs AD-HOC.** It is not a documented workflow, and the integration
files' own docstrings state each one "spins up a fresh schema using Alembic
upgrade … then tears down" against `POSTGRES_TEST_URL`. Running all of them in
one process points every module at the **same** database, so one module's
`downgrade()` collides with another's expected revision. That is a property of the
ad-hoc invocation, not of the code under test.

---

## 2. Results

| Command | `origin/main` | Candidate | Verdict |
|---|---|---|---|
| **CI-1** — `pytest tests/ -m "not integration"` | — | **EXIT 0, 0 failures** | green |
| **CI-2** — 5 named integration files | — | **EXIT 0, 0 failures** | green |
| **AD-HOC** — everything in one process | **22 failures** | see §3 | baseline exception, §4 |

---

## 3. Per-failure attribution (AD-HOC run)

### 3a. Pre-existing — reproduced identically on `origin/main` (21)

Reproduction (identical on both trees):

```bash
createdb <fresh>
POSTGRES_TEST_URL="postgresql+psycopg://$USER@localhost:5432/<fresh>" \
  python -m pytest -q --tb=no
```

| Test | Baseline | Candidate | Root cause | Disposition |
|---|---|---|---|---|
| `test_medication_p0_migrations` ×4 | FAIL | FAIL | shared-DB cross-module interference: each module walks the Alembic chain up/down on the same database | pre-existing; not a merge blocker |
| `test_medication_k1_knowledge_migration` ×5 | FAIL | FAIL | same | pre-existing |
| `test_medication_k1_s2_catalog_migration` ×3 | FAIL | FAIL | same | pre-existing |
| `test_medication_k1_a1b_f1_schema_completion` ×4 | FAIL | FAIL | same | pre-existing |
| `test_medication_k1_a1b_f2_specialty_seed` ×1 | FAIL | FAIL | same | pre-existing |
| (teardown ERRORs for 4 of the above) | ERROR | ERROR | same | pre-existing |

All 21 rows are **proven** on `origin/main` under identical conditions. The
candidate did not introduce them and does not make them worse. Each **passes in
isolation and under CI-2**, the invocation CI actually uses.

### 3b. Candidate-introduced — fixed (1)

| Test | Baseline | Candidate (before) | Root cause | Fix |
|---|---|---|---|---|
| `test_medication_k2_s0_round3_hardening_postgres::test_valid_hash_survives_downgrade_refusal_while_nonempty` | PASS | FAIL | The test asserted the **literal** revision `"k2_s0_round3_hardening"` after a refused downgrade, silently encoding "whatever the repository head happened to be when this was written". It therefore broke on **any** candidate that adds a migration, regardless of content. Observed: `assert 'j4_m9_secf11_phi_encryption' == 'k2_s0_round3_hardening'`. | Capture the revision *before* the attempted downgrade and assert it is unchanged — the property actually under test. Production behaviour (refusing the downgrade) unchanged and still asserted. **Verified on real Postgres: 31/31.** |

Reproduction:
```bash
createdb mcp_k2v
POSTGRES_TEST_URL=".../mcp_k2v" python -m pytest \
  tests/integration/test_medication_k2_s0_round3_hardening_postgres.py -q
```

### 3c. Order-dependent logging failures — root-caused and fixed (3)

| Test | Baseline | Candidate (before) | Disposition |
|---|---|---|---|
| `test_observability::test_access_log_is_json_with_no_phi` | FAIL | **FIXED** | pre-existing on main, fixed here |
| `test_platform_hardening_p1::test_unmatched_path_...` | n/a (file absent on main) | FAIL | **FIXED** |
| `test_meto_context_failclosed::test_failure_is_logged_without_phi` | n/a (file absent on main) | FAIL | **FIXED** |

**Root cause — measured, not inferred.** `alembic/env.py` called
`fileConfig(config.config_file_name)` with both defaults intact, producing two
process-wide, permanent side effects whenever Alembic shares a process with the
app:

1. `disable_existing_loggers` defaults to **True** → sets `.disabled = True` on
   every logger not named in `alembic.ini` (`mcp.access`, `app.services.*`,
   `app.core.*`). Measured directly: `fileConfig("alembic.ini")` flips
   `mcp.access.disabled` `False → True`.
2. `alembic.ini` declares `[logger_root] level = WARNING` → **lowers the host
   application's root level**, so loggers with no explicit level inherit WARNING
   and every INFO application log is filtered out. The access log stops.

**Bisection evidence:** the target test passes alone, passes with its whole
module, passes preceded by the other Meto modules, and the entire suite is
**EXIT 0** with `tests/integration` excluded. The trigger is any test that invokes
Alembic in-process.

This had been hit before and worked around *per test file* — see the
snapshot/restore fixture in `tests/test_medication_k2_s0_migrations_sqlite.py`,
whose docstring calls fixing `alembic/env.py` "out of scope".

**Fix (production code, not tests):**
- `alembic/env.py` passes `disable_existing_loggers=False`, and restores the root
  level after `fileConfig` **only when the application already owns logging**
  (detected via the handler tag). Standalone Alembic — the deploy job's one-shot
  container — is untouched and keeps `alembic.ini`'s levels exactly. Alembic's own
  verbosity is unaffected: `[logger_alembic]` sets INFO explicitly.
- `app/core/logging.py::setup_logging` removes only the handler **it** installed
  (tagged `_OWNED_HANDLER_FLAG`). It previously cleared every root handler —
  idempotent for itself, destructive to everyone else. `create_app()` calls it, so
  constructing the app detached pytest's caplog and would detach an embedding
  process's handlers.

Both previous-session test-side workarounds were **reverted**; the tests pass on
the source fix alone.

**Regression coverage:** `tests/test_logging_lifecycle.py`, 8 tests — Alembic must
not disable app loggers; the stdlib default still would (pins *why* the flag is
needed); `env.py` must keep the argument; repeated `setup_logging` does not
accumulate handlers; it does not evict foreign handlers; repeated `create_app`
leaves exactly one owned handler; caplog still captures after `create_app`; app
loggers still emit after `fileConfig`.

---

## 4. Documented baseline exception

**Claim:** the candidate is green on every command the project actually runs.

- CI-1: EXIT 0.
- CI-2: EXIT 0.
- AD-HOC: the remaining failures are **all proven present on `origin/main` under
  identical conditions**, and all pass in isolation and under CI-2.

**Why they are not a merge blocker:** they are an artefact of pointing every
migration module at one shared database in one process. The candidate neither
introduces nor worsens them — the failure sets are identical apart from the rows
this session fixed. Merging changes nothing about them.

**Why they still matter:** on a healthcare platform, 21 red integration tests are
a standing hazard — they train reviewers to ignore red, and nobody can run the
whole suite locally and trust the result. The fix is to give each integration
module its **own** database, the pattern
`tests/integration/test_secf11_phi_encryption.py` already uses (`CREATE DATABASE`
per fixture, dropped on teardown). That is pre-existing debt on `main`, and is
recommended as a separate follow-up rather than folded into a 55-commit
integration merge.
