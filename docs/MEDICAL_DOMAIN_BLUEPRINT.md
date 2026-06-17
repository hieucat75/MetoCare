# Medical Domain Blueprint — MetoCare
> Version: 1.0-draft · Ngày: 2026-06-17 · Tác giả: OpenClaw Coordinator
> Status: **DRAFT — chờ Claude Code review + PTH approval trước khi code T4**

---

## 0. Mục đích tài liệu

Blueprint này định nghĩa toàn bộ **domain model y tế** cho MetoCare MVP:
entities, relationships, rules nghiệp vụ, RBAC, consent workflow, AI safety boundaries,
và các quyết định thiết kế cần Claude Code xác nhận trước khi bắt đầu implement.

**Blueprint không phải code.** Đây là design input cho Claude Code task T4.

---

## 1. Domain Entities — 10 Entities cốt lõi

### 1.1 Patient

**Mô tả:** Bệnh nhân — người sử dụng app, chủ sở hữu dữ liệu sức khỏe.

| Field | Type | Ghi chú |
|---|---|---|
| `user_id` | FK → User | Identity |
| `full_name` | EncryptedString | PHI |
| `dob` | EncryptedString | PHI — ISO date |
| `phone` | EncryptedString | PHI |
| `gender` | String | male/female/other |
| `height_cm`, `weight_kg`, `waist_cm` | Float | Plaintext — dùng trong scoring |
| `known_conditions` | EncryptedString | PHI |
| `allergies` | EncryptedString | PHI |
| `family_history` | EncryptedString | PHI |
| `lifestyle_profile` | EncryptedString | PHI |
| `risk_segment` | String | low/medium/high/very_high — computed |

**Rules:**
- Mọi truy cập dữ liệu Patient bởi bác sĩ/phòng khám phải qua **Consent check + Audit log**.
- Người dùng có quyền xem, xuất, yêu cầu xóa dữ liệu của mình.
- `risk_segment` chỉ được cập nhật bởi metabolic score engine — không cho phép override thủ công.

**Model hiện có:** `backend/app/models/patient.py` — `PatientProfile` ✅

---

### 1.2 Encounter (Medical Encounter)

**Mô tả:** Một lần tương tác lâm sàng có cấu trúc giữa bệnh nhân và bác sĩ. Encounter là trung tâm kết nối Appointment, CarePlan, LabResult và AIConsultation.

| Field | Type | Ghi chú |
|---|---|---|
| `patient_id` | FK → PatientProfile | |
| `doctor_id` | FK → Doctor | |
| `appointment_id` | FK → Appointment (nullable) | Encounter không nhất thiết từ booking |
| `encounter_type` | Enum | initial / follow_up / teleconsult / triage_escalation |
| `encounter_at` | DateTime | |
| `chief_complaint` | EncryptedString | PHI — triệu chứng chính bệnh nhân khai |
| `clinical_notes` | EncryptedString | PHI — ghi của bác sĩ |
| `assessment` | EncryptedString | PHI — đánh giá lâm sàng |
| `status` | Enum | open / closed / cancelled |

**Rules:**
- Chỉ bác sĩ có role `DOCTOR` với consent hợp lệ mới được tạo/đọc `clinical_notes` và `assessment`.
- Encounter không thể bị xóa — chỉ `status = cancelled` nếu không xảy ra.
- Mọi create/read Encounter phải sinh Audit record.

**Model cần tạo mới:** ❌ Chưa có — cần migration.

---

### 1.3 Care Plan

**Mô tả:** Kế hoạch điều trị do bác sĩ soạn sau một Encounter. AI có thể đề xuất nội dung nhưng bác sĩ phải phê duyệt và ký (Doctor-in-the-Loop).

| Field | Type | Ghi chú |
|---|---|---|
| `patient_id` | FK → PatientProfile | |
| `doctor_id` | FK → Doctor | |
| `encounter_id` | FK → Encounter (nullable) | |
| `title` | String | |
| `goals` | EncryptedString | PHI — mục tiêu điều trị |
| `instructions` | EncryptedString | PHI — hướng dẫn cụ thể |
| `medication_changes` | EncryptedString | PHI — ghi nhận thay đổi thuốc (record-only) |
| `follow_up_date` | Date | |
| `status` | Enum | draft / active / completed / archived |
| `approved_by_doctor` | Boolean | default False — bắt buộc True trước khi active |
| `ai_suggested` | Boolean | True nếu AI đề xuất nội dung |

**Rules:**
- `status = active` chỉ được set khi `approved_by_doctor = True`.
- AI có thể tạo `CarePlan` với `ai_suggested=True` và `status=draft` — bác sĩ phải review và approve.
- AI **không được** set `status = active` — chỉ Doctor endpoint mới có quyền này.
- `medication_changes` là ghi nhận **record-only** — không phải kê đơn điện tử.

**Model hiện có:** `care.py` có `Appointment` nhưng **CarePlan entity chưa có** — cần tạo mới + migration.

---

### 1.4 Lab Result

**Mô tả:** Kết quả xét nghiệm đơn lẻ (một biomarker), trích từ LabDocument qua OCR hoặc nhập tay.

| Field | Type | Ghi chú |
|---|---|---|
| `patient_id` | FK → PatientProfile | |
| `document_id` | FK → LabDocument (nullable) | Null nếu nhập tay |
| `encounter_id` | FK → Encounter (nullable) | Gắn vào encounter nếu bác sĩ order |
| `test_name` | String | Tên thô từ OCR |
| `canonical_name` | String | Tên chuẩn (HbA1c, LDL, ALT...) |
| `value` | Float | |
| `unit` | String | |
| `reference_range` | String | |
| `status` | Enum | normal / low / high / critical |
| `test_date` | Date | |
| `ocr_confidence` | Float | 0-1, null nếu nhập tay |
| `verified_by_user` | Boolean | |
| `verified_by_doctor` | Boolean | |

**Rules:**
- LabResult với `status = critical` phải trigger triage check ngay khi lưu.
- `verified_by_doctor` chỉ Doctor endpoint mới được set.
- AI interpretation chỉ được dùng LabResult đã `verified_by_user = True` hoặc `verified_by_doctor = True`.

**Model hiện có:** `clinical.py` — `LabResult` ✅ (cần thêm `encounter_id`)

---

### 1.5 Medication

**Mô tả:** Danh sách thuốc bệnh nhân đang dùng — **record-only, không phải kê đơn điện tử**.

| Field | Type | Ghi chú |
|---|---|---|
| `patient_id` | FK → PatientProfile | |
| `encounter_id` | FK → Encounter (nullable) | Thuốc được ghi nhận trong encounter nào |
| `name` | String | Tên thuốc |
| `dose` | String | Liều — ghi nhận, không được AI thay đổi |
| `frequency` | String | Tần suất uống |
| `started_at` | Date | |
| `ended_at` | Date (nullable) | Null = vẫn đang dùng |
| `prescribed_by_doctor_id` | FK → Doctor (nullable) | |
| `note` | Text | |
| `is_active` | Boolean | |

**Hard rules (enforce tại tầng API + guardrail):**
- AI **tuyệt đối không được** update `dose`, `frequency`, `is_active` của Medication.
- Chỉ `DOCTOR` role mới được tạo/update Medication.
- Patient chỉ được xem danh sách thuốc của mình, không được tạo/sửa.

**Model hiện có:** `clinical.py` — `Medication` có nhưng thiếu `encounter_id`, `frequency`, `started_at`, `ended_at`, `prescribed_by_doctor_id`, `is_active` — cần migration.

---

### 1.6 Doctor

**Mô tả:** Bác sĩ — có tài khoản User với role `DOCTOR`, liên kết phòng khám.

| Field | Type | Ghi chú |
|---|---|---|
| `user_id` | FK → User | Login identity |
| `clinic_id` | FK → Clinic (nullable) | Có thể không thuộc phòng khám |
| `full_name` | String | |
| `specialty` | String | nội tiết / tim mạch / dinh dưỡng / gan mật |
| `license_no` | String | Số chứng chỉ hành nghề |
| `bio` | Text | Giới thiệu ngắn |
| `avatar_url` | String | |
| `consultation_fee` | Float (nullable) | Phí tư vấn |
| `is_verified` | Boolean | Internal Admin đã xác minh chứng chỉ |
| `is_active` | Boolean | |

**Rules:**
- Bác sĩ chỉ được xem dữ liệu bệnh nhân đã consent cho bác sĩ đó hoặc phòng khám đó.
- `is_verified` chỉ `INTERNAL_ADMIN` mới set được.
- Bác sĩ chưa `is_verified` không được nhận booking.

**Model hiện có:** `care.py` — `Doctor` có nhưng thiếu `bio`, `avatar_url`, `consultation_fee`, `is_verified`, `is_active`.

---

### 1.7 Clinic

**Mô tả:** Phòng khám / cơ sở y tế đối tác.

| Field | Type | Ghi chú |
|---|---|---|
| `name` | String | |
| `address` | String | |
| `phone` | String | |
| `email` | String | |
| `specialty_tags` | String | JSON array |
| `operating_hours` | String | JSON |
| `is_active` | Boolean | |
| `is_verified` | Boolean | Internal Admin xác minh |

**Rules:**
- Clinic chưa `is_verified` không hiện trong danh sách tìm kiếm bệnh nhân.
- Clinic Admin chỉ quản lý được bác sĩ và booking thuộc clinic của mình.

**Model hiện có:** `care.py` — `Clinic` có nhưng thiếu `email`, `specialty_tags`, `operating_hours`, `is_active`, `is_verified`.

---

### 1.8 Booking (Appointment)

**Mô tả:** Một lịch hẹn khám giữa bệnh nhân và bác sĩ.

| Field | Type | Ghi chú |
|---|---|---|
| `patient_id` | FK → PatientProfile | |
| `doctor_id` | FK → Doctor | |
| `clinic_id` | FK → Clinic (nullable) | |
| `encounter_id` | FK → Encounter (nullable) | Tạo sau khi encounter bắt đầu |
| `scheduled_at` | DateTime | |
| `duration_minutes` | Int | default 30 |
| `mode` | Enum | online / offline |
| `status` | Enum | requested / confirmed / checked_in / in_progress / completed / cancelled / no_show |
| `chief_complaint` | String | Bệnh nhân khai trước khi khám |
| `handoff_reason` | String | Nếu từ triage escalation |
| `payment_status` | Enum | pending / paid / refunded / waived |
| `payment_amount` | Float | |
| `cancellation_reason` | String | |
| `patient_health_snapshot` | JSON | Snapshot tóm tắt sức khỏe gửi cho bác sĩ trước khám |

**State machine:**
```
requested → confirmed → checked_in → in_progress → completed
         ↘                        ↘              ↘ no_show
           cancelled (any stage)
```

**Rules:**
- Booking chỉ confirmed khi bác sĩ/clinic admin confirm (không tự động).
- `patient_health_snapshot` được tạo tự động từ PatientProfile + latest metrics khi booking confirmed.
- Chỉ Patient mới tạo booking cho mình, không tạo cho người khác.
- Bác sĩ/Clinic Admin confirm/cancel booking trong phạm vi clinic của họ.

**Model hiện có:** `care.py` — `Appointment` có nhưng thiếu nhiều field — cần migration đáng kể.

---

### 1.9 AI Consultation

**Mô tả:** Một session tương tác AI gồm nhiều message. Bắt buộc có log để review safety.

| Field | Type | Ghi chú |
|---|---|---|
| `patient_id` | FK → PatientProfile | |
| `encounter_id` | FK → Encounter (nullable) | Nếu AI consult trong context encounter |
| `session_type` | Enum | health_assistant / lab_explanation / lifestyle_coach / triage |
| `messages` | Text | JSON — transcript (encrypted) |
| `risk_level` | Enum | low / medium / high / critical |
| `escalated_to_doctor` | Boolean | |
| `escalation_reason` | String | |
| `model_used` | String | |
| `safety_flags` | Text | JSON list |
| `input_blocked` | Boolean | |
| `output_blocked` | Boolean | |
| `total_tokens` | Int | Cost tracking |

**Rules:**
- Mọi AI session phải log đầy đủ — không có AI call nào không ghi AIConsultation.
- `session_type = triage` và `risk_level = critical` phải trigger escalation ngay.
- `messages` field là PHI — mã hóa at rest.
- Chỉ `INTERNAL_ADMIN` và `MEDICAL_REVIEWER` mới có thể đọc AI session logs.

**Model hiện có:** `ai.py` — `AIConversation` có nhưng thiếu `encounter_id`, `session_type`, `escalation_reason`, `input_blocked`, `output_blocked`, `total_tokens` — cần migration.

---

### 1.10 Consent

**Mô tả:** Phạm vi ủy quyền của bệnh nhân cho bác sĩ/phòng khám truy cập dữ liệu.

| Field | Type | Ghi chú |
|---|---|---|
| `patient_id` | FK → User | |
| `consent_type` | Enum | data_sharing / treatment / ai_use / research |
| `data_scope` | String | `*` hoặc `health_metrics,lab_results,...` |
| `granted_to` | String | doctor_id hoặc clinic_id |
| `granted_to_type` | Enum | doctor / clinic | NEW |
| `valid_from` | DateTime | |
| `valid_until` | DateTime (nullable) | |
| `revoked_at` | DateTime (nullable) | |
| `purpose` | String | Lý do truy cập | NEW |
| `version` | Int | Phiên bản consent text đã đồng ý | NEW |

**Rules:**
- Khi Consent bị revoke, tất cả active session của grantee với patient đó phải invalid.
- Consent `ai_use` bắt buộc trước khi AI được phép đọc dữ liệu bệnh nhân.
- Consent cho research chỉ dùng dữ liệu đã de-identify.
- Không thể sửa Consent đã tạo — chỉ revoke và tạo mới.

**Model hiện có:** `governance.py` — `Consent` có nhưng thiếu `granted_to_type`, `purpose`, `version`.

---

## 2. Entity Relationship Map

```
User ─── PatientProfile ─── HealthMetric (TimescaleDB hypertable)
          │                ├── LabDocument → LabResult
          │                ├── Medication
          │                ├── SymptomLog
          │                ├── RiskScore
          │                ├── Consent (grants access to Doctor/Clinic)
          │                ├── Booking (Appointment) → Encounter
          │                │                          └── CarePlan
          │                │                          └── AIConsultation
          │                └── AIConsultation (standalone, no encounter)
User ─── Doctor ─── Clinic
                 └── Booking
                 └── Encounter
                 └── CarePlan

AuditLog (cross-cutting, append-only, no FK — stores resource_type + resource_id)
```

---

## 3. RBAC Matrix

| Endpoint / Action | PATIENT | DOCTOR | CLINIC_ADMIN | INTERNAL_ADMIN | MEDICAL_REVIEWER |
|---|:---:|:---:|:---:|:---:|:---:|
| Read own PatientProfile | ✅ | ✅* | ❌ | ✅ | ✅ |
| Update own PatientProfile | ✅ | ❌ | ❌ | ❌ | ❌ |
| Read other patient's Profile | ❌ | ✅* | ❌ | ✅ | ✅ |
| Create/Read HealthMetric (own) | ✅ | ✅* | ❌ | ❌ | ❌ |
| Create LabDocument | ✅ | ❌ | ❌ | ❌ | ❌ |
| Verify LabResult | ❌ | ✅* | ❌ | ❌ | ✅ |
| Create Encounter | ❌ | ✅* | ❌ | ❌ | ❌ |
| Create/Update CarePlan | ❌ | ✅* | ❌ | ❌ | ❌ |
| Approve CarePlan | ❌ | ✅* | ❌ | ❌ | ❌ |
| Create/Read Medication | ❌ | ✅* | ❌ | ❌ | ❌ |
| Read own Medication | ✅ | ✅* | ❌ | ❌ | ❌ |
| Create Booking | ✅ | ❌ | ❌ | ❌ | ❌ |
| Confirm/Cancel Booking | ❌ | ✅ | ✅** | ❌ | ❌ |
| Read Booking list (own) | ✅ | ✅ | ✅** | ✅ | ❌ |
| Create/Use AI consultation | ✅ | ❌ | ❌ | ❌ | ❌ |
| Read AI consultation logs | ❌ | ❌ | ❌ | ✅ | ✅ |
| Manage Consent (own) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Read AuditLog | ❌ | ❌ | ❌ | ✅ | ✅ |
| Manage Doctor/Clinic | ❌ | ❌ | ✅** | ✅ | ❌ |
| Verify Doctor (is_verified) | ❌ | ❌ | ❌ | ✅ | ❌ |
| Manage Users | ❌ | ❌ | ❌ | ✅ | ❌ |

> `*` = chỉ khi có Consent hợp lệ từ patient cho doctor đó
> `**` = chỉ trong phạm vi clinic của mình

---

## 4. Consent Workflow

```
Bệnh nhân                    Hệ thống                     Bác sĩ/Clinic
    │                            │                              │
    │── Grant Consent ──────────>│                              │
    │   (type, scope,            │── Store Consent ────────────>│
    │    granted_to,             │   (valid_from = now)         │
    │    valid_until)            │                              │
    │                            │                              │
    │                            │<── Request patient data ─────│
    │                            │── Check Consent ─────────────│
    │                            │   (is_active? scope match?)  │
    │                            │── Write AuditLog ────────────│
    │                            │── Return data ───────────────>│
    │                            │                              │
    │── Revoke Consent ─────────>│                              │
    │                            │── Set revoked_at = now ─────>│
    │                            │── Invalidate active sessions │
    │                            │── Write AuditLog ────────────│
```

**Consent scope values:**
- `*` — full access (thường dùng khi bác sĩ điều trị chính)
- `health_metrics` — chỉ chỉ số theo dõi
- `lab_results` — chỉ xét nghiệm
- `ai_use` — AI được phép đọc dữ liệu để tư vấn
- `care_plan` — bác sĩ xem/tạo care plan
- `booking` — phòng khám xem thông tin cần cho booking

**Consent type `ai_use` — bắt buộc:**
Khi bệnh nhân dùng AI assistant, hệ thống kiểm tra `consent_type = ai_use` cho chính bệnh nhân
(grantee = patient's own user_id). Nếu chưa có consent AI, prompt onboarding.

---

## 5. AI Safety Boundaries (Medical Domain)

### 5.1 Allowed (AI có thể làm)

| Hành động | Điều kiện |
|---|---|
| Giải thích kết quả xét nghiệm (explain) | LabResult đã verify, có disclaimer |
| Tính Metabolic Score | Input từ HealthMetric, không chẩn đoán |
| Lifestyle coaching | Chỉ thay đổi hành vi, không phác đồ |
| Triage phân tầng rủi ro | Rule engine trước, LLM sau, escalate khi cần |
| Đề xuất theo dõi thêm chỉ số | Không mang tính chẩn đoán |
| Draft CarePlan nội dung | `ai_suggested=True`, `status=draft`, cần bác sĩ approve |

### 5.2 Strictly Prohibited (hard block tại API + guardrail)

| Hành động | Enforcement |
|---|---|
| Chẩn đoán khẳng định ("Bạn bị tiểu đường type 2") | Input/output guardrail block |
| Kê đơn thuốc | API level — không có endpoint AI → Medication create |
| Thay đổi liều thuốc | API + guardrail |
| Set `CarePlan.status = active` | API endpoint chỉ Doctor mới được gọi |
| Đọc dữ liệu bệnh nhân không có `ai_use` consent | Service layer check |
| Bỏ qua escalation khi red flag | Triage rule engine — không thể override |

### 5.3 Escalation thresholds (Triage)

| Condition | Action |
|---|---|
| `risk_level = critical` | Immediate escalation — notify doctor + emergency message |
| `risk_level = high` | Recommend doctor within 24h, flag in dashboard |
| Glucose > 300 mg/dL hoặc < 50 mg/dL | Critical — không phân tích tiếp, escalate |
| HA > 180/120 | Critical |
| Đau ngực + khó thở | Critical |
| HbA1c > 10% | High |

---

## 6. Migration Plan (Entities cần thay đổi)

### 6.1 New tables

| Table | Priority | Ghi chú |
|---|---|---|
| `encounters` | P0 — T4 | Central entity kết nối clinical data |
| `care_plans` | P0 — T4 | Thay thế CarePlanNote scaffold hiện tại |

### 6.2 Existing tables cần alter

| Table | Fields cần thêm | Migration risk |
|---|---|---|
| `doctors` | `bio`, `avatar_url`, `consultation_fee`, `is_verified`, `is_active` | Low |
| `clinics` | `email`, `specialty_tags`, `operating_hours`, `is_active`, `is_verified` | Low |
| `appointments` | `clinic_id`, `encounter_id`, `duration_minutes`, `chief_complaint`, `payment_status`, `payment_amount`, `cancellation_reason`, `patient_health_snapshot` | Medium |
| `medications` | `encounter_id`, `frequency`, `started_at`, `ended_at`, `prescribed_by_doctor_id`, `is_active` | Low |
| `lab_results` | `encounter_id` | Low |
| `ai_conversations` | `encounter_id`, `session_type`, `escalation_reason`, `input_blocked`, `output_blocked`, `total_tokens` | Low |
| `consents` | `granted_to_type`, `purpose`, `version` | Low |

### 6.3 Migration principles

- Tất cả column mới là nullable hoặc có default → không break existing data.
- Alembic auto-generate + manual review — không viết SQL thủ công.
- CI phải apply migration trên DB sạch xanh trước khi merge.
- TimescaleDB hypertable/CAGG không thay đổi trong sprint này.

---

## 7. API Contract Sketch (T4 input)

### New endpoints cần tạo

```
# Encounter
POST   /api/v1/patients/{patient_id}/encounters
GET    /api/v1/patients/{patient_id}/encounters
GET    /api/v1/patients/{patient_id}/encounters/{id}

# CarePlan
POST   /api/v1/patients/{patient_id}/care-plans          # AI draft hoặc Doctor create
GET    /api/v1/patients/{patient_id}/care-plans
PATCH  /api/v1/patients/{patient_id}/care-plans/{id}     # Doctor approve/update
DELETE /api/v1/patients/{patient_id}/care-plans/{id}     # Soft-delete (archive)

# Doctor
GET    /api/v1/doctors                                    # Public list (verified only)
GET    /api/v1/doctors/{id}
POST   /api/v1/doctors                                    # Internal Admin only
PATCH  /api/v1/doctors/{id}
PATCH  /api/v1/doctors/{id}/verify                        # Internal Admin only

# Clinic
GET    /api/v1/clinics
GET    /api/v1/clinics/{id}
POST   /api/v1/clinics                                    # Internal Admin only
PATCH  /api/v1/clinics/{id}

# Booking
POST   /api/v1/patients/{patient_id}/bookings
GET    /api/v1/patients/{patient_id}/bookings
GET    /api/v1/bookings/{id}
PATCH  /api/v1/bookings/{id}/confirm                      # Doctor / Clinic Admin
PATCH  /api/v1/bookings/{id}/cancel
PATCH  /api/v1/bookings/{id}/status                       # State machine transitions

# Medication
POST   /api/v1/patients/{patient_id}/medications          # Doctor only
GET    /api/v1/patients/{patient_id}/medications          # Doctor + Patient (own)
PATCH  /api/v1/patients/{patient_id}/medications/{id}     # Doctor only

# AI Consultation (existing — extend with encounter_id + session_type)
POST   /api/v1/ai/chat                                    # existing, add session_type
GET    /api/v1/ai/consultations/{id}                      # Internal Admin / Medical Reviewer
```

### Phân quyền convention

Mọi endpoint dữ liệu bệnh nhân:
1. `require_roles([DOCTOR, INTERNAL_ADMIN, MEDICAL_REVIEWER])` hoặc `is_own_patient()`
2. `check_consent(patient_id, grantee_id, scope)` nếu bác sĩ/clinic truy cập
3. `write_audit(actor, action, resource_type, resource_id)`

---

## 8. Questions for Claude Code Review

Các câu hỏi cần Claude Code trả lời trước khi implement T4:

1. **Encounter vs Appointment:** Có nên giữ cả hai entity riêng, hay merge Appointment thành Encounter với pre-booking state? Ảnh hưởng schema như thế nào?

2. **CarePlan approval flow:** Implement approval bằng status machine trong model hay dùng separate `CarePlanApproval` entity để có audit trail rõ hơn?

3. **Consent `ai_use` check:** Check tại service layer của AI assistant là đủ, hay cần middleware riêng? Trade-off performance vs correctness?

4. **Patient health snapshot khi booking:** Snapshot lưu dạng JSON blob trong Appointment hay separate `BookingHealthSnapshot` table? Ảnh hưởng gì đến privacy/audit?

5. **Doctor RBAC + multi-clinic:** Nếu một Doctor thuộc nhiều Clinic (tương lai), schema `doctor.clinic_id` là insufficient. Cần junction table `doctor_clinic` ngay từ MVP không?

6. **Soft delete strategy:** Các entity lâm sàng (Encounter, CarePlan, LabResult) không được hard-delete. Implement bằng `is_deleted` flag hay `deleted_at` timestamp? Ảnh hưởng gì đến queries?

7. **TimescaleDB retention policy:** Ai set retention policy cho `health_metrics` hypertable — migration hay startup hook? Cần verify với Postgres thật trước khi quyết định.

8. **AI Consultation encryption:** `messages` field (transcript) là PHI — nên dùng `EncryptedString` (Fernet field-level) hay encrypt ở service layer? Field-level encrypt ảnh hưởng search/analytics?

---

## 9. Acceptance Criteria cho T4 (input cho Claude Code)

### Medical Domain (model + migration)
- [ ] `encounters` table tạo mới, migration apply sạch trên SQLite + Postgres
- [ ] `care_plans` table tạo mới với state machine enforced tại model layer
- [ ] Tất cả 7 existing table được alter với fields mới — migration idempotent
- [ ] `CarePlan.status = active` chỉ set được bởi Doctor role — enforced tại service + test
- [ ] `Medication.dose/frequency` không thể update bởi AI — enforced tại API + test

### RBAC
- [ ] Tất cả Doctor endpoints kiểm tra consent trước khi trả dữ liệu patient
- [ ] Clinic Admin chỉ thao tác được với data trong clinic của mình
- [ ] `is_verified` cho Doctor/Clinic chỉ Internal Admin mới set

### Consent workflow
- [ ] Grant consent → Doctor có thể đọc patient data
- [ ] Revoke consent → Doctor không còn đọc được
- [ ] Consent `ai_use` missing → AI assistant từ chối với error message rõ

### AI Safety
- [ ] CarePlan tạo bởi AI phải `ai_suggested=True`, `status=draft`
- [ ] Không có code path nào cho AI update Medication
- [ ] Triage `risk_level=critical` → escalation được trigger và logged

### Tests
- [ ] Test coverage ≥ 80% cho encounter, care_plan, booking, medication endpoints
- [ ] Consent gate test: 401 khi không có consent
- [ ] RBAC test: 403 khi sai role
- [ ] AI boundary test: AI không thể kê đơn / set care plan active

---

## 10. Out of Scope (cho T4)

- Payment / billing API (deferred to T5+)
- Notification system (deferred)
- Video consultation (deferred)
- Lab booking (deferred)
- Care program 90 ngày (Phase 2)
- Frontend / Next.js portal (chờ blueprint này được approve)
- Flutter app (chờ blueprint)
- FHIR export (Phase 2)

---

*End of Medical Domain Blueprint v1.0-draft*
*Chờ Claude Code review → PTH approval → Antigravity implement T4*
