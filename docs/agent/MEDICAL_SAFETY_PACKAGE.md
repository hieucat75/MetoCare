# Medical Safety Package — MetoCare
> Reviewer: Claude Code (claude-opus-4-5) · Date: 2026-06-17
> Task: METOCARE-SAFETY-001 · Status: **DRAFT — awaiting Medical Board sign-off + PTH approval**
> Mode: READ-ONLY design — no source files modified, no migrations generated, no tests run
>
> ⚠️ ALL clinical thresholds in this document are `PROPOSED_THRESHOLD` and require MetoCare Medical Board
> written sign-off before production use.

---

## 1. AI Entity Split: AISession + AIClinicalRecommendation

### 1.1 Rationale

The current `AIConversation` model conflates two fundamentally different concerns:
- **Conversational transcript** (the chat thread — privacy-sensitive, session-scoped, user-facing)
- **Structured clinical output** (lab explanation, triage assessment, care plan draft — clinically significant, requires doctor review)

Mixing them into one table creates RBAC ambiguity (who can read what?), makes the doctor-review gate
awkward (review the whole session or just the clinical conclusion?), and complicates audit granularity.
Splitting them is the right boundary.

### 1.2 AISession — entity definition

The conversational session. One session = one continuous interaction of a given type.

| Field | Type | PHI? | Notes |
|---|---|---|---|
| `id` | UUID PK | | |
| `patient_id` | FK → PatientProfile | YES | Required |
| `encounter_id` | FK → Encounter (nullable) | | Blueprint Q1: AI session may exist before/without encounter |
| `session_type` | Enum | | `health_assistant` / `lifestyle_coach` / `lab_explanation` / `triage` |
| `messages` | EncryptedString | **YES** | Fernet field-level, JSON transcript. Blueprint Q8. |
| `key_version` | Integer | | Fernet key rotation support. Blueprint Q8 + R6. |
| `risk_level` | Enum | | `low` / `medium` / `high` / `critical` |
| `escalated_to_doctor` | Boolean | | Set by rule engine only, never LLM free choice |
| `escalation_reason` | String | | Rule name that triggered escalation |
| `model_used` | String | | LLM provider + model name |
| `safety_flags` | Text | | JSON list of fired guardrail rules |
| `input_blocked` | Boolean | | True if L1/L2 blocked the input |
| `output_blocked` | Boolean | | True if L3 blocked the output |
| `total_tokens` | Integer | | Cost tracking |
| `deleted_at` | DateTime (nullable) | | Blueprint Q6: soft-delete |
| `deleted_by` | FK → User (nullable) | | Blueprint Q6: accountability |
| `created_at` / `updated_at` | DateTime | | TimestampMixin |

### 1.3 AIClinicalRecommendation — entity definition

Structured clinical output requiring doctor review. Created only when AI produces clinically significant content.

| Field | Type | PHI? | Notes |
|---|---|---|---|
| `id` | UUID PK | | |
| `session_id` | FK → AISession | | Required — every recommendation links to a session |
| `patient_id` | FK → PatientProfile | YES | Denormalized for efficient RBAC/query |
| `encounter_id` | FK → Encounter (nullable) | | Linked when escalation creates an Encounter |
| `recommendation_type` | Enum | | `lab_explanation` / `care_plan_draft` / `lifestyle_advice` / `triage_assessment` / `metabolic_score` |
| `content` | EncryptedString | **YES** | The structured clinical output, Fernet-encrypted |
| `key_version` | Integer | | Fernet key rotation |
| `status` | Enum | | `pending_review` / `reviewed` / `accepted` / `rejected` / `superseded` |
| `reviewed_by_doctor_id` | FK → Doctor (nullable) | | Set on review |
| `reviewed_at` | DateTime (nullable) | | Set on review |
| `ai_confidence` | Float (0–1) | | Advisory only — never used to auto-clear review (Q-OPEN-9) |
| `safety_cleared` | Boolean (default False) | | Only Doctor or Medical Reviewer may set True |
| `medical_disclaimer` | Text | | Mandatory disclaimer text injected at creation |
| `deleted_at` | DateTime (nullable) | | Blueprint Q6 |
| `deleted_by` | FK → User (nullable) | | Blueprint Q6 |
| `created_at` / `updated_at` | DateTime | | |

### 1.4 Status machine (AIClinicalRecommendation)

```
pending_review  ──doctor review──►  reviewed  ──accept──►  accepted
                                             └──reject──►  rejected
accepted  ──superseded by newer──►  superseded
```

- AI creates **only** `pending_review`. Any other initial status → hard-block + AuditLog deny.
- `safety_cleared=True` set only by Doctor (on accept) or Medical Reviewer.
- `accepted` → `superseded` when a newer recommendation of the same type is accepted for the same patient.
- No terminal state is deleted — soft-delete only within retention window.

### 1.5 RBAC for AISession + AIClinicalRecommendation

**Scope key:** `own` = self · `consent` = active `ai_use` Consent · `clinic` = doctor's clinics via `doctor_clinic` · `platform` = all

| Action | PATIENT | DOCTOR | CLINIC_ADMIN | INTERNAL_ADMIN | MEDICAL_REVIEWER | SUPER_ADMIN | AI_SERVICE |
|---|---|---|---|---|---|---|---|
| AISession **create** | ❌ (via service) | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ consent-gated |
| AISession **read** | ✅ own | ✅ consent + clinic | ❌ | ✅ metadata R | ✅ platform R | ✅ platform | ✅ own session |
| AISession soft-delete | ❌ | ❌ | ❌ | ❌ | ✅ retention | ✅ platform | ❌ |
| AIClinicalRec **create** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ **draft / pending_review only** |
| AIClinicalRec **read** | ✅ own *(only after reviewed/accepted)* | ✅ consent + clinic | ❌ | ✅ metadata R | ✅ platform R | ✅ platform | ✅ own session R |
| AIClinicalRec **review / accept / reject** | ❌ | ✅ **doctor only** | ❌ | ❌ | ✅ review queue (not accept) | ❌ | ❌ **hard-blocked** |
| Set `safety_cleared=True` | ❌ | ✅ on accept | ❌ | ❌ | ✅ reviewer | ❌ | ❌ **hard-blocked** |

**Critical patient-visibility rule:** Patient must NOT see `AIClinicalRecommendation` while `status=pending_review`. Patient sees the conversational `AISession` content immediately (with disclaimer); structured clinical recommendation surfaces only after `status ∈ {reviewed, accepted}`. (Q-OPEN-3.)

**Invariants (test as negative cases):**
1. AI_SERVICE creates recommendation only with `status=pending_review`, `safety_cleared=False` — any other attempt → hard-block + AuditLog(deny, severity=high)
2. AI_SERVICE runs through the same ConsentGuard as humans — no bypass
3. CLINIC_ADMIN and INTERNAL_ADMIN never see clinical body (`content`, `messages`) — metadata only
4. SUPER_ADMIN cannot review/accept — clinical authority is never an admin privilege
5. Every DENY writes AuditLog(outcome=deny, severity=warning)

### 1.6 Migration path from AIConversation

| Step | Migration | Action | Risk | Reversible |
|---|---|---|---|---|
| M1 | `rename_ai_conversations_to_ai_sessions` | `ALTER TABLE ai_conversations RENAME TO ai_sessions`; map `intent` → `session_type` | Low | YES |
| M2 | `extend_ai_session_fields` | Add `encounter_id`, `session_type`, `escalation_reason`, `input_blocked`, `output_blocked`, `total_tokens`, `key_version`, `deleted_at`, `deleted_by` (all nullable/defaulted) | Low | YES |
| M3 | `encrypt_ai_session_messages` | Change `messages` Text → EncryptedString; **backfill**: encrypt existing plaintext rows under `key_version=1`. **Data-touching — requires backup + tested decrypt path before running** | **Medium** | Partial (decrypt script required) |
| M4 | `add_ai_clinical_recommendations` | NEW table per §1.3 | Medium | YES (drop table) |
| M5 | `backfill_recommendations_from_history` (optional) | For historical sessions with `risk_level ∈ {high, emergency}` or lab-explanation intent, create a `superseded` stub for audit continuity. **Defer unless legally required.** | Low | YES |

**M3 gate:** depends on Blueprint R6 (Fernet rotation helper wired with key_version support) being implemented first.

---

## 2. Medical Safety Matrix

Each AI action type evaluated across safety dimensions. **Allowed:** YES / NO / CONDITIONAL.
**Hard-block:** enforced structurally at service/code layer (L2 capability deny-list), NOT via prompt instructions.

| AI action | Allowed? | Consent required | Doctor review before patient sees output? | Escalation trigger? | AuditLog severity | PHI access | Disclaimer required? | Hard-block (code)? |
|---|---|---|---|---|---|---|---|---|
| **lab_interpretation** | CONDITIONAL — explain only, no diagnosis | `ai_use` + `lab_data` scope | YES if abnormal/clinically significant → creates AIClinicalRecommendation pending_review | Vital crosses red-flag threshold → YES | info; **warning** if abnormal | read-own-context | YES | Block "you have [disease]" output (L3); block on low OCR confidence |
| **metabolic_score** | YES — reference tool only | `ai_use` | NO (informational); recommendation row optional | No, unless component vital is red-flag | info | read-own-context | YES ("công cụ tham khảo") | Formula changes config-gated (Guardrail §4.7) |
| **lifestyle_coaching** | YES | `ai_use` | NO | Red flag in chat → YES (short-circuit) | info | read-own-context | YES | Block clinical nutrition prescriptions (L3) |
| **triage_assessment** | CONDITIONAL — rule engine first, LLM clarifies only | `ai_use` | YES for HIGH/EMERGENCY → creates recommendation + escalation | YES — this IS the escalation entry point | **high** on EMERGENCY; warning on HIGH; info otherwise | read-own-context | YES | Red-flag rules run **before** LLM; LLM cannot downgrade rule-forced level |
| **care_plan_draft** | CONDITIONAL — draft only, NEVER active | `ai_use` + clinical scope | YES — **mandatory** | If draft arose from HIGH triage → YES | warning | read-consented | YES | **HARD-BLOCK:** AI cannot set CarePlan APPROVED/ACTIVE; `ai_generated=True`, `status=PENDING_REVIEW` forced |
| **symptom_analysis** | CONDITIONAL — clarify + stratify, no diagnosis | `ai_use` | YES if it yields a clinical assessment | Red flag → YES | warning | read-own-context | YES | Block definitive-diagnosis language (L3); routes through triage rule engine |
| **medication_summary** | CONDITIONAL — **summarize existing only**, no advice | `ai_use` + `medication` scope | NO for read-back summary; YES if any guidance implied | If user asks dose/start/stop → redirect, no escalation unless red flag | warning | read-own-context (read-only) | YES | **HARD-BLOCK:** no prescribe, no dose change, no start/stop (L2 + RBAC) |
| **health_trend_analysis** | YES — describe trends, no diagnosis | `ai_use` | NO (descriptive); YES if it implies clinical action | Trend crossing red-flag vital threshold → YES | info; warning if threshold crossed | read-own-context + aggregate | YES | Block prognosis statements "you will develop X" (L3) |
| **emergency_escalation** | YES — **must always fire** | None (safety overrides consent for escalation action) | N/A — patient sees emergency message immediately | **This IS the escalation** | **critical** | read-own-context (minimal) | YES (emergency message) | **HARD-BLOCK against suppression:** no code path and no LLM may cancel/downplay a rule-fired escalation |
| **general_health_question** | YES — educational, general | `ai_use` (if PHI referenced); none if purely general | NO | Red flag in text → YES | info | none / read-own-context | YES | Block diagnosis/prescription patterns (L3); RAG-only knowledge |

**Cross-cutting rules:**
- Every row that produces user-visible text gets a mandatory disclaimer (L5) — universal
- Every row writes AuditLog regardless of outcome (L6) — including blocks and denials
- Consent checked at L0 (ConsentGuard) for any row touching PHI
- Exception: `emergency_escalation` — consent gate bypassed for the escalation action itself (patient safety overrides); LLM reasoning step still skipped when consent absent; logged with `consent_absent_at_escalation=true`

---

## 3. Escalation Rules

### 3.1 Principle

Escalation is **rule-triggered, never LLM-judged** (Guardrail §4.6). Trigger source: (a) input red-flag engine, (b) risk classifier level, or (c) output validator blocking dangerous generation. The LLM cannot raise or lower an escalation level. Conservative tie-break: **highest severity wins** (matches `triage.py` round-UP rule).

### 3.2 Escalation levels and SLAs

| Level | Definition | Trigger | SLA |
|---|---|---|---|
| **IMMEDIATE** | Life-threatening; emergency services | Any hard red-flag symptom OR critical vital (§4) OR triage EMERGENCY | Patient told to call emergency NOW; doctor notified instantly |
| **URGENT** | Needs a doctor soon | Triage HIGH (vital ≥ 85% of critical threshold) `PROPOSED_THRESHOLD` | Doctor response ≤ 2h `PROPOSED_THRESHOLD` |
| **ROUTINE** | Should be seen, not urgent | Triage MODERATE; abnormal-but-stable lab | Doctor/booking suggested ≤ 24h `PROPOSED_THRESHOLD` |
| **ADVISORY** | Inform only, self-manage | Triage LOW; informational outputs | No doctor action; logged; coaching continues |

> All SLA windows (2h, 24h, and timeout values in §3.5) are `PROPOSED_THRESHOLD` — operational commitments requiring Medical Board + ops ratification.

### 3.3 Escalation decision tree

```
AI interaction (any session_type)
        │
        ▼
[L0] Consent Gate (ai_use) ──absent + PHI──► deny; for escalation-only path: consent bypassed
        │ consent present (or escalation-only)
        ▼
[L1] Input red-flag rule engine ──hard red flag──► IMMEDIATE (bypass LLM entirely)
        │ no hard flag
        ▼
[LLM] clarify / explain (never decides escalation level)
        │
        ▼
[Classifier] risk_level:
  EMERGENCY ──► IMMEDIATE
  HIGH      ──► URGENT
  MODERATE  ──► ROUTINE
  LOW       ──► ADVISORY
        │
        ▼
[L3] Output validator ──blocks dangerous output──► upgrade to ≥ URGENT + safe-template replacement
        │ output clean
        ▼
[L4] Escalation engine routes per highest level reached
        │
        ▼
[L5] Disclaimer injected ──► [L6] Audit (always) ──► Response
```

### 3.4 What happens at each level

| Level | Escalate to | What is created | Patient sees |
|---|---|---|---|
| **IMMEDIATE** | emergency_services (patient self-dials) + attending_doctor, fallback on_call_doctor | Encounter(PENDING_REVIEW), AISession.escalated_to_doctor=True + escalation_reason, AuditLog(severity=critical), AIClinicalRecommendation(triage_assessment, pending_review) | Emergency message (§4.7) — hardcoded string, coaching stops |
| **URGENT** | attending_doctor, fallback on_call_doctor | Encounter(PENDING_REVIEW), recommendation pending_review, AuditLog(severity=warning) | "nên gặp bác sĩ sớm; tóm tắt đã chuẩn bị" |
| **ROUTINE** | attending_doctor (queue) or booking suggestion | Recommendation pending_review, booking suggestion, AuditLog(severity=info) | "nên cân nhắc đặt lịch khám" |
| **ADVISORY** | patient_only | AISession log only | Coaching / self-monitor message + disclaimer |

### 3.5 Timeout / non-response rules (`PROPOSED_THRESHOLD`)

| Scenario | Timeout | Then |
|---|---|---|
| IMMEDIATE — no attending acknowledgement | 5 min `PROPOSED_THRESHOLD` | Auto-page on_call_doctor; ops alert |
| IMMEDIATE — no on-call acknowledgement | +5 min `PROPOSED_THRESHOLD` | Escalate to clinic medical lead + persistent ops critical alert; record `escalation_timeout` |
| URGENT — no attending acknowledgement | 30 min `PROPOSED_THRESHOLD` | Reassign to on_call_doctor; reset 2h SLA |
| URGENT — total SLA breach | 2h `PROPOSED_THRESHOLD` | Escalate to medical lead; flag SLA breach in audit |
| ROUTINE — no action | 24h `PROPOSED_THRESHOLD` | Re-queue + remind patient to book directly |

**Independent:** IMMEDIATE patient-facing emergency instruction shown immediately and unconditionally — does NOT wait on doctor acknowledgement.

### 3.6 Recording an escalation (atomic write)

1. `AISession.escalated_to_doctor=True`, `escalation_reason`, `risk_level`
2. `Encounter(status=PENDING_REVIEW, appointment_id=NULL, doctor_id=assigned-or-null)` linked via `encounter_id`
3. `AIClinicalRecommendation(triage_assessment, pending_review)` for IMMEDIATE/URGENT
4. `AuditLog(action=ai.escalation, actor_type=ai_service, severity=critical|warning)`

### 3.7 Resolution and cancellation

- **Resolution:** Doctor reviews linked Encounter/recommendation → sets recommendation `reviewed|accepted|rejected` → transitions Encounter out of PENDING_REVIEW → `AuditLog(action=ai.escalation_resolved)`
- **Cancellation (false-positive):** Only a DOCTOR may mark as false positive, after reviewing the case, with a written reason → appends `AuditLog(action=red_flag_overridden, severity=warning)`. Original detection record is **never deleted** (soft-delete + append-only audit).
- **No silent auto-resolve:** IMMEDIATE escalation never auto-closes on a timer. Stays open until a clinician closes it.

---

## 4. Emergency Red Flag Policy

> **⚠️ ALL thresholds in this section are `PROPOSED_THRESHOLD` and require MetoCare Medical Board written sign-off before any production use.** Sources cited are the intended evidence base; the board must confirm each value for the Vietnamese adult population and MetoCare's screening (not diagnostic) context.

### 4.1 Detection method

Pure **rule engine**, deterministic, runs **before** any LLM call. Implemented in `triage._detect_symptom_red_flags` + `_detect_vital_red_flags` + `guardrails.check_input`. The LLM **never** participates in red-flag detection. False-negative target = **0** (Guardrail §6). Detection: keyword-based (Vietnamese, diacritic-preserving) for symptoms; threshold-comparison for vitals.

### 4.2 Symptom red flags (from `policies.RED_FLAG_SYMPTOMS`)

| Key | Clinical meaning | Sample VN keywords | Guideline basis |
|---|---|---|---|
| `chest_pain` | Possible ACS | đau ngực, tức ngực, đau thắt ngực, nặng ngực | AHA (ACS) |
| `dyspnea` | Acute breathing difficulty | khó thở, hụt hơi, thở gấp, không thở được | WHO / AHA |
| `cold_sweat` | Autonomic/shock/ACS sign | vã mồ hôi, toát mồ hôi lạnh | AHA |
| `stroke_signs` | Stroke (FAST) | yếu liệt, liệt nửa người, méo miệng, nói khó, tê nửa người, đột quỵ, lú lẫn | AHA/ASA FAST |
| `syncope` | Loss of consciousness | ngất, bất tỉnh, mất ý thức, xỉu | WHO |
| `severe_hypertension_combo` | Hypertensive emergency signs | đau đầu dữ dội, mờ mắt, hoa mắt dữ dội | AHA/ISH |
| `hyperglycemia_combo` | DKA/HHS signs | nôn, mệt lả, lơ mơ, khát nước dữ dội | IDF/ADA |
| `severe_hypoglycemia` | Severe hypoglycemia | run tay, vã mồ hôi lú lẫn, hạ đường huyết nặng, co giật | IDF/ADA |
| `severe_abdominal_pain` | Acute abdomen | đau bụng dữ dội, đau bụng quặn | WHO |
| `cyanosis` | Hypoxia | tím tái, môi tím | WHO |

**⚠️ GAPS — T4 blocking (Q-OPEN-1):**
- `suicidal_ideation` / `self_harm` — named in Blueprint §5 but NOT in current `RED_FLAG_SYMPTOMS`. Must be added. Requires a dedicated **crisis pathway** (separate message + crisis hotline, not generic emergency message). Board to define wording.
- `anaphylaxis` (throat swelling + breathing difficulty + widespread rash) — Blueprint §5 names it, not in current code. Must be added.

**Composite red flags:** `chest_pain` AND `dyspnea` concurrently → IMMEDIATE with elevated priority (Blueprint §5). Board to ratify composite detection approach.

### 4.3 Vital-sign red flags (threshold-based)

| Metric | Critical high | Critical low | Guideline intent | Status |
|---|---|---|---|---|
| `blood_pressure_systolic` (mmHg) | ≥ 180 | ≤ 80 | AHA hypertensive crisis / hypotension | `PROPOSED_THRESHOLD` ✅ |
| `blood_pressure_diastolic` (mmHg) | ≥ 120 | ≤ 50 | AHA hypertensive crisis | `PROPOSED_THRESHOLD` ✅ |
| `fasting_glucose` (mg/dL) | ≥ 300 | ≤ 54 | IDF/ADA Level-2 hypoglycemia `PROPOSED_THRESHOLD` | ✅ |
| `postprandial_glucose` (mg/dL) | ≥ 350 | ≤ 54 | IDF/ADA | `PROPOSED_THRESHOLD` ✅ |

> **⚠️ THRESHOLD CONFLICT (Q-OPEN-2 — T4 blocking):** Blueprint §5 states glucose hypoglycemia `< 50 mg/dL`; `policies.py` encodes `≤ 54.0`. **Recommendation: adopt ≤ 54 mg/dL** (ADA Level-2, more sensitive — consistent with false-negative=0 intent). Correct the Blueprint. **Board to ratify.**

**Missing vital thresholds (Q-OPEN-4 — recommended before GA):** SpO₂ (e.g. < 90%), heart rate (brady/tachy), temperature (sepsis screen), respiratory rate. Current v0 covers only BP + glucose.

### 4.4 Edge cases

| Edge case | Policy |
|---|---|
| **Patient ignores escalation** | Emergency message persists in UI (non-dismissible acknowledgement). Escalation stays open. Doctor still notified. Record `escalation_unacknowledged_by_patient`. AI does NOT retract warning. |
| **Phone/patient unreachable** | Doctor notification proceeds regardless. Fall back to all registered channels (SMS → push → email). Record delivery failure. Escalation never silently dropped. |
| **No assigned doctor** | Route to on_call_doctor → clinic medical lead → platform MEDICAL_REVIEWER queue (critical). Patient emergency message (call emergency services) shown regardless. Absence of a clinician at IMMEDIATE level is an ops incident. |
| **Consent missing/expired at escalation** | Patient-facing emergency instruction + escalation record still fire (safety overrides consent for escalation action). LLM step skipped. Logged with `consent_absent_at_escalation=true`. |
| **Duplicate / repeated red flag** | Dedupe per open Encounter — append to existing escalation, don't create a new one per message. Re-notify on timeout only. |

### 4.5 False-positive and override policy

- **Patient disputes:** patient **cannot** clear a red flag. Escalation stays open; patient told a clinician will review. Dispute is recorded. (Rationale: letting a patient dismiss a red flag reintroduces the false-negative risk the rule engine eliminates — Guardrail §5.)
- **Doctor override:** only a DOCTOR may declare a red flag a clinical false positive, after reviewing the case, with a written reason. Appends `AuditLog(action=red_flag_overridden, severity=warning)`. Original detection record is **never deleted** (soft-delete, append-only audit). AI, patients, admins, and SUPER_ADMIN **cannot** override.
- **No code path may suppress a red flag pre-detection.** Overrides happen *after* detection + logging, never before.

### 4.6 Logging (mandatory, every detection)

Every red-flag detection — whether it leads to escalation, is overridden, or is disputed — writes:
`AuditLog(action=red_flag.detected, actor_type=ai_service|system, severity=critical)` + fires `AISession.safety_flags`. Metrics tracked: false-negative rate (target 0), escalation rate, override rate, SLA compliance.

### 4.7 Patient communication — exact message on red-flag trigger

The patient sees `policies.EMERGENCY_MESSAGE_VI` verbatim. This string is rule-engine-sourced, **not LLM-generated**, so L3 output validator cannot strip or soften it:

> "Mình ghi nhận dấu hiệu có thể nguy hiểm. Bạn nên liên hệ cơ sở y tế hoặc gọi cấp cứu ngay bây giờ. Mình sẽ gắn cảnh báo này để bác sĩ theo dõi. Thông tin này không thay thế tư vấn bác sĩ."

**Board action item (Q-OPEN-6):** add localized emergency-services phone number / instruction for Vietnam (115) and instructions for no-phone scenarios. Confirm crisis-pathway message for self-harm red flags (Q-OPEN-1).

---

## 5. Integration with Blueprint (BLUEPRINT_REVIEW_RESPONSE.md)

| This package | Connects to Blueprint decision |
|---|---|
| `AISession.messages` / `AIClinicalRecommendation.content` as EncryptedString + `key_version` | **Q8** field-level Fernet + **R6** key rotation wired first |
| Both entities: `deleted_at` + `deleted_by` | **Q6** timestamp soft-delete, never hard-delete clinical records |
| `encounter_id` nullable on both; AI-escalation creates Encounter without Appointment | **Q1** Encounter can exist without Booking |
| AIClinicalRecommendation status machine; AI may only draft (pending_review) | **Q2** status machine in model + §4 CarePlan RBAC (AI hard-blocked from approve) |
| L0 ConsentGuard; AI uses same guard; emergency escalation bypasses consent gate for the action only | **Q3** ConsentGuard at service layer + Blueprint §4 inv.1 no bypass |
| §2 matrix hard-blocks (diagnosis, prescription, dose, careplan-approve) | Blueprint §5 **L2** capability deny-list at code layer + §4 RBAC hard-blocked cells |
| §3 escalation engine, §4 red-flag engine | Blueprint §5 **L1/L4** + §4.6 triage architecture |
| §4.3 thresholds flagged PROPOSED_THRESHOLD, config-gated | Blueprint **R5** do not hardcode clinical values |
| §2 disclaimer column + §4.7 fixed emergency string | Blueprint §5 **L5** mandatory disclaimer injection |
| §4.6 / §1 audit on every interaction + every detection | Blueprint §5 **L6** immutable audit, severity tiers |
| §1.6 migration sequence (rename + extend + encrypt + new table) | Extends Blueprint §3 `alter_ai_conversation_extend` (Phase 1 additive) + adds M3 data-touching migration |
| **New dependency beyond Blueprint:** M3 plaintext→ciphertext backfill is data-touching, not yet in Phase-1 table | Must be gated behind tested decrypt path + backup before running |

---

## 6. Open questions / items requiring Medical Board sign-off

| # | Item | Type | T4 blocking? | Recommendation |
|---|---|---|---|---|
| **Q-OPEN-1** | `RED_FLAG_SYMPTOMS` missing **suicidal ideation / self-harm** and **anaphylaxis** (both named in Blueprint §5) | Clinical gap | **YES** | Add both before T4; self-harm needs a dedicated crisis pathway with a crisis hotline — not the generic emergency message. Board to define wording. |
| **Q-OPEN-2** | Glucose hypoglycemia threshold conflict: Blueprint `<50 mg/dL` vs `policies.py ≤54.0` | Threshold reconciliation | **YES** | Adopt **≤54 mg/dL** (ADA Level-2, more sensitive). Correct Blueprint. Board to ratify. |
| **Q-OPEN-3** | Should patient ever see `AIClinicalRecommendation` while `pending_review`? | Policy / UX | YES | This package says **no**: patient sees conversational AISession immediately (disclaimer); structured clinical recommendation surfaces only after `reviewed/accepted`. Confirm. |
| **Q-OPEN-4** | Vital coverage is BP + glucose only. Missing SpO₂, HR, temperature, respiratory rate thresholds | Threshold expansion | Recommended before GA | Board to set PROPOSED_THRESHOLD values (e.g. SpO₂ < 90%, HR/temp bounds). |
| **Q-OPEN-5** | No **pediatric / pregnancy** thresholds. Blueprint §5 names "pediatric emergency" but no rule exists | Clinical scope | YES if minors/pregnant in scope | Board to define age/pregnancy-adjusted thresholds, or formally exclude these populations from AI triage at v0. |
| **Q-OPEN-6** | Emergency message lacks localized emergency-services instruction (Vietnam: 115) | Patient comms | YES | Board + ops to finalize exact emergency-services string per region. |
| **Q-OPEN-7** | All escalation SLAs and timeout values (2h, 24h, 5/30-min timers) are proposed | Ops / clinical | YES | Board + clinical ops to ratify; encode as reviewed config, not constants. |
| **Q-OPEN-8** | `Consent.consent_type` does not yet include `ai_use` value (Blueprint R3) | Data/config | YES | Add to consent_type validation in first T4 migration. |
| **Q-OPEN-9** | `ai_confidence` semantics — confirm advisory only, never used to auto-clear review | Policy | Recommended | Confidence never bypasses `pending_review`. Document LLM source. |
| **Q-OPEN-10** | Metabolic Score formula governance — changes require medical-board review (Guardrail §4.7) | Process | Recommended | Define versioned, board-signed score config + change process. |

### Sign-off block

```
[ ] Medical Board chair — clinical thresholds (§4.3) and red-flag list (§4.2) ratified ......... date / sign
[ ] Medical Board — escalation levels, SLAs, timeouts (§3) ratified ............................ date / sign
[ ] Medical Board — emergency message + crisis pathway (§4.7, Q-OPEN-1/6) ratified ............. date / sign
[ ] PTH — AI entity split + migration plan (§1) approved for T4 ................................. date / sign
[ ] Security/Eng — encryption + RBAC invariants (§1.5) verified by negative tests .............. date / sign
```

---

*End of MEDICAL_SAFETY_PACKAGE.md — Claude Code (claude-opus-4-5), 2026-06-17*
*No source files modified. No migrations generated. No tests run.*
*All clinical thresholds tagged `PROPOSED_THRESHOLD` — pending Medical Board sign-off.*
*Awaiting PTH approval before T4 implementation begins.*
