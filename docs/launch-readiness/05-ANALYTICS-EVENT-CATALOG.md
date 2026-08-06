# 05 — Analytics & Product-Event Catalog (WS5/WS6)

**Date:** 2026-08-04 · **Branch:** `feat/patient-platform-journey2` @ `6ab3b04` · **Assessor:** independent Observability & Analytics assessor (fresh context, direct source inspection).
**Companion:** `04-OBSERVABILITY.md` (operational signals). This document covers **product** analytics.

---

## 1. Ground truth — what is instrumented TODAY

> **There is zero product analytics instrumentation in this codebase. No analytics SDK, no event client, no `track()` call, no batching queue, no analytics table. Not in the mobile app, not in the web frontend, not in the backend.**

This is not a hedge; it is a verified negative:

```
$ grep -rn "analytics|amplitude|posthog|mixpanel|segment|firebase|track\(" \
    mobile/src mobile/app --include="*.ts" --include="*.tsx" -i
# → zero matches

$ grep -rn "analytics|posthog|mixpanel|amplitude|gtag|Sentry" frontend/src frontend/package.json -i
# → one match: frontend/src/app/(patient)/dashboard/page.tsx:234 — a JSX comment
#   ("shown before analytics"), not code.

$ grep -rn "class .*Event|analytics" backend/app/models --include="*.py" -i
# → zero matches
```

`mobile/package.json` and `frontend/package.json` contain no analytics dependency. `backend/requirements.txt` (full file inspected) contains none.

**Every event named in §4 of this document is DESIGN-ONLY.** Nothing below should be read as describing behaviour that exists. Where a signal *is* already obtainable — from the audit log or a domain table — it is marked **[DERIVABLE TODAY]** with the exact `file:line` that writes it. Everything else is **[NOT INSTRUMENTED]**.

### 1.1 What *is* already there — the accidental analytics backbone

The absence of an analytics *client* does not mean the absence of *data*. Three existing stores already carry most of the product funnel, because the compliance work built them:

| Store | What it gives you | Written at |
|---|---|---|
| `audit_logs` | 100+ distinct `action` values covering register/login, document upload→accept→per-candidate confirm/reject/merge, dose taken/skipped, consultation lifecycle, consent grant/revoke | `backend/app/services/audit.py:14-44`; model `backend/app/models/governance.py:57-80` |
| `meto_audit_logs` | per-turn AI telemetry: provider, fallback, safety flags, escalation, latency, token counts, context blocks used — **no message content** | `backend/app/services/meto_chat.py:641-659`; model `backend/app/models/meto.py:91-117` |
| `terms_consents` | onboarding completion with `app_version`, `locale`, `timezone`, `device_platform`, `accepted_source` — a genuine activation + client-mix source | `backend/app/services/auth.py` via `backend/app/api/v1/routes/auth.py:203-229`; model `backend/app/models/consent.py:27-49` |

Plus the HTTP access log, which gives every route's call volume, status and latency (`backend/app/core/middleware.py:96-105`) — see `04-OBSERVABILITY.md §6.2`.

**Consequence for the pilot: roughly 70% of the funnel in §5 is answerable *today* with SQL, with no new code and no new PHI surface.** That is the single most important finding in this document, and it drives the scoping decision in §8.

### 1.2 What the backbone cannot answer

Server-side records only exist where a request reached the server. Everything that happens *before* the request is invisible:

- screen views, tab switches, scroll depth, time-on-screen
- **abandonment** — a user who opens Add-Document, photographs a prescription, sees the review screen and quits before confirming produces `document.accepted` but no confirm/reject; a user who quits *before* upload produces nothing at all
- client-side validation failures, permission denials (camera), offline retries
- app launch, session start/end — hence **crash-free session rate is not computable** (`04-OBSERVABILITY.md` WS4-F1)
- install → first-open (no attribution, no store analytics for a sideloaded APK)

---

## 2. Privacy rules — non-negotiable

MetoCare handles health data. An analytics pipeline is the classic place PHI escapes, because analytics is the one system deliberately designed to copy data *out*. The rules below are absolute and precede any implementation.

### 2.1 The five hard rules

1. **No PHI. Ever.** No lab values, no diagnoses, no medication names, no dosages, no symptoms, no body measurements, no dates of birth, no appointment reasons.
2. **No free text.** Not search queries, not chat messages, not skip reasons, not bug descriptions, not OCR corrections. If a human typed it, it does not enter analytics.
3. **No document content.** No filenames, no extracted strings, no page text, no image bytes, no thumbnails, no hashes of content (a content hash is a cross-user join key — see the "no dedup oracle" invariant already upheld in the MDI design).
4. **No message content.** Meto turns are counted, categorised and timed — never quoted. This mirrors what `meto_audit_logs` already does correctly (`backend/app/models/meto.py:94-95`).
5. **IDs and enums only.** Every property must be a UUID, a bounded enum from a compile-time list, a boolean, a bucketed integer, or a duration in ms.

### 2.2 The concrete allow-list

A property may be emitted **only** if it matches one of these shapes. Anything else is a review-blocking defect.

| Category | Allowed | Example | Forbidden counterpart |
|---|---|---|---|
| Identity | opaque `user_id` (UUID), `patient_id` (UUID) — never email/phone/name | `user_id: "8f3c…"` | `email`, `phone`, `full_name` |
| Entity refs | `document_id`, `candidate_id`, `schedule_id`, `dose_id`, `conversation_id`, `consultation_id`, `doctor_id` (all UUIDs) | `candidate_id: "a12…"` | any human-readable label |
| Enums | `doc_type` ∈ {prescription, lab_report, general} (`backend/app/services/mdi/classifier.py`); `candidate_type` ∈ the 7 constants in `backend/app/models/medical_document.py`; `dose_state` ∈ {taken, skipped, missed} (`backend/app/models/medication_schedule.py:48-50`); `consultation_status`; `screen_id` | `candidate_type: "medication"` | the medication's **name** |
| Counts | `candidate_count`, `page_count`, `corrections_count`, `retry_count` — integers, bucketed above 20 | `candidate_count: 4` | a list of what they were |
| Booleans | `is_first_document`, `had_corrections`, `fallback_used`, `output_replaced`, `consent_granted` | `had_corrections: true` | the correction values |
| Durations | `duration_ms` (int) | `duration_ms: 3120` | wall-clock timestamps of a clinical event |
| Outcome | `outcome` ∈ {success, failure, denied}; `error_code` ∈ the backend's fixed envelope codes (`CONSENT_DENIED`, `VALIDATION_ERROR`, `PERMISSION_DENIED`, `PHI_DECRYPTION_FAILED`, `DUPLICATE_CANDIDATE` — `backend/app/main.py:126,133,140,147,154,170` and `mobile/src/api/client.ts:37,158`) | `error_code: "CONSENT_DENIED"` | the error `message`, which is human text |
| Client context | `app_version`, `platform`, `os_version`, `locale`, `app_env` — exactly the set `mobile/src/lib/monitor.ts:42-49` already builds | `platform: "android"` | device advertising id, precise geolocation |

### 2.3 Enforcement, not intention

Rules that live only in a document get violated in month three. Bind them in code:

- **Typed event union.** `type AnalyticsEvent = { name: 'document_upload_started'; props: { document_id: string; doc_type: DocType } } | …` — a string-keyed `Record<string, unknown>` payload is what makes leaks possible, so the payload type must be closed.
- **Runtime property-shape guard** in the emit function, mirroring the backend's log allow-list (`backend/app/core/logging.py:18-20, 42-44`) — the single best pattern already in this codebase. Drop, and count, anything not matching §2.2. In dev, throw.
- **Reuse the existing redactor** as a backstop for any string that slips through: `redactSensitive` (`mobile/src/lib/monitor.ts:33-40`) already strips bearer tokens, JWTs, emails and 6+ digit runs.
- **CI grep gate:** no analytics call site may pass an identifier matching `*_name`, `*_text`, `raw_*`, `original_*`, `message`, `body`, `content`, `value`, `detail`.
- **Golden test:** serialise one instance of every event in the catalog and assert the JSON matches an allow-listed key schema. This is the test that survives the refactor that would otherwise leak.

---

## 3. Consent & legal posture

**Analytics is not covered by any consent artifact that exists today.**

- `terms_consents` records acceptance of a Terms + Privacy version pair (`backend/app/models/consent.py:36-37`), versioned from `legal-versions.json` (`backend/app/core/legal.py:9-11, 25-30`). Whether the Privacy Policy text discloses product analytics is **UNVERIFIED — read the published Terms/Privacy documents referenced by `legal-versions.json` and confirm.**
- The per-category `MetoConsent` gate (`backend/app/models/meto.py:120-136`) is scoped to *AI context inclusion* — `health_data`, `medications`, `labs`, `metrics`, `care_plan`, `chat_history`. It is not an analytics consent, and must not be repurposed as one.
- `Consent` / `consent_guard` (`backend/app/services/consent_guard.py`) gates doctor and feature access to clinical data. Also not analytics.

### 3.1 Position for the pilot

1. **Pilot cohort is synthetic-data-first** (`12-PILOT-OPERATIONS-RUNBOOK.md §Consent & data policy`), 10–50 explicitly-invited testers who sign a pilot consent. For that cohort, PHI-free product telemetry is defensible under legitimate-interest/service-improvement — **provided** the pilot consent says so in plain Vietnamese.
2. **Analytics stays first-party.** No third-party analytics SDK before public beta. A third-party processor means a DPA, a data-transfer assessment, and an owner decision — the same gate as Sentry (`04-OBSERVABILITY.md §6.4`) and cloud OCR (`00-CURRENT-STATE.md §8`).
3. **Under GDPR-style rules, PHI-free product analytics keyed to a `user_id` is still personal data.** So: it must be included in account export and erased on account deletion. The erasure path already exists and already handles the analogous blob problem (`PRIV-F2` fix, `15-FINAL-LAUNCH-REVIEW.md §4`) — any analytics table must be added to `backend/app/services/account.py`'s delete path at the same time it is created, not after.
4. **Retention:** analytics events get a TTL no longer than the `data_access` audit TTL (730 days, `backend/app/core/config.py:195`) and preferably 180 days. Enforce via the same job (`backend/app/jobs/maintenance.py:23-30`) — which is itself not yet scheduled (`04-OBSERVABILITY.md` WS4-F10).
5. **Add one line to the pilot consent** before the cohort starts: *"We record anonymous usage events (which screens you use, whether an action succeeded) to improve the app. These never include your health data, documents, or messages."*

---

## 4. Product-event catalog (DESIGN — not implemented)

Naming: `snake_case`, `<object>_<past-tense-verb>`. Every event carries the §2.2 client-context block implicitly; only distinguishing properties are listed. PHI classification: **NONE** = no personal data beyond an opaque id; **PSEUDONYMOUS** = linkable to a user via `user_id` but PHI-free. **No event in this catalog is permitted to be anything else.**

### 4.1 Journey 1 — Onboarding & Auth

| Event | Trigger | Properties | PHI | Why it matters | Status |
|---|---|---|---|---|---|
| `app_opened` | app foreground | `is_cold_start`, `session_id` | NONE | Session denominator — without it, crash-free rate and per-session funnels are undefined | **[NOT INSTRUMENTED]** — no session concept exists |
| `onboarding_screen_viewed` | onboarding step render | `step_index`, `step_id` | NONE | Locates *where* onboarding is lost; the server sees only the endpoint | **[NOT INSTRUMENTED]** — `mobile/app/(auth)/onboarding.tsx` |
| `registration_submitted` | `POST /auth/register` | `outcome`, `error_code` | PSEUDONYMOUS | Signup attempt vs success; error mix separates "already exists" from real breakage | **[DERIVABLE TODAY — success only]** `backend/app/services/auth.py:100-107`; route `backend/app/api/v1/routes/auth.py:35`. Failures: access log 4xx only |
| `terms_accepted` | `POST /auth/accept-terms` | `terms_version`, `privacy_version`, `accepted_source`, `app_version`, `platform`, `locale` | PSEUDONYMOUS | **The activation milestone.** Also the legal record | **[DERIVABLE TODAY]** `backend/app/models/consent.py:27-49`; route `backend/app/api/v1/routes/auth.py:203-229` |
| `login_succeeded` | successful `POST /auth/login` | `mfa_used` | PSEUDONYMOUS | Return/retention denominator | **[DERIVABLE TODAY]** `backend/app/services/auth.py:244-251` |
| `login_failed` | 401/423 on login | `reason` ∈ {bad_credentials, mfa_invalid, locked} | PSEUDONYMOUS | Distinguishes "testers can't get in" (support load) from "someone is attacking" (security) | **[NOT INSTRUMENTED — this is WS4-F3]** `backend/app/services/auth.py:240-241` raises before any audit; lockout `backend/app/api/v1/routes/auth.py:104-112` |
| `session_expired_forced_logout` | refresh chain exhausted | `had_refresh_token` | PSEUDONYMOUS | Silent forced logouts are a top pilot-churn cause and currently produce no signal | **[NOT INSTRUMENTED]** `mobile/src/api/client.ts:197-201` |

### 4.2 Journey 2 — Document → OCR → Confirm (the flagship journey)

| Event | Trigger | Properties | PHI | Why it matters | Status |
|---|---|---|---|---|---|
| `document_capture_started` | user opens Add-Document | `entry_point` ∈ {dashboard, documents_tab, empty_state} | NONE | Top of funnel. **Currently invisible** — abandonment before upload leaves no trace | **[NOT INSTRUMENTED]** `mobile/app/(app)/add-document.tsx` |
| `document_upload_session_created` | `POST /documents/upload-session` | `document_id`, `page_count`, `mime_class` ∈ {image, pdf} | PSEUDONYMOUS | Real top-of-funnel; denominator for every rate below | **[DERIVABLE TODAY]** `backend/app/services/mdi/service.py:134`; route `backend/app/api/v1/routes/documents.py:159` |
| `document_finalize_failed` | non-2xx on `POST /documents/{upload_id}/finalize` | `document_id`, `error_code`, `duration_ms` | PSEUDONYMOUS | **The #1 thing that silently kills this journey.** Only the access log has it today, with no client-side view of network/timeout failures | **[PARTIAL]** access log only, route `backend/app/api/v1/routes/documents.py:220` |
| `document_quarantined` | quarantine hold | `document_id`, `reason` | PSEUDONYMOUS | Malware/oversize/malformed rejection rate; a spike means the capture UI is producing bad files | **[DERIVABLE TODAY]** `backend/app/services/mdi/service.py:218, 230` |
| `document_accepted` | pipeline accepted → extraction produced | `document_id`, `doc_type`, `candidate_count`, `ocr_confidence_bucket`, `duration_ms` | PSEUDONYMOUS | OCR reach + latency; `candidate_count == 0` is the "extracted nothing" failure that looks like success | **[DERIVABLE TODAY — partially]** `backend/app/services/mdi/service.py:255`; confidence exists in the pipeline (`backend/app/services/mdi/pipeline.py:81, 94`) but is **not** put in the audit `details` |
| `review_screen_viewed` | review screen render | `document_id`, `candidate_count` | PSEUDONYMOUS | Separates "never reviewed" from "reviewed and rejected" — the single biggest ambiguity in the funnel | **[NOT INSTRUMENTED]** `mobile/app/(app)/review/[documentId].tsx`; server-side `GET /documents/{id}/candidates` (`backend/app/api/v1/routes/documents.py:374`) is a weak proxy |
| `candidate_confirmed` | `POST /candidates/{id}/confirm` | `candidate_id`, `candidate_type`, `had_corrections`, `corrections_count` | PSEUDONYMOUS | The **success** event of Journey 2 | **[DERIVABLE TODAY]** `backend/app/services/mdi/service.py:485`. `had_corrections` is **not** recorded — corrections applied at `:472` |
| `candidate_merged` | `POST /candidates/{id}/merge` | `candidate_id`, `candidate_type`, `promoter_action` | PSEUDONYMOUS | Deduplication working (or the model producing duplicates) | **[DERIVABLE TODAY]** `backend/app/services/mdi/service.py:519` |
| `candidate_rejected` | `POST /candidates/{id}/reject` | `candidate_id`, `candidate_type` | PSEUDONYMOUS | **The best available proxy for OCR quality.** By type, it tells you *which* extractor is wrong | **[DERIVABLE TODAY]** `backend/app/services/mdi/service.py:533` |
| `document_reprocess_requested` | `POST /documents/{id}/reprocess` | `document_id` | PSEUDONYMOUS | Explicit dissatisfaction signal — a user telling you the extraction was wrong | **[DERIVABLE TODAY — as an access-log route hit]** `backend/app/api/v1/routes/documents.py:502` |

**Critical property caveat:** `corrections` payloads contain **corrected clinical values** (`backend/app/services/mdi/service.py:472` `_apply_corrections`). Emit the **count** and the **boolean** only. Emitting the correction *content* would be the single worst PHI leak available in this system — it is literally the patient's medication name and dose, user-verified.

### 4.3 Journey 3 — Medication schedule & adherence

| Event | Trigger | Properties | PHI | Why it matters | Status |
|---|---|---|---|---|---|
| `schedule_created` | `POST .../schedules` | `schedule_id`, `frequency_type`, `doses_per_day`, `source` ∈ {manual, promoted_from_document} | PSEUDONYMOUS | Does the document journey actually produce schedules? The join between J2 and J3 | **[DERIVABLE TODAY]** `backend/app/services/medication_schedule.py:203-208`; `source` not currently recorded |
| `reminder_surfaced` | dose `pending → notified` | `dose_id`, `schedule_id`, `latency_from_scheduled_ms` | PSEUDONYMOUS | The delivery denominator. **Note: pull-based** — fires only when the client calls `GET .../reminders/due` | **[NOT INSTRUMENTED — WS4-F13]** transition at `backend/app/services/medication_schedule.py:281-284` writes no audit row; route `backend/app/api/v1/routes/medication_schedule.py:243` |
| `dose_marked_taken` | `POST .../doses/{id}/taken` | `dose_id`, `minutes_after_scheduled` | PSEUDONYMOUS | Adherence numerator | **[DERIVABLE TODAY]** `backend/app/services/medication_schedule.py:331-337` (`action="medication_dose.taken"`) |
| `dose_marked_skipped` | `POST .../doses/{id}/skipped` | `dose_id`, `skip_reason_code` | PSEUDONYMOUS | Intentional non-adherence vs forgetting — clinically different | **[DERIVABLE TODAY]** same site. **`skip_reason` is free text** (`medication_schedule.py:314, 329`) → emit a **bounded reason code only**, never the text |
| `dose_missed` | sweep marks `missed` | `dose_id`, `hours_overdue` | PSEUDONYMOUS | The failure mode the whole journey exists to prevent | **[PARTIAL]** state exists (`backend/app/models/medication_schedule.py:50`); no audit row on the sweep |
| `schedule_paused` / `schedule_stopped` | pause/stop | `schedule_id`, `reason_code` | PSEUDONYMOUS | Abandonment of the medication loop | **[PARTIAL]** route `backend/app/api/v1/routes/medication_schedule.py:226` |

### 4.4 Journey 4 — Meto AI

`meto_audit_logs` is the best-instrumented surface in the product. Almost everything here already exists.

| Event | Trigger | Properties | PHI | Why it matters | Status |
|---|---|---|---|---|---|
| `meto_consent_changed` | `POST /meto/consent` | `context_type`, `granted`, `policy_version` | PSEUDONYMOUS | Which data categories patients will actually share with an AI — a genuine product finding | **[DERIVABLE TODAY]** `backend/app/services/meto_chat.py:536-542` |
| `meto_turn_completed` | chat/stream turn | `conversation_id`, `screen_id`, `context_blocks[]`, `provider_used`, `fallback_used`, `response_time_ms`, `token_count_in/out` | PSEUDONYMOUS | Usage, cost, latency, availability — all in one row, no message content | **[DERIVABLE TODAY]** `backend/app/services/meto_chat.py:641-659`; model `backend/app/models/meto.py:100-117` |
| `meto_output_replaced` | guardrail replaced the response | `conversation_id`, `pattern_class` | PSEUDONYMOUS | **The clinical-safety KPI.** How often the model tried to say something forbidden | **[LOG-ONLY — WS4-F11]** enforcement `backend/app/services/meto_chat.py:203-212`; log line `:204-208`. The audit boolean merges this with input red-flags at `:213` → not separable in SQL |
| `meto_escalation_shown` | red-flag escalation surfaced | `tier` ∈ {recommend_urgent, recommend_checkup} | PSEUDONYMOUS | Did the safety net fire, and did the patient act? | **[DERIVABLE TODAY]** `backend/app/models/meto.py:112`; escalation built at `backend/app/services/meto_chat.py:214-220`, audited `:694` |
| `meto_unavailable` | all providers failed | `conversation_id` | PSEUDONYMOUS | Users hitting the apology message — a churn driver | **[LOG-ONLY]** `backend/app/services/meto_chat.py:175`, stream `:370` |

**Absolute rule for this journey:** never emit the user's message, the model's response, a summary, an embedding, a topic label derived from content, or a token-level anything. `context_blocks[]` is the list of *block names* (`["recent_labs", …]`, `backend/app/models/meto.py:107-108`) — safe. Anything derived from the *contents* of those blocks is not.

### 4.5 Journey 5 — Doctor marketplace

| Event | Trigger | Properties | PHI | Why it matters | Status |
|---|---|---|---|---|---|
| `marketplace_browsed` | `GET /marketplace/doctors` | `has_specialty_filter`, `has_price_filter`, `result_count` | PSEUDONYMOUS | Is the directory usable? Zero-result rate is the discovery-failure signal | **[PARTIAL]** route `backend/app/api/v1/routes/marketplace.py:20`. **The `name` query param is free text** (`marketplace.py:26`) — emit `has_name_filter: boolean` only, **never the query** |
| `doctor_detail_viewed` | `GET /marketplace/doctors/{id}` | `doctor_id` | PSEUDONYMOUS | Browse→detail conversion | **[PARTIAL]** `backend/app/api/v1/routes/marketplace.py:46` |
| `consultation_booked` | `POST /consultations` | `consultation_id`, `doctor_id`, `method` ∈ {chat, video} | PSEUDONYMOUS | Detail→book conversion — the marketplace's reason to exist | **[DERIVABLE TODAY]** audit `consultation_creation`; route `backend/app/api/v1/routes/consultations.py:80` |
| `consultation_paid` | `POST /consultations/{id}/pay` | `consultation_id`, `outcome` | PSEUDONYMOUS | Mock-payment drop-off (real gateway is a credential gap) | **[DERIVABLE TODAY]** audit `payment_status_change`; route `backend/app/api/v1/routes/consultations.py:150` |
| `consultation_completed` | `POST /consultations/{id}/complete` | `consultation_id`, `duration_minutes` | PSEUDONYMOUS | Did the consult actually happen, or die after payment? | **[DERIVABLE TODAY]** audit `consultation_status_change`; route `:190` |
| `consultation_cancelled` | `POST /consultations/{id}/cancel` | `consultation_id`, `cancelled_by` ∈ {patient, doctor}, `stage` | PSEUDONYMOUS | Where the marketplace loses people | **[DERIVABLE TODAY]** audit `consultation_cancelled`; route `:200` |
| `review_submitted` | review created | `consultation_id`, `rating` (1–5) | PSEUDONYMOUS | Satisfaction. **Rating only — the review body is free text and must never be emitted** | **[DERIVABLE TODAY]** audit `consultation_review_created`; route `backend/app/api/v1/routes/consultations.py:299` |

### 4.6 Cross-cutting

| Event | Trigger | Properties | PHI | Status |
|---|---|---|---|---|
| `api_request_failed` | any non-2xx in the mobile client | `route_template`, `status`, `error_code`, `duration_ms`, `request_id` | PSEUDONYMOUS | **[NOT INSTRUMENTED]** — `mobile/src/api/client.ts:204-207` throws with no telemetry; needs WS4-F2's request id |
| `app_error_captured` | boundary or global handler | `fatal`, `boundary`, `source` | NONE | **[WIRED BUT INERT]** `mobile/src/lib/monitor.ts:74-86` — no-op sink in release (WS4-F1) |
| `consent_category_changed` | in-app consent toggle | `category`, `granted` | PSEUDONYMOUS | **[DERIVABLE TODAY]** audit `grant_consent`/`revoke_consent`; screen `mobile/app/(app)/consent.tsx` |
| `account_exported` / `account_deleted` | GDPR self-service | — | PSEUDONYMOUS | **[DERIVABLE TODAY]** audit `account_export`, `account_deleted` |

---

## 5. Funnels & metric definitions — "is the pilot working?"

Each metric states its denominator (the usual place analytics lies), whether it is computable today, and from what.

### 5.1 Activation

```
activation_rate = users with a terms_consents row
                ÷ users with a users row created in the cohort window
```
**Computable today** — `backend/app/models/consent.py:27-49` joined to `users`. Target ≥ 80% (`12-PILOT-OPERATIONS-RUNBOOK.md:45`).
**Caveat, stated plainly:** the runbook defines activation as "install → onboarding complete → first login". **Install is not measurable** for a sideloaded APK with no store analytics and no first-open event. The computable metric is *register → terms-accepted*, a strictly narrower funnel. Either redefine the KPI or accept an unmeasurable numerator — **do not report the narrow metric against the wide target.**

### 5.2 Document success rate (the headline pilot number)

```
upload_success   = document.accepted ÷ document.upload_session
review_reach     = documents with ≥1 candidate reviewed ÷ document.accepted
confirmation     = (candidate_confirm + candidate_merge)
                   ÷ (candidate_confirm + candidate_merge + candidate_reject)
end_to_end       = documents with ≥1 confirmed candidate ÷ document.upload_session
```
**Computable today** from `audit_logs` — see `04-OBSERVABILITY.md §6.2 q8`. `end_to_end` is the runbook's "Successful document import ≥ 70%" (`12-PILOT-OPERATIONS-RUNBOOK.md:46`).
**Blind spot:** `review_reach` cannot distinguish *never opened the review screen* from *opened and abandoned* — needs `review_screen_viewed` (§4.2). Without it a low confirmation rate is ambiguous between "OCR is bad" and "the review UI is confusing", which are opposite fixes.

### 5.3 OCR correction rate

```
correction_rate = confirms where corrections were applied ÷ all confirms
```
**NOT computable today.** `_apply_corrections` (`backend/app/services/mdi/service.py:472`) mutates the candidate but records nothing about whether corrections occurred. **Fix:** pass `details={"had_corrections": bool(corrections), "corrections_count": len(corrections or {})}` into the `_post_review` audit call (`mdi/service.py:485`) — PHI-free, no migration (`details` is JSON, `backend/app/models/governance.py`). This is the highest-value one-line analytics change in the codebase; the runbook already lists this KPI (`12-PILOT-OPERATIONS-RUNBOOK.md:47`).

### 5.4 Adherence

```
dose_response_rate = (medication_dose.taken + .skipped) ÷ doses reaching state 'notified'
adherence_rate     = medication_dose.taken ÷ (taken + skipped + missed)
```
**Numerator computable today** (`backend/app/services/medication_schedule.py:331-337`); **denominator requires reading `dose_occurrences.state` directly** because delivery is never evented (WS4-F13).
**Structural caveat that must appear next to any adherence number:** reminders are **pull-based** — `deliver_due_reminders` only runs inside a client request (`backend/app/services/medication_schedule.py:255-300`, route `backend/app/api/v1/routes/medication_schedule.py:243`) and there is no push (WS12-F1). A tester who does not open the app never gets reminded, and shows up as non-adherent. **Pilot adherence measures app-opening, not medication-taking.** Reporting it as a health outcome would be misleading.

### 5.5 AI engagement & safety

```
meto_adoption      = users with ≥1 chat_request ÷ activated users
turns_per_user     = chat_request count ÷ users with ≥1
fallback_rate      = AVG(fallback_used)
escalation_rate    = AVG(escalation_triggered)
p95_latency        = PERCENTILE_CONT(0.95) OVER response_time_ms
output_replacement = replaced turns ÷ chat_request          ← NOT computable in SQL
```
First five: **computable today** — `04-OBSERVABILITY.md §6.2 q10`. The last one is WS4-F11: log-only, requires the `details={"output_replaced": …}` fix.

### 5.6 Retention

```
D1 / D7 = users with a login_succeeded (or any authenticated request) on day N ÷ activated cohort
```
**Computable today** — audit `login` rows (`backend/app/services/auth.py:244-251`) or distinct `user_id` in the access log (`backend/app/core/middleware.py:96-105`). With a 15-minute access token and a refresh flow, "distinct authenticated `user_id` per day" from the access log is the more honest activity measure than login count.

### 5.7 Health & support

| Metric | Computable today? |
|---|---|
| Crash-free sessions ≥ 99% (`12-PILOT-OPERATIONS-RUNBOOK.md:51`) | ⛔ **No** — no session concept, and the crash sink is inert (WS4-F1). **This KPI cannot be reported.** |
| 5xx rate, p95 latency | ✅ access log — `04-OBSERVABILITY.md §6.2 q1, q2` |
| Support requests / active user | 🟡 manual — support channel is out-of-band |
| Safety incidents = 0 unresolved P0/P1 | ✅ manual review of `meto_output_replaced` log lines + audit `escalated` |

---

## 6. Implementation note — where instrumentation would hook in

Named real files. This is a design, not a plan of record; §8 argues most of it should not be built for the pilot.

### 6.1 Mobile (client-side events: screen views, abandonment, API failures)

| Hook | File | Why here |
|---|---|---|
| Emitter + typed event union + property guard | **new** `mobile/src/lib/analytics.ts` | Mirror `mobile/src/lib/monitor.ts` exactly: an `AnalyticsAdapter` interface, a swappable sink, a no-op default. That seam is already proven in this codebase and keeps a future vendor a 20-line change. |
| Automatic API-failure + latency events | `mobile/src/api/client.ts:176-211` | One choke point for every backend call. Emit `api_request_failed` from the `!res.ok` branch (`:204-207`) with `route_template` (derived, **never** the interpolated path — that would embed document ids in an event *name*), `status`, `code`. Pairs with the `X-Request-ID` work in WS4-F2. |
| Screen views | `mobile/app/(app)/_layout.tsx` | One `useEffect` on the expo-router pathname emits `screen_viewed` with a **normalised route template**. `mobile/app/(app)/review/[documentId].tsx` must report `/review/[documentId]`, never the id-substituted path. |
| Journey-2 abandonment | `mobile/app/(app)/add-document.tsx`, `mobile/app/(app)/review/[documentId].tsx` | The only place `document_capture_started` and `review_screen_viewed` can originate — the server cannot see them. |
| Session boundaries | `mobile/app/_layout.tsx:11` | Alongside `installGlobalErrorHandler()`; a `session_id` (uuid per foreground) is the prerequisite for crash-free rate. |
| Delivery sink | `mobile/src/lib/analytics.ts` → `POST /api/v1/telemetry/events` | Batch, cap the queue, drop on overflow, never block the UI, never retry indefinitely. First-party only (§3). |

### 6.2 Backend (server-side events)

**Preferred: enrich what already exists rather than build a parallel system.**

| Change | File | Effect |
|---|---|---|
| Add `details` to MDI review audits | `backend/app/services/mdi/service.py:485, 519, 533` (via `_post_review`) | Unlocks §5.3 correction rate. **No migration** — `AuditLog.details` is already JSON. |
| Add `ocr_confidence_bucket`, `candidate_count` to acceptance | `backend/app/services/mdi/service.py:255`; values available at `backend/app/services/mdi/pipeline.py:81, 94` | Unlocks OCR-quality-vs-outcome correlation |
| Audit failed logins + lockouts | `backend/app/api/v1/routes/auth.py:121-123`, `:104-112` | WS4-F3; unlocks §4.1 `login_failed` |
| Audit reminder surfacing | `backend/app/services/medication_schedule.py:284` | WS4-F13; unlocks the §5.4 denominator |
| Split Meto safety flags | `backend/app/services/meto_chat.py:222-240` → `:641-659` | WS4-F11; unlocks §5.5 output-replacement rate |
| Client-event ingest endpoint | **new** `backend/app/api/v1/routes/telemetry.py` | Only if client-side events are actually built. Must: require auth, force `user_id` from the token (never trust the body), validate against a closed Pydantic union, reject unknown properties (`model_config = ConfigDict(extra="forbid")`), rate-limit via the existing limiter (`backend/app/core/ratelimit.py`), and write to a new `analytics_events` table registered in `backend/app/services/account.py`'s deletion path **in the same PR** (§3.1 item 3). |

### 6.3 What NOT to do

- Do not reuse `AuditLog` as the client-event store. It is append-only, compliance-scoped, and retention-classified (`backend/app/services/audit_retention.py:24-30`); flooding it with screen views corrupts a legal record and blows past the TTL design.
- Do not add a third-party SDK to the mobile app before the DPA exists (§3.2).
- Do not emit anything whose value originates from OCR output, a chat turn, a search box, a skip reason, or a review body — §2.1.

---

## 7. Findings

These extend the WS4 series in `04-OBSERVABILITY.md §8`.

| ID | Sev | Finding | Evidence | Exact fix |
|---|---|---|---|---|
| **WS4-F16** | **P1** | **The pilot runbook commits to KPIs that cannot be measured.** `12-PILOT-OPERATIONS-RUNBOOK.md:42-53` lists 8 KPIs "measured via WS6 analytics" and §62 points to "a daily pilot report generated from analytics events (WS6)". No analytics exists (§1). Of the 8: activation is measurable only in a narrower form (§5.1), OCR correction rate is **not** measurable (§5.3), reminder engagement has no reliable denominator (§5.4), and crash-free sessions is **not** measurable at all (WS4-F1). Committing to unmeasurable exit criteria means the pilot cannot be declared pass or fail. | `12-PILOT-OPERATIONS-RUNBOOK.md:42-53, 55-59, 61-62`; §1 negative greps; §5 per-metric analysis | Amend the runbook KPI table to the six metrics computable today (§5), mark the other two "not measurable in pilot — see 05 §5.1/§5.7", and adopt the SQL in `04-OBSERVABILITY.md §6.2 q8–q10` as the daily pilot report. **Or** ship the three one-line backend enrichments in §6.2 (correction rate, reminder surfaced, safety split) and WS4-F1, which restores four of them. |
| **WS4-F17** | **P1** | **No analytics table is registered in the GDPR erasure path — and one will be created without it.** `PRIV-F2` (`15-FINAL-LAUNCH-REVIEW.md §4`) already showed this exact failure once: a new data store was added and account deletion did not erase it. Any `analytics_events` table keyed by `user_id` is personal data and will repeat the bug unless the erasure path is extended in the same change. | erasure path `backend/app/services/account.py` + `backend/app/api/v1/routes/account.py` (the PRIV-F2 fix); regression precedent `backend/tests/test_account_export_delete.py::test_delete_returns_object_storage_keys_for_erasure` | **Pre-emptive control:** make it a hard review rule that no new table with a `user_id` column merges without (a) a delete-path entry and (b) a regression test asserting zero rows after deletion. Cheap now, expensive after the fact. |
| **WS4-F18** | **P2** | **Free-text values sit one careless line away from three would-be event payloads.** The marketplace `name` filter (`backend/app/api/v1/routes/marketplace.py:26`), the dose `skip_reason` (`backend/app/services/medication_schedule.py:314, 329`), and MDI `corrections` (`backend/app/services/mdi/service.py:472`) are all natural "just add it to the event" properties, and all three are patient-authored or clinical content. | as cited | Encode the ban in the typed event union (§2.3) so these properties are not expressible, plus the CI grep gate. Convert `skip_reason` to a bounded enum + optional free-text note kept out of analytics. |
| **WS4-F19** | **P2** | **`document.accepted` records no quality signal.** Neither `ocr_confidence` nor `candidate_count` is persisted at acceptance, so a document that extracted **zero** candidates is indistinguishable from a clean one in the audit log — a total OCR failure looks like a success. | acceptance audit `backend/app/services/mdi/service.py:255`; values available but discarded at `backend/app/services/mdi/pipeline.py:81, 94` | Add `details={"candidate_count": n, "ocr_confidence_bucket": bucket(conf), "doc_type": doc_type}` to the `document.accepted` audit call. No migration. |
| **WS4-F20** | **P2** | **No session concept exists in the mobile app**, so every per-session metric (crash-free rate, screens-per-session, session length) is undefined — including the runbook's crash-free ≥ 99% exit criterion. | no session id in `mobile/src/lib/monitor.ts:42-49`; nothing in `mobile/app/_layout.tsx` | Mint a `session_id` uuid on foreground in `mobile/app/_layout.tsx` next to `installGlobalErrorHandler()` (`:11`), include it in `appContext()` (`monitor.ts:42-49`) so every captured error carries it. Prerequisite for WS4-F1's value. |

**Summary: 0 P0 · 2 P1 · 3 P2.**

---

## 8. Scoping decision — is analytics pilot-blocking?

**Decision: product analytics instrumentation is BETA-SCOPE, not pilot-blocking — with two carve-outs that ARE pilot-blocking.**

**Why not blocking.** A ≤50-user pilot with a named, reachable cohort does not need a product-analytics pipeline. Statistical funnels over 50 users are noise; the reliable instrument at this scale is talking to the testers. And the compliance backbone already answers ~70% of the funnel in SQL (§1.1, §5) with zero new code, zero new PHI surface, and zero vendor. Building a client-event pipeline now would add a new data store, a new ingest endpoint, a new erasure obligation (WS4-F17), and a new leak surface (§2) — to sharpen numbers whose sample size cannot support the sharpening. That is a bad trade, and `15-FINAL-LAUNCH-REVIEW.md:28` already reached the same conclusion ("instrumentation is beta-scope"). Direct source inspection **confirms** it.

**The two carve-outs that ARE blocking**, because they are about *detecting failure*, not measuring product-market fit:

1. **WS4-F1 + WS4-F2 + WS4-F20 (mobile error visibility + correlation + session).** Not analytics — incident detection. A pilot whose testers' apps crash silently is a pilot that learns nothing and burns its cohort. `15-FINAL-LAUNCH-REVIEW.md:78` already lists this as a GO condition.
2. **WS4-F16 (KPI honesty).** Either fix the runbook's KPI table or ship the three one-line audit enrichments. Shipping against exit criteria you cannot evaluate is worse than shipping with fewer criteria.

**The three one-line backend enrichments are recommended regardless** (§6.2: MDI correction details, reminder-surfaced audit, Meto safety split). Each is a `details={...}` addition to an existing `audit.record`/audit-write call, requires **no migration**, adds **no new PHI surface**, and each unlocks a KPI the runbook already promised. Combined effort: well under an hour, including tests.

**Beta-scope, in order:** `mobile/src/lib/analytics.ts` with the typed union + property guard → screen views and Journey-2 abandonment events → the first-party ingest endpoint (with the erasure-path rule from WS4-F17) → only then evaluate a third-party processor, behind the same owner gate as Sentry and cloud OCR.

## 9. Cross-references

`04-OBSERVABILITY.md` (WS4-F1…F15 — operational signals, PHI channel review, KQL/SQL query set) · `12-PILOT-OPERATIONS-RUNBOOK.md §Pilot KPIs, §Pilot exit criteria` (amended by WS4-F16) · `15-FINAL-LAUNCH-REVIEW.md §2 WS6, §5` (analytics beta-scope decision — confirmed) · `14-FEATURE-ROLLOUT.md` (flag states that condition which journeys emit anything at all).
