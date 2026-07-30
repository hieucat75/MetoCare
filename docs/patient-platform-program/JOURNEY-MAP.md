# MetoCare Patient Platform — Patient Journey Map (execution & measurement lens)

**Status:** RATIFIED 2026-07-30. Governed by `CHARTER.md`. Sits **above** the BRD/Plan as the primary sequencing and measurement lens; the Master Plan's bounded contexts and workstreams (WS0–WS12) are **unchanged** — this doc slices them **vertically** (Charter 2) so the program is always measured by **patient value** (Charter 1/10), not module count.

**How to read:** each Journey is a vertical slice delivered **backend → mobile UX → test → review → demo → merge** before the next Journey starts. A Journey is **Done** only when its full patient journey completes end-to-end on a device/artifact (Charter 7) with a **video demo** (Charter 5). Capabilities map to BRD sections (A–R); build detail maps to Master-Plan milestones (M#) and workstreams (WS#).

---

## Execution order (vertical slices)

```
Journey 1 (First-time Patient)      ─ foundation; unblocks everything
   ↓
Journey 2 (Import Health Records)   ─ the document-first heart of the product
   ↓
Journey 3 (Daily Care)              ─ turns imported data into ongoing care
   ↓
Journey 4 (AI Companion)            ─ Meto over confirmed data
   ↓
Journey 5 (Doctor Care)            ─ human care loop
```
Within Journey 2, sub-slices ship in order: **prescription OCR → lab OCR → general-report OCR** (finish one end-to-end before the next). Foundations that multiple journeys need (CI single-head gate, Object Storage §1.7, Notification transports, security hardening) are pulled into the **earliest journey that requires them** and hardened there, not built as a separate horizontal phase.

---

## Journey 1 — First-time Patient
**Bệnh nhân làm được gì mới:** tải app, đăng ký, hoàn tất onboarding, và thấy một dashboard có ý nghĩa — kể cả khi chưa có dữ liệu (empty state dẫn tới "Add Document").

- **Capabilities (BRD):** A (mobile shell/auth), B (health record hub), I (dashboard).
- **Substrate (Plan):** M0 (CI single-head gate), M1 (mobile foundation + email/password auth + secure/biometric), Batch 0–1; WS1, WS10, WS12. Auth scope = email/password (OTP deferred, ADR-02); app installation UUID (ADR-03).
- **Journey Done (Charter 7):** install → register → onboarding → dashboard (empty-state → "Add Document" CTA) on Android internal artifact / iOS simulator; token refresh + forced-logout-on-reuse proven; VN copy.
- **Demo:** install → register → onboarding → dashboard.

## Journey 2 — Import Health Records (document-first core)
**Bệnh nhân làm được gì mới:** chỉ cần **chụp** đơn thuốc / phiếu xét nghiệm / tài liệu y tế → hệ thống trích xuất → bệnh nhân **xác nhận từng mục** → dữ liệu vào hồ sơ, không phải gõ tay.

- **Capabilities (BRD):** C (secure Add-Document upload), D (prescription OCR), E (lab OCR), F (general-report OCR); depends on the one-to-many candidate/promotion model.
- **Substrate (Plan):** Object Storage §1.7 (upload-session→quarantine→finalize→accept), MDI candidate/`PromotionLink` model §1.5, staged OCR §1.4; M2, M3, M4, M7; WS2, WS3, WS4; security WS9 for object-storage authz **before any real doc in staging**. Enable `OCR` flag in staging only **after** M4 exit (Charter 12 / §1.10).
- **Sub-slices (strict order):** 2a prescription (M3) → 2b lab (M4) → 2c general report (M7). Each: photo → per-candidate confirm/reject → promote → record + timeline; no duplicate promotion on reprocess.
- **Journey Done:** photograph each of the three document types → per-candidate confirm → confirmed records appear in the health record + timeline, with backlink to source image; no canonical write pre-confirmation; unstructurable prescription frequency → med confirmed without a guessed schedule.
- **Demo:** camera → OCR → per-medicine review → confirm → medications + lab trend + timeline entry.

## Journey 3 — Daily Care
**Bệnh nhân làm được gì mới:** được **nhắc uống thuốc** đúng giờ, ghi taken/skipped, thấy adherence, và một **timeline hợp nhất** + dashboard hành động phản ánh mọi thứ.

- **Capabilities (BRD):** G (medication schedule/reminder/adherence/reconciliation), H (unified timeline), I (dashboard, action-first).
- **Substrate (Plan):** medication scheduling §1.8 (tz/type/occurrence, idempotent, confirmed-only), Notification Delivery §1.1 (deterministic + in-app transports — real push is a DIST-RC add-on), timeline unification (docs/labs/meds/adherence/appointments); M5, M6; WS5, WS6, WS7.
- **Journey Done (Charter 7 full loop):** confirmed med → schedule → dose occurrence → reminder delivered (deterministic/in-app) → tap → taken → adherence + timeline + dashboard update; PRN never auto-reminds; scheduler retry never duplicates a dose.
- **Demo:** confirmed med → scheduled reminder fires → mark taken → dashboard + timeline + adherence update.

## Journey 4 — AI Companion
**Bệnh nhân làm được gì mới:** hỏi **Meto** để hiểu kết quả xét nghiệm / thuốc / lịch sử — chỉ dựa trên **dữ liệu đã xác nhận**, an toàn, có nguồn.

- **Capabilities (BRD):** J (Meto on confirmed data).
- **Substrate (Plan):** Meto confirmed-data restriction + flag/consent gate + existing `SafetyGuard`; enable Meto flag in staging only **after** M8 exit; M8; WS7. AI gateway is pre-existing infra (audit AI1/AI8 COMPLETE), CI uses deterministic mock gate.
- **Journey Done:** "explain my confirmed HbA1c / this medication" answers from confirmed data only, with source/time badges; forbidden patterns blocked; red-flag → escalation; provider/model/version audited.
- **Demo:** open Meto from a confirmed lab result → explanation with source badge → red-flag escalation shown.

## Journey 5 — Doctor Care
**Bệnh nhân làm được gì mới:** tìm bác sĩ, đặt tư vấn, và **chia sẻ hồ sơ có kiểm soát** (consent-scoped), bác sĩ thấy rõ dữ liệu nào đã xác nhận vs OCR-chưa-xác nhận.

- **Capabilities (BRD):** K (marketplace/booking/consultation, mock payment), L (record sharing + revocation/masking), M (clinic continuity slice).
- **Substrate (Plan):** reuse the COMPLETE consultation/marketplace vertical + `ConsultationAccessGrant`/`ConsentGuard` (after fixing fail-open, F5); payment = mock abstraction (Charter 8 deferral); M9; WS8, WS9.
- **Journey Done:** discover → book → consult (mock payment) → consented record share → doctor sees provenance badges → revoke → doctor view masked; all access audited.
- **Demo:** discover doctor → book → consult → share records (with provenance) → revoke → masked.

---

## Cross-journey guarantees (apply to every slice)
- **Security is in-slice, not a later phase:** object-storage authz, consent default-deny (F5), BOLA tests, secret/key hardening land **inside** the journey that first exposes them (Charter 4 — no deferred debt).
- **Progressive flags (Charter 12 / §1.10):** `OCR` after Journey 2b, `MEDICATION_KNOWLEDGE_RETRIEVAL` after its content/authz gate, Meto after Journey 4 — staging only, never production.
- **Two-tier RC (§5):** every Journey Done above is at **Engineering-RC** level (no external credential). Real device push / TestFlight / Play track upgrade to Distribution-RC later without reopening functional work.
- **Evidence per slice (Charter 9):** Demo video · tests · coverage · screenshots · commit/PR · independent review · known limitations — nothing more.
