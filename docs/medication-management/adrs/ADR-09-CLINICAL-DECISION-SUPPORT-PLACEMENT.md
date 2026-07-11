# ADR-09 — Clinical Decision Support Placement

**Status:** PROPOSED — Gate 1 (blocks all implementation)  
**Date:** 2026-07-11  
**Deciders:** PTH, Tech Lead

---

## ADR Metadata

| Field | Value |
|-------|-------|
| ADR | ADR-09 |
| Status | Accepted |
| Architecture Version | medication-architecture-v1.0 |
| Implementation Gate | Gate 1 |
| Domain | CDS Placement |
| Supersedes | None |
| Superseded By | None |

---


## Context

Clinical Decision Support (CDS) là engine thực thi safety checks và advisory rules. Câu hỏi: code này nên chạy ở đâu trong tech stack?

MetoCare cần CDS cho: allergy check, interaction check, duplicate detection, lab-drug flag, organ function caution. Kết quả là `ClinicalAlert` records được lưu và surface cho user.

---

## Problem

Nếu CDS chạy ở sai layer:
- **Frontend**: có thể bị bypass (direct API call), không reliable
- **Database trigger**: không testable, không observable, hard to version
- **AI layer**: AI is non-deterministic — safety checks MUST be deterministic
- **Middleware (request-level)**: chạy mọi request kể cả khi không cần → performance overhead
- **Async worker**: alert không available ngay khi medication được add → patient sees no warning

---

## Decision Drivers

- Safety checks phải deterministic — không thể depend on AI
- Safety checks phải testable in isolation
- Safety checks phải run BEFORE medication is confirmed (synchronous for write operations)
- Safety checks phải không bị bypass qua direct API call
- Lab-drug checks có thể run async (không block lab result save)
- Must be clear separation: deterministic safety vs AI explanation

---

## Options Considered

### Option A — Frontend validation
Check before submit. Can be bypassed. Not reliable for safety.

### Option B — Database trigger
Hard to test, hard to version, invisible in code review.

### Option C — API middleware/interceptor
Runs on every request. Too broad. Performance overhead.

### Option D — Domain service (synchronous for medication writes)
CDS as a Python service/module called explicitly in write endpoints.

### Option E — Async background worker (Celery/RQ)
Decoupled. Alert generated after save. May introduce delay.

### Option F — Hybrid: synchronous CDS for writes, async for lab-drug checks
Medication add/confirm → synchronous CDS → surface alerts before response.  
New lab result → async CDS → alert generated in background.

---

## Trade-off Table

| Criterion | A (frontend) | B (DB trigger) | C (middleware) | D (domain service sync) | E (async) | F (hybrid) |
|-----------|-------------|----------------|----------------|-------------------------|-----------|------------|
| Cannot be bypassed | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Deterministic | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Testable | ✅ | ❌ | ⚠️ | ✅ | ✅ | ✅ |
| Alert available immediately | ⚠️ | ⚠️ | ⚠️ | ✅ | ❌ | ✅ (for medication add) |
| Performance | ✅ | ✅ | ❌ | ⚠️ Adds latency to writes | ✅ | ✅ |
| Separation of concerns | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Lab-drug check feasible | N/A | ⚠️ | N/A | ⚠️ Slows lab save | ✅ | ✅ |

---

## Recommended Decision

**Option F — Hybrid: synchronous domain service for medication write events, asynchronous worker for lab-triggered checks.**

---

## Why This Option

Medication add/edit is a low-frequency, high-importance operation. Synchronous CDS adds 50–200ms latency to this operation — acceptable. Patient gets immediate alert feedback.

Lab result saves are higher frequency. Running full medication CDS on every lab save synchronously would slow lab save unacceptably. Async worker: lab save → queue event → worker runs CDS → alert created → patient sees on next page load or via push.

AI explanation is always separate from CDS checks. AI explains what CDS already detected — AI never generates the safety check.

---

## Consequences

**CDS as domain service (Python module, no new infrastructure):**
```
app/domain/cds/
  __init__.py
  engine.py           — orchestrates all checks
  allergy_check.py    — runs allergy match + cross-reactivity
  interaction_check.py — runs drug interaction rules
  duplication_check.py — duplicate ingredient/class detection
  lab_drug_check.py   — lab value + medication thresholds
  organ_caution.py    — eGFR, LFT, age-based cautions
  alert_types.py      — ClinicalAlert dataclass, severity enum
```

**CDS invocation (synchronous — called from medication service):**
```python
# In medication_service.add_medication() AFTER medication record created:
alerts = cds_engine.run_medication_checks(
    new_medication_id=medication.id,
    patient_id=patient_id,
    db=db
)
# Persist alerts
for alert in alerts:
    alert_service.save_alert(alert, db)
# Return medication + alerts to API response
return MedicationCreateResponse(medication=med_out, new_alerts=alerts)
```

**CDS invocation (async — called from lab result service):**
```python
# In lab_service.save_lab_result() AFTER lab record saved:
background_tasks.add_task(
    cds_engine.run_lab_drug_checks,
    lab_result_id=lab_result.id,
    patient_id=patient_id
    # Uses FastAPI BackgroundTasks — no Celery needed for MVP
)
```

**Clear separation of CDS vs AI:**
```
CDS Engine
  Input: patient medications + allergies + labs (structured DB data)
  Processing: deterministic rule execution
  Output: ClinicalAlert records (persisted)
  Nature: always same output for same input

AI Explanation
  Input: ClinicalAlert record (already persisted)
  Processing: LLM translates alert into plain Vietnamese
  Output: Conversational explanation
  Nature: language generation only, not clinical determination
```

**AI NEVER generates clinical alerts.** If AI is asked "am I at risk from my medications?", it answers based on active alerts count in context — it does NOT run its own analysis.

**`medication_alerts` table (replaces `medication_warnings`):**
```sql
CREATE TABLE medication_alerts (
    id                    UUID PK,
    patient_id            VARCHAR(36) NOT NULL,
    alert_type            VARCHAR(64) NOT NULL,
      -- allergy | interaction | duplication | lab_drug | organ_caution | supplement_caution
    severity              VARCHAR(16) NOT NULL,
      -- critical | high | medium | low | informational
    involved_medication_ids JSON NOT NULL,          -- list of medication IDs
    involved_alert_ids     JSON nullable,           -- for deduplication chains
    title                 TEXT NOT NULL,            -- Vietnamese display title
    body                  TEXT NOT NULL,            -- Vietnamese explanation
    mechanism_ref         VARCHAR(64) nullable,     -- FK to interaction/cross-reactivity rule that triggered
    evidence_level        VARCHAR(8) NOT NULL,
    source                VARCHAR(255) NOT NULL,
    can_be_dismissed      BOOLEAN NOT NULL,
    requires_doctor_ack   BOOLEAN NOT NULL,
    is_dismissed          BOOLEAN NOT NULL DEFAULT FALSE,
    dismissed_by_user_id  VARCHAR(36) nullable,
    dismissed_at          DATETIME nullable,
    dismiss_acknowledgment TEXT nullable,           -- "Tôi đã hỏi bác sĩ" acknowledgment text
    triggered_at          DATETIME NOT NULL,
    trigger_event         VARCHAR(64) NOT NULL,     -- medication_add | lab_result_save | daily_check
    INDEX (patient_id, is_dismissed, severity)
);
```

**Deduplication:** CDS engine checks for existing active alert for same (patient, alert_type, medication_pair) before creating new one. Prevents duplicate alerts on every medication edit.

**Alert lifecycle:**
- `is_dismissed = FALSE`: shown to patient
- `is_dismissed = TRUE` + MEDIUM/LOW: patient dismissed
- `is_dismissed = FALSE` + CRITICAL: no dismiss option — requires clinical action
- On medication soft-delete or status change to discontinued: mark related alerts as auto-resolved

---

## Data Model Impact

- `medication_alerts` table (replaces `medication_warnings` from P0 design)
- No modification to `medications` table needed
- CDS engine reads from: `medications`, `patient_allergies`, `drug_interactions`, `allergy_cross_reactivity_rules`, `lab_results` (recent), `drug_ingredient_knowledge`

---

## API Impact

- `GET /patients/{id}/medications/alerts` — list active alerts
- `GET /patients/{id}/medications/alerts?severity=critical` — filter by severity
- `POST /patients/{id}/medications/alerts/{aid}/dismiss` — dismiss (enforces severity rules)
- Medication create response: includes `new_alerts` array

---

## Security and Privacy Impact

`medication_alerts` is PHI (derived from medication + lab data).  
Access: PATIENT (own), DOCTOR (consent), CAREGIVER (MEDIUM/LOW only — CRITICAL always visible to caregiver if viewing medications).

---

## Clinical Safety Impact

CDS as domain service allows isolated unit testing of every safety rule. Regression tests can confirm: "adding warfarin when aspirin is active ALWAYS generates HIGH alert." This is the core clinical safety assurance.

Determinism guarantee: same input → same output. Essential for safety-critical code.

---

## Migration Impact

`medication_alerts` table is new. No migration of existing data needed.  
`medication_warnings` (designed but never created) → rename to `medication_alerts` in implementation.

---

## Operational Ownership

CDS engine: Tech Lead owns code.  
CDS rules: Clinical Advisor owns rule content.  
CDS test suite: must include test cases for every rule. Failure = block deployment.

---

## Open Questions

1. **FastAPI BackgroundTasks vs dedicated queue:** For lab-drug async checks, FastAPI BackgroundTasks is sufficient for MVP (same process, runs after response). When volume grows, migrate to Redis Queue. Decision for P3 scale assessment. **[Tech Lead owns]**
2. **Daily background re-evaluation:** CDS should run daily to catch cases where catalog updates change alert outcomes. Implementation: cron job or startup check? **[Tech Lead design decision]**

---

## Approval Required From

- [ ] PTH — hybrid synchronous/async architecture approval
- [ ] Tech Lead — FastAPI BackgroundTasks vs dedicated queue decision
- [ ] Tech Lead — CDS module structure and isolation

## Implementation Gate

**Gate 1 — blocks all implementation.**  
Every medication feature that triggers a safety check (P3: allergy, interaction) needs this architecture decided first. If CDS placement changes later (e.g., from sync to async), API response contracts change.
