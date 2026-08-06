# Clinical unit normalization + remaining release blockers

**Branch:** `feat/patient-platform-journey2`
**HEAD at this write:** `8fd0f00`
**Date:** 2026-08-05

## P0 — CLOSED (`e72127b`)

One authoritative registry, `app/domain/unit_registry.py`, on every path that
writes a canonical `LabResult`.

**Reproduced before the fix**, and the second half was worse than reported:

| Path | Behaviour before |
|---|---|
| MDI document | `is_unit_convertible` accepts only canonical/SI → **refused** platelet `20 G/L`, WBC `0.8 G/L`, Hb `70 g/L` |
| `/lab-uploads`, manual entry | **no guard**; `normalize_value_to_si` returns the value unchanged under its original unit and `classify_value` ignores the unit → a **normal** Hb of `140 g/L` classified **critical** |

So one printed report gave a refusal on one path and a fabricated critical on
another; the refusal's own message invited retyping `g/L` as `g/dL` without
converting, landing on the same wrong value.

**Registry rule version:** `lab-units-1.0.0`.

**Supported conversions** — keyed by the analyte's canonical unit, which is what
restricts them to compatible analytes:

| Canonical unit | Accepts | Factor | Analytes |
|---|---|---|---|
| `g/dL` | `g/L` | ×0.1 | hemoglobin |
| `10^9/L` | `G/L`, `10^9/L` | ×1 | wbc, absolute differentials, platelet |
| `10^12/L` | `T/L`, `10^12/L` | ×1 | rbc |
| analyte-specific | `si_unit` | `spec.si_factor` | molar (mmol/L ↔ mg/dL) |

**Notation handled:** `G/L`, `G/l`, `10^9/L`, `10⁹/L`, `x10^9/L`, `×10^9/L`,
`10*9/L`, `T/L`, `10^12/L`, `10¹²/L`, `g/L`, `g/dL`, spacing, NBSP, micro-sign.

**Case is semantic.** `G/L` (giga/L) is a CELL COUNT; `g/L` is a MASS
CONCENTRATION. Every other normalizer here lower-cases before comparing, which
merges them. Tokenization preserves the numerator's case.

**Refused:** dimension mismatch, unknown unit, missing unit (document paths),
ambiguous analyte, non-blood specimen, impossible converted value, non-finite /
overflow. A refusal returns `normalized_value=None` — never a pass-through.

**Three further defects found while wiring it:**

1. `detect_specimen` matched accent-STRIPPED patterns against the RAW label, so
   `"Creatinin niệu"` never matched and every urine label passed as blood — the
   exact defect the function exists to stop. Caught by its own new test.
2. A refused conversion left a **stale** metric. `correct_lab_result` stored the
   raw number under the typed unit and synced with `status=None`, which
   `_sync_linked_health_metrics` ignores — so the dashboard kept showing a
   `normal` creatinine on a value just declined. Now the canonical fields are
   emptied and the metric withdrawn.
3. Recovery was impossible: once withdrawn, fixing the unit never restored the
   trend. Now re-promotes.

**Deliberate behaviour change:** creatinine `88 mg/dL` exceeds
`physiological_max` (30) and is refused rather than classified critical. Three
tests in `test_creatinine_consistency.py` updated (not deleted) — the property
they protect, "never leave a stale reassuring metric", is asserted in its
stronger form.

**Evidence:** +57 registry tests, +46 cross-path parity tests comparing manual /
OCR / correction / shared classifier **against each other**, not against a
constant.

## P1 — closed

| # | Item | Commit |
|---|---|---|
| 1 | pause → resume restoration (`resume_schedule` + route) | `ef4ea04` |
| 2 | dose-cancellation audit, PHI-minimised (counts only) | `ef4ea04` |
| 4 | `needs_anchor_repair` on `ScheduleOut` + `start_date` repair path | `ef4ea04` |
| 5 | timeline dose events filtered by medication lifecycle | `ef4ea04` |
| 6 | build identity on the **auto**-deploy path (backend + frontend) | `8fd0f00` |

## P1 — OPEN (blockers)

### P1-3 · Adherence denominator depends on app-open frequency
`compute_occurrences` never backfills and materialisation is pull-only (no
server-side scheduler) — `materialize_due` runs only from request handlers. A
patient who stops opening the app for 30 days accumulates at most the doses
materialised on their last visit; days 8–30 never become rows, so they are absent
from `total`, `missed` and the rate. `adherence_summary` can report
`taken 5 / missed 2 → 0.71` for a month in which 60 doses were prescribed.

Preserving MISSED made the *recorded* doses honest; the rate still
under-reports. Needs a deterministic expected-occurrence calculation (or a scheduler),
plus explicit taken/skipped/missed denominator semantics and dormant-period
tests. **Not started.**

### P1-7 · No post-deploy check exercises a PHI decrypt path
`/health` is `SELECT 1`; the smoke suite is unauthenticated. Boot-time Fernet
validation (added earlier) closes the malformed-key case, but a
**wrong-but-well-formed** key still deploys green. Needs a sanitized
authenticated post-deploy check touching `MetoMessage` and `ExtractionCandidate`
encrypted fields, failing verification on decrypt/key mismatch, with no plaintext
PHI in CI logs. **Not started.**

## Gates at `8fd0f00`

| Gate | Result |
|---|---|
| CI-1 `pytest tests/ -m "not integration"` | EXIT 0 |
| CI-2 16 integration modules, own DB each | EXIT 0, 220 tests |
| ruff | clean |
| mobile tsc | clean |
| mobile jest | 138/138, 28 suites |
| Alembic | single head `j4_m10_p15_residual_phi` |

**Not yet run for this round:** frontend suite/build, fresh independent reviews
(clinical, security, privacy, migration, integration), `--no-ff` merge rehearsal
in an isolated worktree.

## Constraints observed
No merge to main. No production deploy. No Cloudflare change. No credentials,
real PHI, private logs or test passwords committed.
