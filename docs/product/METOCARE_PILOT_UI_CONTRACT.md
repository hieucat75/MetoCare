# MetoCare Pilot — UI/API Contract

> **Document:** Screen-to-API contract for pilot UI development  
> **Branch:** `feature/t18b-api-contract-docs`  
> **Base URL:** `https://<host>/api/v1`  
> **Auth:** Bearer token (JWT) in `Authorization` header on all protected endpoints  
> **Last updated:** 2026-06-18  
> **Status:** READY FOR CONSISTENCY CHECK

---

## Table of Contents

1. [Global Conventions](#1-global-conventions)
2. [Patient Journey Screens](#2-patient-journey-screens)
3. [Doctor Journey Screens](#3-doctor-journey-screens)
4. [Admin Journey Screens](#4-admin-journey-screens)
5. [Permission Matrix](#5-permission-matrix)
6. [Gap List](#6-gap-list)
7. [Standard Error Codes Reference](#7-standard-error-codes-reference)

---

## 1. Global Conventions

### 1.1 Authentication Flow

All endpoints (except `/auth/register`, `/auth/login`, `/auth/refresh`, `/health`, `/info`) require:

```
Authorization: Bearer <access_token>
```

Access tokens expire per `settings.access_token_expire_minutes`. Use `POST /auth/refresh` to rotate before expiry.

### 1.2 Pagination Envelope

List endpoints that support pagination use query params `?limit=20&offset=0` and return:

```json
{
  "patient_id": "<uuid>",
  "total": 42,
  "items": [ ... ]
}
```

Exceptions: endpoints that return `list[...]` directly (AI sessions, care plans, encounters) do not wrap in an envelope — they return a plain JSON array.

### 1.3 Rate Limiting

| Endpoint scope | Limit |
|----------------|-------|
| `POST /auth/register` | Rate-limited per IP |
| `POST /auth/login` | Rate-limited; account locked after repeated failures (`423 Locked`) |
| `POST /auth/refresh` | Rate-limited per IP |
| `POST /auth/mfa/verify` | Rate-limited per IP |
| `POST /ai/chat` | `429` with `Retry-After` header on LLM saturation |

### 1.4 Role Identifiers

| Token role value | Description |
|-----------------|-------------|
| `patient` | Self-registered patient |
| `doctor` | Licensed physician (provisioned by admin) |
| `internal_admin` | Platform operations admin |
| `super_admin` | Super admin (full access) |
| `ai_service` | Machine-to-machine AI worker (no UI) |
| `clinic_admin` | Clinic staff (limited read) |

---

## 2. Patient Journey Screens

---

### 2.1 Onboarding / Registration

**Screen purpose:** New user creates an account. Role is always `patient` on self-registration.

#### API Calls

| Method | Path | Auth |
|--------|------|------|
| `POST` | `/auth/register` | None |

#### Request

```json
POST /auth/register
{
  "email": "user@example.com",
  "password": "minimum8chars",
  "full_name": "Nguyễn Văn A",
  "role": "patient"
}
```

> `role` is ignored by the server — self-registration always creates `patient`. Send `"patient"` or omit.

#### Response `201`

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer",
  "role": "patient",
  "user_id": "<uuid>",
  "mfa": false
}
```

#### UI States

| State | Behavior |
|-------|----------|
| **Loading** | Disable submit button; show spinner |
| **Success** | Store tokens → redirect to Health Profile setup |
| **409 Conflict** | Email already registered → show "Email đã tồn tại" |
| **422** | Validation error (e.g. password < 8 chars) → field-level error messages |
| **429** | Rate limited → "Thử lại sau ít phút" |

---

### 2.2 Login / MFA

**Screen purpose:** Authenticate returning user. MFA step is conditional on `mfa_enabled`.

#### API Calls

| Method | Path | Auth |
|--------|------|------|
| `POST` | `/auth/login` | None |
| `POST` | `/auth/mfa/enroll` | Bearer (first-time MFA setup) |
| `POST` | `/auth/mfa/verify` | Bearer (confirm TOTP enrollment) |
| `POST` | `/auth/refresh` | None |
| `POST` | `/auth/logout` | Bearer |
| `GET` | `/auth/me` | Bearer |

#### Login Request

```json
POST /auth/login
{
  "email": "user@example.com",
  "password": "password123",
  "totp_code": "123456",      // Required if MFA enabled; omit otherwise
  "backup_code": null          // Alternative to totp_code
}
```

#### Login Response `200`

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer",
  "role": "patient",
  "user_id": "<uuid>",
  "mfa": true
}
```

> **MFA flow:** If `mfa: false` on first login and the user opts into MFA setup, call `POST /auth/mfa/enroll` → display QR code from `provisioning_uri` → prompt TOTP code → `POST /auth/mfa/verify`.

#### MFA Enroll Response `200`

```json
{
  "secret": "<base32>",
  "provisioning_uri": "otpauth://totp/MetoCare:user@example.com?secret=...",
  "backup_codes": ["abc123", "def456", ...]
}
```

#### Token Refresh Request

```json
POST /auth/refresh
{ "refresh_token": "<jwt>" }
```

Returns same `TokenResponse` shape.

#### Logout Request

```json
POST /auth/logout
{ "refresh_token": "<jwt>" }
```

Response `200`: `{ "message": "logged out" }`

#### Current User (`GET /auth/me`)

Response `200`:

```json
{
  "id": "<uuid>",
  "email": "user@example.com",
  "role": "patient",
  "full_name": "Nguyễn Văn A",
  "mfa_enabled": false
}
```

#### UI States

| State | Behavior |
|-------|----------|
| **Loading** | Disable login button |
| **Success (mfa: false)** | Store tokens → redirect to Dashboard |
| **Success (mfa: true)** | TOTP already verified → Dashboard |
| **MFA required** | Server returns `401 "MFA code required"` → show TOTP input |
| **401** | Wrong password → "Email hoặc mật khẩu không đúng" |
| **423 Locked** | Too many failures → "Tài khoản tạm khóa. Liên hệ admin." |
| **Expired access token** | Auto-refresh via `/auth/refresh`; re-attempt on success |

---

### 2.3 Patient Profile (View + Edit)

**Screen purpose:** Patient views and updates their health profile. Doctors with consent can also view.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET` | `/patients/{patient_id}/profile` | Bearer | Read profile |
| `PATCH` | `/patients/{patient_id}/profile` | Bearer | Partial update |

#### GET Response `200`

```json
{
  "id": "<uuid>",
  "user_id": "<uuid>",
  "full_name": "Nguyễn Văn A",
  "dob": "1985-03-20",
  "phone": "0901234567",
  "gender": "male",
  "height_cm": 170.0,
  "weight_kg": 75.5,
  "waist_cm": 88.0,
  "risk_segment": "high",
  "known_conditions": "Tiền tiểu đường",
  "allergies": "Penicillin"
}
```

> **Note:** `address`, `family_history`, `lifestyle_profile` are intentionally excluded (deferred per T12 spec).

#### PATCH Request (partial — send only changed fields)

```json
PATCH /patients/{patient_id}/profile
{
  "weight_kg": 74.0,
  "waist_cm": 86.5
}
```

PATCH Response `200`: same shape as GET.

#### RBAC

| Role | View | Edit |
|------|------|------|
| PATIENT (own) | ✅ | ✅ |
| DOCTOR (consent `scope=profile`) | ✅ | ✅ |
| INTERNAL_ADMIN / SUPER_ADMIN | ✅ | ✅ |
| AI_SERVICE | ❌ 403 | ❌ 403 |
| CLINIC_ADMIN | ❌ 403 | ❌ 403 |

#### UI States

| State | Behavior |
|-------|----------|
| **Loading** | Skeleton loader for profile fields |
| **Empty (no profile)** | Show onboarding prompt to complete profile |
| **Edit mode** | Inline edit form; PATCH on save |
| **403** | "Bạn không có quyền xem hồ sơ này" |
| **404** | Profile not found → redirect to create profile flow |

---

### 2.4 Health Metrics Dashboard (List + Chart)

**Screen purpose:** Patient views tracked health metrics over time with trend lines.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET` | `/patients/{patient_id}/metrics` | Bearer | List metrics; filter by `metric_type` |
| `GET` | `/patients/{patient_id}/metrics/trend` | Bearer | Trend summary for a metric type |

#### List Metrics

```
GET /patients/{patient_id}/metrics?metric_type=fasting_glucose
```

Response `200` — array of:

```json
[
  {
    "id": "<uuid>",
    "metric_type": "fasting_glucose",
    "value": 6.2,
    "unit": "mmol/L",
    "measured_at": "2026-06-15T08:30:00Z",
    "status": "borderline"
  }
]
```

#### Get Trend

```
GET /patients/{patient_id}/metrics/trend?metric_type=fasting_glucose&days=30
```

Response `200`:

```json
{
  "metric_type": "fasting_glucose",
  "days": 30,
  "count": 12,
  "min": 5.4,
  "max": 7.1,
  "avg": 6.2,
  "first": 6.8,
  "last": 5.9,
  "direction": "improving"
}
```

> `direction` values: `"improving"`, `"worsening"`, `"stable"`, `null`

#### Common `metric_type` values

`fasting_glucose`, `hba1c`, `weight`, `bmi`, `waist_cm`, `systolic_bp`, `diastolic_bp`, `triglyceride`, `hdl`, `ldl`, `alt`, `ast`, `creatinine`, `tsh`

#### RBAC

| Role | List | Trend |
|------|------|-------|
| PATIENT (own) | ✅ | ✅ |
| DOCTOR | ✅ | ✅ |
| CLINIC_ADMIN | ✅ | ✅ |
| INTERNAL_ADMIN / SUPER_ADMIN | ✅ | ✅ |
| AI_SERVICE | ❌ 403 | ❌ 403 |

#### UI States

| State | Behavior |
|-------|----------|
| **Loading** | Skeleton chart; spinner on list |
| **Empty** | "Chưa có dữ liệu. Thêm chỉ số đầu tiên." with CTA |
| **Single data point** | Hide trend chart; show single value card |
| **403** | "Không có quyền truy cập" |

---

### 2.5 Add Health Metric

**Screen purpose:** Patient logs a new health measurement.

#### API Call

| Method | Path | Auth |
|--------|------|------|
| `POST` | `/patients/{patient_id}/metrics` | Bearer |

#### Request

```json
POST /patients/{patient_id}/metrics
{
  "metric_type": "fasting_glucose",
  "value": 6.1,
  "unit": "mmol/L",
  "measured_at": "2026-06-18T07:45:00Z",
  "source": "manual",
  "normal_range_min": 3.9,
  "normal_range_max": 5.6
}
```

> `measured_at` defaults to server time if omitted. `source` defaults to `"manual"`.

#### Response `201`

```json
{
  "id": "<uuid>",
  "metric_type": "fasting_glucose",
  "value": 6.1,
  "unit": "mmol/L",
  "measured_at": "2026-06-18T07:45:00Z",
  "status": "borderline"
}
```

#### RBAC

PATIENT (own), DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN. AI_SERVICE → ❌ 403.

#### UI States

| State | Behavior |
|-------|----------|
| **Loading** | Spinner on submit button |
| **201 Success** | Toast "Đã lưu chỉ số" → refresh metric list |
| **422** | Field validation error → highlight invalid fields |
| **403** | "Không có quyền ghi chỉ số cho bệnh nhân này" |

---

### 2.6 Lab Documents (List + Upload + Status)

**Screen purpose:** Patient uploads lab result PDFs/images; views processing status and AI interpretation.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `POST` | `/patients/{patient_id}/lab-documents` | Bearer | Register document (after client-side upload to storage) |
| `POST` | `/lab-documents/{document_id}/process` | Bearer | Enqueue for OCR + interpretation |
| `GET` | `/lab-documents/{document_id}` | Bearer | Poll processing status |
| `POST` | `/lab-documents/{document_id}/interpret` | Bearer | Trigger AI interpretation on processed document |

#### Register Document Request

```json
POST /patients/{patient_id}/lab-documents
{
  "storage_key": "uploads/patients/<uuid>/lab_20260618.pdf",
  "file_type": "pdf",
  "lab_name": "Bệnh viện Bạch Mai"
}
```

Response `201`:

```json
{
  "id": "<uuid>",
  "patient_id": "<uuid>",
  "ocr_status": "pending",
  "status": "uploaded"
}
```

#### Enqueue for Processing Request

```
POST /lab-documents/{document_id}/process
```

(No body)

Response `202`:

```json
{
  "id": "<uuid>",
  "status": "processing",
  "ocr_status": "queued",
  "enqueued": true
}
```

#### Poll Status

```
GET /lab-documents/{document_id}
```

Response `200`:

```json
{
  "id": "<uuid>",
  "status": "processed",
  "ocr_status": "done",
  "enqueued": false
}
```

> `ocr_status` values: `pending`, `queued`, `processing`, `done`, `failed`

#### Interpret Document

```
POST /lab-documents/{document_id}/interpret
```

Response `200`:

```json
{
  "biomarkers": [
    {
      "canonical": "HbA1c",
      "value": 6.4,
      "unit": "%",
      "status": "borderline_high",
      "reference_range": "< 5.7%",
      "needs_verification": false,
      "patient_note": "HbA1c của bạn hơi cao..."
    }
  ],
  "abnormal": ["HbA1c", "LDL"],
  "critical": [],
  "needs_verification": false,
  "patient_explanation": "Kết quả cho thấy...",
  "doctor_summary": "Patient HbA1c 6.4%, borderline pre-diabetic range..."
}
```

#### RBAC

| Action | PATIENT | DOCTOR | CLINIC_ADMIN | INTERNAL_ADMIN / SUPER_ADMIN | AI_SERVICE |
|--------|---------|--------|--------------|-------------------------------|------------|
| Register | ✅ own | ✅ | ❌ | ✅ | ❌ |
| Enqueue | ✅ own | ✅ | ❌ | ✅ | ❌ |
| Status | ✅ own | ✅ | ✅ | ✅ | ❌ |
| Interpret | ✅ own | ✅ | ❌ | ✅ | ❌ |

> Doctor access to lab documents requires **active consent** `scope="lab"` for the patient.

#### UI States

| State | Behavior |
|-------|----------|
| **Uploading** | Progress bar during client-side file upload to storage |
| **Processing** | Poll `/lab-documents/{id}` every 3s; show progress indicator |
| **Done** | "Xem kết quả AI" CTA enabled |
| **Failed OCR** | "Không đọc được file. Thử lại hoặc nhập tay." |
| **needs_verification: true** | Show yellow banner "Một số chỉ số cần xác nhận bởi bác sĩ" |
| **critical non-empty** | Show red alert; recommend seeing doctor immediately |

---

### 2.7 Metabolic Score (View + History + Trend)

**Screen purpose:** Patient views their current metabolic score, contributing risk factors, and score history trend.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `POST` | `/ai/metabolic-score` | Bearer | Compute + persist new score |
| `GET` | `/patients/{patient_id}/metabolic-scores` | Bearer | Paginated score history + trend |

#### Compute Score Request

```json
POST /ai/metabolic-score
{
  "waist_cm": 88.0,
  "fasting_glucose": 6.2,
  "hba1c": 6.3,
  "triglyceride": 1.8,
  "hdl": 1.1,
  "systolic_bp": 132,
  "is_male": true
}
```

All fields are optional (partial inputs are scored from available data).

Response `200`:

```json
{
  "score": 42,
  "band": "moderate",
  "factors": [
    { "name": "waist_cm", "points": 8, "detail": "Vòng bụng > 90cm (ngưỡng nam)" },
    { "name": "fasting_glucose", "points": 6, "detail": "Đường huyết đói > 5.6 mmol/L" }
  ],
  "explanation": "Điểm 42/100 cho thấy nguy cơ chuyển hóa trung bình..."
}
```

> `band` values: `"low"`, `"moderate"`, `"high"`, `"critical"`

#### Score History Request

```
GET /patients/{patient_id}/metabolic-scores?limit=20&offset=0
```

Response `200`:

```json
{
  "patient_id": "<uuid>",
  "total": 8,
  "items": [
    {
      "id": "<uuid>",
      "metabolic_score": 42,
      "band": "moderate",
      "top_risks": [{"name": "waist_cm", "points": 8}, ...],
      "created_at": "2026-06-18T10:00:00Z"
    }
  ],
  "trend": "improving"
}
```

> `trend` values: `"improving"`, `"worsening"`, `"stable"`, `"insufficient_data"`

#### RBAC

| Action | PATIENT | DOCTOR | CLINIC_ADMIN | INTERNAL_ADMIN / SUPER_ADMIN | AI_SERVICE |
|--------|---------|--------|--------------|-------------------------------|------------|
| Compute score | ✅ own | ✅ | ✅ | ✅ | ❌ |
| View history | ✅ own | ✅ (consent) | ❌ | ✅ | ❌ |

#### UI States

| State | Behavior |
|-------|----------|
| **Loading** | Animated circular score gauge |
| **No score yet** | "Tính điểm ngay" CTA → navigate to score input form |
| **Low (0–25)** | Green badge |
| **Moderate (26–50)** | Yellow badge |
| **High (51–75)** | Orange badge |
| **Critical (76–100)** | Red badge + escalate CTA |
| **History empty** | "Chưa có lịch sử. Tính điểm lần đầu." |
| **insufficient_data trend** | Hide trend arrow; show "Cần thêm dữ liệu" |

---

### 2.8 Nutrition Log (List + Add)

**Screen purpose:** Patient logs meals and snacks; reviews nutrition history.

#### API Calls

| Method | Path | Auth |
|--------|------|------|
| `POST` | `/patients/{patient_id}/nutrition` | Bearer |
| `GET` | `/patients/{patient_id}/nutrition` | Bearer |

#### Add Nutrition Log Request

```json
POST /patients/{patient_id}/nutrition
{
  "description": "Cơm gà xối mỡ, rau xào",
  "meal_type": "lunch",
  "calories_kcal": 650,
  "logged_at": "2026-06-18T12:15:00Z"
}
```

> `meal_type` must be one of: `breakfast`, `lunch`, `dinner`, `snack` (or omit).  
> `logged_at` defaults to server time if omitted.

Response `201`:

```json
{
  "id": "<uuid>",
  "patient_id": "<uuid>",
  "description": "Cơm gà xối mỡ, rau xào",
  "meal_type": "lunch",
  "calories_kcal": 650,
  "logged_at": "2026-06-18T12:15:00Z",
  "created_at": "2026-06-18T12:16:00Z"
}
```

#### List Nutrition Logs

```
GET /patients/{patient_id}/nutrition?limit=20&offset=0
```

Response `200`:

```json
{
  "patient_id": "<uuid>",
  "total": 45,
  "items": [ /* NutritionLogOut array */ ]
}
```

#### RBAC

PATIENT (own), DOCTOR (consent), INTERNAL_ADMIN, SUPER_ADMIN. AI_SERVICE, CLINIC_ADMIN → ❌ 403.

#### UI States

| State | Behavior |
|-------|----------|
| **Loading** | Skeleton list |
| **Empty** | "Chưa ghi bữa ăn hôm nay. Thêm ngay!" |
| **201 Success** | Toast "Đã lưu bữa ăn" → refresh list |
| **422** | `description` missing or too long → field error |

---

### 2.9 Symptom Log (List + Add)

**Screen purpose:** Patient logs self-reported symptoms; views symptom history.

#### API Calls

| Method | Path | Auth |
|--------|------|------|
| `POST` | `/patients/{patient_id}/symptoms` | Bearer |
| `GET` | `/patients/{patient_id}/symptoms` | Bearer |

#### Add Symptom Request

```json
POST /patients/{patient_id}/symptoms
{
  "description": "Đau đầu nhẹ, chóng mặt sau ăn",
  "severity": 4,
  "reported_at": "2026-06-18T14:00:00Z"
}
```

> `severity`: integer 0–10.  
> `reported_at` defaults to server time if omitted.

Response `201`:

```json
{
  "id": "<uuid>",
  "patient_id": "<uuid>",
  "description": "Đau đầu nhẹ, chóng mặt sau ăn",
  "severity": 4,
  "reported_at": "2026-06-18T14:00:00Z",
  "created_at": "2026-06-18T14:01:00Z"
}
```

#### List Symptoms

```
GET /patients/{patient_id}/symptoms?limit=20&offset=0
```

Response `200`: paginated envelope with `SymptomLogOut` items.

#### RBAC

PATIENT (own), DOCTOR (consent), INTERNAL_ADMIN, SUPER_ADMIN. AI_SERVICE, CLINIC_ADMIN → ❌ 403.

#### UI States

| State | Behavior |
|-------|----------|
| **Empty** | "Chưa ghi triệu chứng nào." with CTA |
| **Severity ≥ 7** | Surface a prompt: "Triệu chứng nặng — muốn kiểm tra nhanh?" → Triage CTA |
| **201 Success** | Toast + refresh list |

---

### 2.10 Medications (List + Add + Delete)

**Screen purpose:** Patient manages their current medication list.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `POST` | `/patients/{patient_id}/medications` | Bearer | Add medication |
| `GET` | `/patients/{patient_id}/medications` | Bearer | List active medications |
| `DELETE` | `/patients/{patient_id}/medications/{med_id}` | Bearer | Soft-delete |

#### Add Medication Request

```json
POST /patients/{patient_id}/medications
{
  "name": "Metformin 500mg",
  "dose": "1 viên sáng, 1 viên tối",
  "note": "Uống sau bữa ăn"
}
```

Response `201`:

```json
{
  "id": "<uuid>",
  "patient_id": "<uuid>",
  "name": "Metformin 500mg",
  "dose": "1 viên sáng, 1 viên tối",
  "note": "Uống sau bữa ăn",
  "created_at": "2026-06-18T09:00:00Z"
}
```

#### List Medications

```
GET /patients/{patient_id}/medications?limit=20&offset=0
```

Returns only non-deleted (`deleted_at IS NULL`) records. Response: paginated envelope.

#### Delete Medication

```
DELETE /patients/{patient_id}/medications/{med_id}
```

Response `204 No Content`.

#### RBAC

| Action | PATIENT (own) | DOCTOR | CLINIC_ADMIN | INTERNAL_ADMIN / SUPER_ADMIN | AI_SERVICE |
|--------|--------------|--------|--------------|-------------------------------|------------|
| Add | ✅ | ✅ (consent) | ❌ | ✅ | ❌ (**SAFETY**) |
| List | ✅ | ✅ (consent) | ❌ | ✅ | ❌ |
| Delete | ✅ | ❌ (**clinical safety**) | ❌ | ✅ | ❌ |

> **Safety rule:** AI_SERVICE is hard-blocked from all medication writes. Doctors **cannot** delete medication history (clinical safety).

#### UI States

| State | Behavior |
|-------|----------|
| **Empty** | "Chưa có thuốc nào. Thêm thuốc đang dùng." |
| **Delete confirm** | Modal: "Xóa thuốc này?" with confirm/cancel |
| **204** | Remove item from list; toast "Đã xóa thuốc" |
| **403 on delete** | Hide delete button for DOCTOR role |

---

### 2.11 Triage (Enter Symptoms → Result)

**Screen purpose:** Patient enters current symptoms to get immediate risk assessment and recommended action.

#### API Call

| Method | Path | Auth |
|--------|------|------|
| `POST` | `/ai/triage` | Bearer |

#### Request

```json
POST /ai/triage
{
  "symptom_text": "Đau ngực trái, khó thở, đổ mồ hôi lạnh",
  "vitals": [
    { "metric_type": "systolic_bp", "value": 160 },
    { "metric_type": "fasting_glucose", "value": 9.2 }
  ],
  "reported_severity": 8
}
```

> `vitals` and `reported_severity` are optional. `symptom_text` can be empty string but results will be low-fidelity.

#### Response `200`

```json
{
  "risk_level": "critical",
  "action": "call_emergency",
  "message": "Có dấu hiệu cần cấp cứu ngay. Gọi 115 hoặc đến cơ sở y tế gần nhất.",
  "red_flags": ["chest_pain", "dyspnea", "diaphoresis"],
  "escalated_to_doctor": true,
  "rule_forced": true
}
```

> **`risk_level`** values: `"low"`, `"moderate"`, `"high"`, `"critical"`  
> **`action`** values: `"monitor"`, `"see_doctor"`, `"urgent_care"`, `"call_emergency"`

> **Side-effect:** For PATIENT callers with an active `PatientProfile`, the triage result is automatically persisted to the triage log (see §2.12).

#### RBAC

PATIENT, DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN. AI_SERVICE → ❌ 403.

#### UI States

| State | Behavior |
|-------|----------|
| **Loading** | Spinner; "Đang phân tích triệu chứng…" |
| **low** | Green card; "Theo dõi tại nhà. Liên hệ bác sĩ nếu không cải thiện." |
| **moderate** | Yellow card; "Nên gặp bác sĩ trong 24-48 giờ" + Booking CTA |
| **high** | Orange card; "Đến phòng khám sớm hôm nay" + Booking CTA |
| **critical** | Red full-screen alert; "GỌI CẤP CỨU 115" button; `tel:115` deep link |
| **escalated_to_doctor** | Show "Đã thông báo bác sĩ của bạn" |

---

### 2.12 Triage History

**Screen purpose:** Patient reviews past triage sessions.

#### API Call

| Method | Path | Auth |
|--------|------|------|
| `GET` | `/patients/{patient_id}/triage-history` | Bearer |

#### Request

```
GET /patients/{patient_id}/triage-history?limit=20&offset=0
```

#### Response `200`

```json
{
  "patient_id": "<uuid>",
  "total": 5,
  "items": [
    {
      "id": "<uuid>",
      "patient_id": "<uuid>",
      "symptom_text": "Đau ngực...",
      "risk_level": "critical",
      "action": "call_emergency",
      "red_flags": ["chest_pain"],
      "message": "...",
      "created_at": "2026-06-18T14:30:00Z"
    }
  ]
}
```

#### RBAC

PATIENT (own), DOCTOR (consent), INTERNAL_ADMIN, SUPER_ADMIN. AI_SERVICE, CLINIC_ADMIN → ❌ 403.

#### UI States

| State | Behavior |
|-------|----------|
| **Empty** | "Chưa có lịch sử triage." |
| **critical entries** | Highlight row in red |

---

### 2.13 AI Chat

**Screen purpose:** Patient asks health questions to AI assistant; gets guided responses with safety guardrails.

#### API Call

| Method | Path | Auth |
|--------|------|------|
| `POST` | `/ai/chat` | Bearer |

#### Request

```json
POST /ai/chat
{
  "message": "Đường huyết của tôi 6.4 mmol/L có bình thường không?",
  "intent": "health_assistant"
}
```

> `intent` default: `"health_assistant"`. Other values: `"lifestyle_coach"`, `"lab_explanation"`, `"triage_followup"`.

#### Response `200`

```json
{
  "text": "Đường huyết đói 6.4 mmol/L nằm trong vùng tiền tiểu đường (5.6–6.9 mmol/L)...",
  "intent": "health_assistant",
  "risk_level": "moderate",
  "escalated_to_doctor": false,
  "safety_flags": [],
  "blocked": false,
  "model_used": "gemini-2.0-flash",
  "cached": false
}
```

> If `blocked: true` → AI guardrail triggered; display generic safety message.  
> If `escalated_to_doctor: true` → show "Bác sĩ của bạn đã được thông báo."  
> `safety_flags`: list of triggered safety categories (e.g. `"prescription_intent"`, `"suicidal_ideation"`).

#### RBAC

PATIENT, DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN. AI_SERVICE → ❌ 403.

#### UI States

| State | Behavior |
|-------|----------|
| **Sending** | Streaming indicator (dots) or spinner |
| **blocked: true** | Show: "Tôi không thể trả lời câu hỏi này. Vui lòng tham khảo ý kiến bác sĩ." |
| **risk_level: high/critical** | Show escalation banner |
| **429** | "Hệ thống đang bận. Thử lại sau." with `Retry-After` seconds |

---

### 2.14 AI Sessions (List + View)

**Screen purpose:** Patient (and doctor/admin) views AI session history and clinical recommendations.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `POST` | `/ai_sessions` | Bearer | Create new AI session |
| `GET` | `/ai_sessions` | Bearer | List sessions (filter by `patient_id`) |
| `GET` | `/ai_sessions/{session_id}` | Bearer | View single session |
| `GET` | `/ai_sessions/{session_id}/recommendations` | Bearer | List clinical recommendations (feature-flagged) |

#### Create Session Request

```json
POST /ai_sessions
{
  "patient_id": "<uuid>",
  "encounter_id": "<uuid>",   // optional
  "session_type": "lifestyle_coaching"
}
```

> **Guards:** `AI_SESSION_ENABLED` feature flag must be on (503 if off). Patient must have active consent `type="ai_use"`.

Response `201`: `AISessionOut` shape.

#### List Sessions

```
GET /ai_sessions?patient_id=<uuid>
```

Response `200`: array of `AISessionOut`.

#### Single Session

```
GET /ai_sessions/{session_id}
```

Response `200` (`AISessionOut`):

```json
{
  "id": "<uuid>",
  "patient_id": "<uuid>",
  "encounter_id": null,
  "session_type": "lifestyle_coaching",
  "messages": null,
  "key_version": 1,
  "risk_level": "low",
  "escalated_to_doctor": false,
  "escalation_reason": null,
  "model_used": "gemini-2.0-flash",
  "safety_flags": null,
  "input_blocked": false,
  "output_blocked": false,
  "total_tokens": 512,
  "created_at": "2026-06-18T10:00:00Z",
  "updated_at": "2026-06-18T10:05:00Z"
}
```

#### List Recommendations (feature-flagged)

```
GET /ai_sessions/{session_id}/recommendations
```

> Returns `503` if `AI_CLINICAL_RECS_ENABLED` flag is off.

Response `200`: array of `AIClinicalRecommendationOut`.

#### RBAC

| Action | PATIENT (own) | DOCTOR / CLINIC_ADMIN | INTERNAL_ADMIN / SUPER_ADMIN | AI_SERVICE |
|--------|--------------|----------------------|-------------------------------|------------|
| Create | ✅ | ✅ | ✅ | ✅ |
| List | ✅ own | ✅ | ✅ | ✅ |
| View single | ✅ own | ✅ | ✅ | ✅ |
| Recommendations | ✅ own | ✅ | ✅ | ✅ |

#### UI States

| State | Behavior |
|-------|----------|
| **503 on create** | "Tính năng AI tạm thời không khả dụng." |
| **403 (no consent)** | "Bạn cần đồng ý sử dụng AI trước." → link to Consent screen |
| **Empty list** | "Chưa có phiên AI nào." |
| **escalated_to_doctor** | Show escalation badge on session card |

---

### 2.15 Consent Management (View + Grant + Revoke)

**Screen purpose:** Patient manages data access permissions granted to doctors/services.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `POST` | `/patients/{patient_id}/consents` | Bearer (PATIENT only) | Grant consent |
| `DELETE` | `/patients/{patient_id}/consents/{consent_id}` | Bearer (PATIENT only) | Revoke consent |

> **⚠️ Legal constraint (Luật BVDLCN Vietnam 2026):** Only `PATIENT` role can grant or revoke consent. All other roles → 403.  
> There is **no GET endpoint** for listing consents in the current API. Frontend must store granted consents client-side or infer from RBAC errors.

#### Grant Consent Request

```json
POST /patients/{patient_id}/consents
{
  "consent_type": "data_sharing",
  "data_scope": "profile",
  "granted_to": "<doctor_id_or_service_id>",
  "valid_until": "2027-01-01T00:00:00Z"
}
```

> Common `consent_type` values: `"data_sharing"`, `"ai_use"`  
> Common `data_scope` values: `"profile"`, `"lab"`, `"*"` (all)

Response `201`:

```json
{
  "id": "<uuid>",
  "patient_id": "<uuid>",
  "data_scope": "profile",
  "granted_to": "<doctor_id>"
}
```

#### Revoke Consent

```
DELETE /patients/{patient_id}/consents/{consent_id}
```

Response `200`: `{ "message": "revoked" }`

#### RBAC

| Action | PATIENT (own) | All other roles |
|--------|--------------|-----------------|
| Grant | ✅ | ❌ 403 |
| Revoke | ✅ | ❌ 403 |

#### UI States

| State | Behavior |
|-------|----------|
| **Grant success** | Toast "Đã cấp quyền truy cập" |
| **Revoke confirm** | Modal: "Thu hồi quyền này sẽ ngắt truy cập của bác sĩ. Tiếp tục?" |
| **Revoke 404** | Consent already revoked; refresh consent list |
| **List consents** | ⚠️ No GET endpoint — **see Gap List §6** |

---

### 2.16 Care Plans (List + View)

**Screen purpose:** Patient views care plans created by their doctor.

#### API Calls

| Method | Path | Auth |
|--------|------|------|
| `GET` | `/care_plans` | Bearer |
| `GET` | `/care_plans/{care_plan_id}` | Bearer |

#### List Care Plans

```
GET /care_plans?patient_id=<uuid>
```

Response `200`: array of `CarePlanOut`.

#### Single Care Plan

```
GET /care_plans/{care_plan_id}
```

Response `200`:

```json
{
  "id": "<uuid>",
  "patient_id": "<uuid>",
  "encounter_id": "<uuid>",
  "title": "Kế hoạch kiểm soát tiền tiểu đường",
  "content": "1. Giảm 5% cân nặng...",
  "status": "ACTIVE",
  "approved_by_doctor_id": "<uuid>",
  "approved_at": "2026-06-15T10:00:00Z",
  "ai_generated": false,
  "version": 1,
  "created_at": "2026-06-14T09:00:00Z",
  "updated_at": "2026-06-15T10:00:00Z"
}
```

> `status` values: `DRAFT`, `PENDING_REVIEW`, `APPROVED`, `ACTIVE`, `SUPERSEDED`, `ARCHIVED`

#### RBAC

PATIENT sees own care plans only. DOCTOR/CLINIC_ADMIN sees assigned patients' plans. ADMIN sees all.

#### UI States

| State | Behavior |
|-------|----------|
| **Empty** | "Bác sĩ của bạn chưa tạo kế hoạch chăm sóc nào." |
| **DRAFT** | Show "Đang soạn" badge (grey) |
| **PENDING_REVIEW** | Show "Chờ duyệt" badge (yellow) |
| **ACTIVE** | Show "Đang thực hiện" badge (green) |
| **ARCHIVED** | Show "Đã kết thúc" badge (grey, dimmed) |

---

### 2.17 Encounters (List + View)

**Screen purpose:** Patient views consultation encounter records.

#### API Calls

| Method | Path | Auth |
|--------|------|------|
| `GET` | `/encounters` | Bearer |
| `GET` | `/encounters/{encounter_id}` | Bearer |

#### List Encounters

```
GET /encounters?patient_id=<uuid>
```

Response `200`: array of `EncounterOut`.

#### Single Encounter

```
GET /encounters/{encounter_id}
```

Response `200`:

```json
{
  "id": "<uuid>",
  "patient_id": "<uuid>",
  "doctor_id": "<uuid>",
  "appointment_id": "<uuid>",
  "encounter_type": "consultation",
  "status": "completed",
  "chief_complaint": "Kiểm tra đường huyết định kỳ",
  "notes": "Bệnh nhân cải thiện...",
  "encounter_date": "2026-06-10T09:30:00Z",
  "created_at": "2026-06-10T09:00:00Z",
  "updated_at": "2026-06-10T10:00:00Z"
}
```

#### RBAC

PATIENT sees own encounters. DOCTOR/CLINIC_ADMIN sees assigned encounters. ADMIN sees all.

#### UI States

| State | Behavior |
|-------|----------|
| **Empty** | "Chưa có lịch sử khám." |
| **pending_review** | Show "Đang xử lý" badge |
| **completed** | Show "Đã hoàn thành" badge |

---

## 3. Doctor Journey Screens

---

### 3.1 Doctor Dashboard

**Screen purpose:** Doctor sees an overview of patients, pending review queue, and recent encounters.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET` | `/review/queue` | Bearer (DOCTOR) | Pending review recommendations |
| `GET` | `/encounters` | Bearer (DOCTOR) | Recent encounters (filtered by assigned doctor) |
| `GET` | `/care_plans` | Bearer (DOCTOR) | Care plans awaiting action |

#### Pending Review Queue

```
GET /review/queue
```

Response `200`: array of `AIClinicalRecommendationOut`:

```json
[
  {
    "id": "<uuid>",
    "session_id": "<uuid>",
    "patient_id": "<uuid>",
    "encounter_id": null,
    "recommendation_type": "lifestyle",
    "content": "Patient presents with elevated HbA1c...",
    "status": "pending_review",
    "reviewed_by_doctor_id": null,
    "reviewed_at": null,
    "ai_confidence": 0.87,
    "safety_cleared": true,
    "medical_disclaimer": "AI-generated; requires physician review.",
    "created_at": "2026-06-18T08:00:00Z",
    "updated_at": "2026-06-18T08:00:00Z"
  }
]
```

#### RBAC

DOCTOR only for `/review/queue`. Encounters and care plans: DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN.

#### UI States

| State | Behavior |
|-------|----------|
| **Queue empty** | "Không có mục chờ duyệt." |
| **safety_cleared: false** | Show red "Safety check failed" warning badge |

---

### 3.2 Patient List / Patient Detail

**Screen purpose:** Doctor finds a patient and views their full clinical profile (consent-gated).

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET` | `/patients/{patient_id}/profile` | Bearer (DOCTOR, consent `scope=profile`) | Profile |
| `GET` | `/patients/{patient_id}/metrics` | Bearer | Health metrics |
| `GET` | `/patients/{patient_id}/metabolic-scores` | Bearer | Score history |
| `GET` | `/patients/{patient_id}/symptoms` | Bearer | Symptom log |
| `GET` | `/patients/{patient_id}/medications` | Bearer | Medication list |
| `GET` | `/patients/{patient_id}/nutrition` | Bearer | Nutrition logs |
| `GET` | `/patients/{patient_id}/triage-history` | Bearer | Triage history |

> All patient data reads require valid consent. A `403` response means either no consent or consent expired.

#### UI States

| State | Behavior |
|-------|----------|
| **No consent** | "Bệnh nhân chưa cấp quyền truy cập hồ sơ." with instructions |
| **Loading** | Skeleton tabs for each section |
| **Each section empty** | Per-section empty state message |

---

### 3.3 Lab Review Queue (List + Interpret)

**Screen purpose:** Doctor views pending lab documents and reviews AI interpretation.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET` | `/lab-documents/{document_id}` | Bearer (DOCTOR) | Status check |
| `POST` | `/lab-documents/{document_id}/interpret` | Bearer (DOCTOR) | Trigger/view interpretation |

> There is no list-all-lab-documents endpoint. Doctors access documents via `patient_id` patient detail flow (documents linked from lab section). **See Gap §6.**

#### UI States

| State | Behavior |
|-------|----------|
| **needs_verification: true** | Flag items needing manual verification |
| **critical non-empty** | Red banner; notify patient option |

---

### 3.4 Doctor Review (Approve / Reject / Request Info)

**Screen purpose:** Doctor reviews AI clinical recommendations and records decision.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET` | `/review/{rec_id}` | Bearer | View single recommendation |
| `POST` | `/review/{rec_id}/review` | Bearer (DOCTOR) | Submit decision |
| `POST` | `/review/{rec_id}/submit` | Bearer (AI_SERVICE / SUPER_ADMIN) | Submit for review (not a doctor action) |

#### Review Decision Request

```json
POST /review/{rec_id}/review
{
  "verdict": "accepted",
  "notes": "Đồng ý với khuyến nghị. Bệnh nhân cần tăng cường hoạt động thể chất."
}
```

> `verdict` values: `"accepted"`, `"rejected"`, `"request_info"`

Response `200`: `AIClinicalRecommendationOut` with updated `status` and `reviewed_at`.

#### RBAC

| Action | DOCTOR | AI_SERVICE | SUPER_ADMIN | Others |
|--------|--------|------------|-------------|--------|
| View recommendation | ✅ (assigned/consent) | ✅ | ✅ | ❌ |
| Submit verdict | ✅ | ❌ | ❌ | ❌ |
| Submit for review | ❌ | ✅ | ✅ | ❌ |

#### UI States

| State | Behavior |
|-------|----------|
| **pending_review** | Show action buttons: Accept / Reject / Request Info |
| **already reviewed** | Show read-only decision + notes; hide action buttons |
| **503** | AI review feature disabled → show banner |
| **404** | Recommendation deleted or not found |

---

### 3.5 Care Plan (Create + Update + Approve)

**Screen purpose:** Doctor creates, edits, and approves care plans for patients.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `POST` | `/care_plans` | Bearer (DOCTOR, ADMIN) | Create |
| `PATCH` | `/care_plans/{care_plan_id}` | Bearer (DOCTOR, ADMIN) | Update |
| `POST` | `/care_plans/{care_plan_id}/approve` | Bearer (DOCTOR only) | Approve |

#### Create Care Plan Request

```json
POST /care_plans
{
  "patient_id": "<uuid>",
  "encounter_id": "<uuid>",
  "title": "Kế hoạch kiểm soát tiền tiểu đường 90 ngày",
  "content": "Mục tiêu: giảm HbA1c xuống < 5.7%...",
  "status": "DRAFT",
  "ai_generated": false,
  "version": 1
}
```

Response `201`: `CarePlanOut`.

#### Update Care Plan Request (partial)

```json
PATCH /care_plans/{care_plan_id}
{
  "content": "Updated content...",
  "status": "PENDING_REVIEW"
}
```

> AI_SERVICE **cannot** set status to `APPROVED`, `ACTIVE`, `PENDING_REVIEW`, `SUPERSEDED`, `ARCHIVED`.

#### Approve Care Plan Request

```json
POST /care_plans/{care_plan_id}/approve
{
  "approved_by_doctor_id": "<doctor_record_uuid>",
  "approved_at": "2026-06-18T15:00:00Z"
}
```

Response `200`: `CarePlanOut` with `status: "APPROVED"`.

> Returns `409 Conflict` if plan is already `APPROVED` or `ARCHIVED`.

#### RBAC

| Action | PATIENT | DOCTOR (assigned) | CLINIC_ADMIN | INTERNAL_ADMIN / SUPER_ADMIN | AI_SERVICE |
|--------|---------|-------------------|--------------|-------------------------------|------------|
| Create | ❌ | ✅ | ❌ | ✅ | ❌ |
| Update | ❌ | ✅ | ❌ | ✅ | ❌ |
| Approve | ❌ | ✅ | ❌ | ❌ | ❌ |
| Read list | ✅ own | ✅ | ✅ | ✅ | ❌ |

#### UI States

| State | Behavior |
|-------|----------|
| **DRAFT** | Show "Gửi duyệt" button → PATCH to `PENDING_REVIEW` |
| **PENDING_REVIEW** | Show "Duyệt" button → POST `/approve` |
| **409 on approve** | "Kế hoạch đã được duyệt trước đó." |
| **Doctor not assigned** | 403 "Bác sĩ không được phân công cho bệnh nhân này" |

---

### 3.6 Encounter (Create + Update)

**Screen purpose:** Doctor creates and updates consultation encounter records.

#### API Calls

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `POST` | `/encounters` | Bearer | Create encounter |
| `PATCH` | `/encounters/{encounter_id}` | Bearer (DOCTOR, ADMIN) | Update encounter |

#### Create Encounter Request

```json
POST /encounters
{
  "patient_id": "<uuid>",
  "doctor_id": "<doctor_record_uuid>",
  "appointment_id": "<uuid>",
  "encounter_type": "consultation",
  "status": "pending_review",
  "chief_complaint": "Kiểm tra HbA1c định kỳ",
  "notes": "...",
  "encounter_date": "2026-06-18T09:30:00Z"
}
```

Response `201`: `EncounterOut`.

#### Update Encounter Request

```json
PATCH /encounters/{encounter_id}
{
  "status": "completed",
  "notes": "Bệnh nhân đã cải thiện. Điều chỉnh thuốc như kế hoạch."
}
```

#### RBAC

| Action | PATIENT | DOCTOR (assigned) | CLINIC_ADMIN | INTERNAL_ADMIN / SUPER_ADMIN | AI_SERVICE |
|--------|---------|-------------------|--------------|-------------------------------|------------|
| Create | ❌ | ✅ | ✅ | ✅ | ❌ |
| Update | ❌ | ✅ | ❌ | ✅ | ❌ |
| Read | ✅ own | ✅ | ✅ | ✅ | ❌ |

#### UI States

| State | Behavior |
|-------|----------|
| **pending_review** | Show "Hoàn thành" button |
| **completed** | Read-only view |
| **403** | "Bạn không được phân công cho cuộc hẹn này" |

---

## 4. Admin Journey Screens

---

### 4.1 Audit Log Viewer

**Screen purpose:** Admin views immutable audit trail of all platform actions.

#### API Call

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET` | `/admin/audit-logs` | Bearer (INTERNAL_ADMIN, SUPER_ADMIN) + **MFA required** | List audit logs |

#### Request

```
GET /admin/audit-logs?limit=50
```

Response `200`:

```json
[
  {
    "id": "<uuid>",
    "actor_type": "user",
    "actor_id": "<uuid>",
    "action": "grant_consent",
    "resource_type": "consent",
    "resource_id": "<uuid>",
    "outcome": "success",
    "timestamp": "2026-06-18T10:00:00Z"
  }
]
```

> **MFA required:** Admin endpoints require MFA-verified token (`mfa: true` in JWT claims). If MFA not verified, returns `403`.

#### RBAC

INTERNAL_ADMIN, SUPER_ADMIN only. All other roles → ❌ 403.

#### UI States

| State | Behavior |
|-------|----------|
| **Loading** | Table skeleton |
| **Empty** | "Không có audit log." |
| **403 (no MFA)** | "Vui lòng xác thực MFA để truy cập tính năng admin." |
| **Max 500 entries** | Warning: "Đang hiển thị tối đa 500 mục. Dùng bộ lọc để tìm kiếm." |

---

### 4.2 Account Unlock

**Screen purpose:** Admin unlocks a user account locked due to repeated failed login attempts.

#### API Call

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `POST` | `/admin/unlock-account` | Bearer (INTERNAL_ADMIN, SUPER_ADMIN) + **MFA required** | Unlock by email |

#### Request

```json
POST /admin/unlock-account
{
  "email": "user@example.com"
}
```

Response `200`: `{ "message": "account unlocked" }`

#### RBAC

INTERNAL_ADMIN, SUPER_ADMIN only.

#### UI States

| State | Behavior |
|-------|----------|
| **Success** | Toast "Tài khoản đã được mở khóa" |
| **Email not found** | Endpoint succeeds silently (clears lockout counter) — no 404 |
| **403** | Role not authorized |

---

### 4.3 User Management

**Screen purpose:** Admin manages platform users. The schemas exist (`UserAdminOut`, `UserStatusUpdate`, `UserRoleUpdate`) but **routes are not yet implemented**.

> ⚠️ **Gap:** No API endpoints exist for user management (list users, activate/deactivate, change role). See **Gap List §6**.

---

## 5. Permission Matrix

The table below summarizes read/write access across all screens and actions.

**Legend:** ✅ = Allowed, ❌ = Denied (403), `C` = Requires active consent, `O` = Own data only, `A` = Assigned patients only

| Screen / Action | PATIENT | DOCTOR | INTERNAL_ADMIN | SUPER_ADMIN | AI_SERVICE | CLINIC_ADMIN |
|----------------|---------|--------|----------------|-------------|------------|--------------|
| **Auth** | | | | | | |
| Register | ✅ | — | — | — | — | — |
| Login | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MFA Enroll/Verify | ✅ O | ✅ O | ✅ O | ✅ O | — | ✅ O |
| **Patient Profile** | | | | | | |
| View profile | ✅ O | ✅ C,A | ✅ | ✅ | ❌ | ❌ |
| Edit profile | ✅ O | ✅ C,A | ✅ | ✅ | ❌ | ❌ |
| **Health Metrics** | | | | | | |
| Add metric | ✅ O | ✅ | ✅ | ✅ | ❌ | ❌ |
| List metrics | ✅ O | ✅ | ✅ | ✅ | ❌ | ✅ |
| Trend data | ✅ O | ✅ | ✅ | ✅ | ❌ | ✅ |
| **Lab Documents** | | | | | | |
| Register document | ✅ O | ✅ C | ✅ | ✅ | ❌ | ❌ |
| Enqueue processing | ✅ O | ✅ C | ✅ | ✅ | ❌ | ❌ |
| View status | ✅ O | ✅ C | ✅ | ✅ | ❌ | ✅ C |
| AI interpret | ✅ O | ✅ C | ✅ | ✅ | ❌ | ❌ |
| **Metabolic Score** | | | | | | |
| Compute score | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| View score history | ✅ O | ✅ C | ✅ | ✅ | ❌ | ❌ |
| **Nutrition Log** | | | | | | |
| Add log | ✅ O | ✅ C | ✅ | ✅ | ❌ | ❌ |
| List logs | ✅ O | ✅ C | ✅ | ✅ | ❌ | ❌ |
| **Symptom Log** | | | | | | |
| Add symptom | ✅ O | ✅ C | ✅ | ✅ | ❌ | ❌ |
| List symptoms | ✅ O | ✅ C | ✅ | ✅ | ❌ | ❌ |
| **Medications** | | | | | | |
| Add medication | ✅ O | ✅ C | ✅ | ✅ | ❌ ⚠️ | ❌ |
| List medications | ✅ O | ✅ C | ✅ | ✅ | ❌ | ❌ |
| Delete medication | ✅ O | ❌ ⚠️ | ✅ | ✅ | ❌ | ❌ |
| **Triage** | | | | | | |
| Run triage | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| View triage history | ✅ O | ✅ C | ✅ | ✅ | ❌ | ❌ |
| **AI Chat** | | | | | | |
| Chat | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| **AI Sessions** | | | | | | |
| Create session | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| List sessions | ✅ O | ✅ A | ✅ | ✅ | ✅ | ✅ A |
| View session | ✅ O | ✅ | ✅ | ✅ | ✅ | ✅ |
| View recommendations | ✅ O | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Consent** | | | | | | |
| Grant consent | ✅ O | ❌ | ❌ | ❌ | ❌ | ❌ |
| Revoke consent | ✅ O | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Care Plans** | | | | | | |
| Create care plan | ❌ | ✅ A | ✅ | ✅ | ❌ | ❌ |
| Update care plan | ❌ | ✅ A | ✅ | ✅ | ❌ | ❌ |
| Approve care plan | ❌ | ✅ A | ❌ | ❌ | ❌ | ❌ |
| List/view care plans | ✅ O | ✅ A | ✅ | ✅ | ❌ | ✅ A |
| **Encounters** | | | | | | |
| Create encounter | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Update encounter | ❌ | ✅ A | ✅ | ✅ | ❌ | ❌ |
| List/view encounters | ✅ O | ✅ A | ✅ | ✅ | ❌ | ✅ A |
| **Doctor Review** | | | | | | |
| View queue | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Submit verdict | ❌ | ✅ A | ❌ | ❌ | ❌ | ❌ |
| Submit for review | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **Admin** | | | | | | |
| View audit logs | ❌ | ❌ | ✅ MFA | ✅ MFA | ❌ | ❌ |
| Unlock account | ❌ | ❌ | ✅ MFA | ✅ MFA | ❌ | ❌ |
| User management | ❌ | ❌ | ❌ ⚠️ GAP | ❌ ⚠️ GAP | ❌ | ❌ |

**Notes:**
- `C` = active consent required for the relevant scope; 403 returned otherwise
- `A` = must be assigned doctor/clinic; 403 if not assigned
- `O` = own data only; accessing another patient's data → 403
- ⚠️ = safety-critical restriction (see individual screen notes)
- `MFA` = MFA-verified JWT required

---

## 6. Gap List

The following screens or actions are implied by the MVP scope (`BRD.md`, `Product_Module_Map.md`) but have **no API endpoint currently implemented**.

| # | Screen / Feature | MVP Priority | Notes |
|---|-----------------|-------------|-------|
| G-01 | **List Consents** (`GET /patients/{id}/consents`) | P0 | Schema exists (`ConsentOut`); route missing. Patient cannot list their own active consents. Frontend workaround: store consent IDs client-side. |
| G-02 | **User Management** — List users, activate/deactivate, change role | P0 (admin portal) | Schemas exist (`UserAdminOut`, `UserStatusUpdate`, `UserRoleUpdate`). Routes in `admin.py` not implemented beyond audit-log + unlock. |
| G-03 | **List Lab Documents** for a patient (`GET /patients/{id}/lab-documents`) | P0 | Only POST (register) exists. Doctors and patients cannot list all lab documents for a patient. |
| G-04 | **Doctor Booking / Appointment** create + list | P0 | Schemas `AppointmentCreate`, `AppointmentOut` exist in `schemas/care.py`. No appointment routes implemented. |
| G-05 | **Doctor List** (`GET /doctors`) and doctor search | P0 | Schema `DoctorOut`, `DoctorSummaryOut` exist. No routes to find/list doctors for booking. |
| G-06 | **Notification API** (push/SMS/email preference management, notification list) | P0 | No notification routes exist. Notification infrastructure not yet exposed via API. |
| G-07 | **Payment** (booking payment, subscription) | P0 | Schema mentions `Payment`; no payment routes implemented. |
| G-08 | **PDF Report Export** (`GET /patients/{id}/report.pdf`) | P0 | Mentioned in BRD FR-16 and MVP scope; no route exists. |
| G-09 | **Clinic Admin** — Manage doctors, view bookings for clinic | P0 | Schemas `ClinicOut`, `ClinicCreate` exist; no clinic management routes. |
| G-10 | **Patient Search** for doctors (doctor-side patient list) | P0 | Doctors currently access patients by `patient_id` directly; no search/list endpoint. |
| G-11 | **Medication Update** (`PATCH /patients/{id}/medications/{med_id}`) | P1 | Schema `MedicationUpdate` exists in `clinical.py`; no PATCH route. |
| G-12 | **System Stats** (`GET /admin/stats`) | P1 | Schema `SystemStatsOut` exists in `admin.py`; no route. |
| G-13 | **Consent Scope Filter** on read endpoints | P0 | Consent check is present for doctors but consent `scope` values are not surfaced to frontend. API does not return which scopes a doctor has been granted. |
| G-14 | **MFA Disable** endpoint | P1 | No route to disable MFA once enrolled. |

---

## 7. Standard Error Codes Reference

| HTTP Code | When Returned | Frontend Behavior |
|-----------|--------------|-------------------|
| **200 OK** | Successful read/update | Render response data |
| **201 Created** | Successful resource creation | Toast success; update local state |
| **202 Accepted** | Async operation enqueued (e.g. lab processing) | Show processing indicator; begin polling |
| **204 No Content** | Successful delete (no body) | Remove item from UI list |
| **400 Bad Request** | Invalid operation (e.g. approve already-approved plan) | Show specific error message from `detail` field |
| **401 Unauthorized** | Missing/expired/invalid JWT | Clear tokens → redirect to Login |
| **403 Forbidden** | Valid JWT but insufficient role or consent denied | Show "Không có quyền truy cập"; surface consent CTA if applicable |
| **404 Not Found** | Resource does not exist or is soft-deleted | Show "Không tìm thấy" state; navigate back |
| **409 Conflict** | Resource already in incompatible state (e.g. duplicate email, double-approve) | Show specific conflict message from `detail` |
| **422 Unprocessable Entity** | Request body fails Pydantic validation | Map `errors[].loc` to field-level validation messages |
| **423 Locked** | Account locked due to repeated login failures | Show lockout message; disable login form; suggest contacting admin |
| **429 Too Many Requests** | Rate limit hit (auth endpoints, AI chat) | Disable action button; show `Retry-After` countdown |
| **503 Service Unavailable** | Feature flag is off (AI session, AI recs) | Show "Tính năng tạm thời không khả dụng" banner |

### Error Response Body Shape

All error responses from FastAPI use:

```json
{
  "detail": "Human-readable message or structured validation errors"
}
```

For `422` validation errors, `detail` is an array:

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

### Auth Token Lifecycle

```
POST /auth/login → { access_token, refresh_token }
↓
(access_token expires)
↓
POST /auth/refresh { refresh_token } → { new_access_token, new_refresh_token }
↓
(user logs out or refresh_token expires)
↓
POST /auth/logout { refresh_token } → revoke
```

- Store both tokens securely (Keychain on iOS, EncryptedSharedPreferences on Android, httpOnly cookie on web).
- Never expose tokens in URL parameters or logs.
- On any `401` response, attempt one silent refresh; if refresh also returns `401`, clear tokens and redirect to login.

---

*End of document. For questions or corrections, open a PR against `docs/product/METOCARE_PILOT_UI_CONTRACT.md`.*
