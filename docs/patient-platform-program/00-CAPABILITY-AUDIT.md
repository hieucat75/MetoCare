# MetoCare — Patient Platform Completion Program

## Phase 0 — Repository Reality Audit (Current-State Capability Matrix)

**Date:** 2026-07-30
**Method:** Direct source inspection of the repository root (backend, frontend, mobile, tests, migrations, CI) by five parallel audit passes. Not derived from conversation memory. Every row below is anchored to real files.

**Repo shape verified:**
- `backend/` — FastAPI + SQLAlchemy/Alembic. 40+ route modules, ~3,150 backend tests, **single Alembic head** (`k2_s0_round3_hardening`, 72 revisions).
- `frontend/` — Next.js 14 App Router (`src/app`), TS + Tailwind + Radix. 4 surfaces (patient / doctor / admin / clinic). ~505 Jest tests, **no E2E**.
- `mobile/` — **EMPTY.** Contains only `design-reference/source.html` + editor settings. **No Expo/RN app, no `package.json`, no `app.json`, no `eas.json`, no build pipeline.**
- CI: `ci.yml` PR-gated (backend, backend-postgres, frontend, meto-gate) → staging CD live on green `main`; production is manual `workflow_dispatch` only. DigitalOcean = legacy/frozen.

### Legend
`COMPLETE` = built + wired + tested · `PARTIAL` = built but gaps · `DISCONNECTED` = built but no usable journey · `STUB` = placeholder UI/logic · `MISSING` = does not exist

---

### A. Platform Foundations (cross-cutting)

| # | Capability | Status | Evidence / Note |
|---|---|---|---|
| F1 | Auth: JWT HS256 + refresh-token rotation (family, reuse-detect, revoke) + Argon2id | **COMPLETE** | `core/security.py`, `models/auth_tokens.py`, `services/auth.py` |
| F2 | MFA enforcement | **PARTIAL (off)** | `config.py:mfa_enforcement_enabled=False`; TOTP enroll/verify works but never forced |
| F3 | Password policy (length/complexity) | **MISSING** | `register`/`change_password` accept any non-empty string |
| F4 | PHI field-level encryption (Fernet/MultiFernet, rotation) | **COMPLETE** | `core/crypto.py:EncryptedString`, `models/patient.py`; caveat `on_decrypt_failure="none"` (silent None) |
| F5 | Consent + PHI authorization (ConsentGuard, per-route BOLA) | **PARTIAL** | `services/consent_guard.py` **fails OPEN when `CONSENT_GATE` off**; dual id namespace `User.id` ≠ `PatientProfile.id` is a live footgun |
| F6 | **Object storage** for uploaded documents | **MISSING** | Uploads read into memory, OCR'd, **discarded**. No S3/Blob/disk write, no signed URLs, no retrieval endpoint. `storage_mode` setting unused |
| F7 | **Notification delivery** (push/email/SMS) | **MISSING** | `services/notification.py` = in-app DB rows only; `services/notifications.py` = in-memory stub. No APNs/FCM/SMTP/SES/SMS |
| F8 | AI provider gateway (Meto registry, routing chain, circuit breaker, cost/RPM guard) | **COMPLETE** | `llm/gateway.py`, `ai/registry.py`; caveat: no explicit model-version/prompt-hash persisted |
| F9 | Audit log (append-only) + category retention TTL | **COMPLETE** | `services/audit.py`, `audit_retention.py`; caveat: `record()` only flushes (caller must commit) |
| F10 | Upload security: magic-byte MIME sniff, size cap (10MB), PDF page cap, SSRF-guarded URL fetch | **PARTIAL** | `services/lab_upload.py`; **no AV scan, no rate-limit on upload endpoint** (ratelimit wired only to auth/admin/knowledge, in-memory only) |
| F11 | Secrets management | **PARTIAL** | No hardcoded secrets, but `config.py` ships committed **dev-default `secret_key` AND Fernet `encryption_keys`**; prod safety = warn-only, not fail |
| F12 | Rate limiting (token bucket + lockout) | **PARTIAL** | `core/ratelimit.py` in-memory only; Redis backend raises `NotImplementedError` (won't hold across ACA replicas) |

### B. Medical Document Intelligence & OCR

| # | Capability | Status | Evidence / Note |
|---|---|---|---|
| D1 | Generic **Medical Document** bounded context (artifact, hash, multi-page, doc-type classification, `uploaded→…→needs_review→confirmed` lifecycle) | **MISSING** | Only lab-bound `LabDocument`/`OCRCase`; state machine is lab-only (`uploaded→ocr_pending→ocr_done→interpreted`). No doc-type router |
| D2 | OCR engines: Tesseract (live, local), Azure Document Intelligence (real, per-word conf), Anthropic Vision (real) | **COMPLETE (gated off)** | `services/ocr_engine.py`; `MockOcrEngine` is default (`ocr_mode="mock"`) |
| D3 | Provider abstraction as swappable *stages* (preprocess / OCR / entity-extract / normalize / confidence / review / promote) | **PARTIAL** | Only OCR↔cloud-fallback is abstracted; stages are procedural in `lab_upload.py`. Legacy `ocr.py:OCRProvider` ABC is skeleton-only; `ai/registry.py` is chat-only, not wired to OCR |
| D4 | **Prescription OCR** (medicine/strength/dose/frequency) | **MISSING** | `report_type` hard-enumerated to `lab_result`. `drug_catalog.py` parses typed text only, never images |
| D5 | **Lab report OCR** (analytes, SI normalization, per-field confidence, provenance, confirm→promote) | **COMPLETE (lab, gated off)** | `domain/lab_interpreter.py` (`ConfidenceDetail`, `OCR_CONFIDENCE_THRESHOLD=0.75`), `lab_provenance.py`; **confirm-then-promote, never auto-write** (`routes/lab_upload.py` returns draft, `services/lab.py:create_manual_entry` promotes) |
| D6 | **General medical report OCR** (discharge/imaging/pathology/referral) | **MISSING** | Zero non-lab extraction |
| D7 | Field-level confidence + review-UI contract | **COMPLETE (lab)** | `RawLabValue`/`InterpretedBiomarker`: `original_value`, `requires_review`, `needs_verification`, `date_needs_confirmation` |
| D8 | Fixture/eval harness, per-field accuracy, thresholds | **COMPLETE (lab)** | `ocr_dataset/` golden+benchmark per hospital; `domain/ocr_gap_analysis.py`; targets Vinmec ≥95% / Medlatec ≥90% |

### C. Medication, Clinical, AI

| # | Capability | Status | Evidence / Note |
|---|---|---|---|
| M1 | Medication CRUD (statement-first, lifecycle/verification status, append-only audit, soft-delete) | **COMPLETE** | `routes/patients.py`, `services/medication.py` |
| M2 | Adherence: taken/skipped events, streaks, summary | **COMPLETE** | `services/medication.py:log_adherence`, `MedicationAdherence` model |
| M3 | **Medication reminder/scheduling engine** | **MISSING** | `frequency` is free text; no structured schedule, no scheduler/cron, no proactive prompt |
| M4 | Doctor verification + provenance (MedicationStatement → canonical) | **COMPLETE** | `medication.py:verify_medication`, `MedicationAuditLog` |
| M5 | Reconciliation operator journey (list/accept/merge pending statements) | **PARTIAL** | Gap logic exists inline; **no API endpoint** to drive it |
| K1 | K2 knowledge lifecycle (draft→submit→approve→retire, AI-provenance) | **DISCONNECTED** | `services/knowledge_repository.py` reachable only via import scripts; no API route calls write funcs |
| K2 | K2 knowledge retrieval endpoints (BOLA-safe, verified-doctor gated) | **PARTIAL (off)** | `routes/medication_knowledge.py`; `MEDICATION_KNOWLEDGE_RETRIEVAL` default OFF (503) |
| C1 | Clinical insight / priority engine / metabolic score (verified-data-based) | **COMPLETE** | `domain/patient_insight.py` filters to `verified_by_user/doctor`; `priority_engine.py`, `metabolic_score.py`, `next_best_action.py`; `CLINICAL_INSIGHT` default ON |
| AI1 | Meto AI chat: context builder (profile/labs/meds/metrics/appts), safety in/out guardrails, audit | **COMPLETE** | `services/meto_chat.py`, `ai/context/builder.py`, `ai/prompt/safety.py` |
| AI2 | Meto **confirmed-data restriction** + flag/consent gate | **PARTIAL (safety gap)** | Context feeds **unverified** active/paused meds + unfiltered labs; `/meto/chat` has **no flag gate**, consent not enforced in chat |
| T1 | Health timeline unification | **PARTIAL** | `domain/health_timeline.py` unifies labs/metrics/meds-started/symptoms; **omits appointments/consultations, documents, nutrition, adherence** (adherence event declared but never emitted) |

### D. Verticals & Web Surfaces

| # | Capability | Status | Evidence / Note |
|---|---|---|---|
| V1 | Doctor marketplace + booking + consultation lifecycle + consent-scoped record sharing | **COMPLETE (un-gated)** | `routes/marketplace.py`, `booking.py`, `consultations.py`; `ConsultationAccessGrant` gates patient-summary/notes |
| V2 | Payment | **STUB** | Mock `/pay`; no real gateway |
| V3 | Clinic SaaS multi-tenant (M05–M08) | **COMPLETE (dormant)** | `CLINIC_SAAS` flag OFF |
| W1 | Patient **web** app (dashboard, metrics+charts, labs OCR upload/review, meds, marketplace, consultations, profile, timeline, care-plan, Meto chat) | **COMPLETE** | `frontend/src/app/(patient)/*`; hand-rolled SVG charts |
| W2 | Patient web: ai-copilot subpages (body/coach/journey/network) | **STUB** | Render `@/lib/mock/aiCopilotData` |
| W3 | Patient web: devices/wearables | **STUB** | No API wiring |
| W4 | Doctor portal (dashboard/queue/appointments/consultations/patients/notes/copilot) | **COMPLETE** | `frontend/src/app/doctor/*` |
| W5 | Admin portal (dashboard/doctors/patients/users/feature-flags/audit/ai-safety) | **COMPLETE** | `frontend/src/app/admin/*`; `clinics`+`reports` pages STUB |
| W6 | Web token storage | **PARTIAL (risk)** | Access+refresh in `localStorage` (XSS-exposed) |
| W7 | Web document upload | **PARTIAL** | Labs-only, `accept="image/*"` (no PDF picker), no generic doc vault |

### E. Mobile & Release

| # | Capability | Status | Evidence / Note |
|---|---|---|---|
| X1 | Patient **native mobile app** (iOS + Android) | **MISSING** | `mobile/` has only `design-reference/source.html` |
| X2 | Mobile build/release pipeline (Expo EAS, signing, TestFlight, internal Android) | **MISSING** | No config anywhere |
| Q1 | Backend test suite (~3,150 tests, broad) | **COMPLETE** | `pytest --co` clean; pass/fail unverified this pass |
| Q2 | Alembic single-head + migration roundtrip tests + PG parity | **COMPLETE** | `tests/test_migrations.py`; but **no CI single-head gate** |
| Q3 | OCR deterministic fixture tests (lab) | **COMPLETE** | `tests/data/lab_reports/*`, `test_lab_table_extractor.py` |
| Q4 | Authorization tests (RBAC/consent/tenant) | **PARTIAL** | Strong at service/consent layer; **no systematic per-endpoint BOLA/IDOR matrix** |
| Q5 | Frontend E2E / post-deploy staging smoke gate | **MISSING** | Jest units only; no Playwright |
| Q6 | CI PR-gate + staging CD + gated prod | **COMPLETE** | `ci.yml`, `azure-*.yml` |

---

## Reusability Verdict (what NOT to rebuild)

**Reuse as-is (wire to mobile):** auth+refresh, PHI encryption, AI gateway, audit, lab OCR engines + confidence/provenance + eval harness, medication CRUD/adherence/verification, clinical insight/priority/metabolic score, Meto chat core + guardrails, doctor marketplace/consultation vertical, clinic SaaS, patient web app (as design + contract reference), migration discipline, CI/CD.

**Net-new (the real program):**
1. **Entire native mobile app** + build/release pipeline (biggest lift).
2. **Document-first foundation:** generic Medical Document context + object storage + doc-type classifier + prescription OCR + general-report OCR (extend the proven lab pattern).
3. **Notification delivery** (push) — precondition for reminders.
4. **Medication reminder/schedule engine.**
5. **Timeline unification** (add appointments/docs/nutrition/adherence).

**Hardening (safety-blocking):** consent fail-open, committed default keys, MFA/password policy, upload rate-limit + AV, web token storage, Meto confirmed-data restriction + gating, reconciliation API, K2 lifecycle API.

**Payment:** productionize behind an abstraction (mock adapter default; real gateway pluggable).
