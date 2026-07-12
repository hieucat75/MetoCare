# MEDICATION_RBAC_AND_PRIVACY.md
# MetoCare — Medication RBAC and Privacy Model

**Version:** 1.0  
**Date:** 2026-07-10  
**Scope:** Who can see, add, edit, delete medication data in MetoCare.

---

## 1. Role Definitions (Existing)

| Role | Description |
|------|-------------|
| `PATIENT` | The account owner / patient themselves |
| `DOCTOR` | Licensed medical professional with a patient consent grant |
| `CLINIC_ADMIN` | Clinic staff (scheduling, front desk) |
| `MEDICAL_REVIEWER` | Read-only clinical reviewer |
| `INTERNAL_ADMIN` | Platform admin (not clinical) |
| `SUPER_ADMIN` | Full platform access |
| `AI_SERVICE` | Internal service token used by AI inference layer |
| `CAREGIVER` | NEW — patient-designated caregiver (P4 addition) |

---

## 2. Medication RBAC Matrix (Current)

| Action | PATIENT (own) | DOCTOR (consent) | CLINIC_ADMIN | INTERNAL_ADMIN | SUPER_ADMIN | AI_SERVICE |
|--------|--------------|-----------------|--------------|---------------|------------|------------|
| Add medication | ✅ | ✅ | ❌ 403 | ✅ | ✅ | ❌ 403 (SR-001) |
| Edit medication | ✅ | ✅ | ❌ 403 | ✅ | ✅ | ❌ 403 (SR-001) |
| Soft-delete medication | ✅ | ❌ 403 (SR-012) | ❌ 403 | ✅ | ✅ | ❌ 403 |
| View medication list | ✅ | ✅ (consent) | ❌ | ✅ | ✅ | ✅ (read context) |
| Log adherence | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ 403 |
| View adherence summary | ✅ | ✅ (consent) | ❌ | ✅ | ✅ | ✅ (read context) |
| Drug catalog suggest | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ |

**Enforcement:** All RBAC checks are at the route layer, before any service call.  
`_check_write_access()` and `_check_read_access()` helpers in `routes/patients.py`.

---

## 3. Target RBAC Matrix (Post P0–P4)

### 3.1 Core Medications

| Action | PATIENT | DOCTOR | CAREGIVER | CLINIC_ADMIN | AI_SERVICE |
|--------|---------|--------|-----------|--------------|------------|
| Add medication | ✅ own | ✅ w/consent | ❌ | ❌ | ❌ |
| Edit medication | ✅ own | ✅ w/consent | ❌ | ❌ | ❌ |
| Delete medication | ✅ own | ❌ | ❌ | ❌ | ❌ |
| View medication list | ✅ own | ✅ w/consent | ✅ w/assignment + `can_view_medications` | ❌ | ✅ read-only context |
| View medication detail | ✅ own | ✅ w/consent | ✅ w/assignment | ❌ | ✅ read-only |
| Update medication status | ✅ own | ✅ w/consent | ❌ | ❌ | ❌ |

### 3.2 Adherence

| Action | PATIENT | DOCTOR | CAREGIVER |
|--------|---------|--------|-----------|
| Log adherence (taken/skipped) | ✅ own | ❌ | ❌ |
| View adherence summary | ✅ own | ✅ w/consent | ✅ w/assignment + `can_view_adherence` |
| View per-day history | ✅ own | ✅ w/consent | ✅ w/assignment + `can_view_adherence` |

### 3.3 Reminders / Schedules

| Action | PATIENT | DOCTOR | CAREGIVER |
|--------|---------|--------|-----------|
| Add/edit schedule | ✅ own | ❌ | ❌ |
| View schedules | ✅ own | ❌ | ✅ w/`can_view_medications` |
| Receive reminder notifications | ✅ own | ❌ | ✅ w/`can_receive_reminders` |

### 3.4 Allergies

| Action | PATIENT | DOCTOR | CAREGIVER |
|--------|---------|--------|-----------|
| Add allergy | ✅ own | ✅ w/consent (set verified_by_doctor=True) | ❌ |
| Edit allergy | ✅ own | ✅ w/consent | ❌ |
| Delete allergy | ✅ own | ❌ | ❌ |
| View allergy list | ✅ own | ✅ w/consent | ❌ (PHI — not included in caregiver scope by default) |

### 3.5 Interaction Warnings

| Action | PATIENT | DOCTOR | CAREGIVER |
|--------|---------|--------|-----------|
| View warnings | ✅ own | ✅ w/consent | ✅ w/assignment (MEDIUM/LOW only — CRITICAL visible) |
| Dismiss MEDIUM/LOW warnings | ✅ own | ✅ w/consent | ❌ |
| Dismiss HIGH warnings | ✅ (with acknowledgment) | ✅ | ❌ |
| Dismiss CRITICAL warnings | ❌ Never | ❌ Never | ❌ Never |

### 3.6 Refills

| Action | PATIENT | DOCTOR | CAREGIVER |
|--------|---------|--------|-----------|
| Add refill record | ✅ own | ❌ | ❌ |
| View refill history | ✅ own | ✅ w/consent | ❌ |
| View refill alerts | ✅ own | ❌ | ✅ w/`can_view_medications` |

### 3.7 Caregiver Assignment

| Action | PATIENT | DOCTOR |
|--------|---------|--------|
| Add caregiver | ✅ own (must specify permissions) | ❌ |
| Revoke caregiver | ✅ own | ❌ |
| View caregiver list | ✅ own | ❌ |

---

## 4. Doctor Consent Requirements

Doctor access to patient medication data requires:
1. Active `Consent` row: `consent_type = 'doctor_access'`, `data_scope = 'health_metric'` or `'*'`
2. `granted_to = doctor_id`
3. Consent is not revoked (`revoked_at IS NULL`)
4. Consent is not expired (`valid_until IS NULL OR valid_until > NOW()`)

After consent revocation: Doctor gets 403 on all patient medication endpoints immediately.

---

## 5. Caregiver Access Model (P4)

### 5.1 Assignment Permissions

Each caregiver assignment has granular permissions:

| Permission Flag | Controls |
|-----------------|---------|
| `can_view_medications` | View medication list + details |
| `can_view_adherence` | View adherence summary + history |
| `can_receive_reminders` | Receive copy of medication reminder notifications |
| `can_add_notes` | Add read-visible notes (not modify medications) |

### 5.2 What Caregiver CANNOT Do

- Add, edit, or delete patient medications
- Change dose, frequency, or schedule
- Mark doses as taken (patient marks their own adherence)
- Add or remove allergies
- Dismiss any warning
- Access other health data not explicitly shared (labs, metrics, etc.)

### 5.3 Caregiver Notification

When `can_receive_reminders = True`:
- Caregiver receives notification AFTER patient does
- Notification body: "Người thân của bạn có lịch uống thuốc vào lúc [time]."
- No medication name in caregiver notification (higher PHI protection)
- Caregiver can see name ONLY via their app view, not notification

### 5.4 Caregiver Authentication

- Caregiver must have a registered MetoCare account
- Caregiver uses their own credentials (not the patient's)
- Patient-caregiver link verified via `caregiver_assignments.caregiver_user_id`

---

## 6. PHI Classification

### 6.1 What Is PHI in Medication Context

| Data | PHI Level | Notes |
|------|-----------|-------|
| Medication name | HIGH | Reveals condition |
| Active ingredient / generic name | HIGH | Reveals condition |
| Drug class | MEDIUM | Reveals condition category |
| Dose amount / unit | HIGH | Clinical PHI |
| Frequency / schedule | MEDIUM | Behavioral PHI |
| Start date / end date | MEDIUM | Timeline PHI |
| Prescribed by (doctor name) | MEDIUM | |
| Indication (reason for use) | HIGH | Diagnosis-adjacent |
| Adherence history | HIGH | Behavioral health data |
| Allergy list | HIGH | Clinical + identity risk |
| Interaction warnings | MEDIUM | Derived, not raw |

### 6.2 Data Residency

- All medication data stored in Azure SQL / SQLite within same region as patient data
- No medication data exported to third-party analytics
- No medication data sent to AI providers except as part of Meto context (in-flight, not stored by provider)

### 6.3 Encryption at Rest

**Current state:** medications table is plaintext in SQLite.  
**Target:** Apply `EncryptedString` to `name`, `dose`, `indication` columns (same approach as `LabDocument.raw_text`).

Priority: P1 (before production scale).

---

## 7. Audit Logging Requirements

All medication-related write actions must produce an `AuditLog` entry.

| Action | Audit Fields |
|--------|-------------|
| add_medication | patient_id, medication_id, action="add_medication", requester_role |
| update_medication | patient_id, medication_id, action="update_medication", fields_changed |
| delete_medication | patient_id, medication_id, action="delete_medication" |
| ocr_confirm_medication | patient_id, medication_id, action="ocr_confirm_medication", confidence |
| add_allergy | patient_id, allergy_id, action="add_allergy" |
| delete_allergy | patient_id, allergy_id, action="delete_allergy" |
| dismiss_warning | patient_id, warning_id, severity, action="dismiss_warning" |
| add_caregiver | patient_id, caregiver_user_id, action="add_caregiver" |
| revoke_caregiver | patient_id, caregiver_user_id, action="revoke_caregiver" |

AuditLog must NOT store:
- Medication names or doses (medication_id only)
- Allergy names (allergy_id only)

---

## 8. API Endpoint Security Summary (Target)

| Endpoint | Auth Required | Rate Limit |
|----------|--------------|------------|
| `POST /patients/{id}/medications` | JWT + PATIENT/DOCTOR/ADMIN | 20/min |
| `GET /patients/{id}/medications` | JWT + RBAC | 60/min |
| `PATCH /patients/{id}/medications/{mid}` | JWT + PATIENT/DOCTOR/ADMIN | 20/min |
| `DELETE /patients/{id}/medications/{mid}` | JWT + PATIENT/ADMIN only | 10/min |
| `POST /patients/{id}/medications/{mid}/adherence` | JWT + PATIENT only | 60/min |
| `GET /patients/{id}/medications/adherence-summary` | JWT + PATIENT/DOCTOR | 30/min |
| `GET /medications/suggest` | JWT (any authenticated) | 30/min |
| `POST /patients/{id}/allergies` | JWT + PATIENT/DOCTOR | 10/min |
| `GET /patients/{id}/allergies` | JWT + PATIENT/DOCTOR | 30/min |
| `GET /patients/{id}/medications/warnings` | JWT + PATIENT/DOCTOR/CAREGIVER | 30/min |
| `POST /patients/{id}/medications/{mid}/schedules` | JWT + PATIENT only | 10/min |
| `POST /patients/{id}/caregivers` | JWT + PATIENT only | 5/min |
