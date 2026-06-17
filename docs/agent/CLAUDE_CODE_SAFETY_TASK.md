# Claude Code Task — Medical Safety Package
> Task ID: METOCARE-SAFETY-001
> Date: 2026-06-17 12:06 GMT+7
> Requester: OpenClaw Coordinator (PTH approval)
> Mode: READ-ONLY DESIGN — NO CODE, NO FILE CHANGES except output docs

---

## Mission

Produce 4 deliverables as part of the Medical Safety Package required before T4 implementation:

1. **AISession + AIClinicalRecommendation entity split** (replaces AIConversation)
2. **Medical Safety Matrix**
3. **Escalation Rules**
4. **Emergency Red Flag Policy**

Write all output to: `docs/agent/MEDICAL_SAFETY_PACKAGE.md`

Do NOT modify any source files. Do NOT create migrations. Do NOT run tests.

---

## Context files to read

```
docs/AI_Safety_Guardrail.md
docs/MEDICAL_DOMAIN_BLUEPRINT.md
docs/agent/BLUEPRINT_REVIEW_RESPONSE.md       ← approved design decisions
backend/app/models/ai.py                       ← current AIConversation model
backend/app/models/governance.py               ← Consent, AuditLog
backend/app/models/user.py                     ← UserRole
backend/app/domain/guardrails.py               ← existing guardrail logic
backend/app/domain/triage.py                   ← existing triage logic
backend/app/domain/policies.py                 ← SYSTEM_SAFETY_PROMPT, prohibited list
```

---

## Deliverable 1 — AISession + AIClinicalRecommendation split

PTH requires splitting AIConversation into two entities:

**AISession** — the conversational session (chat transcript, triage, lifestyle coach):
- Patient-facing interaction log
- Multiple messages per session
- Session type: health_assistant / lifestyle_coach / lab_explanation / triage
- Fields: patient_id, encounter_id (nullable), session_type, messages (EncryptedString), risk_level,
  escalated_to_doctor, escalation_reason, model_used, safety_flags, input_blocked, output_blocked,
  total_tokens, key_version, deleted_at, deleted_by

**AIClinicalRecommendation** — structured AI output with clinical significance:
- Created when AI produces output that has clinical relevance (lab explanation, care plan draft, triage result)
- Always linked to AISession
- Requires doctor review before acting on
- Fields: session_id FK, patient_id, encounter_id (nullable), recommendation_type
  (lab_explanation / care_plan_draft / lifestyle_advice / triage_assessment / metabolic_score),
  content (EncryptedString), status (pending_review / reviewed / accepted / rejected / superseded),
  reviewed_by_doctor_id (FK nullable), reviewed_at, ai_confidence (Float 0-1),
  safety_cleared (Boolean), medical_disclaimer (Text), key_version

Define:
- Exact fields for both entities
- Relationship between them
- RBAC: who can read/write each
- How these replace the current AIConversation model
- Migration path from AIConversation

---

## Deliverable 2 — Medical Safety Matrix

A comprehensive matrix covering:

**Rows:** All AI action types:
  lab_interpretation, metabolic_score, lifestyle_coaching, triage_assessment,
  care_plan_draft, symptom_analysis, medication_summary, health_trend_analysis,
  emergency_escalation, general_health_question

**Columns:**
  - Allowed? (YES / NO / CONDITIONAL)
  - Consent required (type)
  - Doctor review required before patient sees output?
  - Escalation trigger?
  - AuditLog severity
  - PHI access level
  - Disclaimer required?
  - Hard-block (enforced at code level, not prompt)?

---

## Deliverable 3 — Escalation Rules

Define the complete escalation decision tree:

- What triggers escalation (rule-based, not LLM judgment)
- Escalation levels: IMMEDIATE (call/emergency) / URGENT (within 2h) / ROUTINE (within 24h) / ADVISORY (inform only)
- What happens at each level: who is notified, what is created, what patient sees
- Escalation to: attending_doctor / on_call_doctor / emergency_services / patient_only
- Timeout rules: if doctor doesn't respond within X minutes → escalate further
- How escalation is recorded (Encounter status, AuditLog, AISession)
- How escalation is cancelled or resolved

---

## Deliverable 4 — Emergency Red Flag Policy

Define the complete red flag detection policy:

- Full list of emergency conditions with clinical thresholds (vital sign values, symptom combinations)
- Source: evidence-based thresholds (AHA, WHO, IDF, VNHA guidelines for Vietnamese population)
- Detection method: rule engine (not LLM) — exact conditions
- False positive policy: what happens if patient disputes a red flag
- Override policy: can a doctor override a red flag? Under what conditions?
- Logging: every red flag detection must be logged regardless of outcome
- Patient communication: exact message shown to patient on red flag trigger
- Edge cases: patient ignores escalation, phone unreachable, no assigned doctor

---

## Output format

Write to `docs/agent/MEDICAL_SAFETY_PACKAGE.md`:

```
# Medical Safety Package — MetoCare
> Version, Date, Reviewer

## 1. AI Entity Split: AISession + AIClinicalRecommendation
## 2. Medical Safety Matrix
## 3. Escalation Rules
## 4. Emergency Red Flag Policy
## 5. Integration with Blueprint (how this connects to approved BLUEPRINT_REVIEW_RESPONSE.md)
## 6. Open questions / items requiring medical board sign-off
```

---

## Hard constraints

- No source file edits except writing `docs/agent/MEDICAL_SAFETY_PACKAGE.md`
- No git commits
- No migrations generated
- No test runs
- All clinical thresholds must be flagged as "requires medical board sign-off"
- No hardcoding absolute clinical values as final — mark as PROPOSED_THRESHOLD
