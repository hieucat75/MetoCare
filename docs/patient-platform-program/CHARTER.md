# MetoCare Patient Platform — Program Charter (Hiến pháp vận hành)

**Status:** RATIFIED 2026-07-30 — **APPROVED FOR AUTONOMOUS EXECUTION**
**Authority:** This Charter is the **highest operating law** of the program. It does **not** replace `01-CONSOLIDATED-BRD.md` or `02-MASTER-IMPLEMENTATION-PLAN.md` (v1.1, approved) — it governs how they are executed. On any conflict, the Charter wins over the plan; the plan wins over local convenience.

---

## ⭐ North Star (mục tiêu cuối cùng)

> **Xây dựng ứng dụng chăm sóc sức khỏe cho bệnh nhân mắc hoặc có nguy cơ mắc bệnh chuyển hóa, nơi bệnh nhân chỉ cần chụp tài liệu y tế thay vì nhập liệu thủ công, và toàn bộ hành trình từ tài liệu → dữ liệu → theo dõi → nhắc thuốc → AI → bác sĩ diễn ra liền mạch, an toàn và có thể kiểm chứng.**

Every batch, PR, review, and demo is judged against this sentence — not against module count.

---

## The 10 Charters

### Charter 1 — Product-first, không phải Feature-first
Every batch must answer **"Bệnh nhân hôm nay làm được thêm điều gì?"** — never "how many APIs/models were added." "+15 endpoints, +12 models" is **not** progress; "patient photographs a prescription → confirms meds → reminder runs → timeline updates" **is**.

### Charter 2 — Vertical Slice
No horizontal layering (Backend 100% → Frontend 100% → Mobile 100%). Each slice goes **backend → mobile UI → test → review → demo → merge**, then move to the next slice. This minimizes integration risk. One journey slice is finished end-to-end before the next begins.

### Charter 3 — Mobile is the source of truth for UX
Direction is inverted: **Mobile UX → API → Backend** (not Backend → Web → Mobile). The patient app defines the contract; the backend serves it. Web remains a reference, not the driver.

### Charter 4 — No technical debt because "chưa production"
"Sẽ sửa khi lên production" is banned. If a model, architecture, or ownership is known to be wrong, **fix it now** — do not paper over it with a TODO. (Reinforces the audit's hardening backlog and finding-round corrections.)

### Charter 5 — Demo-driven Development
Every milestone ships a **video demo** of the real patient journey (e.g. M3: install → login → camera → OCR → review → confirm → timeline → reminder). **No slides.** The video is the evidence.

### Charter 6 — No rebuild
**Reuse > Rewrite** is law. To rewrite an existing module an agent must prove: (a) it cannot be reused, (b) rewrite cost is lower than adapting, and (c) no existing test coverage is lost. Otherwise reuse is mandatory. (The audit's reuse verdict stands.)

### Charter 7 — Definition of Done = Patient Journey Completed
Not "code runs." A capability is Done only when the full patient journey completes. Example (Reminder): **OCR → confirm → schedule → push/deliver → tap → taken → timeline → dashboard → analytics** — not merely "scheduler created an event."

### Charter 8 — No scope creep
Keep the deferral discipline already set (OTP, Payment, Apple, Google, Azure Doc Intelligence, VNPay/MoMo all deferred). If an agent notices "tiện đây…", it **does not** open a new program. New scope requires a new owner decision, not an in-flight expansion.

### Charter 9 — Evidence > Report
Per batch, deliver only: **Demo · Test · Coverage · Screenshots · Video · Commit · Review · Known limitations.** No 20-page reports.

### Charter 10 — Final Goal is the North Star (above)
The goal is not "Build MetoCare Mobile" — it is the North Star sentence. Measure the whole program by **patient value delivered**, never by modules completed.

---

## Governance hierarchy (order of authority)

1. **North Star** (this doc) — why we exist.
2. **Charter 1–10** (this doc) — how we operate.
3. **`JOURNEY-MAP.md`** — the primary execution & measurement lens (5 patient journeys as vertical slices).
4. **`01-CONSOLIDATED-BRD.md` / `02-MASTER-IMPLEMENTATION-PLAN.md` (v1.1)** — product behavior + technical substrate (bounded contexts, workstreams, schema, migrations).
5. **`00-CAPABILITY-AUDIT.md`** — the verified current-state baseline.

The bounded contexts and workstreams in the Master Plan are **unchanged**; the Journey Map re-sequences and re-measures them as vertical, patient-value slices.
