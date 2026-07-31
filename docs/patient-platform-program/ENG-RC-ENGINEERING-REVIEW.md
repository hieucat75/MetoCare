# MetoCare Patient Platform — Engineering Release Candidate (ENG-RC) Review

**Date:** 2026-07-31
**Branch:** `feat/patient-platform-journey2` (off `main`, not merged)
**Scope:** Autonomous completion of the approved Patient Platform Completion Program (Journeys 1–5) to Engineering Release Candidate.
**Governance:** Charter + Consolidated BRD v1.1 + Master Implementation Plan v1.1.

> This is the **single comprehensive engineering review** the owner requested at RC — not an intermediate progress report. It presents everything delivered, the evidence, the safety/security posture, and the small set of decisions that require the owner.

---

## 1. Verdict

**Engineering Release Candidate reached.** All five patient journeys are implemented, independently reviewed, and committed with green automated verification. The clear-cut, no-external-credential safety blockers (P0 default-secret boot, P1 OCR DoS) are closed.

Three items remain that are **product/scope decisions, not engineering gaps** (§5), plus one **physical verification caveat** (native on-device runtime for the J2–J5 mobile surfaces, §6). None is a code defect; each is flagged for your single review.

---

## 2. What was delivered (by journey)

| Journey | Outcome | Key commits |
|---|---|---|
| **J1 — First-time patient** | Expo RN app boots on Android emulator; onboarding→login→dashboard vs FastAPI; secure-store AES at rest; cold-boot session restore. Role-gate + boot-resilience P1s fixed. | `e54794d` (native runtime) |
| **J2 — Import health records** | Medical Document Intelligence: Object Storage abstraction + signed blob tokens; staged OCR pipeline (Preprocessor→…→Promoter) with extractor/promoter registries; one-document→many-candidate→per-candidate confirm model. Real VN extractors for **prescription (2a)**, **lab (2b)**, **general report (2c)**; statement-first medication promotion; lab→HealthMetric reuse; diagnosis never auto-canonical. Mobile Add-Document + review UI. | `f5085cc`, `4e5278d`, `5542c3b`, `1aca416`, `fc4f90f`, `0fd17f6` |
| **J3 — Daily care** | Timezone-aware idempotent medication schedule + dose materialization (`ON CONFLICT DO NOTHING`); reminder delivery (deterministic + in-app always; push/email capability-gated); adherence (taken/skipped/missed with sweep); edit=supersession. Unified health timeline (doses/documents/confirmed candidates) + action-first dashboard. | `1a12932`, `40eccc5`, `160a94b` |
| **J4 — Meto AI on confirmed data** | Closed the AI2 gap: assistant context is now **confirmed-data-only** (labs gated `verified_by_user OR verified_by_doctor`; other blocks confirmed by construction). Flag gate (`AI_ASSISTANT`, fail-closed 503) on chat endpoints. Removed an ungated debug endpoint that leaked a data-existence oracle. | `559d8c2` |
| **J5 — Doctor care** | Doctor-marketplace mobile: browse/search → doctor detail → consent-gated booking → mock payment → my consultations → detail with read-only doctor notes → review. Reuses the existing consultation backend vertical (no backend change). | `317edeb` |
| **WS9 — Pre-RC hardening** | Fail-loud on committed default JWT/PHI secrets in real environments; rate-limit on the synchronous lab-OCR endpoint. | `4539a3d` |

Full program commit chain on this branch: `a500453, f5085cc, 4e5278d, 5542c3b, 1aca416, fc4f90f, 0fd17f6, 1a12932, 40eccc5, 160a94b, 559d8c2,317edeb, 4539a3d` (J1 on its own branch `feat/patient-platform-journey1`, tip `e54794d`).

---

## 3. Quality evidence

- **Backend test suite:** green (0 failures) at every committed checkpoint; **3761 tests collected** at RC.
- **Mobile:** `tsc --noEmit` clean; Jest **62/62** across 14 suites; lint 0 errors.
- **Static:** `ruff` clean; single Alembic head maintained (CI single-head gate); migration up/down/re-up round-trips + Postgres integration tests.
- **Independent review loop (per slice):** each slice reviewed by the relevant specialist agents (`security-reviewer`, `healthcare-reviewer`, `code-reviewer`, and for mobile `react-reviewer` + `typescript-reviewer`). **All confirmed P0/P1 were fixed in-slice with regression tests** before commit. Notable fixes: MDI TOCTOU-safe accept (2 P0), lab unit-misclassification clinical P0, reminder-for-stopped-schedule + inflated-adherence P1s, Meto debug-endpoint leak P1, marketplace double-charge P1, consent-literal P1.
- **Pre-commit local-CI** (ruff + backend unit/sentinel tests) passed on every commit.

---

## 4. Safety & security posture

- **PHI-to-AI:** Meto now sees confirmed clinical data only; fail-closed feature-flag gate; provider name never disclosed. SafetyGuard output enforcement (diagnosis/dose-change/provider-disclosure) is **enforcing, not detection-only** — a response failing the output check is replaced with a safe fallback before it reaches the patient, on both the non-streaming path and the streaming path (streaming is buffered so the check runs before any content is emitted). *(This was corrected during the post-RC verification audit — see §8.)*
- **Secrets:** boot now refuses committed default JWT/Fernet secrets in any non-dev/test environment (closes silent-injection-failure risk).
- **Object storage:** server-generated keys, HMAC signed op-bound short-lived blob tokens (key derived separately from JWT secret), path-traversal guard, TOCTOU-safe accept.
- **Authorization / BOLA:** verified already-safe — dashboard, lab, medication_schedule, documents, consultations all enforce caller-owns-resource.
- **Rate-limiting:** documents + (now) lab-upload endpoints throttled.
- **Least privilege:** the patient mobile client exposes no doctor-only transitions.

---

## 5. Decisions required from you (product/scope — not engineering defects)

1. **Meto AI consent legal basis.** The AI context has no per-request consent gate; the current documented basis is **terms-of-service acceptance at registration**. The `MetoConsent` per-category table exists but is not wired as a runtime gate (wiring it fail-closed with no grant-path would make Meto return nothing for all existing users). BRD §J references a "consent gate." **Decide:** T&C-at-registration is the accepted legal basis (keep current), **or** we implement explicit per-category consent with a grant/revoke UX and fail-closed enforcement (additional slice). *Safety note: today's behavior is confirmed-data-only + flag-gated, so no unverified PHI reaches the model; the open question is honoring per-category revocation.*

2. **Data-subject rights (GDPR-style export/erasure).** No patient self-service data export or account deletion exists. **Decide:** is this in **ENG-RC** scope or deferred to **DIST-RC** (distribution) alongside the other external-dependency items? If in scope, it's a self-contained new slice (self-scoped export bundle + soft-delete/anonymize).

3. **MFA + password policy restore timing.** MFA enforcement is off and password minimum is 6 chars — an **intentional build-phase relaxation** (previously risk-accepted). **Confirm** these are restored before production/DIST-RC (not required for engineering evaluation).

---

## 6. Caveats & remaining verification

- **Native on-device DoD (Charter-7).** J1 was verified on a booted Android emulator. The J2–J5 mobile surfaces (Add-Document/OCR review, reminders, Meto, marketplace) are **headless-verified only** (tsc + Jest). Confirming the photo→confirmed and browse→book flows on a booted artifact needs **one native-runtime session** with an Expo dev-client rebuild (the `expo-image-picker` native module) — deferred because the emulator toolchain proved flaky during J1 and this is a long, physical session best run interactively.
- **Staging flag enablement.** After your review: enable the `OCR` flag in staging (post-M4 exit) and confirm `AI_ASSISTANT` (already set on staging). Both are progressive-enablement config, not code.
- **Documented deferrals (fast-follow, non-blocking):** retire the legacy `ocr.py` skeleton; per-candidate LabDocument/batch grouping; central unmount/abort guard for fetch-on-mount mobile hooks; timeline date-bound queries + missing_source labels.

---

## 7. Recommended next steps

1. Review §5 decisions.
2. Schedule the one native-runtime session for the J2–J5 on-device DoD (§6).
3. On approval, open the integration PR(s) to `main` and enable staging flags.
4. Address any in-scope §5 items as discrete reviewed slices, then proceed toward DIST-RC (external credentials: Apple/Google signing, APNs/FCM, Azure DI + PHI-cloud authorization, real payment gateway).

---

## 8. Post-RC verification audit (2026-07-31)

Before treating this report as distribution-ready, every claim above was re-verified by four independent adversarial auditors (security, clinical/privacy, migration+API contract, mobile flow), each required to CONFIRM or REFUTE against actual code + tests.

**Result:** Security 7/7, mobile 8/8, migration+API 8/8 all CONFIRMED. The clinical/privacy audit found **one real discrepancy**: the §4 SafetyGuard claim was **overstated** — `check_output` was called but its result was discarded (detection-only), so a forbidden model response (provider self-disclosure / diagnosis / dose-change) could still reach the patient, and in the streaming path content was emitted before the check ran.

**Fixed (`app/services/meto_chat.py`):** output safety is now enforcing — unsafe responses are replaced with a safe fallback on the non-streaming path, and the streaming path is buffered so the check runs before any content is emitted. Regression tests: `tests/test_meto_output_safety.py` (non-stream replacement + stream buffered-replacement, exercising the real SafetyGuard). §4 above corrected to match.

**Minor phrasing corrected:** test count is 3761 (was "~3540+"); the MDI candidate→promotion relation is enforced at-most-once (one-to-one), while document→candidate is the one-to-many.

**Tracked defense-in-depth follow-up (not a current gap):** `_build_recent_metrics` in the AI context builder has no verification filter of its own — it is safe today because `health_metrics` is only written from `self_report` (patient-authored) or from lab→metric promotion that already gates on verified rows. A future writer inserting an unverified metric would not be caught at the builder. Add a source/verification guard (or a verified column) as defense-in-depth before DIST-RC.

With the enforcement fix in place and all other claims verified against code + tests, the report accurately reflects the implementation.
