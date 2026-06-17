# Claude Code Task — Medical Domain Blueprint Review
> Task ID: METOCARE-BLUEPRINT-REVIEW-001
> Date: 2026-06-17
> Requester: OpenClaw Coordinator
> Mode: READ-ONLY REVIEW + DESIGN ANSWERS — NO CODE, NO FILE CHANGES

---

## Mission

Review the Medical Domain Blueprint at `docs/MEDICAL_DOMAIN_BLUEPRINT.md` and answer 8 design questions.
Return a structured design document. Do NOT implement anything. Do NOT create migrations. Do NOT edit source files.

## Context files to read (ONLY these — no full repo scan)

```
docs/MEDICAL_DOMAIN_BLUEPRINT.md        ← primary input
docs/Architecture_Doctrine.md           ← constraints
docs/Technical_Architecture.md          ← tech stack decisions
docs/AI_Safety_Guardrail.md             ← AI safety rules
backend/app/models/care.py              ← Doctor, Clinic, Appointment models
backend/app/models/clinical.py          ← LabResult, Medication, HealthMetric
backend/app/models/ai.py                ← AIConversation
backend/app/models/governance.py        ← Consent, AuditLog
backend/app/models/user.py              ← UserRole, MFA_REQUIRED_ROLES
backend/app/core/crypto.py              ← EncryptedString (PHI field encryption)
backend/alembic/versions/               ← list existing migrations (names only)
```

## PTH Conditions (must address each explicitly)

1. Encounter entity — define exact relations; clarify can exist without Booking
2. CarePlan approval — AI draft only, Doctor activate only, audit trail all changes
3. Medication — AI hard-blocked create/update, Doctor-only, AI may only summarize with disclaimer
4. Consent ai_use — mandatory before AI reads clinical data, checked at service/API not UI
5. Doctor multi-clinic — recommend junction table vs single FK; PTH preference = junction table if low cost
6. AI Safety Enforcement — red flags, restricted advice, escalation, audit log, not-diagnosis/not-prescription
7. RBAC matrix — Patient own-only, Doctor consent-gated, Clinic Admin clinic-scope, SuperAdmin platform, AI service account no bypass
8. Migration risk — additive + reversible, test requirements

## Required Output (write to docs/agent/BLUEPRINT_REVIEW_RESPONSE.md)

Sections:
1. Design answers (8 questions)
2. Final entity relationship proposal (text diagram)
3. Migration plan (table: migration name, tables affected, risk, reversible?)
4. RBAC matrix (full table)
5. AI safety enforcement plan (layers, rules, enforcement points)
6. Test plan (what to test, not how to code it)
7. Open risks / recommendations for PTH

## Hard constraints

- No file edits except writing docs/agent/BLUEPRINT_REVIEW_RESPONSE.md
- No git commits
- No pip installs
- No test runs
- No migration generation
- Budget: complete in one focused session
