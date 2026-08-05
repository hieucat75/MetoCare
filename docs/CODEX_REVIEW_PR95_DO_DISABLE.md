# Codex Review — PR #95 chore(deploy): disable DO deployment

**Reviewer:** Codex (read-only)
**Date:** 2026-07-07
**Branch:** chore/disable-do-deployment
**Head SHA:** e49923a
**Files reviewed:**
- `.github/workflows/deploy-do.yml`
- `docs/PROD_HARDENING_AUTH.md`
- `docs/agent/TASK_D_DO_DISABLE_REPORT.md`
- `docs/ops/PRODUCTION_READINESS_CHECKLIST.md`

---

VERDICT: **PASS**

**P0 Blockers:** 0
**P1 High:** 0
**P2 Warnings:** 1

---

## Checklist Results

| Check | Result | Evidence |
|-------|--------|----------|
| Job `build` has if:false | PASS | line 54 |
| Job `migrate` has if:false | PASS | line 96 |
| Job `deploy` has if:false | PASS | line 134 |
| Regression sentinel present + if:false | PASS | line 189–191 (`_do_deployment_disabled`) |
| No job without if:false | PASS | 4 jobs × 4 guards; all confirmed |
| Deprecated comment at top | PASS | lines 1–12: DISABLED (2026-07-07), Azure ACA named sole target, "DO NOT re-enable without explicit PTH approval" |
| workflow_dispatch neutralised | PASS | `push:` removed; `image_tag` input replaced with `_disabled` input; DISABLED notice in description |
| No push/schedule trigger | PASS | `grep -n "^  push:\|^  schedule:"` → no results |
| No secret/credential in diff | PASS | All references use `${{ secrets.* }}` — no literal values; VPS IP appears only in pre-existing comment headers and `secrets.DO_VPS_IP` references (dead code, guarded by `if: false`) |
| Docs accurate (`PROD_HARDENING_AUTH.md`) | PASS (with W2) | Item D section (lines 68–82) records Option 1 decision, actions taken, and PR link correctly |
| Docs accurate (`PRODUCTION_READINESS_CHECKLIST.md`) | PASS | ACA listed as ACTIVE; DO listed as DEPRECATED/DISABLED 2026-07-07; DO must not be re-enabled without PTH approval |
| Azure workflows untouched | PASS | `git diff main...origin/chore/disable-do-deployment -- .github/workflows/ci.yml .github/workflows/azure-staging.yml` → 0 lines diff |
| deploy/do/ compose untouched | PASS | `git diff main...origin/chore/disable-do-deployment -- deploy/` → 0 lines diff |
| No source code changes | PASS | `git diff main...origin/chore/disable-do-deployment -- backend/ frontend/` → 0 lines diff |
| YAML syntax valid | PASS | `python3 -c "import yaml; yaml.safe_load(open(...))"` → YAML_VALID |

---

## Findings

### W2 — Stale Ordering Text in `docs/PROD_HARDENING_AUTH.md` (P2 Warning)

**Severity:** P2 (non-blocking warning)
**File:** `docs/PROD_HARDENING_AUTH.md`
**Line:** 122
**Evidence:**
```
5. Item D (DO cleanup) — pending PTH decision on Option 1 vs 2.
```
**Issue:** The "Implementation Order" section (lines 118–127) still says Item D is "pending PTH decision on Option 1 vs 2." However, the decision was made (Option 1 — Disable, 2026-07-07) and is documented 50 lines earlier in the same file (lines 68–82). This is stale text left from before the decision was taken.

**Impact:** No functional impact. The `if: false` enforcement is correct and the decision IS documented in the Item D section. This is a docs-consistency issue only.

**Recommended Fix (non-blocking):** In a follow-up commit or next PR, update line 122 to:
```
5. Item D (DO cleanup) — ✅ DONE (2026-07-07). Workflow disabled via PR #95.
```

---

## YAML Validation Output

```
$ python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-do.yml'))" && echo YAML_VALID
YAML_VALID
```

---

## Job Count Verification

Explicit job enumeration from `grep -n "^  [a-z_].*:" .github/workflows/deploy-do.yml` (on `origin/chore/disable-do-deployment`):

| Line | Job name | if: false guard |
|------|----------|----------------|
| 53 | `build` | line 54 ✅ |
| 95 | `migrate` | line 96 ✅ |
| 133 | `deploy` | line 134 ✅ |
| 189 | `_do_deployment_disabled` | line 191 ✅ |

4 jobs × 4 `if: false` guards. No job found without a guard.

---

## Recommended Action

**SAFE_TO_MERGE**

All mandatory checks pass. The `if: false` enforcement is complete, correctly applied to all 4 jobs, and independently verified by the job-count. No secrets are exposed. No Azure or compose files were touched. YAML is valid.

The one P2 warning (stale ordering text in `PROD_HARDENING_AUTH.md`) is non-blocking and can be resolved in a follow-up commit.
