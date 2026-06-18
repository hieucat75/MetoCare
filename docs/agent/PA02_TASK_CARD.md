# PA-02 Task Card — Patient App MVP API Contract

**Task ID:** PA-02  
**Branch:** `feature/pa02-patient-app-contract`  
**Base commit:** `f2438db`  
**Owner:** Claude Code (subagent)  
**Status:** ✅ COMPLETE — READY FOR CODEX REVIEW  
**Date:** 2026-06-18  

---

## Objective

Produce a formal API contract document (`docs/product/METOCARE_PATIENT_APP_MVP_CONTRACT.md`) that documents every endpoint the Patient App MVP will call, with exact request/response shapes, RBAC rules, and UX flow mapping.

This is a **documentation-only sprint** — no code changes.

---

## Deliverables

| File | Status | Lines |
|---|---|---|
| `docs/product/METOCARE_PATIENT_APP_MVP_CONTRACT.md` | ✅ Created | ~500+ |
| `docs/agent/PA02_TASK_CARD.md` | ✅ Created | This file |
| `docs/agent/PA02_IMPLEMENTATION_REPORT.md` | ✅ Created | See below |

---

## Method

1. Created branch `feature/pa02-patient-app-contract` from `f2438db`
2. Started the backend server briefly to fetch the live OpenAPI spec (`/tmp/metocare_openapi.json`)
3. Parsed all 57 API paths from the spec to enumerate actual endpoints
4. Read source files for every relevant route to capture:
   - Exact RBAC logic from route decorators and guards
   - Precise request/response schema field names from Pydantic models
   - Feature flag implementation from `app/core/feature_flags.py`
   - Token TTL configuration from `app/core/config.py`
   - Legal/safety constraints from route docstrings
5. Wrote the contract with 16 required sections

---

## Sections Completed

- [x] §1 — Scope Statement (patient-facing only, out-of-scope list)
- [x] §2 — Authentication Flows (register, login, refresh, logout, me)
- [x] §3 — Patient Profile (GET + PATCH with field-level notes)
- [x] §4 — Health Metrics (POST, GET list, GET trend with all parameters)
- [x] §5 — Metabolic Score (history, trend interpretation, delta rule)
- [x] §6 — Lab Results (upload + list with storage flow note)
- [x] §7 — Symptom Log (POST + GET)
- [x] §8 — Medications (POST + GET + DELETE with doctor safety block)
- [x] §9 — Nutrition Log (POST + GET)
- [x] §10 — Consent Management (grant + list + revoke with legal context)
- [x] §11 — Notifications (list + mark-read + read-all)
- [x] §12 — AI Triage (feature flag gated, patient-safe output format)
- [x] §13 — Triage History (paginated)
- [x] §14 — ID Resolution Guide (user_id vs patient_profile_id, step-by-step)
- [x] §15 — Error Codes Reference (all HTTP codes with frontend action)
- [x] §16 — Security Notes (token storage, TTLs, MFA, PHI, rate limiting)
