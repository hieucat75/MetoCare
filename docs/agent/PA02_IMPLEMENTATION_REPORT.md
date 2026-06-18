# PA-02 Implementation Report

**Task:** Patient App MVP API Contract  
**Branch:** `feature/pa02-patient-app-contract`  
**Date:** 2026-06-18  
**Status:** COMPLETE — READY FOR CODEX REVIEW

---

## Summary

Produced the complete Patient App MVP API Contract as a documentation-only deliverable. All 16 required sections are present. Schemas are sourced from the live OpenAPI spec and route source code — no guessed field names.

---

## Methodology

### Source of Truth

All schemas were extracted from the actual running OpenAPI spec:

```bash
MCP_DATABASE_URL=sqlite:///./data/mcp_dev.sqlite3 uvicorn app.main:app --port 8001
curl http://localhost:8001/openapi.json > /tmp/metocare_openapi.json
```

57 API paths were enumerated. All patient-facing paths were documented with:
- Exact field names from Pydantic schema definitions
- Required vs optional markers (`*` = required, `?` = optional)
- Enum values where applicable

### RBAC Accuracy

RBAC rules were read directly from route files:
- `app/api/v1/routes/patients.py` — profile, metabolic scores, symptoms, medications, nutrition, triage history
- `app/api/v1/routes/health.py` — metrics (note: `CLINIC_ADMIN` has read-only access, not write)
- `app/api/v1/routes/consent.py` — consent endpoints (Luật BVDLCN Vietnam 2026 compliance)
- `app/api/v1/routes/lab.py` — lab documents
- `app/api/v1/routes/notifications.py` — notifications
- `app/api/v1/routes/ai.py` — AI triage and metabolic score

### Feature Flag

The triage feature flag implementation was read from `app/core/feature_flags.py`:
- Flag name: `FEATURE_AI_TRIAGE` (env var)
- Default: `False` (fail-closed)
- Requires Medical Board approval to enable in production

### Token TTLs

Sourced from `app/core/config.py`:
- `access_token_ttl_minutes = 15`
- `refresh_token_ttl_minutes = 60 * 24 * 7` (7 days)

---

## Key Findings and Clarifications

### 1. patient_profile_id vs user_id (§14)

This is the most critical integration point. The `user_id` from the JWT and login response is NOT the same as `patient_profile_id` used in all `/patients/{id}/...` endpoints. Section 14 provides:
- A clear ID type table
- Step-by-step first-login resolution flow
- A diagram showing the relationship
- Note that PatientProfile is NOT auto-created at registration (admin must create it)

### 2. Consent is PATIENT-only (§10)

Under Luật BVDLCN Vietnam 2026, only the patient can grant or revoke consent. Doctors, admins, and AI services are all blocked from grant/revoke endpoints. This is hardcoded in the route (not just configuration).

### 3. Doctor DELETE medication is blocked (§8)

Clinical safety rule: `DOCTOR` role is explicitly blocked (403) from `DELETE /patients/{id}/medications/{med_id}`. Only patients and admins can soft-delete medications. This is documented in §8.3 with a safety note.

### 4. Health Metrics RBAC differs from other endpoints (§4)

`CLINIC_ADMIN` has READ access to metrics (GET endpoints) but not WRITE (POST is blocked). This is different from most other patient endpoints. The RBAC table in §4 reflects this accurately.

### 5. Lab Documents require consent scope='lab' (§6)

Unlike profile endpoints which use scope=`profile`, lab document access requires a separate consent with scope=`lab`. Both the GET and POST lab-document endpoints enforce this consent gate.

### 6. AI Triage persistence is role-dependent (§12)

When a `PATIENT` calls `POST /ai/triage`, the result is automatically persisted to `TriageLog` (accessible via triage history). When a `DOCTOR`, `CLINIC_ADMIN`, or other role calls it, the result is returned but NOT persisted. This is documented in §12.

### 7. Notifications: CLINIC_ADMIN is blocked (§11)

`CLINIC_ADMIN` cannot read, mark, or create notifications. Only `PATIENT`, `DOCTOR`, admin roles, and `MEDICAL_REVIEWER` have access.

---

## Files Changed

| File | Action | Notes |
|---|---|---|
| `docs/product/METOCARE_PATIENT_APP_MVP_CONTRACT.md` | Created | Main deliverable, ~500 lines, 16 sections |
| `docs/agent/PA02_TASK_CARD.md` | Created | Task tracking |
| `docs/agent/PA02_IMPLEMENTATION_REPORT.md` | Created | This report |

**No code files were modified.**

---

## Acceptance Criteria Check

| Criterion | Status |
|---|---|
| Branch `feature/pa02-patient-app-contract` created from `f2438db` | ✅ |
| `docs/product/METOCARE_PATIENT_APP_MVP_CONTRACT.md` exists | ✅ |
| Min 300 lines | ✅ (~500+ lines) |
| All 16 sections present | ✅ |
| No code files touched | ✅ |
| Schemas sourced from OpenAPI spec (not guessed) | ✅ |

---

## PA-02 — READY FOR CODEX REVIEW

**Branch:** `feature/pa02-patient-app-contract`  
**Files:** `docs/product/METOCARE_PATIENT_APP_MVP_CONTRACT.md` (min 300 lines ✅)  
**Status:** Contract complete, all 16 sections present ✅
