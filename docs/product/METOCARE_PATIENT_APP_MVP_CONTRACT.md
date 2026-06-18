# MetoCare Patient App MVP — API Contract

**Document version:** 1.0.0  
**API version:** 0.3.0  
**Branch:** `feature/pa02-patient-app-contract`  
**Status:** READY FOR CODEX REVIEW  
**Last updated:** 2026-06-18  
**Owner:** Claude Code (PA-02)

---

## Table of Contents

1. [Scope Statement](#1-scope-statement)
2. [Authentication Flows](#2-authentication-flows)
3. [Patient Profile](#3-patient-profile)
4. [Health Metrics](#4-health-metrics)
5. [Metabolic Score](#5-metabolic-score)
6. [Lab Results](#6-lab-results)
7. [Symptom Log](#7-symptom-log)
8. [Medications](#8-medications)
9. [Nutrition Log](#9-nutrition-log)
10. [Consent Management](#10-consent-management)
11. [Notifications](#11-notifications)
12. [AI Triage (Feature Flag Gated)](#12-ai-triage-feature-flag-gated)
13. [Triage History](#13-triage-history)
14. [ID Resolution Guide](#14-id-resolution-guide)
15. [Error Codes Reference](#15-error-codes-reference)
16. [Security Notes for Frontend](#16-security-notes-for-frontend)

---

## 1. Scope Statement

### In Scope — Patient-Facing Flows Only

This contract covers every API endpoint the **Patient App MVP** will call on behalf of an authenticated patient. All endpoints use the base URL:

```
https://<host>/api/v1
```

Covered modules:
- Registration and login (auth flows)
- Patient profile read/write
- Health metrics logging and trend analysis
- Metabolic score history
- Lab document upload and listing
- Symptom logging
- Medication management
- Nutrition logging
- Consent management (grant/revoke access to doctors)
- Notifications
- AI-powered triage (feature-flag gated)
- Triage session history

### Out of Scope

The following are **NOT** part of this contract and must not be called by the Patient App:

| Portal | Example Endpoints |
|---|---|
| Doctor portal | `GET /patients/{id}/summary`, `GET /patients/{id}/summary.pdf`, `GET /doctor/review/*` |
| Admin portal | `GET /admin/users`, `PATCH /admin/users/{id}/role`, `GET /admin/audit-logs` |
| AI session orchestration | `POST /ai_sessions`, `GET /ai_sessions/{id}/recommendations` |
| Care plans / encounters | `POST /care_plans`, `POST /encounters` |
| Booking management (doctor side) | `GET /doctors/me/appointments`, `POST /doctors/{id}/availability` |

The Patient App may view its own appointments via `GET /patients/{patient_id}/appointments`, but appointment _creation_ is not in the MVP scope.

---

## 2. Authentication Flows

All auth endpoints are under `/api/v1/auth/`. No `Authorization` header is required for register/login/refresh.

### Token Format

All tokens are **JWT (HS256)**. The `Authorization` header format for protected endpoints:

```
Authorization: Bearer <access_token>
```

JWT `access_token` claims include:
- `sub` — User UUID (`user_id`)
- `role` — User role string (e.g. `"patient"`)
- `mfa` — Boolean; whether MFA was verified in this session
- `exp` — Expiry timestamp (Unix epoch)

---

### 2.1 Register

**POST** `/api/v1/auth/register`

Create a new patient account. On success, returns tokens immediately (no separate login step required).

> **Note:** The `role` field is ignored on registration — all self-registered users receive the `patient` role by server enforcement.

**Rate limit:** 20 requests / 60 seconds per IP.

#### Request Body

```json
{
  "email": "patient@example.com",
  "password": "SecurePass123!",
  "full_name": "Nguyễn Văn An"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `email` | string | ✅ | Must be a valid email address |
| `password` | string | ✅ | Min length enforced server-side |
| `full_name` | string | ❌ | Display name |

#### Response `201 Created`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "patient",
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "mfa": false
}
```

| Field | Type | Notes |
|---|---|---|
| `access_token` | string | JWT; TTL = 15 minutes |
| `refresh_token` | string | JWT; TTL = 7 days |
| `token_type` | string | Always `"bearer"` |
| `role` | string | Always `"patient"` for self-registration |
| `user_id` | string (UUID) | User.id — store for subsequent ID resolution |
| `mfa` | boolean | Always `false` on initial registration |

#### Error Codes

| HTTP | Condition |
|---|---|
| `409 Conflict` | Email already registered |
| `422 Unprocessable Entity` | Invalid email format or missing required fields |
| `429 Too Many Requests` | Rate limit exceeded |

---

### 2.2 Login

**POST** `/api/v1/auth/login`

Authenticate with email + password. Returns access/refresh tokens.

**Rate limit:** 20 requests / 60 seconds per IP.  
**Account lockout:** After 5 failed attempts, the account is locked for 15 minutes.

#### Request Body

```json
{
  "email": "patient@example.com",
  "password": "SecurePass123!",
  "totp_code": "123456"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `email` | string | ✅ | |
| `password` | string | ✅ | |
| `totp_code` | string | ❌ | Required only when MFA is enabled for this account |
| `backup_code` | string | ❌ | Alternative to `totp_code` when TOTP device is unavailable |

#### Response `200 OK`

Same shape as Register response (see §2.1).

#### Error Codes

| HTTP | Condition |
|---|---|
| `401 Unauthorized` | Invalid email or password; or MFA code required/invalid |
| `422 Unprocessable Entity` | Validation error |
| `423 Locked` | Account temporarily locked (too many failures) |
| `429 Too Many Requests` | Rate limit exceeded |

---

### 2.3 Refresh Token

**POST** `/api/v1/auth/refresh`

Exchange a valid refresh token for a new access/refresh token pair (token rotation).

> **Important:** The old `refresh_token` is invalidated after each refresh. Store the new one.

**Rate limit:** 20 requests / 60 seconds per IP.

#### Request Body

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

| Field | Type | Required |
|---|---|---|
| `refresh_token` | string | ✅ |

#### Response `200 OK`

Same shape as Register response (see §2.1). MFA level is preserved from the original session.

#### Error Codes

| HTTP | Condition |
|---|---|
| `401 Unauthorized` | Refresh token expired, revoked, or invalid |
| `422 Unprocessable Entity` | Missing field |
| `429 Too Many Requests` | Rate limit exceeded |

---

### 2.4 Logout

**POST** `/api/v1/auth/logout`

Revoke the refresh token (invalidates the session). Access tokens continue to work until their 15-minute TTL expires.

Requires: `Authorization: Bearer <access_token>`

#### Request Body

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Response `200 OK`

```json
{
  "message": "logged out"
}
```

#### Error Codes

| HTTP | Condition |
|---|---|
| `401 Unauthorized` | Access token missing or expired |
| `422 Unprocessable Entity` | Missing `refresh_token` |

---

### 2.5 Get Current User

**GET** `/api/v1/auth/me`

Return the authenticated user's account details. The `id` field returned here is `user_id` — **not** the `patient_profile_id`. See §14 for how to resolve the patient profile ID.

Requires: `Authorization: Bearer <access_token>`

#### Response `200 OK`

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "patient@example.com",
  "role": "patient",
  "full_name": "Nguyễn Văn An",
  "mfa_enabled": false
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | string (UUID) | User.id — this is the `user_id`, NOT the `patient_profile_id` |
| `email` | string | |
| `role` | string | e.g. `"patient"` |
| `full_name` | string or null | |
| `mfa_enabled` | boolean | Whether TOTP MFA is enrolled |

#### Error Codes

| HTTP | Condition |
|---|---|
| `401 Unauthorized` | Token missing or expired |
| `404 Not Found` | User record deleted (edge case) |

---

## 3. Patient Profile

All profile endpoints require `Authorization: Bearer <access_token>`.

The `{patient_id}` path parameter is the **PatientProfile UUID** — NOT the User UUID. See §14 for the full ID resolution pattern.

### RBAC Matrix — Profile Endpoints

| Role | GET profile | PATCH profile |
|---|---|---|
| `patient` (own) | ✅ | ✅ |
| `doctor` (with consent, scope=`profile`) | ✅ | ✅ |
| `internal_admin` / `super_admin` | ✅ | ✅ |
| `ai_service` | ❌ 403 | ❌ 403 |
| `clinic_admin` | ❌ 403 | ❌ 403 |

---

### 3.1 Get Patient Profile

**GET** `/api/v1/patients/{patient_id}/profile`

#### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `patient_id` | string (UUID) | PatientProfile.id (NOT User.id — see §14) |

#### Response `200 OK`

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "full_name": "Nguyễn Văn An",
  "dob": "1985-03-15",
  "phone": "+84901234567",
  "gender": "male",
  "height_cm": 170.0,
  "weight_kg": 72.5,
  "waist_cm": 88.0,
  "risk_segment": "moderate",
  "known_conditions": "Type 2 Diabetes",
  "allergies": "Penicillin"
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | string (UUID) | PatientProfile.id |
| `user_id` | string (UUID) | The linked User.id |
| `full_name` | string or null | |
| `dob` | string (ISO8601 date) or null | Date of birth `YYYY-MM-DD` |
| `phone` | string or null | |
| `gender` | string or null | Free text (e.g. `"male"`, `"female"`, `"other"`) |
| `height_cm` | float or null | |
| `weight_kg` | float or null | |
| `waist_cm` | float or null | |
| `risk_segment` | string or null | Server-computed; read-only. Values: `"low"`, `"moderate"`, `"high"` |
| `known_conditions` | string or null | Encrypted at rest (PHI) |
| `allergies` | string or null | Encrypted at rest (PHI) |

#### Error Codes

| HTTP | Condition |
|---|---|
| `401 Unauthorized` | Token missing/expired |
| `403 Forbidden` | Wrong patient ownership or blocked role |
| `404 Not Found` | PatientProfile not found |

---

### 3.2 Update Patient Profile (Partial)

**PATCH** `/api/v1/patients/{patient_id}/profile`

Partial update — only fields included in the request body are written. Omitted fields are left unchanged.

Every successful update produces an audit log entry (`action='update_profile'`).

#### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `patient_id` | string (UUID) | PatientProfile.id |

#### Request Body (all fields optional)

```json
{
  "full_name": "Nguyễn Văn An",
  "dob": "1985-03-15",
  "phone": "+84901234567",
  "gender": "male",
  "height_cm": 170.0,
  "weight_kg": 72.5,
  "waist_cm": 88.0,
  "known_conditions": "Type 2 Diabetes, Hypertension",
  "allergies": "Penicillin"
}
```

| Field | Type | Notes |
|---|---|---|
| `full_name` | string | |
| `dob` | string | ISO8601 date `YYYY-MM-DD` |
| `phone` | string | |
| `gender` | string | |
| `height_cm` | float | |
| `weight_kg` | float | |
| `waist_cm` | float | |
| `known_conditions` | string | PHI — encrypted at rest |
| `allergies` | string | PHI — encrypted at rest |

> **Note:** `risk_segment` is computed server-side and cannot be set by the client.

#### Response `200 OK`

Returns the full updated profile (same shape as GET, see §3.1).

#### Error Codes

| HTTP | Condition |
|---|---|
| `401 Unauthorized` | Token missing/expired |
| `403 Forbidden` | Not own profile or blocked role |
| `404 Not Found` | PatientProfile not found |
| `422 Unprocessable Entity` | Field validation failed |

---

## 4. Health Metrics

All metrics endpoints require `Authorization: Bearer <access_token>`.

### RBAC Matrix

| Role | POST metric | GET metrics | GET trend |
|---|---|---|---|
| `patient` (own) | ✅ | ✅ | ✅ |
| `doctor` | ✅ | ✅ | ✅ |
| `clinic_admin` | ❌ 403 | ✅ | ✅ |
| `internal_admin` / `super_admin` | ✅ | ✅ | ✅ |
| `ai_service` | ❌ 403 | ❌ 403 | ❌ 403 |

### Supported Metric Types

| `metric_type` value | Description | Typical Unit |
|---|---|---|
| `blood_glucose` | Blood glucose reading | `mmol/L` or `mg/dL` |
| `blood_pressure` | Blood pressure (systolic/diastolic) | `mmHg` |
| `weight` | Body weight | `kg` |
| `heart_rate` | Resting heart rate | `bpm` |
| `spo2` | Oxygen saturation | `%` |

> Any string value is accepted by the server; the above are the canonical patient-facing types.

---

### 4.1 Log a Metric

**POST** `/api/v1/patients/{patient_id}/metrics`

#### Request Body

```json
{
  "metric_type": "blood_glucose",
  "value": 6.2,
  "unit": "mmol/L",
  "measured_at": "2026-06-18T08:30:00+07:00",
  "source": "manual",
  "normal_range_min": 3.9,
  "normal_range_max": 7.8
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `metric_type` | string | ✅ | See table above |
| `value` | float | ✅ | Numeric measurement |
| `unit` | string | ❌ | Unit string (e.g. `"mmol/L"`) |
| `measured_at` | string (ISO8601) | ❌ | Defaults to server time if omitted |
| `source` | string | ❌ | e.g. `"manual"`, `"device"` |
| `normal_range_min` | float | ❌ | Lower bound of normal range |
| `normal_range_max` | float | ❌ | Upper bound of normal range |

#### Response `201 Created`

```json
{
  "id": "c1d2e3f4-a5b6-7890-cdef-012345678901",
  "metric_type": "blood_glucose",
  "value": 6.2,
  "unit": "mmol/L",
  "measured_at": "2026-06-18T08:30:00+07:00",
  "status": "normal"
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | string (UUID) | Metric record ID |
| `metric_type` | string | |
| `value` | float | |
| `unit` | string or null | |
| `measured_at` | string (ISO8601) | |
| `status` | string or null | Server-computed: `"normal"`, `"high"`, `"low"` |

---

### 4.2 List Metrics

**GET** `/api/v1/patients/{patient_id}/metrics`

#### Query Parameters

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `metric_type` | string | ❌ | Filter by metric type (e.g. `blood_glucose`) |

#### Response `200 OK`

Array of metric objects (same shape as POST response):

```json
[
  {
    "id": "c1d2e3f4-a5b6-7890-cdef-012345678901",
    "metric_type": "blood_glucose",
    "value": 6.2,
    "unit": "mmol/L",
    "measured_at": "2026-06-18T08:30:00+07:00",
    "status": "normal"
  }
]
```

---

### 4.3 Get Metric Trend

**GET** `/api/v1/patients/{patient_id}/metrics/trend`

Returns statistical trend data for a specific metric type over a window.

#### Query Parameters

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `metric_type` | string | ✅ | — | e.g. `blood_glucose` |
| `days` | integer | ❌ | 30 | Range: 1–365 |

#### Response `200 OK`

```json
{
  "metric_type": "blood_glucose",
  "days": 30,
  "count": 15,
  "min": 5.1,
  "max": 8.4,
  "avg": 6.5,
  "first": 7.2,
  "last": 6.2,
  "direction": "improving"
}
```

| Field | Type | Notes |
|---|---|---|
| `metric_type` | string | |
| `days` | integer | Window requested |
| `count` | integer | Number of readings in the window |
| `min` | float or null | |
| `max` | float or null | |
| `avg` | float or null | |
| `first` | float or null | Oldest value in window |
| `last` | float or null | Most recent value |
| `direction` | string or null | `"improving"`, `"worsening"`, `"stable"` |

---

## 5. Metabolic Score

### 5.1 Get Metabolic Score History

**GET** `/api/v1/patients/{patient_id}/metabolic-scores`

Returns paginated score history and a directional trend. The metabolic score is computed and persisted automatically when the patient calls `POST /api/v1/ai/metabolic-score`.

#### RBAC

| Role | Access |
|---|---|
| `patient` (own) | ✅ |
| `doctor` (consent-gated, scope=`profile`) | ✅ |
| `internal_admin` / `super_admin` | ✅ |
| `ai_service` / `clinic_admin` | ❌ 403 |

#### Query Parameters

| Parameter | Type | Default |
|---|---|---|
| `limit` | integer | 20 (max 100) |
| `offset` | integer | 0 |

#### Response `200 OK`

```json
{
  "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "total": 8,
  "items": [
    {
      "id": "s1t2u3v4-w5x6-7890-yz01-234567890abc",
      "metabolic_score": 42,
      "band": "moderate",
      "top_risks": [
        {
          "name": "fasting_glucose",
          "points": 15,
          "detail": "Fasting glucose above threshold"
        }
      ],
      "created_at": "2026-06-18T08:00:00+00:00"
    }
  ],
  "trend": "stable"
}
```

#### Score Interpretation

| Field | Description |
|---|---|
| `metabolic_score` | Integer; higher = worse metabolic health |
| `band` | Categorical risk band: `"low"`, `"moderate"`, `"high"`, `"very_high"` |
| `top_risks` | Array of contributing risk factors |
| `trend` | `"improving"` (delta < −5), `"worsening"` (delta > +5), `"stable"` otherwise |

**Delta interpretation rule:**
- Score delta > +5 between consecutive readings → **worsening**
- Score delta < −5 → **improving**
- Otherwise → **stable**

The `trend` field in the history response is computed across the most recent readings in the returned page.

---

## 6. Lab Results

All lab endpoints require `Authorization: Bearer <access_token>`.

### RBAC Matrix

| Role | POST lab-document | GET lab-documents |
|---|---|---|
| `patient` (own) | ✅ | ✅ |
| `doctor` (consent-gated, scope=`lab`) | ✅ | ✅ |
| `internal_admin` / `super_admin` | ✅ | ✅ |
| `clinic_admin` | ❌ 403 | ❌ 403 |
| `ai_service` | ❌ 403 | ❌ 403 |

---

### 6.1 Upload Lab Document

**POST** `/api/v1/patients/{patient_id}/lab-documents`

Register a lab result document. The `storage_key` is a pre-allocated storage path (S3 key or local path). The document is queued for asynchronous OCR processing; `ocr_status` begins as `"pending"`.

> **Storage flow (MVP):** The client first uploads the file to the storage backend and receives a `storage_key`, then calls this endpoint with that key. In dev/test, `storage_mode=local` is used.

#### Request Body

```json
{
  "storage_key": "uploads/patient/a1b2c3d4/labresult_20260618.pdf",
  "file_type": "pdf",
  "lab_name": "FV Hospital"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `storage_key` | string | ✅ | Path/key of the already-uploaded file |
| `file_type` | string | ❌ | e.g. `"pdf"`, `"jpg"`, `"png"` |
| `lab_name` | string | ❌ | Name of the originating lab |

#### Response `201 Created`

```json
{
  "id": "d1e2f3a4-b5c6-7890-defg-123456789012",
  "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "ocr_status": "pending",
  "status": "uploaded"
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | string (UUID) | LabDocument.id — use for status polling |
| `patient_id` | string (UUID) | |
| `ocr_status` | string | `"pending"`, `"processing"`, `"done"`, `"failed"` |
| `status` | string | Document pipeline status |

---

### 6.2 List Lab Documents

**GET** `/api/v1/patients/{patient_id}/lab-documents`

Returns lab documents newest-first (paginated).

#### Query Parameters

| Parameter | Type | Default |
|---|---|---|
| `limit` | integer | 20 (max 100) |
| `offset` | integer | 0 |

#### Response `200 OK`

Array of lab document objects (same shape as POST response).

---

## 7. Symptom Log

All symptom endpoints require `Authorization: Bearer <access_token>`.

### RBAC

| Role | POST symptom | GET symptoms |
|---|---|---|
| `patient` (own) | ✅ | ✅ |
| `doctor` (consent-gated, scope=`profile`) | ✅ | ✅ |
| `internal_admin` / `super_admin` | ✅ | ✅ |
| `ai_service` | ❌ 403 | ❌ 403 |
| `clinic_admin` | ❌ 403 | ❌ 403 |

---

### 7.1 Log a Symptom

**POST** `/api/v1/patients/{patient_id}/symptoms`

Produces an audit log entry (`action='log_symptom'`).

#### Request Body

```json
{
  "description": "Fatigue after meals, mild dizziness",
  "severity": 4,
  "reported_at": "2026-06-18T10:00:00+07:00"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `description` | string | ✅ | Free-text symptom description |
| `severity` | integer | ❌ | Scale 1–10 (1 = minimal, 10 = severe) |
| `reported_at` | string (ISO8601) | ❌ | Defaults to server time if omitted |

#### Response `201 Created`

```json
{
  "id": "e1f2a3b4-c5d6-7890-efab-234567890123",
  "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "description": "Fatigue after meals, mild dizziness",
  "severity": 4,
  "reported_at": "2026-06-18T03:00:00+00:00",
  "created_at": "2026-06-18T03:01:12+00:00"
}
```

---

### 7.2 List Symptoms

**GET** `/api/v1/patients/{patient_id}/symptoms`

Returns symptom logs newest-first (paginated).

#### Query Parameters

| Parameter | Type | Default |
|---|---|---|
| `limit` | integer | 20 (max 100) |
| `offset` | integer | 0 |

#### Response `200 OK`

```json
{
  "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "total": 12,
  "items": [
    {
      "id": "e1f2a3b4-c5d6-7890-efab-234567890123",
      "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "description": "Fatigue after meals, mild dizziness",
      "severity": 4,
      "reported_at": "2026-06-18T03:00:00+00:00",
      "created_at": "2026-06-18T03:01:12+00:00"
    }
  ]
}
```

---

## 8. Medications

All medication endpoints require `Authorization: Bearer <access_token>`.

### RBAC

| Role | POST medication | GET medications | DELETE medication |
|---|---|---|---|
| `patient` (own) | ✅ | ✅ | ✅ |
| `doctor` (consent-gated) | ✅ | ✅ | ❌ 403 (clinical safety) |
| `internal_admin` / `super_admin` | ✅ | ✅ | ✅ |
| `ai_service` | ❌ 403 | ❌ 403 | ❌ 403 |
| `clinic_admin` | ❌ 403 | ❌ 403 | ❌ 403 |

> **Safety note:** Doctors are explicitly blocked from DELETE (HTTP 403). Clinical safety rule: doctors must not remove a patient's medication history.

---

### 8.1 Add Medication

**POST** `/api/v1/patients/{patient_id}/medications`

Produces an audit log entry (`action='add_medication'`).

#### Request Body

```json
{
  "name": "Metformin",
  "dose": "500mg twice daily",
  "note": "Take with meals"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | ✅ | Medication name |
| `dose` | string | ❌ | Dosage description |
| `note` | string | ❌ | Additional notes |

#### Response `201 Created`

```json
{
  "id": "f1a2b3c4-d5e6-7890-fabc-345678901234",
  "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Metformin",
  "dose": "500mg twice daily",
  "note": "Take with meals",
  "created_at": "2026-06-18T03:05:00+00:00"
}
```

---

### 8.2 List Active Medications

**GET** `/api/v1/patients/{patient_id}/medications`

Returns non-deleted (active) medication records, newest-first.

#### Query Parameters

| Parameter | Type | Default |
|---|---|---|
| `limit` | integer | 20 (max 100) |
| `offset` | integer | 0 |

#### Response `200 OK`

```json
{
  "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "total": 3,
  "items": [
    {
      "id": "f1a2b3c4-d5e6-7890-fabc-345678901234",
      "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Metformin",
      "dose": "500mg twice daily",
      "note": "Take with meals",
      "created_at": "2026-06-18T03:05:00+00:00"
    }
  ]
}
```

---

### 8.3 Delete Medication (Soft Delete)

**DELETE** `/api/v1/patients/{patient_id}/medications/{med_id}`

Soft-deletes a medication record (sets `deleted_at` timestamp). The record is no longer returned by GET list. Produces an audit log entry (`action='delete_medication'`).

#### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `patient_id` | string (UUID) | PatientProfile.id |
| `med_id` | string (UUID) | Medication record ID |

#### Response `204 No Content`

Empty response body on success.

#### Error Codes

| HTTP | Condition |
|---|---|
| `403 Forbidden` | DOCTOR attempting delete (clinical safety block) |
| `404 Not Found` | Medication record not found |

---

## 9. Nutrition Log

All nutrition endpoints require `Authorization: Bearer <access_token>`.

### RBAC

Same as symptom log (§7): patient (own), doctor (consent-gated), admin unrestricted. `ai_service` and `clinic_admin` are blocked (403).

---

### 9.1 Log Nutrition Entry

**POST** `/api/v1/patients/{patient_id}/nutrition`

Produces an audit log entry (`action='log_nutrition'`).

#### Request Body

```json
{
  "description": "Cơm tấm với thịt nướng, salad",
  "meal_type": "lunch",
  "calories_kcal": 650,
  "logged_at": "2026-06-18T12:15:00+07:00"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `description` | string | ✅ | Meal description (free text) |
| `meal_type` | string | ❌ | Enum: `breakfast`, `lunch`, `dinner`, `snack` |
| `calories_kcal` | float | ❌ | Estimated calories |
| `logged_at` | string (ISO8601) | ❌ | Defaults to server time if omitted |

#### Response `201 Created`

```json
{
  "id": "g1h2i3j4-k5l6-7890-ghij-456789012345",
  "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "description": "Cơm tấm với thịt nướng, salad",
  "meal_type": "lunch",
  "calories_kcal": 650.0,
  "logged_at": "2026-06-18T05:15:00+00:00",
  "created_at": "2026-06-18T05:16:00+00:00"
}
```

---

### 9.2 List Nutrition Logs

**GET** `/api/v1/patients/{patient_id}/nutrition`

Returns nutrition logs newest-first (paginated).

#### Query Parameters

| Parameter | Type | Default |
|---|---|---|
| `limit` | integer | 20 (max 100) |
| `offset` | integer | 0 |

#### Response `200 OK`

```json
{
  "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "total": 5,
  "items": [
    {
      "id": "g1h2i3j4-k5l6-7890-ghij-456789012345",
      "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "description": "Cơm tấm với thịt nướng, salad",
      "meal_type": "lunch",
      "calories_kcal": 650.0,
      "logged_at": "2026-06-18T05:15:00+00:00",
      "created_at": "2026-06-18T05:16:00+00:00"
    }
  ]
}
```

---

## 10. Consent Management

All consent endpoints require `Authorization: Bearer <access_token>`.

### Legal Context

Consent management enforces **Luật BVDLCN Vietnam 2026** requirements:

- Only the **patient** may grant or revoke their own consent. No other role (including doctors, admins, or AI services) can grant/revoke consent on behalf of a patient.
- Doctors and Clinic Admins are blocked (403) from grant and revoke endpoints.
- The patient grants consent to a specific `granted_to` (doctor's `user_id`), which then allows that doctor to access the patient's clinical data.

### RBAC Matrix

| Role | POST consent (grant) | GET consents | DELETE consent (revoke) |
|---|---|---|---|
| `patient` (own) | ✅ | ✅ | ✅ |
| `doctor` | ❌ 403 | ❌ 403 | ❌ 403 |
| `internal_admin` / `super_admin` | ❌ 403 (grant/revoke) | ✅ | ❌ 403 |
| `clinic_admin` / `ai_service` | ❌ 403 | ❌ 403 | ❌ 403 |

---

### 10.1 Grant Consent

**POST** `/api/v1/patients/{patient_id}/consents`

Grant a doctor access to a specific data scope.

#### Request Body

```json
{
  "granted_to": "doctor-user-uuid-here",
  "consent_type": "data_access",
  "data_scope": "profile",
  "valid_until": "2027-06-18T00:00:00+00:00"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `granted_to` | string (UUID) | ✅ | The doctor's `user_id` |
| `consent_type` | string | ❌ | e.g. `"data_access"` |
| `data_scope` | string | ❌ | e.g. `"profile"`, `"lab"`. Defaults to `"profile"` if omitted |
| `valid_until` | string (ISO8601) | ❌ | Expiry; null = no expiry |

#### Response `201 Created`

```json
{
  "id": "h1i2j3k4-l5m6-7890-hijk-567890123456",
  "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "data_scope": "profile",
  "granted_to": "doctor-user-uuid-here"
}
```

---

### 10.2 List Active Consents

**GET** `/api/v1/patients/{patient_id}/consents`

#### Query Parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `active_only` | boolean | `true` | When `true`, returns only non-revoked, non-expired consents |

#### Response `200 OK`

Array of consent objects (same shape as POST response).

---

### 10.3 Revoke Consent

**DELETE** `/api/v1/patients/{patient_id}/consents/{consent_id}`

Revokes a consent. Sets `revoked_at` timestamp. The doctor's access is immediately blocked on next request.

#### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `patient_id` | string (UUID) | PatientProfile.id |
| `consent_id` | string (UUID) | Consent record ID |

#### Response `200 OK`

```json
{
  "message": "revoked"
}
```

#### Error Codes

| HTTP | Condition |
|---|---|
| `403 Forbidden` | Not own consent, or non-patient role |
| `404 Not Found` | Consent record not found |

---

## 11. Notifications

All notification endpoints require `Authorization: Bearer <access_token>`.

### RBAC

| Role | GET notifications | PATCH mark-read | POST read-all |
|---|---|---|---|
| `patient` | ✅ | ✅ | ✅ |
| `doctor` | ✅ | ✅ | ✅ |
| `internal_admin` / `super_admin` | ✅ | ✅ | ✅ |
| `medical_reviewer` | ✅ | ✅ | ✅ |
| `ai_service` | ❌ 403 | ❌ 403 | ❌ 403 |
| `clinic_admin` | ❌ 403 | ❌ 403 | ❌ 403 |

---

### 11.1 List Own Notifications

**GET** `/api/v1/notifications`

Returns the caller's own notifications, newest-first.

#### Query Parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `unread_only` | boolean | `false` | When `true`, returns only unread notifications |
| `limit` | integer | 20 (max 100) | |
| `offset` | integer | 0 | |

#### Response `200 OK`

```json
[
  {
    "id": "i1j2k3l4-m5n6-7890-ijkl-678901234567",
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "type": "reminder",
    "title": "Nhắc đo đường huyết",
    "body": "Đã đến giờ đo đường huyết buổi sáng của bạn.",
    "is_read": false,
    "read_at": null,
    "created_at": "2026-06-18T01:00:00+00:00",
    "metadata_": null
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `id` | string (UUID) | Notification ID |
| `user_id` | string (UUID) | The recipient user's ID |
| `type` | string | Notification type (e.g. `"reminder"`, `"alert"`, `"info"`) |
| `title` | string | Short notification title |
| `body` | string | Full notification body |
| `is_read` | boolean | `false` = unread |
| `read_at` | string (ISO8601) or null | Timestamp when marked read |
| `created_at` | string (ISO8601) | |
| `metadata_` | object or null | Optional structured metadata |

---

### 11.2 Mark Notification as Read

**PATCH** `/api/v1/notifications/{notification_id}/read`

Mark a single notification as read. Ownership is enforced — the notification must belong to the calling user.

#### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `notification_id` | string (UUID) | Notification ID |

#### Response `200 OK`

Returns the updated notification object (same shape as GET list item).

#### Error Codes

| HTTP | Condition |
|---|---|
| `403 Forbidden` | Notification belongs to a different user |
| `404 Not Found` | Notification not found |

---

### 11.3 Mark All Notifications as Read

**POST** `/api/v1/notifications/read-all`

Mark all unread notifications for the calling user as read.

#### Response `200 OK`

```json
{
  "count": 5
}
```

`count` is the number of notifications that were marked as read.

---

## 12. AI Triage (Feature Flag Gated)

> ⚠️ **Feature Flag:** This endpoint is **disabled by default** (`FEATURE_AI_TRIAGE=false`). It is only enabled when:
> 1. The server environment variable `FEATURE_AI_TRIAGE=true` is set, AND
> 2. Medical Board approval has been obtained.
>
> **Client responsibility:** Before displaying the triage feature to users, the frontend should check whether triage is available. The recommended approach is to attempt the call and handle a `503 Service Unavailable` response gracefully (show "Feature not available" UI).
>
> **Patient-safe output:** The triage response is designed for patients. It uses plain language (`message`) and never exposes raw clinical scores. The app **must not** display `risk_level` raw values (e.g. `"high"`) without UX framing — use the `message` field for patient display.

Requires: `Authorization: Bearer <access_token>`

### RBAC

| Role | Access |
|---|---|
| `patient` | ✅ (result persisted to triage history automatically) |
| `doctor` / `clinic_admin` / `internal_admin` / `super_admin` | ✅ (not persisted) |
| `ai_service` | ❌ 403 |

---

### 12.1 Submit Triage Input

**POST** `/api/v1/ai/triage`

Submit symptom text and optional vitals for AI-powered triage assessment. The rule engine runs first (deterministic safety rules), then AI enhances the message.

#### Request Body

```json
{
  "symptom_text": "Đau ngực, khó thở khi lên cầu thang trong 2 ngày qua",
  "vitals": [
    { "metric_type": "heart_rate", "value": 95 },
    { "metric_type": "spo2", "value": 96 }
  ],
  "reported_severity": 7
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `symptom_text` | string | ❌ | Free-text symptom description |
| `vitals` | array of VitalIn | ❌ | Recent vital measurements to include |
| `reported_severity` | integer | ❌ | Patient self-reported severity 1–10 |

**VitalIn object:**

| Field | Type | Required |
|---|---|---|
| `metric_type` | string | ✅ |
| `value` | float | ✅ |

#### Response `200 OK`

```json
{
  "risk_level": "high",
  "action": "seek_emergency_care",
  "message": "Các triệu chứng của bạn có thể cần chăm sóc y tế khẩn cấp. Vui lòng liên hệ bác sĩ hoặc đến cơ sở y tế ngay.",
  "red_flags": [
    "Chest pain",
    "Shortness of breath"
  ],
  "escalated_to_doctor": true,
  "rule_forced": true
}
```

| Field | Type | Notes |
|---|---|---|
| `risk_level` | string | `"low"`, `"moderate"`, `"high"`, `"critical"` — **do not display raw to patient** |
| `action` | string | Action code: `"monitor"`, `"consult_doctor"`, `"seek_emergency_care"` |
| `message` | string | **Patient-safe plain language explanation** — use this for UI display |
| `red_flags` | array of string | Specific concerning symptoms identified |
| `escalated_to_doctor` | boolean | Whether the system auto-escalated to the doctor |
| `rule_forced` | boolean | Whether a deterministic safety rule overrode AI output |

#### Error Codes

| HTTP | Condition |
|---|---|
| `503 Service Unavailable` | `FEATURE_AI_TRIAGE=false` (feature not enabled) |
| `429 Too Many Requests` | LLM rate limit exceeded; includes `Retry-After` header |
| `422 Unprocessable Entity` | Validation error |

---

## 13. Triage History

Requires: `Authorization: Bearer <access_token>`

### RBAC

| Role | Access |
|---|---|
| `patient` (own) | ✅ |
| `doctor` (consent-gated, scope=`profile`) | ✅ |
| `internal_admin` / `super_admin` | ✅ |
| `ai_service` / `clinic_admin` | ❌ 403 |

---

### 13.1 List Triage History

**GET** `/api/v1/patients/{patient_id}/triage-history`

Returns past triage sessions newest-first (paginated). Only sessions submitted by the patient role are persisted; doctor/admin sessions are not stored.

#### Query Parameters

| Parameter | Type | Default |
|---|---|---|
| `limit` | integer | 20 (max 100) |
| `offset` | integer | 0 |

#### Response `200 OK`

```json
{
  "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "total": 3,
  "items": [
    {
      "id": "j1k2l3m4-n5o6-7890-jklm-789012345678",
      "patient_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "symptom_text": "Đau ngực, khó thở khi lên cầu thang trong 2 ngày qua",
      "risk_level": "high",
      "action": "seek_emergency_care",
      "red_flags": ["Chest pain", "Shortness of breath"],
      "message": "Các triệu chứng của bạn có thể cần chăm sóc y tế khẩn cấp.",
      "created_at": "2026-06-18T03:30:00+00:00"
    }
  ]
}
```

---

## 14. ID Resolution Guide

This is a **critical** section. Confusing `user_id` with `patient_profile_id` is the most common integration mistake.

### ID Types at a Glance

| ID Name | Source | Format | Description |
|---|---|---|---|
| `user_id` | JWT `sub` claim; login/register response | UUID string | The User account identifier. Used for auth, notifications |
| `patient_profile_id` | `PatientProfile.id` in DB; returned by profile endpoints | UUID string | The clinical profile identifier. Used in ALL `/patients/{id}/...` endpoints |

These are **different UUIDs**. A `user_id` cannot be used in place of `patient_profile_id` in API calls.

---

### How to Resolve `patient_profile_id` After Login

There is no single dedicated "get my patient profile ID" endpoint. The recommended resolution pattern is:

**Step 1:** Call `GET /api/v1/auth/me` → receive `user_id`.

**Step 2:** Call `GET /api/v1/patients/{patient_id}/profile` — but you need the `patient_profile_id` first. The resolution flow is:

> The profile endpoint returns `{ "id": "<patient_profile_id>", "user_id": "<user_id>" }`. The link is established at registration when a `PatientProfile` record is created with `user_id` set to the registering user's ID.

**Recommended approach:** After a successful login, the frontend should cache the `patient_profile_id` in the app session. This can be obtained by calling `GET /api/v1/auth/me` and then querying for the profile using the pattern below.

---

### Concrete Example: First-Login Flow

```
Step 1: Register
  POST /api/v1/auth/register
  → Response: { "user_id": "USR-001", "access_token": "...", ... }
  → Store: user_id = "USR-001", tokens

Step 2: Get current user to confirm identity
  GET /api/v1/auth/me
  Authorization: Bearer <access_token>
  → Response: { "id": "USR-001", "email": "...", "role": "patient" }

Step 3: The backend auto-creates a PatientProfile on registration.
  To get the patient_profile_id, the app must query the profile.
  
  At registration time, the backend creates PatientProfile with user_id = "USR-001".
  
  The app needs to discover PATIENT-PROFILE-001. Options:
  
  Option A (if you store patient_profile_id in your app state from a previous session):
    Use the cached patient_profile_id directly.
  
  Option B (first login, no cache):
    The backend should provide a "me profile" convenience endpoint.
    Workaround: After registration, the server returns user_id in the TokenResponse.
    The frontend should call GET /api/v1/patients/{user_id}/profile and expect a 404
    or 403 — then prompt the user to complete their profile setup.
    
    ** Current implementation note: **
    The PatientProfile is NOT automatically created at registration.
    A SUPER_ADMIN or INTERNAL_ADMIN must create the PatientProfile record linked
    to the user. Once created, the patient_profile_id is stored in the Profile
    record's `id` field (returned by GET /patients/{patient_id}/profile).
    
    ** Recommended integration pattern: **
    Store patient_profile_id in app local storage after the first successful
    GET /patients/{patient_id}/profile call. Refresh it on next login.

Step 4: Access patient data using patient_profile_id
  GET /api/v1/patients/PATIENT-PROFILE-001/profile
  GET /api/v1/patients/PATIENT-PROFILE-001/metrics
  GET /api/v1/patients/PATIENT-PROFILE-001/metabolic-scores
  ... etc
```

### Summary Diagram

```
[Login]
  ↓
TokenResponse.user_id = "USR-001"   ← User.id (auth identity)
  ↓
GET /auth/me → id = "USR-001"
  ↓
[App needs patient_profile_id]
  ↓
GET /patients/{patient_profile_id}/profile
  → id = "PROF-001"          ← PatientProfile.id (clinical identity)
  → user_id = "USR-001"      ← Links back to the user

Store PROF-001 as patient_profile_id in app session.
Use PROF-001 in all /patients/{patient_id}/... API calls.
```

---

## 15. Error Codes Reference

All error responses follow this structure:

```json
{
  "detail": "Human-readable error message or validation detail array"
}
```

For validation errors (422), `detail` is an array:

```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

### HTTP Error Code Reference

| Code | Name | When It Occurs | Frontend Action |
|---|---|---|---|
| `400 Bad Request` | Bad Request | Malformed request body | Fix request format |
| `401 Unauthorized` | Unauthorized | Token expired, missing, or revoked | Redirect to login; attempt refresh first |
| `403 Forbidden` | Forbidden | RBAC check failed (wrong role, consent not granted, ownership mismatch) | Show "Access denied"; do not retry |
| `404 Not Found` | Not Found | Resource (patient, metric, notification, etc.) does not exist | Show "Not found" state |
| `409 Conflict` | Conflict | Resource already exists (e.g. duplicate email on register) | Show specific error message |
| `422 Unprocessable Entity` | Validation Error | Request body fails validation rules | Extract `detail` array and show field errors |
| `423 Locked` | Locked | Account locked due to repeated login failures | Show lockout message with cooldown duration |
| `429 Too Many Requests` | Rate Limit | Request rate exceeded; check `Retry-After` header | Back off and retry after `Retry-After` seconds |
| `503 Service Unavailable` | Service Unavailable | Feature flag disabled (`FEATURE_AI_TRIAGE=false`), DB degraded, or maintenance mode | Show "Feature unavailable" message; do not retry in a loop |

### Token Lifecycle Error Handling

```
Request → 401 Unauthorized
  ↓
Try: POST /auth/refresh with stored refresh_token
  ↓ success
Store new access_token + refresh_token
Retry original request
  ↓ fail (401 on refresh itself)
Clear all stored tokens
Redirect user to login screen
```

---

## 16. Security Notes for Frontend

### Token Storage Rules

| Token | Storage Location | Reason |
|---|---|---|
| `access_token` | **In-memory only** (e.g. React state, Zustand store) | Prevents XSS exfiltration via `localStorage` |
| `refresh_token` | **httpOnly cookie** (server-set) OR in-memory only | `httpOnly` prevents JavaScript access; protects against XSS |

> **Never store tokens in `localStorage` or `sessionStorage`.** These are accessible to any JavaScript running on the page, including injected scripts.

### Token TTLs

| Token | TTL | Notes |
|---|---|---|
| `access_token` | **15 minutes** | Short-lived; refresh proactively before expiry |
| `refresh_token` | **7 days** | Token rotation: a new refresh token is issued on each refresh |

### Request Requirements

Every call to a protected endpoint (all endpoints except login/register/refresh) must include:

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Proactive Token Refresh

Do not wait for a `401` before refreshing. Implement proactive refresh:

1. Track `access_token` expiry from the `exp` JWT claim.
2. Refresh ~60 seconds before expiry.
3. On `401`, attempt one refresh, then redirect to login on failure.

### MFA Handling

If `mfa_enabled: true` in `/auth/me` response:
- The login request must include `totp_code` (6-digit TOTP).
- If TOTP device is lost, `backup_code` can be used instead.
- The `mfa: true` field in the token response confirms MFA was satisfied.

### PHI Fields

The following fields contain Protected Health Information and are encrypted at rest on the server:

- `PatientProfile.known_conditions`
- `PatientProfile.allergies`

The frontend must:
- Not log these fields to analytics or error reporting services.
- Not cache them in browser storage beyond the active session.
- Mask them in UI when appropriate (e.g. blur on screenshot).

### HTTPS

All API communication must use HTTPS (TLS 1.2+). HTTP is not supported in production.

### Rate Limiting Headers

When `429 Too Many Requests` is received, check the `Retry-After` header:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 30
```

Back off for the indicated number of seconds before retrying.

---

*End of contract. For implementation questions, refer to `docs/agent/PA02_IMPLEMENTATION_REPORT.md`.*
