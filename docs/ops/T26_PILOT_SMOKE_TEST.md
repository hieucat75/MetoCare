# T26 Pilot Smoke Test Checklist

**Sprint:** T26 — Final Pilot Hardening  
**Date:** 2026-06-18  
**Environment:** Local SQLite (test client) — production deploy uses PostgreSQL  
**Test Suite:** 515 passed, 1 skipped (TimescaleDB integration)  
**Ruff:** PASS  

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ PASS | Covered by automated test suite; expected status confirmed |
| ⚠️ MANUAL | Requires manual verification in staging/pilot deployment |
| 🔵 DEFER | Deferred to post-pilot |

---

## Section 1: System / Infrastructure

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 1.1 | `/api/v1/health` | GET | Anonymous | 200 (healthy) / 503 (DB down) | `test_system_api.py` | ✅ PASS |
| 1.2 | `/api/v1/info` | GET | Anonymous | 200 with `db_version`, `service`, `environment` | `test_system_api.py` | ✅ PASS |

**Notes:**
- Health endpoint returns 503 with `{"status":"unhealthy","detail":"..."}` when DB is unreachable (T25 production hardening)
- `/info` includes migration version (`db_version`) for deployment validation

---

## Section 2: Authentication & Session Management

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 2.1 | `/api/v1/auth/register` | POST | New user | 201 with tokens | `test_auth_api.py` | ✅ PASS |
| 2.2 | `/api/v1/auth/login` | POST | Patient (valid creds) | 200 with tokens | `test_auth_api.py` | ✅ PASS |
| 2.3 | `/api/v1/auth/login` | POST | Invalid password | 401 | `test_ratelimit.py` | ✅ PASS |
| 2.4 | `/api/v1/auth/login` | POST | Locked account | 423 | `test_ratelimit.py` | ✅ PASS |
| 2.5 | `/api/v1/auth/refresh` | POST | Valid refresh token | 200 | `test_auth_api.py` | ✅ PASS |
| 2.6 | `/api/v1/auth/refresh` | POST | Rate-limited (>capacity) | 429 | `test_ratelimit.py` | ✅ PASS |
| 2.7 | `/api/v1/auth/logout` | POST | Authenticated | 200 | `test_auth_api.py` | ✅ PASS |
| 2.8 | `/api/v1/auth/me` | GET | Authenticated | 200 with user data | `test_auth_api.py` | ✅ PASS |
| 2.9 | `/api/v1/auth/mfa/enroll` | POST | Authenticated | 200 with TOTP secret | `test_auth_api.py` | ✅ PASS |
| 2.10 | `/api/v1/auth/mfa/verify` | POST | MFA enrolled user | 200 / 401 | `test_auth_api.py` | ✅ PASS |

---

## Section 3: Patient Profile

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 3.1 | `GET /patients/{id}/profile` | GET | Patient (own) | 200 | `test_patient_profile_api.py` | ✅ PASS |
| 3.2 | `GET /patients/{id}/profile` | GET | Patient (other patient's) | 403 | `test_patient_profile_api.py` | ✅ PASS |
| 3.3 | `GET /patients/{id}/profile` | GET | Doctor (with consent) | 200 | `test_patient_profile_api.py` | ✅ PASS |
| 3.4 | `GET /patients/{id}/profile` | GET | Doctor (without consent) | 403 | `test_patient_profile_api.py` | ✅ PASS |
| 3.5 | `PATCH /patients/{id}/profile` | PATCH | Patient (own) | 200 | `test_patient_profile_api.py` | ✅ PASS |
| 3.6 | `PATCH /patients/{id}/profile` | PATCH | AI_SERVICE | 403 | `test_patient_profile_api.py` | ✅ PASS |

---

## Section 4: Health Metrics

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 4.1 | `POST /patients/{id}/health-metrics` | POST | Patient (own) | 201 | `test_health_api.py` | ✅ PASS |
| 4.2 | `GET /patients/{id}/health-metrics` | GET | Patient (own) | 200 | `test_health_api.py` | ✅ PASS |
| 4.3 | `GET /patients/{id}/health-metrics/trend` | GET | Patient (own) | 200 with trend | `test_health_api.py` | ✅ PASS |
| 4.4 | `GET /patients/{id}/metabolic-scores` | GET | Patient (own) | 200 with history | `test_metabolic_score_history_api.py` | ✅ PASS |

---

## Section 5: AI Sessions & Recommendations

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 5.1 | `POST /ai_sessions` | POST | Patient (with consent) | 201 | `test_ai_sessions_api.py` | ✅ PASS |
| 5.2 | `POST /ai_sessions` | POST | Patient (no consent) | 403 | `test_ai_sessions_api.py` | ✅ PASS |
| 5.3 | `POST /ai_sessions` | POST | Any (feature flag off) | 503 | `test_ai_sessions_api.py` | ✅ PASS |
| 5.4 | `GET /ai_sessions/{id}` | GET | Patient (own) | 200 | `test_ai_sessions_api.py` | ✅ PASS |
| 5.5 | `GET /ai_sessions/{id}` | GET | Patient (other) | 403 | `test_ai_sessions_full.py` | ✅ PASS |
| 5.6 | `GET /ai_sessions` | GET | Patient | 200 (own only) | `test_ai_sessions_api.py` | ✅ PASS |
| 5.7 | `POST /ai_sessions/{id}/close` | POST | Patient (own) | 204 | `test_ai_session_close_api.py` | ✅ PASS |
| 5.8 | `POST /ai_sessions/{id}/close` | POST | Patient (idempotent) | 204 | `test_ai_session_close_api.py` | ✅ PASS |
| 5.9 | `POST /ai_sessions/{id}/close` | POST | Patient (other's session) | 403 | `test_ai_session_close_api.py` | ✅ PASS |
| 5.10 | `GET /ai_sessions/{id}/recommendations` | GET | Doctor | 200 | `test_ai_sessions_api.py` | ✅ PASS |
| 5.11 | `GET /ai_sessions/{id}/recommendations` | GET | Any (feature flag off) | 503 | `test_ai_sessions_api.py` | ✅ PASS |

---

## Section 6: AI Routes (Triage, Chat, Metabolic Score)

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 6.1 | `POST /ai/chat` | POST | Patient (with consent) | 200 | `test_ai_routes_api.py` | ✅ PASS |
| 6.2 | `POST /ai/triage` | POST | Patient | 200 with risk level | `test_ai_routes_api.py` | ✅ PASS |
| 6.3 | `POST /ai/metabolic-score` | POST | Patient | 200 with score | `test_ai_routes_api.py` | ✅ PASS |

---

## Section 7: Lab Documents

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 7.1 | `POST /patients/{id}/lab-documents` | POST | Doctor (with consent) | 201 | `test_lab_api.py` | ✅ PASS |
| 7.2 | `POST /patients/{id}/lab-documents` | POST | Doctor (no consent) | 403 | `test_lab_api.py` | ✅ PASS |
| 7.3 | `GET /patients/{id}/lab-documents` | GET | Doctor (with consent) | 200 | `test_lab_list_api.py` | ✅ PASS |
| 7.4 | `GET /lab-documents/{id}` | GET | Doctor | 200 | `test_lab_api.py` | ✅ PASS |
| 7.5 | `POST /lab-documents/{id}/process` | POST | AI_SERVICE | 200 | `test_lab_api.py` | ✅ PASS |
| 7.6 | `POST /lab-documents/{id}/interpret` | POST | AI_SERVICE | 200 | `test_lab_pipeline_e2e_api.py` | ✅ PASS |

---

## Section 8: Consent Management

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 8.1 | `GET /patients/{id}/consents` | GET | Patient (own) | 200 | `test_consent_api.py` | ✅ PASS |
| 8.2 | `GET /patients/{id}/consents` | GET | Patient (other's) | 403 | `test_consent_api.py` | ✅ PASS |
| 8.3 | `POST /patients/{id}/consents` | POST | Patient (own) | 201 | `test_consent_api.py` | ✅ PASS |
| 8.4 | `DELETE /patients/{id}/consents/{cid}` | DELETE | Patient (revoke own) | 200 | `test_consent_api.py` | ✅ PASS |
| 8.5 | `GET /patients/{id}/consents?active_only=true` | GET | Admin | 200 (filtered) | `test_consent_list_api.py` | ✅ PASS |

---

## Section 9: Symptoms & Medications

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 9.1 | `POST /patients/{id}/symptoms` | POST | Patient (own) | 201 | `test_symptom_medication_api.py` | ✅ PASS |
| 9.2 | `GET /patients/{id}/symptoms` | GET | Patient (own) | 200 | `test_symptom_medication_api.py` | ✅ PASS |
| 9.3 | `POST /patients/{id}/medications` | POST | Doctor | 201 | `test_symptom_medication_api.py` | ✅ PASS |
| 9.4 | `GET /patients/{id}/medications` | GET | Patient (own) | 200 | `test_symptom_medication_api.py` | ✅ PASS |
| 9.5 | `DELETE /patients/{id}/medications/{mid}` | DELETE | Doctor | 200 | `test_symptom_medication_api.py` | ✅ PASS |

---

## Section 10: Nutrition

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 10.1 | `POST /patients/{id}/nutrition-logs` | POST | Patient (own) | 201 | `test_nutrition_log_api.py` | ✅ PASS |
| 10.2 | `GET /patients/{id}/nutrition-logs` | GET | Patient (own) | 200 | `test_nutrition_log_api.py` | ✅ PASS |

---

## Section 11: Care Plans

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 11.1 | `POST /care-plans` | POST | Doctor | 201 | `test_care_plans_api.py` | ✅ PASS |
| 11.2 | `GET /care-plans/{id}` | GET | Patient (own) | 200 | `test_care_plans_api.py` | ✅ PASS |
| 11.3 | `GET /care-plans` | GET | Doctor | 200 | `test_care_plans_api.py` | ✅ PASS |
| 11.4 | `PATCH /care-plans/{id}` | PATCH | Doctor | 200 | `test_care_plans_api.py` | ✅ PASS |
| 11.5 | `POST /care-plans/{id}/approve` | POST | Internal Admin | 200 | `test_care_plan_approve.py` | ✅ PASS |
| 11.6 | `POST /care-plans/{id}/approve` | POST | AI_SERVICE | 403 | `test_care_plan_approve.py` | ✅ PASS |

---

## Section 12: Encounters

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 12.1 | `POST /encounters` | POST | Doctor | 201 | `test_encounters_api.py` | ✅ PASS |
| 12.2 | `GET /encounters/{id}` | GET | Doctor | 200 | `test_encounters_api.py` | ✅ PASS |
| 12.3 | `GET /encounters` | GET | Patient (own) | 200 | `test_encounters_api.py` | ✅ PASS |
| 12.4 | `PATCH /encounters/{id}` | PATCH | Doctor | 200 | `test_encounters_api.py` | ✅ PASS |
| 12.5 | `GET /encounters` | GET | Patient (other's) | 403 | `test_encounters_full.py` | ✅ PASS |

---

## Section 13: Booking

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 13.1 | `POST /doctors/{id}/availability` | POST | Doctor (own) | 201 | `test_booking_api.py` | ✅ PASS |
| 13.2 | `GET /doctors/{id}/availability` | GET | Patient | 200 | `test_booking_api.py` | ✅ PASS |
| 13.3 | `POST /appointments` | POST | Patient | 201 | `test_booking_api.py` | ✅ PASS |
| 13.4 | `GET /patients/{id}/appointments` | GET | Patient (own) | 200 | `test_booking_api.py` | ✅ PASS |
| 13.5 | `GET /doctors/me/appointments` | GET | Doctor | 200 | `test_booking_api.py` | ✅ PASS |
| 13.6 | `PATCH /appointments/{id}/status` | PATCH | Doctor | 200 | `test_booking_api.py` | ✅ PASS |

---

## Section 14: Notifications

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 14.1 | `GET /notifications` | GET | Patient (own) | 200 | `test_notifications_api.py` | ✅ PASS |
| 14.2 | `PATCH /notifications/{id}/read` | PATCH | Patient (own) | 200 | `test_notifications_api.py` | ✅ PASS |
| 14.3 | `POST /notifications/mark-all-read` | POST | Patient | 200 | `test_notifications_api.py` | ✅ PASS |
| 14.4 | `POST /notifications` | POST | Admin only | 201 | `test_notifications_api.py` | ✅ PASS |
| 14.5 | `POST /notifications` | POST | Non-admin | 403 | `test_notifications_api.py` | ✅ PASS |

---

## Section 15: Doctor Portal (Summary + PDF)

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 15.1 | `GET /patients/{id}/summary` | GET | Doctor (with consent) | 200 | `test_doctor_portal_api.py` | ✅ PASS |
| 15.2 | `GET /patients/{id}/summary` | GET | Doctor (no consent) | 403 | `test_doctor_portal_api.py` | ✅ PASS |
| 15.3 | `GET /patients/{id}/summary` | GET | Patient (own) | 403 (doctor-only) | `test_doctor_portal_api.py` | ✅ PASS |
| 15.4 | `GET /patients/{id}/summary/pdf` | GET | Doctor (with consent) | 200 (application/pdf) | `test_pdf_export_api.py` | ✅ PASS |
| 15.5 | `GET /patients/{id}/summary/pdf` | GET | Patient | 403 | `test_pdf_export_api.py` | ✅ PASS |

---

## Section 16: Doctor Review Queue (AI Recommendations)

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 16.1 | `GET /doctor-review/queue` | GET | Doctor | 200 (pending list) | `test_doctor_review_api.py` | ✅ PASS |
| 16.2 | `POST /doctor-review` | POST | AI_SERVICE | 201 (pending_review) | `test_doctor_review_api.py` | ✅ PASS |
| 16.3 | `POST /doctor-review` | POST | AI_SERVICE (status=accepted) | 422 (C1 violation) | `test_doctor_review_api.py` | ✅ PASS |
| 16.4 | `POST /doctor-review/{id}/review` | POST | Doctor | 200 (status updated) | `test_doctor_review_api.py` | ✅ PASS |
| 16.5 | `POST /doctor-review/{id}/review` | POST | AI_SERVICE | 403 | `test_doctor_review_api.py` | ✅ PASS |
| 16.6 | `GET /doctor-review/{id}` | GET | Doctor | 200 | `test_doctor_review_api.py` | ✅ PASS |

---

## Section 17: Admin Portal

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 17.1 | `GET /admin/audit-logs` | GET | Internal Admin | 200 | `test_admin_api.py` | ✅ PASS |
| 17.2 | `POST /admin/unlock-account` | POST | Admin | 200 | `test_ratelimit.py` | ✅ PASS |
| 17.3 | `GET /admin/users` | GET | Internal Admin | 200 (list) | `test_admin_users_api.py` | ✅ PASS |
| 17.4 | `GET /admin/users/{id}` | GET | Internal Admin | 200 | `test_admin_users_api.py` | ✅ PASS |
| 17.5 | `PATCH /admin/users/{id}/role` | PATCH | Super Admin only | 200 | `test_admin_users_api.py` | ✅ PASS |
| 17.6 | `PATCH /admin/users/{id}/role` | PATCH | Internal Admin (non-super) | 403 | `test_admin_users_api.py` | ✅ PASS |
| 17.7 | `DELETE /admin/users/{id}` | DELETE | Internal Admin | 200 (soft-delete) | `test_admin_users_api.py` | ✅ PASS |
| 17.8 | `GET /admin/users/{id}/audit-log` | GET | Internal Admin | 200 | `test_admin_users_api.py` | ✅ PASS |

---

## Section 18: Triage Log

| # | Endpoint | Method | Role Tested | Expected Status | Coverage | Result |
|---|----------|--------|-------------|-----------------|----------|--------|
| 18.1 | `GET /patients/{id}/triage-history` | GET | Patient (own) | 200 | `test_triage_log_api.py` | ✅ PASS |
| 18.2 | `GET /patients/{id}/triage-history` | GET | Doctor | 200 | `test_triage_log_api.py` | ✅ PASS |
| 18.3 | `GET /patients/{id}/triage-history` | GET | Patient (other's) | 403 | `test_triage_log_api.py` | ✅ PASS |

---

## Clinical Safety Flows (Red Team)

| # | Scenario | Expected | Coverage | Result |
|---|----------|----------|----------|--------|
| CS-01 | Patient access to another patient's data | 403 | Multiple test files | ✅ PASS |
| CS-02 | AI cannot create clinical records with status=accepted | 422 | `test_doctor_review_api.py` | ✅ PASS |
| CS-03 | AI cannot approve care plans | 403 | `test_care_plan_approve.py` | ✅ PASS |
| CS-04 | Doctor requires consent for patient data | 403 without consent | `test_patient_profile_api.py`, etc. | ✅ PASS |
| CS-05 | Unauthenticated access → 401 everywhere | 401 | All API test files | ✅ PASS |
| CS-06 | Rate limiting on auth endpoints | 429 | `test_ratelimit.py` | ✅ PASS |
| CS-07 | Account lockout after N failures | 423 | `test_ratelimit.py` | ✅ PASS |
| CS-08 | AI triage red-flag detection | risk_level = critical | `test_ai_routes_api.py` | ✅ PASS |

---

## Summary

| Section | Flows | Automated | Manual |
|---------|-------|-----------|--------|
| System/Infrastructure | 2 | 2 | 0 |
| Auth | 10 | 10 | 0 |
| Patient Profile | 6 | 6 | 0 |
| Health Metrics | 4 | 4 | 0 |
| AI Sessions | 11 | 11 | 0 |
| AI Routes | 3 | 3 | 0 |
| Lab Documents | 6 | 6 | 0 |
| Consent | 5 | 5 | 0 |
| Symptoms & Medications | 5 | 5 | 0 |
| Nutrition | 2 | 2 | 0 |
| Care Plans | 6 | 6 | 0 |
| Encounters | 5 | 5 | 0 |
| Booking | 6 | 6 | 0 |
| Notifications | 5 | 5 | 0 |
| Doctor Portal | 5 | 5 | 0 |
| Doctor Review | 6 | 6 | 0 |
| Admin | 8 | 8 | 0 |
| Triage Log | 3 | 3 | 0 |
| Clinical Safety | 8 | 8 | 0 |
| **TOTAL** | **106** | **106** | **0** |

**All flows: 100% covered by automated test suite.**

---

## Known Gaps (Post-Pilot)

1. **Real push/email notification transport** — in-app only; `send_push/send_email` stubs always succeed
2. **TimescaleDB hypertable integration test** — requires real PostgreSQL + TimescaleDB (1 skipped test)
3. **AI_SERVICE session ownership** — can close any session; P2-deferred pending model change
4. **`valid_until` consent filter** — `active_only` does not check expiry date; P2-deferred
