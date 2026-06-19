# PA-07 — Backend Contract Verification Report

**Date:** 2026-06-19  
**Task:** Verify backend support for Symptoms, Medications, Care Plan, AI Chat  
**Scope:** Endpoint inventory · Missing fields · Schema inconsistencies · Frontend integration guide  
**Analyst:** OpenClaw (Claude Code)  
**No frontend code changes.**

---

## 1. Endpoint Inventory

### 1.1 Symptoms

| Contract endpoint | HTTP | Backend route | Status |
|---|---|---|---|
| `POST /patients/{id}/symptoms` | POST | `/patients/{patient_id}/symptoms` | ✅ Exists |
| `GET /patients/{id}/symptoms` | GET | `/patients/{patient_id}/symptoms` | ✅ Exists |

**Backend file:** `app/api/v1/routes/patients.py` → `create_symptom_log`, `list_symptom_logs`  
**Schema:** `app/schemas/symptom.py` → `SymptomLogCreate`, `SymptomLogOut`  
**Model:** `app/models/clinical.py` → `SymptomLog`  
**RBAC:** PATIENT (own), DOCTOR (consent-gated scope=`profile`), INTERNAL_ADMIN, SUPER_ADMIN; AI_SERVICE + CLINIC_ADMIN → 403 ✅

---

### 1.2 Medications

| Contract endpoint | HTTP | Backend route | Status |
|---|---|---|---|
| `POST /patients/{id}/medications` | POST | `/patients/{patient_id}/medications` | ✅ Exists |
| `GET /patients/{id}/medications` | GET | `/patients/{patient_id}/medications` | ✅ Exists |
| `DELETE /patients/{id}/medications/{med_id}` | DELETE | `/patients/{patient_id}/medications/{med_id}` | ✅ Exists |

**Backend file:** `app/api/v1/routes/patients.py` → `add_medication`, `list_medications`, `delete_medication`  
**Schema:** `app/schemas/medication.py` → `MedicationCreate`, `MedicationOut`  
**Model:** `app/models/clinical.py` → `Medication`  
**RBAC:** PATIENT (own), DOCTOR (consent-gated, no DELETE); INTERNAL_ADMIN, SUPER_ADMIN; AI_SERVICE + CLINIC_ADMIN → 403 ✅  
**Clinical safety:** DOCTOR → 403 on DELETE (enforced in route) ✅

---

### 1.3 Care Plan

| Contract endpoint | HTTP | Backend route | Status |
|---|---|---|---|
| `GET /patients/{id}/care-plans` | GET | `/care_plans?patient_id={id}` | ⚠️ URL MISMATCH — see §2.1 |
| `GET /care_plans/{id}` | GET | `/care_plans/{care_plan_id}` | ✅ Exists |
| `POST /care_plans` | POST | `/care_plans` | ✅ Exists (doctor/admin only) |
| `PATCH /care_plans/{id}` | PATCH | `/care_plans/{care_plan_id}` | ✅ Exists |
| `POST /care_plans/{id}/approve` | POST | `/care_plans/{care_plan_id}/approve` | ✅ Exists |

**Backend file:** `app/api/v1/routes/care_plans.py`  
**Schema:** `app/schemas/care.py` → `CarePlanCreate`, `CarePlanUpdate`, `CarePlanOut`, `CarePlanApprove`  
**Model:** `app/models/care.py` → `CarePlan`, `CarePlanStatus`  
**RBAC (read):** PATIENT (own), DOCTOR (assigned), CLINIC_ADMIN (assigned), INTERNAL_ADMIN, SUPER_ADMIN ✅  
**RBAC (write):** DOCTOR + admins only; AI_SERVICE cannot approve ✅  

**Note:** Contract §1 lists Care Plan as **out of scope** for patient app (`POST /care_plans`, `POST /encounters` listed as out of scope). The patient app should only **read** their own care plans.

---

### 1.4 AI Chat / AI Triage

| Contract endpoint | HTTP | Backend route | Status |
|---|---|---|---|
| `POST /ai/chat` | POST | `/ai/chat` | ✅ Exists |
| `POST /ai/triage` | POST | `/ai/triage` | ✅ Exists (feature-flag gated) |
| `GET /patients/{id}/triage-history` | GET | `/patients/{patient_id}/triage-history` | ✅ Exists |
| `POST /ai/explain` | POST | `/ai/explain` | ✅ Exists |
| `POST /ai/metabolic-score` | POST | `/ai/metabolic-score` | ✅ Exists |

**Backend file:** `app/api/v1/routes/ai.py`  
**Schema:** `app/schemas/ai.py` → `ChatRequest/Response`, `TriageRequest/Response`, `AiExplainRequest/Response`  

**Feature flag:** `POST /ai/triage` → guarded by `FEATURE_AI_TRIAGE` env var; returns `503` when disabled. The current backend implementation calls `triage.assess()` directly **without checking the feature flag**. This is a gap — see §2.3.

---

### 1.5 Supporting Domain (already verified in earlier tasks, shown for completeness)

| Domain | Route | Status |
|---|---|---|
| Health Metrics | `GET/POST /patients/{id}/metrics` | ✅ |
| Metric Trend | `GET /patients/{id}/metrics/trend` | ✅ |
| Metabolic Score History | `GET /patients/{id}/metabolic-scores` | ✅ |
| Lab Documents | `GET/POST /patients/{id}/lab-documents` | ✅ |
| Notifications | `GET /notifications`, `PATCH /notifications/{id}/read`, `POST /notifications/read-all` | ✅ |
| Consent | `GET/POST/DELETE /patients/{id}/consents` | ✅ |
| Nutrition | `GET/POST /patients/{id}/nutrition` | ✅ |
| Patient Profile | `GET/PATCH /patients/{id}/profile` | ✅ |

---

## 2. Missing Fields & Schema Inconsistencies

### 2.1 ⚠️ [MISMATCH] Care Plan URL — frontend vs backend

**Severity: P1 frontend bug**

| | Path |
|---|---|
| `patient.ts` call | `GET /patients/${patientId}/care-plans` |
| Backend route | `GET /care_plans?patient_id=${patientId}` (prefix `/care_plans`) |

The backend uses a standalone `/care_plans` router, not a nested `/patients/{id}/care-plans` path. The patient app frontend at `frontend/src/lib/api/patient.ts:350`:

```typescript
return api.get<CarePlan[]>(`/patients/${patientId}/care-plans`)
// → 404 Not Found
```

**Correct call:**
```typescript
return api.get<CarePlanListResponse>(`/care_plans?patient_id=${patientId}`)
```

**Note:** Backend `list_care_plans` returns `list[CarePlanOut]` (plain array), not a paginated wrapper. Frontend type `CarePlan[]` is correct but is missing patient navigation fields — see §2.5.

---

### 2.2 ⚠️ [MISMATCH] Symptom Log URL — `symptom-logs` vs `symptoms`

**Severity: P1 frontend bug**

| | Path |
|---|---|
| `patient.ts` calls | `GET /patients/${id}/symptom-logs` and `POST /patients/${id}/symptom-logs` |
| Backend routes | `GET /patients/{id}/symptoms` and `POST /patients/{id}/symptoms` |

```typescript
// patient.ts:227 — wrong path
return api.get<SymptomLogListResponse>(`/patients/${patientId}/symptom-logs${qs}`)
// patient.ts:239 — wrong path
return api.post<SymptomLog>(`/patients/${patientId}/symptom-logs`, data)
```

**Correct paths:**
```
GET  /api/v1/patients/{patient_id}/symptoms
POST /api/v1/patients/{patient_id}/symptoms
```

---

### 2.3 ⚠️ [MISMATCH] Notifications URL — patient-scoped vs user-scoped

**Severity: P1 frontend bug**

| | Path |
|---|---|
| `patient.ts` calls | `GET /patients/${id}/notifications/{notifId}` |
| Backend routes | `GET /notifications`, `PATCH /notifications/{id}/read` |

The backend uses a **user-scoped** notification endpoint (no `patient_id` in path). It returns notifications for the calling user based on JWT identity:

```typescript
// patient.ts:381-390 — wrong paths
return api.get<NotificationListResponse>(
  `/patients/${patientId}/notifications...`  // → 404
)
return api.patch(
  `/patients/${patientId}/notifications/${notificationId}`, ...  // → 404
)
```

**Correct calls:**
```typescript
// GET
api.get<NotificationOut[]>('/notifications?limit=20&unread_only=false')
// PATCH mark read
api.patch(`/notifications/${notificationId}/read`, {})
```

**Backend response shape is also different:**  
`patient.ts` expects `NotificationListResponse { patient_id, total, unread_count, items[] }` but backend returns a plain `list[NotificationOut]` array. See §2.6.

---

### 2.4 ⚠️ [MISMATCH] Consent Revoke — PATCH vs DELETE

**Severity: P1 frontend bug**

| | Method | Path |
|---|---|---|
| `patient.ts:411` | `PATCH /patients/${id}/consents/${consentId}` with `{ status: 'revoked' }` |
| Backend | `DELETE /patients/{id}/consents/{consent_id}` |

The backend `revoke_consent` uses HTTP `DELETE`, not `PATCH`. The PATCH call will 404 or 405.

**Correct call:**
```typescript
api.delete(`/patients/${patientId}/consents/${consentId}`)
// response: { message: "revoked" }
```

---

### 2.5 ⚠️ [MISMATCH] `AiExplainResponse` field name — `explanation` vs `plain_language_summary`

**Severity: P1 frontend bug**

| | Field |
|---|---|
| `patient.ts` TypeScript interface (line 191) | `explanation: string` |
| Backend `AiExplainResponse` schema | `plain_language_summary: str` |

The frontend `ai-assistant/page.tsx:49` renders `response.explanation`, but the backend response JSON key is `plain_language_summary`. The UI will always show `undefined`.

**Backend actual response:**
```json
{
  "explanation_type": "metabolic_score",
  "plain_language_summary": "...",
  "safety_level": "informational",
  "disclaimer": "...",
  "generated_at": "..."
}
```

**Fix in `patient.ts`:**
```typescript
export interface AiExplainResponse {
  explanation_type: string
  plain_language_summary: string   // was: explanation: string
  safety_level: 'informational'
  disclaimer: string
  generated_at: string
}
```

---

### 2.6 [INFO] Notification response is array, not paginated object

**Severity: P2 — visual/type mismatch**

`patient.ts` defines `NotificationListResponse { patient_id, total, unread_count, items }` but backend returns `list[NotificationOut]` (plain array). There is no `unread_count` in the GET response. Frontend code that reads `.unread_count` will get `undefined`.

**Workaround:** Call `GET /notifications?unread_only=true` to get unread count as `list.length`.

---

### 2.7 [INFO] Metabolic Score endpoint — frontend calls wrong path

**Severity: P2 — edge case**

`patient.ts:125` calls `GET /patients/${id}/metabolic-score?limit=1` (singular, with query param style), but backend route is `GET /patients/{id}/metabolic-scores` (plural, `limit` and `offset` as standard query params).

Also: backend returns `RiskScoreHistoryResponse { patient_id, total, items[], trend }` but `patient.ts` casts response directly as `MetabolicScore[]`.

---

### 2.8 [INFO] Symptom schema field differences

**Severity: P2 — data model drift**

The contract (§7) defines `description` (string), `severity` (int 1-10), `reported_at`. The backend matches this.

However, `patient.ts` SymptomLog interface includes additional fields not in backend schema:
```typescript
symptoms: string[]    // array — backend has description: string (single text field)
severity: 'mild' | 'moderate' | 'severe'  // backend uses int 0-10
duration_hours: number | null             // not in backend model
triage_result: 'routine' | 'soon' | 'urgent' | 'emergency' | null  // not in backend
```

These appear to be from an older/alternative design. The backend schema is simpler and does not support these fields. Frontend symptom log form must use `description` (string) + `severity` (int 0-10).

---

### 2.9 [INFO] Medication schema — frontend has extra fields not in backend

**Severity: P2**

`patient.ts` Medication interface includes:
```typescript
dosage: string          // backend: dose (field name differs!)
frequency: string       // not in backend model
start_date: string      // not in backend model
end_date: string | null // not in backend model
status: 'active' | 'completed' | 'discontinued'  // not in backend
next_dose_at: string | null  // not in backend
prescribed_by: string | null // not in backend
```

Backend `Medication` model only has: `name`, `dose`, `note`, `created_at`, `deleted_at` (soft delete).

The frontend currently expects rich medication data that the backend doesn't store. Frontend medication screens need to be designed against the **backend** schema (`name`, `dose`, `note`).

---

### 2.10 [INFO] AI triage — feature flag not enforced in backend

**Severity: P2 — production safety gap**

The contract states `POST /ai/triage` should return 503 when `FEATURE_AI_TRIAGE=false`. The backend route currently calls `triage.assess()` unconditionally without checking `feature_flags.FEATURE_AI_TRIAGE`. This is a backend gap — separate backend task.

---

### 2.11 [INFO] Care Plan `CarePlanOut` schema — patient-facing fields missing

**Severity: P2**

Backend `CarePlanOut` includes:
```python
id, patient_id, encounter_id, title, content, status,
approved_by_doctor_id, approved_at, ai_generated, version,
created_at, updated_at
```

The `patient.ts` CarePlan interface includes `items: CarePlanItem[]` (task checklist), `doctor_name`, `description`. These are **not in the backend schema** — `CarePlan` model has no `items` relation or `doctor_name` computed field in the current implementation.

---

## 3. Summary Table

| # | Finding | Severity | Domain | Fix Location |
|---|---|---|---|---|
| 2.1 | Care Plan URL: `/patients/{id}/care-plans` → should be `/care_plans?patient_id=` | **P1** | Care Plan | `patient.ts:350` |
| 2.2 | Symptom URL: `symptom-logs` → should be `symptoms` | **P1** | Symptoms | `patient.ts:227,239` |
| 2.3 | Notifications URL: `/patients/{id}/notifications` → should be `/notifications` | **P1** | Notifications | `patient.ts:381,390` |
| 2.4 | Consent revoke: `PATCH` → should be `DELETE` | **P1** | Consent | `patient.ts:411` |
| 2.5 | AiExplainResponse: `explanation` → should be `plain_language_summary` | **P1** | AI Chat | `patient.ts:191` + `ai-assistant/page.tsx:49` |
| 2.6 | Notifications response: expects paginated object, backend returns array | P2 | Notifications | `patient.ts` types |
| 2.7 | Metabolic score: wrong endpoint path + response cast | P2 | Metabolic | `patient.ts:125` |
| 2.8 | Symptom interface: `symptoms[]`, `severity string`, `duration_hours` not in backend | P2 | Symptoms | `patient.ts` types |
| 2.9 | Medication interface: `dosage`/`frequency`/`status`/`start_date` not in backend | P2 | Medications | `patient.ts` types |
| 2.10 | AI triage feature flag not enforced backend-side | P2 | AI Triage | `routes/ai.py` |
| 2.11 | CarePlan `items[]` / `doctor_name` not in backend schema | P2 | Care Plan | `patient.ts` types |

**P1 count: 5 — all in frontend API client (`patient.ts`). Zero backend P1s.**

---

## 4. Backend Completeness Assessment

| Domain | Backend Status | RBAC | Schema | Missing |
|---|---|---|---|---|
| Symptoms | ✅ Complete | ✅ Correct | ✅ Correct | — |
| Medications | ✅ Complete | ✅ Correct | ✅ Correct | Rich fields (freq, dates, status) not built |
| Care Plan (read) | ✅ Complete | ✅ Correct | ✅ Correct | `items[]` / `doctor_name` not in model |
| AI Chat (`/ai/chat`) | ✅ Exists | ✅ Correct | ✅ Correct | No `ai_chat` in patient.ts (page calls `/ai/explain` instead) |
| AI Triage | ✅ Exists | ✅ Correct | ✅ Correct | Feature flag check missing (backend gap) |
| AI Explain | ✅ Exists | ✅ PATIENT-only | ⚠️ Field name mismatch | `plain_language_summary` vs `explanation` |
| Notifications | ✅ Exists | ✅ Correct | ⚠️ Response shape mismatch | No `unread_count` in list response |
| Consent | ✅ Exists | ✅ Correct | ✅ Correct | Revoke is DELETE not PATCH |

**All four requested domains have backend support. Every P1 is a frontend API client bug, not a missing backend endpoint.**

---

## 5. Frontend Integration Guide

### 5.1 Correct API paths (fix in `frontend/src/lib/api/patient.ts`)

```typescript
// ── Symptoms ──────────────────────────────────────────────────────────────────
// WRONG:  /patients/${id}/symptom-logs
// CORRECT:
api.get(`/patients/${patientId}/symptoms?limit=${limit}`)
api.post(`/patients/${patientId}/symptoms`, {
  description: string,   // free text, max 2048 chars
  severity: number,      // int 0–10 (NOT 'mild'|'moderate'|'severe')
  reported_at?: string   // ISO8601, optional
})

// ── Medications ───────────────────────────────────────────────────────────────
// Path is correct. Fields to use:
api.post(`/patients/${patientId}/medications`, {
  name: string,          // required
  dose?: string,         // NOT 'dosage'
  note?: string
})
// GET response: { patient_id, total, items: [{ id, patient_id, name, dose, note, created_at }] }

// ── Care Plans ────────────────────────────────────────────────────────────────
// WRONG:  /patients/${id}/care-plans
// CORRECT:
api.get(`/care_plans?patient_id=${patientId}`)
// Returns: CarePlanOut[] (plain array, not paginated)

// ── Notifications ─────────────────────────────────────────────────────────────
// WRONG:  /patients/${id}/notifications
// CORRECT:
api.get(`/notifications?limit=20&unread_only=false`)
// Returns: NotificationOut[] (plain array, no unread_count)
// Mark read:
api.patch(`/notifications/${notificationId}/read`, {})  // body empty

// ── Consent revoke ────────────────────────────────────────────────────────────
// WRONG:  api.patch(`.../consents/${id}`, { status: 'revoked' })
// CORRECT:
api.delete(`/patients/${patientId}/consents/${consentId}`)
// Returns: { message: "revoked" }

// ── AI Explain ────────────────────────────────────────────────────────────────
// Request unchanged. Fix response type:
interface AiExplainResponse {
  explanation_type: string
  plain_language_summary: string  // was: explanation
  safety_level: 'informational'
  disclaimer: string
  generated_at: string
}
// Usage in ai-assistant/page.tsx: response.plain_language_summary (not response.explanation)
```

### 5.2 NotificationOut schema (backend)

```typescript
interface NotificationOut {
  id: string
  user_id: string
  type: string            // e.g. 'reminder', 'alert', 'info'
  title: string
  body: string
  is_read: boolean        // NOT 'read'
  read_at: string | null
  created_at: string
  metadata_: object | null
}
```

### 5.3 ConsentOut schema (backend)

```typescript
interface ConsentOut {
  id: string
  patient_id: string
  data_scope: string      // e.g. 'profile', 'lab'
  granted_to: string      // doctor user_id
  // No: doctor_name, status, granted_at, revoked_at in basic ConsentOut
}
```

### 5.4 CarePlanOut schema (backend)

```typescript
interface CarePlanOut {
  id: string
  patient_id: string
  encounter_id: string | null
  title: string
  content: string | null   // NOT description; NOT items[]
  status: string           // 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED' | 'ACTIVE' | 'SUPERSEDED' | 'ARCHIVED' | 'REJECTED'
  approved_by_doctor_id: string | null
  approved_at: string | null
  ai_generated: boolean
  version: number
  created_at: string
  updated_at: string
}
```

### 5.5 SymptomLogOut schema (backend)

```typescript
interface SymptomLogOut {
  id: string
  patient_id: string
  description: string      // single text field, not array
  severity: number | null  // 0–10 integer
  reported_at: string
  created_at: string
  // No: symptoms[], duration_hours, triage_result
}
```

### 5.6 MedicationOut schema (backend)

```typescript
interface MedicationOut {
  id: string
  patient_id: string
  name: string
  dose: string | null      // NOT dosage
  note: string | null
  created_at: string
  // No: frequency, start_date, end_date, status, next_dose_at, prescribed_by
}
```

### 5.7 AI Chat (`POST /ai/chat`)

The `ai-assistant/page.tsx` currently uses `POST /ai/explain` (general explanation endpoint). If a real chat-style interface is needed, `POST /ai/chat` exists and accepts:

```typescript
// Request
{ message: string, intent?: string }  // intent default: "health_assistant"
// Response
{
  text: string
  intent: string
  risk_level: string
  escalated_to_doctor: boolean
  safety_flags: string[]
  blocked: boolean
  model_used: string
  cached: boolean
}
```

Note: `POST /ai/chat` uses the guardrail but is NOT PATIENT-only (any authenticated role). For patient MVP, using `/ai/explain` is the correct safe approach (PATIENT-only RBAC).

### 5.8 Recommended frontend fix priority

1. **Fix `patient.ts` P1 URL bugs** (5 fixes, ~30 min):
   - `symptom-logs` → `symptoms`
   - `/patients/{id}/care-plans` → `/care_plans?patient_id={id}`
   - `/patients/{id}/notifications` → `/notifications`
   - Consent revoke: `PATCH` → `DELETE`
   - `AiExplainResponse.explanation` → `plain_language_summary`

2. **Fix TypeScript interfaces** (P2, ~1h):
   - `SymptomLog`: remove `symptoms[]`, `duration_hours`, `triage_result`; replace `severity string` with `severity: number | null`
   - `Medication`: rename `dosage` → `dose`; remove `frequency`, `start_date`, `end_date`, `status`, `next_dose_at`, `prescribed_by`
   - `Notification`: use `is_read` not `read`; remove `unread_count` from list response type
   - `CarePlan`: remove `items`, `description`, `doctor_name`; add `content`; fix `status` enum to uppercase values

3. **Backend gap** (separate task):
   - Add feature flag check in `POST /ai/triage` → return `503` when `FEATURE_AI_TRIAGE=false`

---

## 6. Backend Gaps Requiring New Work

No critical missing endpoints found. All four domains (Symptoms, Medications, Care Plan, AI) have working backend implementations.

However, these backend enhancements may be needed for a richer patient experience:

| Gap | Domain | Priority |
|---|---|---|
| Feature flag check in `POST /ai/triage` | AI Triage | P2 backend |
| `unread_count` in notification list response | Notifications | P2 backend |
| Rich medication fields: `frequency`, `start_date`, `end_date`, `status` | Medications | Future scope |
| Care plan items checklist (`CarePlanItem[]`) | Care Plan | Future scope |
| `doctor_name` computed field in CarePlanOut | Care Plan | Future scope |

---

*Report complete. 5 P1 frontend fixes required in `patient.ts` before symptoms/medications/care-plan/AI screens can function correctly.*
