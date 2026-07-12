# MEDICATION_GAP_AND_PRIORITY_MATRIX.md
# MetoCare — Medication Management: Gap & Priority Matrix

**Version:** 1.0  
**Date:** 2026-07-10

---

## 1. Scoring Legend

- **Impact (1–5):** How much this improves patient safety, UX, or clinical value
- **Effort (1–5):** Development effort (1=hours, 5=weeks)
- **Risk (1–5):** Risk to production stability or patient safety if done wrong (5=high risk)
- **Priority Score = Impact × 2 − Effort − Risk** (higher = do first)

---

## 2. Full Gap Matrix

| ID | Gap | Impact | Effort | Risk | Score | Phase |
|----|-----|--------|--------|------|-------|-------|
| G01 | No medication `status` field (active/paused/discontinued) | 5 | 2 | 1 | **7** | P0 |
| G02 | No `start_date` / `end_date` on medications | 4 | 2 | 1 | **5** | P0 |
| G03 | No `generic_name` linkage on patient medication records | 5 | 2 | 2 | **6** | P0 |
| G04 | No supplement / traditional medicine classification | 5 | 2 | 2 | **6** | P0 |
| G05 | Medication list page lacks structured dose fields | 3 | 3 | 1 | **2** | P0 |
| G06 | Weekly adherence bars are approximated (not real per-day) | 4 | 3 | 1 | **4** | P1 |
| G07 | No medication detail page (`/medications/[id]`) | 4 | 3 | 1 | **4** | P0 |
| G08 | No scheduled dose times / reminder system | 5 | 4 | 2 | **4** | P1 |
| G09 | No allergy table | 5 | 3 | 3 | **4** | P3 |
| G10 | No drug-drug interaction detection | 5 | 4 | 3 | **3** | P3 |
| G11 | No drug-lab interaction detection | 4 | 4 | 3 | **1** | P3 |
| G12 | Caution flags from catalog never surfaced to user | 3 | 2 | 1 | **3** | P0 |
| G13 | Drug catalog has 41 drugs — gaps in coverage | 4 | 3 | 1 | **4** | P0 |
| G14 | OCR prescription capture (zero implementation) | 4 | 5 | 4 | **-1** | P2 |
| G15 | No refill tracking | 3 | 3 | 1 | **2** | P4 |
| G16 | No caregiver access model | 4 | 4 | 2 | **2** | P4 |
| G17 | No medication export for doctor visits | 3 | 3 | 1 | **2** | P4 |
| G18 | No prescribing doctor stored on record | 3 | 2 | 1 | **3** | P0 |
| G19 | PHI fields not encrypted at rest in medications table | 4 | 3 | 2 | **3** | P1 |
| G20 | Notification type `medication_reminder` missing | 4 | 2 | 1 | **5** | P1 |
| G21 | No per-day adherence history API | 3 | 3 | 1 | **2** | P1 |
| G22 | Meto AI medication context lacks generic_name / warnings | 3 | 2 | 1 | **3** | P0 |
| G23 | No drug interaction rules table | 5 | 4 | 4 | **2** | P3 |
| G24 | MedicationCard design system component not wired to API | 3 | 3 | 1 | **2** | P0 |

---

## 3. Top Priority Items (Score ≥ 4)

| Rank | ID | Gap | Score | Phase | Why Now |
|------|----|-----|-------|-------|---------|
| 1 | G01 | Medication status field | 7 | P0 | Safe migration, high UX value, blocks MedicationCard wiring |
| 2 | G03 | Generic name linkage | 6 | P0 | Prerequisite for any duplicate/interaction detection |
| 3 | G04 | Supplement classification | 6 | P0 | Safety rule SR-009 — required before more drugs added |
| 4 | G02 | Start/end date | 5 | P0 | Patient UX basic need |
| 5 | G20 | medication_reminder notification type | 5 | P1 | Enables adherence loop closure |
| 6 | G06 | Real per-day adherence history | 4 | P1 | Current weekly chart is misleading |
| 7 | G07 | Medication detail page | 4 | P0 | Route exists, page missing |
| 8 | G08 | Reminder schedule | 4 | P1 | Adherence cornerstone |
| 9 | G09 | Allergy table | 4 | P3 | Safety-critical but complex |
| 10 | G13 | Drug catalog coverage | 4 | P0 | Low effort, high value |

---

## 4. Clinical Risk Hotspots

Issues where a gap creates direct patient safety risk:

| Gap | Clinical Risk |
|-----|--------------|
| G09 — No allergy table | Patient allergic to penicillin prescribed amoxicillin — system has zero data to flag this |
| G10 — No drug-drug interaction | Warfarin + aspirin co-prescribed — major bleeding risk unchecked |
| G03 — No generic name linkage | Patient taking Diamicron + Glimepiride (two sulfonylureas) — duplicate detected only if names match exactly |
| G04 — No supplement flag | Patient taking herbal hepatotoxin with metformin — no tracking, no warning |
| G14 — OCR no confirmation gate | If implemented carelessly, could auto-activate wrong medication |
| G13 — Catalog gaps | Drug not in 41-drug catalog = no autocomplete, no interaction check |

---

## 5. Dependencies Map

```
G01 (status) ─────────────────────────────────────────────────┐
G02 (start/end date) ─────────────────────────────────────────┤
G03 (generic name) ────────────────────────────────────────────┤── P0 Complete ──┐
G04 (supplement) ─────────────────────────────────────────────┤                  │
G07 (detail page) ────────────────────────────────────────────┤                  │
G12 (caution flags) ──────────────────────────────────────────┘                  │
                                                                                   │
G06 (real adherence) ─────────────────────────────────────────┐                  │
G08 (reminders) ──────────────────────────────────────────────┤── P1 Complete ──┬┘
G20 (reminder notification type) ─────────────────────────────┤                  │
G19 (PHI encryption) ─────────────────────────────────────────┘                  │
                                                                                   │
G14 (OCR) ────────────────────────────────────────────── P2 (standalone) ────────┤
                                                                                   │
G09 (allergy) ────────────────────────────────────────────────┐                  │
G23 (interaction rules) ──────────────────────────────────────┤── P3 ──needs──P0─┘
G10 (drug-drug interaction) ──────────────────────────────────┤
G11 (drug-lab interaction) ───────────────────────────────────┘

G15 (refill) ─────────────────────────────────────────────────┐
G16 (caregiver) ──────────────────────────────────────────────┤── P4
G17 (export) ─────────────────────────────────────────────────┘
```

**Key dependency:** G09 (allergy) and G10 (interaction) require G03 (generic name linkage) to work correctly.  
G03 is a P0 item — must be done before P3 begins.

---

## 6. Effort Estimates by Phase

| Phase | Items | Backend Effort | Frontend Effort | Test Effort | Total |
|-------|-------|---------------|----------------|-------------|-------|
| P0 | G01, G02, G03, G04, G05, G07, G12, G13, G18, G22, G24 | 3–4 days | 3–4 days | 2 days | ~10 days |
| P1 | G06, G08, G19, G20, G21 | 3–4 days | 3–4 days | 2 days | ~10 days |
| P2 | G14 | 5–7 days | 3–4 days | 3 days | ~15 days |
| P3 | G09, G10, G11, G23 | 7–10 days | 4–5 days | 4 days | ~20 days |
| P4 | G15, G16, G17 | 4–5 days | 3–4 days | 2 days | ~11 days |

**Total estimate:** ~66 developer-days (backend + frontend + test)  
**Recommended sprint size:** P0 as one sprint (~2 weeks), then P1 standalone sprint.

---

## 7. Stop Gate Conditions

Do NOT proceed to implementation without PTH approval if:

| Condition | Gate |
|-----------|------|
| P3 interaction rules need external drug database | STOP — license/cost decision |
| P1 reminders need production SMS/push infrastructure | STOP — infrastructure + user consent |
| OCR prescription feature needs to be enabled for real users | STOP — PTH manual staging verification first |
| P3 allergy feature ships before Vietnamese doctor reviews clinical logic | STOP — clinical review required |
| Any migration is destructive (drops existing columns) | STOP — explicit PTH approval |
| Caregiver access model needs legal/privacy review | STOP — Vietnamese personal data law |
