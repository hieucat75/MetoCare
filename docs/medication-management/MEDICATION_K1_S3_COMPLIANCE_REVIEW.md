# MetoCare Medication — K1-S3 Compliance Review

**Version:** 1.0
**Date:** 2026-07-15
**PR scope:** K1-S3 — draft-only repository/service layer for the 5 in-scope ADR-13 knowledge tables
**Branch:** `feat/k1-s3-draft-repository`
**Reviewer:** Tech Lead (self-review) + independent Codex CLI review

---

## Scope lock verification

| Requirement | Status | Evidence |
|---|---|---|
| Repository/service layer for the 5 knowledge groups | ✅ | `app/services/knowledge_repository.py` — one shared module (not 5 duplicates), parameterized by model class, matching this codebase's plain-function service convention (no repository classes anywhere else in the codebase). |
| Only draft creation/editing | ✅ | `create_draft()` is the only write path that creates content; "editing" = calling it again for the same business key, producing a new row. |
| No path to `approved` | ✅ | No function in the module can set `status='approved'`. `validate_transition()` implements the ADR-13 rule for `clinical_review → approved` as a pure, unit-tested function, but nothing calls it from a real write path with that target — see module docstring for why (no Clinical Advisor role wired up yet). |
| No real clinical content authored | ✅ | Tests use synthetic strings only (e.g. `"synthetic test content — never staged/production"`), inserted into a throwaway SQLite test DB, never staging/production. |
| Versioning, provenance, specialty requirements, self-approval — ADR-13 | ✅ | See Requirements section below. |
| No patient-facing API | ✅ | No route added under `app/api/`. |
| No frontend | ✅ | `frontend/` untouched. |
| No AI | ✅ | No Meto/context-builder module touched. |
| No `drug_interactions` | ✅ | Not one of the 5 model classes this module imports. |

## Requirement — Versioning (append-only)

`create_draft()` always performs an `INSERT`, never an `UPDATE` of existing content. Verified: `test_create_new_version_does_not_overwrite` creates two draft rows for the identical business key (`drug_ingredient_id`, `locale`, `audience`) and asserts both exist with distinct content, and that the first row's content is unchanged after the second insert.

## Requirement — Provenance

`create_draft()` sets `authored_by`, `status_changed_by`, `status_changed_at` on every row (all NOT NULL per K1-M01's schema). `source`/`version`/`evidence_level`/`reviewed_by`/`last_reviewed_at` remain caller-supplied optional fields (nullable at schema level per K1-M01 — populated progressively through the lifecycle, not required until `approved`, which this module never reaches).

## Requirement — Specialty requirements

`check_specialty_completeness()` compares a row's ingredient's `drug_class.required_specialties` against recorded `knowledge_review_specialties` rows for that exact `(knowledge_table, knowledge_row_id)`. Verified: complete when no specialties are required (trivial case), incomplete when a required specialty has no recorded review, complete once `record_specialty_review()` records it.

## Requirement — Self-approval rule

`validate_transition()` raises `TransitionError` when `actor_user_id == authored_by` for any `clinical_review → approved` transition attempt. Verified directly (unit test), independent of whether any code path can actually reach that state today.

## Requirement — No illegal transitions

`validate_transition()`'s `_ALLOWED_TRANSITIONS` set only permits `draft→clinical_review`, `clinical_review→approved`, `approved→deprecated`, `deprecated→retired` — matching ADR-13's "no transition ever skips clinical_review" rule exactly. Verified: `draft→approved` directly is rejected; re-submitting an already-`clinical_review` row for review again is rejected (not `draft`).

## Test coverage (14 tests, `tests/test_knowledge_repository.py`)

Create draft (2), published-query exclusion + zero-approved-rows (2), transition validation incl. self-approval + specialty-completeness gating (6), specialty completeness (3), rollback/transaction atomicity (1).

## 5-question governance answers

1. **Which ADR?** ADR-13 (lifecycle transition rules, provenance, specialty governance) — this PR implements the service-layer enforcement ADR-13 explicitly assigns there ("enforced in the service layer, not left to the client").
2. **Which Exit Criterion?** Advances EC-06 (draft workflow functional) for the 5 in-scope tables. Does not close it fully — `drug_interactions` (deferred) has no equivalent workflow yet, and no API/frontend exposes this workflow to real users (out of scope by design).
3. **Scope expansion?** No — verified against every item in the scope-lock table above.
4. **Technical debt?** (a) `KNOWLEDGE_TABLE_NAME` in this module duplicates `KNOWLEDGE_TABLES` in `drug_knowledge_governance.py` by hand (no shared import to avoid a circular dependency) — must be kept in sync manually if either changes. (b) The `approved→deprecated` automatic-transition behavior ADR-13 describes is not implemented (nothing can reach `approved` to trigger it) — deferred to whichever future PR adds the real approval path.
5. **Rollback loss?** N/A at the schema level (no migration in this PR). At the service level: `create_draft`/`submit_for_review`/`record_specialty_review` each roll back their own transaction on error, verified by `test_missing_required_field_rolls_back_cleanly`.

### Codex review (round 1) — 1 P1 + 2 P2, all resolved

| # | Finding | Severity | Resolution |
|---|---|---|---|
| 1 | `submit_for_review()` validated the in-memory `row.status`, then committed an unconditional UPDATE — two concurrent callers reading `draft` could both pass validation and both commit, silently double-transitioning a row. | P1 | Rewrote to an atomic `UPDATE ... WHERE id = :id AND status = 'draft'`, matching this codebase's existing optimistic-concurrency convention (`app/services/medication.py`). Raises `TransitionError` if `rowcount != 1`. Verified with a genuine two-session concurrency test (`test_concurrent_submit_for_review_only_one_wins`). |
| 2 | `check_specialty_completeness()` crashed with `AttributeError` (not a return value) if the ingredient, its class, or a referenced specialty was missing — `db.get()` returns `None`, and the next attribute access on `None` raises. | P2 | Now fails closed (`return False`) at each lookup instead of crashing. Verified with two new tests: missing ingredient, and a `knowledge_review_specialties.specialty_id` pointing at a deleted specialty (that column is not FK-enforced). |
| 3 | `test_zero_approved_rows_exist_anywhere` only checked `DrugUsage`, not all 5 in-scope tables; there was no explicit regression test proving a caller can't pass `status='approved'` through `create_draft`'s `**fields`. | P2 | Parameterized the zero-approved-rows test across all 5 model classes. Added `test_status_kwarg_cannot_override_draft`, which locks in the `TypeError` behavior Codex confirmed already prevents this (duplicate keyword argument), rather than leaving it as an incidental property of the implementation. |

Also confirmed clean by Codex: no code path sets `status='approved'` (the `TypeError` on duplicate kwargs is real, not assumed); `list_published()`'s `filter_by(**business_key_filter)` is injection-safe and can't override the fixed `status='approved'` filter for the same reason; the self-approval check and the 4-pair transition set are both correct with no missing edge cases.

Re-verified: 22/22 unit tests pass (up from 14 — added concurrency + missing-reference + status-override regression tests), full backend unit suite green.
