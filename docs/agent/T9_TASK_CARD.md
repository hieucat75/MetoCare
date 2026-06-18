# T9 Task Card — Health Metrics + Consent Routes RBAC Hardening + API Tests

**TASK_ID:** T9  
**LABEL:** Health Metrics + Consent Routes RBAC + API Tests  
**Branch:** `feature/t9-health-consent-rbac`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

Two route files still use bare `current_user_id` with no RBAC:
- `backend/app/api/v1/routes/health.py` — 3 routes (POST/GET/GET trend)
- `backend/app/api/v1/routes/consent.py` — 2 routes (POST grant / DELETE revoke)

These handle PHI (health metrics) and legal consent — highest-sensitivity data. This sprint hardens both with `CurrentUser` + `require_roles` and adds comprehensive API-level tests.

---

## Scope

### ALLOWED_FILES

- `backend/app/api/v1/routes/health.py` — RBAC hardening
- `backend/app/api/v1/routes/consent.py` — RBAC hardening
- `backend/tests/api/test_health_api.py` — NEW
- `backend/tests/api/test_consent_api.py` — NEW
- `docs/agent/T9_IMPLEMENTATION_REPORT.md` — NEW

### DO NOT TOUCH

- `backend/app/services/health_metrics.py`
- `backend/app/services/consent.py`
- Any existing passing tests
- Migration files
- Models

---

## RBAC Requirements

### Health Metrics (`/patients/{patient_id}/metrics`)

| Endpoint | Allowed Roles |
|----------|---------------|
| `POST /metrics` | PATIENT (own), DOCTOR (assigned/clinic), INTERNAL_ADMIN, SUPER_ADMIN |
| `GET /metrics` | PATIENT (own), DOCTOR (assigned/clinic), CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN |
| `GET /metrics/trend` | PATIENT (own), DOCTOR (assigned/clinic), CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN |

- AI_SERVICE blocked from all health metric routes
- PATIENT ownership: `patient_profile.user_id == user.id` → 403 on mismatch
- DOCTOR/CLINIC_ADMIN: service-layer consent gate already handles (pass through via `user.id`)
- ADMIN bypass: no ownership check

### Consent (`/patients/{patient_id}/consents`)

| Endpoint | Allowed Roles |
|----------|---------------|
| `POST /consents` (grant) | PATIENT only — patient may only grant consent over their own data |
| `DELETE /consents/{id}` (revoke) | PATIENT only — patient may only revoke their own consent |

- Only PATIENT role may grant/revoke consent
- DOCTOR/ADMIN may NOT grant or revoke consent on behalf of a patient
- AI_SERVICE blocked
- Existing ownership check in `grant_consent` (`requester_id != patient_id` → 403) must be preserved and strengthened (currently weak — uses `has_access` with `__owner__` scope which may not exist)

**Simplification for grant/revoke:** Use `require_roles(UserRole.PATIENT)` + verify `user.id` maps to patient profile with `patient_id`. This replaces the fragile `has_access(scope="__owner__")` check.

---

## Test Requirements

### `tests/api/test_health_api.py` (minimum 12 tests)

**POST /metrics:**
1. `test_patient_creates_own_metric` → 201
2. `test_doctor_creates_metric_for_patient` → 201 (with consent)
3. `test_patient_cannot_create_metric_for_another_patient` → 403
4. `test_ai_service_cannot_create_metric` → 403
5. `test_unauthenticated_cannot_create_metric` → 401

**GET /metrics:**
6. `test_patient_lists_own_metrics` → 200, list
7. `test_patient_cannot_list_another_patients_metrics` → 403
8. `test_admin_lists_any_patient_metrics` → 200

**GET /metrics/trend:**
9. `test_patient_gets_own_trend` → 200, has `data_points`
10. `test_unauthenticated_cannot_get_trend` → 401

### `tests/api/test_consent_api.py` (minimum 8 tests)

**POST /consents (grant):**
1. `test_patient_grants_consent_for_own_data` → 201
2. `test_patient_cannot_grant_consent_for_another_patient` → 403
3. `test_doctor_cannot_grant_consent` → 403
4. `test_ai_service_cannot_grant_consent` → 403
5. `test_unauthenticated_cannot_grant_consent` → 401

**DELETE /consents/{id} (revoke):**
6. `test_patient_revokes_own_consent` → 200
7. `test_doctor_cannot_revoke_consent` → 403
8. `test_revoke_nonexistent_consent` → 404

### Payload helpers:
- Metric: `{"metric_type": "weight", "value": 70.5, "unit": "kg", "measured_at": null, "source": "manual", "normal_range_min": null, "normal_range_max": null}`
- Consent grant: `{"consent_type": "lab_access", "data_scope": "lab", "granted_to": "<doctor_id>", "valid_until": null}`

---

## Acceptance Criteria

- [ ] All 5 routes use `CurrentUser` (not bare `current_user_id`)
- [ ] `require_roles` applied with correct sets per endpoint
- [ ] PATIENT ownership enforced for health metrics (403 on mismatch)
- [ ] PATIENT-only enforcement on consent grant/revoke (403 for DOCTOR/ADMIN/AI_SERVICE)
- [ ] AI_SERVICE blocked from all 5 routes
- [ ] Existing service-layer consent gate preserved in health routes
- [ ] Audit records preserved for grant_consent + revoke_consent
- [ ] All 20 test cases pass (10 health + 10 consent — add extras freely)
- [ ] Zero existing tests broken (248 baseline → 268+ total)
- [ ] Ruff clean
- [ ] `docs/agent/T9_IMPLEMENTATION_REPORT.md` written

---

## Validation Commands

```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
ruff check .
pytest tests/ --tb=short
```

---

## Required Final Status

```
READY FOR CODEX REVIEW
```

---

## Medical + Legal Safety Reminders

- Consent management is a **legal requirement** (Luật BVDLCN Vietnam 2026)
- Do NOT allow DOCTOR to grant/revoke patient consent — this is a P0 violation
- Health metrics are PHI — AI_SERVICE must never write health metrics directly
- Audit log for consent actions is mandatory — do not remove

---

*Task Card issued: 2026-06-18 05:22 GMT+7 | Coordinator: OpenClaw*
