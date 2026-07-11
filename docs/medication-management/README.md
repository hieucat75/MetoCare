# Medication Management — Documentation Index

**Generated:** 2026-07-10 by OpenClaw (Product Architecture + Research)  
**Status:** Audit & Design complete. No production code written.  
**Constraint:** Clinic SaaS M08 not touched. Shared RBAC utilities not modified.

---

## Documents

| # | File | Description |
|---|------|-------------|
| 1 | `MEDICATION_CURRENT_STATE_AUDIT.md` | Full audit of what exists today — schema, APIs, frontend, gaps |
| 2 | `MEDICATION_TARGET_ARCHITECTURE.md` | 4-layer target architecture design |
| 3 | `MEDICATION_DATA_MODEL.md` | Full schema: tables, fields, constraints, migration sequence |
| 4 | `MEDICATION_SAFETY_RULES.md` | Clinical safety rules — mandatory reading before implementation |
| 5 | `MEDICATION_UX_FLOWS.md` | UX flows for all 15 major user journeys |
| 6 | `MEDICATION_AI_BEHAVIOR.md` | What Meto AI can and cannot do for medications |
| 7 | `MEDICATION_RBAC_AND_PRIVACY.md` | RBAC matrix, caregiver model, PHI classification |
| 8 | `MEDICATION_TEST_MATRIX.md` | Test cases for P0–P4 + safety red-team tests |
| 9 | `MEDICATION_ROADMAP.md` | P0–P4 roadmap with scope, schema, AC, rollout, Codex gates |
| 10 | `MEDICATION_GAP_AND_PRIORITY_MATRIX.md` | 24-gap analysis with impact/effort/risk scoring |

---

## Quick Start for Implementation

1. Read `MEDICATION_SAFETY_RULES.md` first — non-negotiable constraints
2. Read `MEDICATION_CURRENT_STATE_AUDIT.md` — understand what already exists
3. Read `MEDICATION_ROADMAP.md` Phase P0 section — first slice to implement
4. Check `MEDICATION_GAP_AND_PRIORITY_MATRIX.md` — priority order

## Key Findings Summary

- **Drug catalog exists (41 drugs)** but patient records have no FK linkage → cannot detect duplicate active ingredients
- **Adherence system exists and works** but weekly chart is approximated — not real per-day data
- **Zero allergy infrastructure** — highest clinical safety gap
- **Zero interaction detection** — highest clinical safety gap
- **Zero prescription OCR** — lab OCR infrastructure can be reused
- **Zero reminder/schedule system** — `notify_medication` preference exists but nothing behind it
- **Supplement/TCM not classified** — no evidence quality labels

## Recommended P0 Start Point

Start with `MEDICATION_ROADMAP.md` → Phase P0.  
All P0 migrations are nullable column additions — zero risk of data loss.  
P0 does not require clinical review or external dependencies.

## Stop Gates (Summary)

- External drug database license → **STOP**
- Production push/SMS for reminders → **STOP**
- OCR on real users without staging check → **STOP**
- P3 interaction rules without Vietnamese doctor review → **STOP**
- Destructive schema migration → **STOP**
