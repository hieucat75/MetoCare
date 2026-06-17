# Medical Domain Blueprint — Design Response
> Reviewer: Claude Code (claude-opus-4-5) · Date: 2026-06-17
> Task: METOCARE-BLUEPRINT-REVIEW-001 · Status: **COMPLETE**
> Mode: READ-ONLY review — no source files modified, no migrations generated

---

## 0. Executive Summary

All 8 design questions answered. All PTH conditions addressed. Recommendations are decisive.
Blueprint is approved for T4 implementation pending PTH sign-off on this document.

---

## 1. Design Answers — 8 Questions

### Q1. Encounter vs Appointment

**Decision: Separate entities. Encounter CAN exist without Booking.**

- `Appointment` = administrative intent (scheduling slot). It may be cancelled, no-show, or future.
- `Encounter` = the clinical event that actually happened (visit, teleconsult, walk-in, AI-escalation).

Merging them corrupts both: cancelled appointments would carry clinical FKs, and walk-in/unscheduled clinical events could not be represented without a booking. This is wrong architecturally and clinically.

**Relationship:** `Encounter.appointment_id` is a **nullable FK**. One Appointment → 0..1 Encounter.
Encounter without appointment = valid and expected (walk-in, AI-escalated, async lab review).

---

### Q2. CarePlan Approval Model

**Decision: Status machine in the model. NOT a separate CarePlanApproval entity.**

A single mandatory approval gate (doctor) does not warrant a multi-approver workflow table.

```
CarePlan.status:
  DRAFT → PENDING_REVIEW → APPROVED → ACTIVE → SUPERSEDED / ARCHIVED
                         ↘ REJECTED

CarePlan.approved_by_doctor_id  (FK Doctor, nullable until approved)
CarePlan.approved_at            (timestamp)
CarePlan.ai_generated           (bool — AI-drafted plans require explicit review)
```

**Audit trail:** every status transition writes `AuditLog(action=careplan.status_change, actor_id, outcome)`.
The append-only AuditLog is the authoritative trail — a separate mutable approval row adds complexity
with no benefit at MVP. Promote to junction table only if multi-signer approval is required later.

---

### Q3. Consent `ai_use` Enforcement Point

**Decision: Service layer via a single `ConsentGuard` dependency. NOT middleware.**

Middleware cannot know which patient, which data_scope, or which consent_type a request touches
without re-parsing the body — it is the wrong altitude for row-level access control.

**Enforcement:**
```python
# Called at top of every clinical service method reading PHI or invoking AI
consent_guard.require(patient_id, consent_type=AI_USE, data_scope=scope, actor=actor_id)
# Raises ConsentDenied (→ HTTP 403) and writes AuditLog(outcome=denied, severity=warning)
```

- One choke point per operation, independently testable.
- AI service path uses the **same guard** — no separate code path, no bypass.
- Every denied check is an audit event.

---

### Q4. Booking Health Snapshot

**Decision: Separate `BookingHealthSnapshot` table. NOT a JSON blob on Appointment.**

Rationale:
1. **PHI isolation** — snapshot (symptoms, vitals, intake answers) is PHI. Appointment is administrative.
   Separate tables allow independent encryption, retention-purge, and access audit.
2. **Immutability** — snapshot = point-in-time record. Separate append-only table prevents in-place mutation.
3. **Access scope** — schedulers/clinic admins see Appointment metadata but must NOT see health snapshot.
   Separate table = separate RBAC resource_type + separate audit trail.

**Shape:**
```
BookingHealthSnapshot(
  id, appointment_id FK, patient_id FK,
  payload EncryptedString(JSON),  # PHI
  created_at
)
```
Encrypted at field level. Append-only. Linked to Encounter on encounter creation.

---

### Q5. Doctor Multi-Clinic

**Decision: Implement `doctor_clinic` junction table NOW. Drop `doctor.clinic_id`.** ✅ Matches PTH preference.

Cost is genuinely low now; cost after Encounter/Appointment FKs proliferate is high.
Multi-site practice (locum, group practice, specialist visiting) is a near-certain real requirement.

```
doctor_clinic(
  doctor_id     FK → doctors,
  clinic_id     FK → clinics,
  role_at_clinic  String,   # attending / visiting / consultant
  is_primary    Boolean,    # preserves "default clinic" convenience
  is_active     Boolean,
  joined_at     Date,
  left_at       Date (nullable),
  PRIMARY KEY (doctor_id, clinic_id)
)
```

**Migration:** backfill one row per existing doctor from `doctor.clinic_id` with `is_primary=true`,
then drop the column in a **separate migration** after code is updated.

---

### Q6. Soft Delete Strategy

**Decision: `deleted_at TIMESTAMP NULL` + `deleted_by FK(user_id)`. NOT a boolean `is_deleted`.**

Timestamp is a strict superset: answers "deleted?" AND "when?" AND "by whom?" — all required for
retention, legal-hold, and audit. A boolean discards temporal information you will need.

Apply to: `Encounter`, `CarePlan`, `LabResult`, `AIConsultation`, `Medication`.

- SQLAlchemy query filter mixin excludes soft-deleted rows by default.
- MEDICAL_REVIEWER and SUPER_ADMIN can query includes-deleted via explicit flag.
- **Clinical/legal:** never hard-delete clinical records within the legal retention window.
  Soft delete + AuditLog = compliant pattern.

---

### Q7. TimescaleDB Retention Policy

**Decision: Declare in Alembic migration. NOT a startup hook.**

Retention is schema state. It must be versioned, reviewed, and reproducible per environment.

```sql
-- in Alembic migration (runs after create_hypertable)
SELECT add_compression_policy('health_metrics', INTERVAL '7 days');
SELECT add_retention_policy('health_metrics', INTERVAL '24 months');
```

Startup hooks are wrong: they run every boot (idempotency hazard), aren't code-reviewed as schema,
drift between environments, and mutate retention silently based on app version.

> Retention interval must be a compliance decision, not a hardcoded constant.
> Expose as a reviewed, named value in the migration.

---

### Q8. AI Consultation Transcript Encryption

**Decision: Field-level `EncryptedString` on transcript column. NOT service-layer encryption.**

The existing Fernet `EncryptedString` type guarantees encryption-at-rest **unconditionally** at the ORM
boundary. Service-layer encryption scatters responsibility and creates plaintext-leak paths
(logging, forgotten code paths, new endpoints).

**Implementation:**
- `AIConsultation.messages` → `EncryptedString` (Fernet, existing infra)
- Add `key_version` column to support Fernet key rotation
- Search limitation: field-level encryption makes transcript non-searchable in SQL.
  Solution: blind-index over non-PHI tokens only (blind-index infra already exists from P2-HARDENING-1).

---

## 2. Final Entity Relationship Proposal

```
User ──────────── PatientProfile ─────────────────────────────────────────────────┐
│                 │                                                                │
│                 ├── HealthMetric (TimescaleDB hypertable)                        │
│                 ├── LabDocument → LabResult ──────────── Encounter (nullable)   │
│                 ├── Medication ────────────────────────── Encounter (nullable)   │
│                 ├── SymptomLog                                                   │
│                 ├── RiskScore                                                    │
│                 ├── Consent (grants doctor/clinic access)                        │
│                 ├── AIConsultation ─────────────────────── Encounter (nullable) │
│                 ├── BookingHealthSnapshot ←── Appointment ──────────────────────┤
│                 └── Appointment ─────────────── Encounter (nullable FK)         │
│                                                 │                                │
│                                                 ├── CarePlan (doctor-approved)  │
│                                                 ├── LabResult (encounter-linked) │
│                                                 ├── Medication (doctor-only)     │
│                                                 └── AIConsultation (linked)      │
│                                                                                  │
User ── Doctor ────── doctor_clinic ──── Clinic                                   │
              └────── Encounter (attending doctor, nullable)                       │
                                                                                   │
AuditLog (cross-cutting, append-only, no FK — resource_type + resource_id strings)│
```

### Key relationship rules
| Relationship | Cardinality | Constraint |
|---|---|---|
| Patient → Encounter | 1:many | patient_id NOT NULL |
| Doctor → Encounter | 1:many | doctor_id NULLABLE (AI-only or unassigned) |
| Appointment → Encounter | 1:0..1 | encounter.appointment_id NULLABLE |
| Encounter → CarePlan | 1:many | encounter_id NULLABLE |
| Encounter → LabResult | 1:many | encounter_id NULLABLE |
| Encounter → Medication | 1:many | encounter_id NULLABLE |
| Encounter → AIConsultation | 1:many | encounter_id NULLABLE |
| Doctor ↔ Clinic | many:many | via doctor_clinic junction |
| Appointment → BookingHealthSnapshot | 1:0..1 | separate table, append-only |

---

## 3. Migration Plan

### Phase 1 — Additive (low risk, all nullable/defaulted columns)

| Migration | Tables affected | Risk | Reversible |
|---|---|---|---|
| `add_encounter_table` | NEW encounters | Medium | YES (drop table) |
| `add_doctor_clinic_junction` | NEW doctor_clinic, backfill from doctor.clinic_id | Low | YES |
| `add_booking_health_snapshot` | NEW booking_health_snapshots | Low | YES |
| `add_care_plan_table` | NEW care_plans | Medium | YES |
| `add_soft_delete_columns` | encounters, care_plans, lab_results, ai_conversations, medications | Low | YES (drop cols) |
| `alter_medication_add_fields` | medications: encounter_id, frequency, started_at, ended_at, prescribed_by_doctor_id, is_active | Low | YES |
| `alter_lab_result_add_encounter` | lab_results: encounter_id | Low | YES |
| `alter_ai_conversation_extend` | ai_conversations: encounter_id, session_type, escalation_reason, input_blocked, output_blocked, total_tokens, key_version | Low | YES |
| `alter_consent_add_fields` | consents: granted_to_type, purpose, version | Low | YES |
| `alter_doctor_add_fields` | doctors: bio, avatar_url, consultation_fee, is_verified, is_active | Low | YES |
| `alter_clinic_add_fields` | clinics: email, specialty_tags, operating_hours, is_active, is_verified | Low | YES |
| `timescale_hypertable_policies` | health_metrics: compression + retention policies | Medium | Partial (retention interval adjustable) |

### Phase 2 — Destructive (after code ships reading junction)

| Migration | Tables affected | Risk | Reversible |
|---|---|---|---|
| `drop_doctor_clinic_id_column` | doctors: DROP clinic_id | **Medium** | NO — gate behind impact check |

**Rule:** Phase 1 migrations are a single reviewed PR. Phase 2 ships only after all code reading
`doctor.clinic_id` is replaced and tests pass against junction-only queries.

---

## 4. RBAC Matrix

**Scope key:** own = self only · consent = active Consent required · clinic = actor's clinic(s) via doctor_clinic · platform = all records

| Resource / Action | PATIENT | DOCTOR | CLINIC_ADMIN | INTERNAL_ADMIN | MEDICAL_REVIEWER | SUPER_ADMIN | AI_SERVICE |
|---|---|---|---|---|---|---|---|
| Own PatientProfile R/U | ✅ own | ✅ consent | ❌ | ✅ platform R | ✅ platform R | ✅ platform | ❌ |
| Other Patient PHI R | ❌ | ✅ consent | ❌ | ❌ | ✅ platform R (audited) | ✅ platform | ✅ consent R only |
| Encounter C/U | ❌ | ✅ assigned + consent | ❌ | ❌ | ❌ | ✅ platform | ❌ **hard-blocked** |
| Encounter R | ✅ own | ✅ consent + clinic | ✅ clinic metadata only (no clinical body) | ❌ | ✅ platform R | ✅ platform | ✅ consent R |
| CarePlan C (draft) | ❌ | ✅ doctor | ❌ | ❌ | ❌ | ✅ platform | ✅ **draft only, ai_generated=true** |
| CarePlan APPROVE / set ACTIVE | ❌ | ✅ **doctor only** | ❌ | ❌ | ❌ | ❌ | ❌ **hard-blocked** |
| Medication C/U | ❌ | ✅ **doctor only** | ❌ | ❌ | ❌ | ❌ | ❌ **hard-blocked** |
| Medication R | ✅ own | ✅ consent + clinic | ❌ | ❌ | ✅ platform R | ✅ platform | ✅ consent R (summarize only) |
| LabResult R | ✅ own | ✅ consent + clinic | ❌ | ❌ | ✅ platform R | ✅ platform | ✅ consent R |
| LabResult verify_by_doctor | ❌ | ✅ doctor | ❌ | ❌ | ✅ | ❌ | ❌ |
| Appointment C (book self) | ✅ own | ❌ | ❌ | ❌ | ❌ | ✅ platform | ❌ |
| Appointment confirm/cancel | ❌ | ✅ clinic | ✅ clinic | ❌ | ❌ | ✅ platform | ❌ |
| BookingHealthSnapshot R | ✅ own | ✅ consent + clinic | ❌ | ❌ | ✅ platform R | ✅ platform | ✅ consent R |
| AIConsultation R | ✅ own | ✅ consent + clinic | ❌ | ✅ platform R | ✅ platform R | ✅ platform | ✅ own session only |
| Consent grant/revoke | ✅ own | ❌ | ❌ | ❌ | ❌ | ✅ break-glass, audited | ❌ |
| AuditLog R | ❌ | ❌ | ✅ clinic-scoped | ✅ platform | ✅ platform | ✅ platform | ❌ (write-only via system) |
| Doctor/Clinic mgmt | ❌ | ❌ | ✅ own clinic | ✅ platform | ❌ | ✅ platform | ❌ |
| Doctor is_verified set | ❌ | ❌ | ❌ | ✅ INTERNAL_ADMIN only | ❌ | ✅ platform | ❌ |
| Diagnosis (any form) | ❌ | ✅ doctor | ❌ | ❌ | ❌ | ❌ | ❌ **hard-blocked** |
| Prescription / dose change | ❌ | ✅ doctor | ❌ | ❌ | ❌ | ❌ | ❌ **hard-blocked** |

**Critical invariants (test these as negative cases):**
1. AI_SERVICE has no bypass — runs through the same ConsentGuard as human callers.
2. CLINIC_ADMIN denied clinical body (encounter notes, lab values, medication details) — sees metadata only.
3. INTERNAL_ADMIN denied clinical body (administrative access only, not clinical).
4. SUPER_ADMIN denied care-plan approval and prescription — clinical authority is never an admin privilege.
5. Every DENY writes `AuditLog(outcome=denied, severity=warning)`.

---

## 5. AI Safety Enforcement Plan

**Defense-in-depth. Each layer is independently testable. All fail closed.**

### Layer ordering (request flow)
```
Request
  → Layer 0: Consent Gate (ai_use check)
  → Layer 1: Input Red-Flag Detection
  → Layer 2: Capability Deny-List (pre-model, structural)
  → [LLM call]
  → Layer 3: Output Restricted-Advice Filter
  → Layer 4: Escalation Engine (triggered by L1 or L3)
  → Layer 5: Mandatory Disclaimer Injection
  → Layer 6: Immutable Audit (always, including on deny/block)
→ Response
```

### Layer definitions

| Layer | Name | Enforcement point | What it does |
|---|---|---|---|
| L0 | Consent Gate | `ConsentGuard` in service layer | Blocks AI from reading any PHI without active `ai_use` consent. HTTP 403 + AuditLog(denied). |
| L1 | Input Red-Flag Detection | Domain `triage.py` rule engine (pre-LLM) | Detects: chest pain + dyspnea, glucose <50/>300, BP >180/120, suicidal ideation, pediatric emergency, stroke signs, anaphylaxis. Trigger: short-circuit → Escalation (L4), bypass LLM. |
| L2 | Capability Deny-List | Service method boundary (code-level) | Structural block — AI `actor_type` denied write access to: diagnosis fields, Medication C/U, CarePlan approval, dose fields. Enforced in service methods, NOT in prompts. |
| L3 | Output Restricted-Advice Filter | Post-LLM scan | Detects diagnosis-like ("you have X", "this means you have") and prescriptive language ("take X mg", "stop your medication"). Match → replace with safe template + escalate. |
| L4 | Escalation Engine | Service layer + notification | Creates/links Encounter with `status=PENDING_REVIEW`, routes to assigned/on-call doctor, fires notification. Sets `AIConsultation.escalated_to_doctor=true` + reason. |
| L5 | Disclaimer Injection | Response formatter | Every AI message tagged `not_a_diagnosis=true`, user-visible disclaimer appended. Non-removable. |
| L6 | Immutable Audit | AuditLog (always writes, even on block) | Logs every AI interaction: guardrails fired, escalation triggered, blocked intents, model used, token count. Severity: info (normal), warning (L3 hit), critical (L1 red-flag). |

### Emergency red flags (L1 — always escalate, never route to LLM)
- Blood glucose < 50 mg/dL or > 300 mg/dL
- Systolic BP > 180 or diastolic > 120
- Chest pain + shortness of breath (concurrent)
- Suicidal ideation / self-harm intent
- Stroke symptoms (FAST criteria: face droop, arm weakness, speech)
- Anaphylaxis indicators (throat swelling, widespread rash + breathing difficulty)
- Pediatric emergency (child + any critical vital)
- Any user-reported symptom tagged as "emergency" / "cấp cứu"

### Prohibited outputs (L2/L3)
- Definitive diagnoses ("Bạn bị / You have [condition]")
- Specific drug prescriptions or dosage instructions
- Instructions to start, stop, or change prescribed medication
- Quantified treatment plans (e.g., "reduce insulin by X units")
- Prognosis statements ("This will / won't improve")

---

## 6. Test Plan

### Model / Migration tests
- [ ] Every new migration: `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` on clean DB
- [ ] `doctor_clinic` junction: backfill correctness, `is_primary` unique per doctor
- [ ] Soft-delete mixin: default queries exclude `deleted_at IS NOT NULL`; reviewer/admin include-deleted path
- [ ] TimescaleDB: hypertable created; compression + retention policies exist (requires Postgres)

### Encounter relation tests
- [ ] Encounter created with null `appointment_id` (walk-in) succeeds
- [ ] Encounter created with `appointment_id` succeeds and links correctly
- [ ] Retroactive link: pre-existing LabResult/AIConsultation assigned `encounter_id` after creation
- [ ] Soft-deleting Encounter with active children: defined cascade/restrict behavior enforced

### RBAC tests (matrix-driven — one per high-risk cell)
- [ ] Patient A cannot read Patient B's profile, metrics, encounters, medications
- [ ] Doctor without active consent: HTTP 403 on patient PHI endpoint
- [ ] Doctor with active consent: HTTP 200; consent revoke mid-session → 403 on next request
- [ ] ClinicAdmin: HTTP 200 on appointment metadata; HTTP 403 on encounter clinical body
- [ ] InternalAdmin: HTTP 403 on encounter clinical notes
- [ ] SuperAdmin: HTTP 403 on care-plan approval and medication create endpoints
- [ ] Every denied request: AuditLog row exists with `outcome=denied`

### Consent gate tests (Q3)
- [ ] No consent: ConsentGuard raises ConsentDenied → HTTP 403
- [ ] Expired consent: denied
- [ ] Wrong data_scope: denied
- [ ] Revoked consent: denied
- [ ] AI service path hits same guard (no bypass): AI call with no ai_use consent → denied

### AI safety tests (per layer)
- [ ] L1: each red-flag input → escalation triggered, no LLM call, AIConsultation logged
- [ ] L2: AI actor_type rejected on Medication.create, CarePlan.approve, diagnosis field write
- [ ] L3: prescriptive/diagnostic output replaced with safe template
- [ ] L4: escalation creates Encounter `PENDING_REVIEW` + AuditLog
- [ ] L5: every AI response contains disclaimer
- [ ] L6: every AI interaction has AuditLog row; L1/L3 events have elevated severity
- [ ] CarePlan from AI: `ai_generated=True`, `status=PENDING_REVIEW` never `ACTIVE`

### CarePlan state machine tests
- [ ] Legal transitions: DRAFT→PENDING_REVIEW→APPROVED→ACTIVE allowed
- [ ] Illegal transitions: ACTIVE→DRAFT, direct DRAFT→ACTIVE rejected
- [ ] Approval sets `approved_by_doctor_id` + `approved_at` + AuditLog

### Encryption tests
- [ ] AIConsultation.messages: raw DB column value is ciphertext, ORM returns plaintext
- [ ] Key rotation: old ciphertext decryptable with versioned key
- [ ] No PHI in application logs (log-scrubber test)
- [ ] BookingHealthSnapshot.payload: ciphertext at rest

### Privacy / retention tests
- [ ] BookingHealthSnapshot: no UPDATE path exists (append-only enforced at service layer)
- [ ] BookingHealthSnapshot: HTTP 403 for CLINIC_ADMIN / scheduler roles
- [ ] Retention policy purges health_metrics beyond interval (requires TimescaleDB)

---

## 7. Open Risks and Recommendations for PTH

| # | Risk | Level | Recommendation |
|---|---|---|---|
| R1 | Drop `doctor.clinic_id` is the only irreversible migration step | Medium | Two-phase deploy: add junction → ship code → verify tests → drop column in separate release |
| R2 | TimescaleDB hypertable + retention not verified on real Postgres (Docker was DOWN) | Medium | Run T2 (Postgres verify) before shipping T4 migrations to staging |
| R3 | `Consent.ai_use` type not yet in existing consent_type values | Low | Add to consent_type enum/validation in first T4 migration |
| R4 | `ConsentGuard` dependency doesn't yet exist as a reusable service | Low | Implement as first T4 task, before any endpoint that calls it |
| R5 | Red-flag thresholds (glucose, BP) need medical board sign-off | High | Do not hardcode clinical thresholds — make configurable and flag for medical reviewer approval |
| R6 | Fernet key rotation (`key_version`) not yet wired to existing crypto infra | Low | Add `key_version` column in migration; wire rotation helper before any production data |
| R7 | AI hard-blocks enforced at service layer only — need integration test harness, not just unit | Medium | CI must include at least one end-to-end AI safety test (mock LLM → guardrail → response) |

---

*End of BLUEPRINT_REVIEW_RESPONSE.md — Claude Code, 2026-06-17*
*Awaiting PTH approval before T4 implementation begins.*
