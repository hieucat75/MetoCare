# ADR-12 — PHI, Privacy and Encryption

**Status:** PROPOSED — Gate 2 (blocks production scale)  
**Date:** 2026-07-11  
**Deciders:** PTH, Legal Advisor, Tech Lead

---

## ADR Metadata

| Field | Value |
|-------|-------|
| ADR | ADR-12 |
| Status | Proposed |
| Architecture Version | medication-architecture-v1.0 |
| Implementation Gate | Gate 2 |
| Domain | PHI & Privacy |
| Supersedes | None |
| Superseded By | None |

---


## Context

Medication data trong MetoCare là Protected Health Information (PHI) theo bất kỳ định nghĩa nào của healthcare privacy law. Danh sách thuốc của một bệnh nhân tiết lộ: bệnh lý, tình trạng sức khỏe, hành vi, lịch sử lâm sàng.

MetoCare hiện tại: medications table lưu plaintext. Không có encryption at rest, không có field-level masking, không có purpose-based access control, không có data retention policy.

---

## Problem

**Những rủi ro hiện tại:**
1. **DB dump = full medication history exposed**: nếu DB bị access bởi unauthorized party, toàn bộ medication data của tất cả patients là plaintext
2. **No audit log of data access**: không biết ai đã đọc medication data của patient nào, khi nào
3. **AI prompt exposure**: medication data được inject vào LLM prompts — chưa có policy về LLM provider data retention
4. **Notification PHI**: future medication reminders có thể include medication names — OS notification center = visible to anyone who picks up the phone
5. **Error messages**: nếu code sai, medication names có thể appear trong error logs
6. **Vietnamese privacy law**: Luật An toàn thông tin mạng 2015 + Nghị định 13/2023 về bảo vệ dữ liệu cá nhân — health data là "sensitive personal data" với yêu cầu đặc biệt

---

## Decision Drivers

- Vietnamese law (Nghị định 13/2023): health data = sensitive personal data, requires consent, purpose limitation, security measures
- Clinical data breach = significant reputational and legal risk for MetoCare
- Encryption must not make data unsearchable (autocomplete, queries)
- PHI in AI prompts: must confirm LLM provider data processing policy
- Audit access log: who read what patient data, when
- Data retention: Vietnamese law may require keeping health records minimum period
- Budget: HSM (Hardware Security Module) is expensive — evaluate necessity
- Priority order: prevent unauthorized bulk access first; field-level encryption is secondary

---

## Options Considered

### Option A — No encryption (current state)
OS/disk encryption only. Application-level plaintext. Insufficient.

### Option B — Database-level encryption at rest (full DB)
Encrypt entire DB file (SQLite) or tablespace (PostgreSQL). Transparent to application.

### Option C — Column-level encryption (EncryptedString)
Encrypt specific PHI columns at application layer. Non-PHI columns remain searchable.

### Option D — Field-level encryption + tokenization
Encrypt + replace values with tokens. Tokenization service maps tokens → values.

### Option E — Hybrid: DB-level encryption + column-level for highest-sensitivity fields + access audit
DB encryption as base. Column encryption for highest-sensitivity (diagnosis-equivalent fields). Full access audit log.

---

## Trade-off Table

| Criterion | A (none) | B (DB-level) | C (column-level) | D (tokenization) | E (hybrid) |
|-----------|----------|--------------|-----------------|-----------------|------------|
| Bulk dump protection | ❌ | ✅ | ✅ | ✅ | ✅ |
| Searchability | ✅ | ✅ | ❌ Encrypted = no index | ❌ | ⚠️ Selective |
| Performance | ✅ | ✅ | ⚠️ Decrypt per read | ❌ High | ⚠️ Moderate |
| Implementation complexity | ✅ | ✅ | ⚠️ Medium | ❌ High | ⚠️ Medium |
| Access audit | ❌ | ❌ | ❌ | ⚠️ | ✅ Add separately |
| Key management | N/A | ⚠️ One key | ⚠️ Per-table keys | ❌ Complex | ⚠️ Moderate |
| Legal compliance | ❌ | ⚠️ Partial | ✅ | ✅ | ✅ |

---

## Recommended Decision

**Option E — Hybrid approach, phased:**

**P0–P1 (now):** 
- Enable database-level encryption at rest (if cloud deployment — Azure SQL Transparent Data Encryption, or SQLite with SQLCipher)
- NO plaintext PHI in application logs (enforce via log middleware)
- NO PHI in error message responses (enforce at service layer)
- NO medication names in notification bodies (enforce at notification service)

**P1–P2 (before scale):**
- Column-level encryption for highest-sensitivity fields: `medications.indication` (reveals diagnosis), `medication_history.snapshot` (full clinical context), `patient_allergies` (reveals medical history)
- Implement access audit log

**P3+ (before production safety features):**
- LLM data processing agreements confirmed
- Data retention policy implemented
- PHI minimization in AI context (patient ID replaced with session token in LLM call)

---

## Consequences

### PHI Classification (Medication Domain)

**Level 3 — Highest sensitivity (column encryption):**
- `medications.indication` — explicitly states diagnosis-adjacent info
- `medication_history.snapshot` — full clinical record snapshot
- `patient_allergies` table — medical history, reaction details
- `medication_statements.raw_source_encrypted` — raw OCR text (prescription content)

**Level 2 — High sensitivity (DB encryption + access audit sufficient):**
- `medications.name`, `medications.dose`, `medications.frequency`
- `medication_adherence` records
- `medication_alerts` records

**Level 1 — Medium (no field encryption needed):**
- `drug_catalog`, `drug_interactions` — reference data, not patient-specific
- `medications.status` — on its own doesn't reveal much
- `medication_events.event_type` — without patient context

### Log Policy (ENFORCE IN P0)
```python
# FORBIDDEN in any log:
logger.info(f"Patient {patient_id} medication: {med.name} {med.dose}")  # ❌
logger.error(f"Allergy conflict: {allergy.allergen_name}")               # ❌

# REQUIRED:
logger.info(f"medication_add: medication_id={med.id} patient_id={patient_id}")  # ✅
logger.error(f"allergy_conflict: allergy_id={allergy.id} medication_id={med.id}")  # ✅
```

Log middleware: scan outgoing log messages for patterns matching drug names from catalog → raise alert if found in non-audit logs.

### Error Response Policy (ENFORCE IN P0)
```python
# FORBIDDEN in 4xx/5xx response body:
{"detail": f"Medication '{med.name}' conflicts with allergy '{allergy.allergen_name}'"}  # ❌

# REQUIRED:
{"detail": "Cannot add medication: safety conflict detected.", "conflict_id": "alert_uuid"}  # ✅
# Client fetches conflict details via /medications/alerts/{conflict_id}
```

### Notification PHI Policy (ENFORCE IN P1, when reminders ship)
```
Notification title: "Nhắc nhở thuốc" (NOT medication name)
Notification body: "Đến giờ uống thuốc theo lịch." (NOT name, dose, or frequency)
Deep link: opens app → full medication detail inside app (encrypted, authenticated)
```
Rationale: iOS/Android notification centers are visible on lock screen. Medication names on lock screen = PHI exposure.

### AI Prompt PHI Policy (ENFORCE BEFORE P3 SHIPS)
```python
# Before injecting medication context into LLM:
context = {
    "medications": [
        {
            "med_ref": "med_001",  # internal reference, not UUID (prevents linkage)
            "generic_name": med.generic_name,    # OK — not patient-specific
            "drug_class": med.drug_class,         # OK — not patient-specific
            "dose_text": med.dose_text,           # Acceptable for clinical reasoning
            # EXCLUDED from LLM prompt:
            # med.name (brand name may contain patient's local brand)
            # med.indication (too sensitive)
            # med.prescribed_by (doctor name)
            # med.prescription_ref (hospital reference)
        }
    ],
    "patient_token": sha256(patient_id + session_id)  # NOT the real patient_id
}
```

LLM provider policy confirmation required:
- Anthropic: zero data retention policy (confirmed per public policy)
- Google Gemini: data processing amendment required for health data
- OpenAI: require DPA for healthcare usage

**STOP GATE:** If LLM provider cannot confirm no training on submitted data AND data processed under DPA, that provider CANNOT be used for medication context injection.

### Access Audit Log
```sql
CREATE TABLE phi_access_log (
    id                UUID PK,
    accessed_at       DATETIME NOT NULL,
    accessor_user_id  VARCHAR(36) NOT NULL,
    accessor_role     VARCHAR(32) NOT NULL,
    patient_id        VARCHAR(36) NOT NULL,
    resource_type     VARCHAR(64) NOT NULL,  -- medication | allergy | medication_history
    resource_ids      JSON NOT NULL,          -- list of IDs accessed
    access_purpose    VARCHAR(64) NOT NULL,   -- patient_view | doctor_review | ai_context | admin_audit
    request_id        VARCHAR(64) nullable,   -- HTTP request ID for correlation
    INDEX (patient_id, accessed_at)
);
```

Note: PHI access log itself must be protected — accessible to SUPER_ADMIN only, and to the patient for their own records.

### Data Retention Policy
- Medication records: 10 years after last activity (align with Vietnamese medical record law — seek legal confirmation)
- Medication history snapshots: same as medication records
- `phi_access_log`: 5 years
- `medication_statements` (OCR pending, rejected): 30 days then purge
- Hard delete is NEVER allowed for medication records (only status change to `entered_in_error`)
- Exception: patient requests data deletion under Vietnamese law → anonymize, do not delete clinical records entirely (legal obligation conflicts with right to erasure — requires legal guidance)

### Key Management
- DB encryption key: stored in Azure Key Vault (or equivalent) — NOT in codebase, NOT in env vars in plain text
- Column encryption keys: derived from master key via KDF — different key per table
- Key rotation: annual rotation, documented procedure
- Emergency access: break-glass procedure, fully logged, requires two approvers

---

## Data Model Impact

New table: `phi_access_log`  
Modified tables: column-level encryption applied to Level 3 fields (P1–P2)  
No structural schema change needed for DB-level encryption (transparent)

---

## API Impact

- Error responses: never include PHI in detail field
- All medication responses: access logged asynchronously
- Patient data export endpoint (right to data portability): must decrypt and include all records

---

## Security and Privacy Impact

**Highest impact ADR for legal compliance.** Non-compliance with Nghị định 13/2023 = significant legal risk in Vietnam.

Healthcare data breach disclosure: Vietnamese law requires notification to relevant authorities within 72 hours of discovery.

---

## Clinical Safety Impact

PHI minimization in AI prompts reduces risk but doesn't affect clinical accuracy (generic name + drug class is sufficient for clinical reasoning — patient's specific brand name is not needed).

---

## Migration Impact

**P0 (immediate, no downtime):**
- Enable DB-level encryption (if not already)
- Deploy log middleware (PHI scrubbing)
- Deploy error response policy (API middleware)

**P1–P2 (requires migration):**
- Column encryption: encrypt existing values in `medications.indication` and `patient_allergies` fields
- Migration: read → encrypt → write per batch (can run online with low traffic)

---

## Operational Ownership

- Key management: PTH (owner) with Tech Lead as custodian
- Privacy policy and retention: Legal Advisor
- PHI access log review: quarterly audit, Clinical Advisor + PTH
- Incident response: defined procedure, PTH as data controller

---

## Open Questions

1. **Vietnamese Nghị định 13/2023:** Exactly what security measures are required for "sensitive personal data"? Does it mandate encryption at rest? **[Legal Advisor must answer before production launch]**
2. **Data deletion vs anonymization:** When patient requests data deletion, can MetoCare anonymize clinical records (replacing PII with pseudonyms) rather than deleting? **[Legal Advisor must clarify]**
3. **LLM DPA status:** Has Anthropic/Google confirmed DPA for health data from Vietnamese users specifically? **[PTH must confirm with each provider — STOP GATE for P3 AI features]**
4. **SQLite vs PostgreSQL:** Current use of SQLite — SQLCipher (encrypted SQLite) vs migrating to PostgreSQL with TDE. SQLCipher is production-viable but SQLite itself has scale limitations. **[Tech Lead architecture decision — before P2 scale]**

---

## Approval Required From

- [ ] PTH — DB encryption activation (requires key management setup)
- [ ] PTH — LLM provider DPA confirmation (stop gate)
- [ ] Legal Advisor — Vietnamese privacy law compliance requirements
- [ ] Legal Advisor — data deletion vs anonymization policy
- [ ] Tech Lead — column encryption implementation and migration plan

## Implementation Gate

**Gate 2 — DB encryption and log PHI policy should ideally be in P0 (low-effort, high-protection). Column encryption can be P1–P2.**  
**LLM DPA is a hard stop gate before any medication data is injected into LLM calls at production scale.**  
**Vietnamese law compliance review must be completed before public launch.**
