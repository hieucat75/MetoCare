# MetoCare Clinic SaaS — Master Program Plan (C1–C4)

Status: Draft, self-checked against BRD before C1 start. Written 2026-07-09 per PTH's
standing continuous-implementation approval. Source of truth for phase/milestone
mapping: `docs/brd/v1.0/executive-brd.md` §18, `docs/brd/v2.0/00-overview.md`,
`docs/brd/v2.0/appendix-c-traceability.md`. Cross-cutting gaps: `docs/clinic-saas/BRD_ANALYSIS.md`.
Architecture baseline: `TENANT_ARCHITECTURE.md`, `RBAC_MATRIX.md`, `THREAT_MODEL.md`,
`DATA_MODEL.md`, `MIGRATION_STRATEGY.md`, `CURRENT_ARCHITECTURE_AUDIT.md`.

## 0. Naming correction (per instruction A.5 — reported, not silently changed)

**The BRD defines phases C0–C4, not C1–C5.** `executive-brd.md` §18 ("Phân kỳ triển
khai") is explicit: C0 Multi-tenant Foundation, C1 Clinic Operations MVP, C2 Chronic
Care Engine, C3 AI and Automation, C4 Ecosystem. There is no C5 anywhere in the BRD
set (`docs/brd/v1.0/`, `docs/brd/v2.0/*`, `docs/clinic-saas/*`). This plan uses the
BRD's own C0–C4 names throughout. "C1 đến C5" in the standing-approval instruction is
read as "C1 through the end of the phased roadmap (C4)."

A second, smaller naming note: the instruction says "M00–M18"; the BRD's module
numbering starts at **M01** (18 modules, M01–M18) — there is no M00.

## 1. M01–M18 → C0–C4 mapping (verbatim from BRD, not inferred)

| Module | Name | Phase | Priority | Status |
|---|---|---|---|---|
| M01 | Tenant & Clinic Management | C0 | P0 | **DONE** (merged, dormant) |
| M02 | Branch Management | C0 | P0 | **DONE** |
| M03 | Staff, Membership & RBAC | C0 | P0 | **DONE** |
| M04 | Subscription & Entitlement | C0 | P0 | **PARTIAL** — schema+routes exist; BRD_ANALYSIS Finding 5 (M02/M03 don't cross-check M04 caps) not yet closed |
| M05 | Services & Pricing | C1 | P0 | Not started |
| M06 | Patient Management | C1 | P0 | Not started |
| M07 | Appointment Management | C1 | P0 | Not started |
| M08 | Check-in & Queue | C1 | P0 | Not started |
| M09 | Encounter & Clinical Notes | C1 | P0 | Not started |
| M10 | Billing & Invoicing | C1 | P1 | Not started |
| M11 | Care Plan | C2 | P0 | Not started |
| M12 | Care Gap Queue | C2 | P0 | Not started |
| M13 | CRM / Patient Outreach | C2 | P1 | Not started |
| M14 | Clinical Copilot (AI) | C3 | P1 | Not started (existing *non-tenant* Copilot code predates this program — see §6) |
| M15 | Notifications & Reminders | C1–C2 (MVP: C1, Push+Email only) | P0 | Not started |
| M16 | Dashboard & Reports | C1–C2 (operational: C1, retention/clinical: C2) | P1 | Not started |
| M17 | Consent & Privacy | C0 | P0 | **PARTIAL** — `Consent` model exists (pre-Clinic-SaaS, `governance.py`), not yet wired to `ClinicMembership`/clinic-scoped gating |
| M18 | Audit Log | C0 | P0 | **DONE** — `audit_logs.clinic_id` shipped in C0 migration #9 |

"DONE" = merged to main per the C0 PR (#96) and the C0 status memory. "PARTIAL" flags
where the C0 code audit (below) found gaps against the BRD, not new scope — these are
picked up as fix-forward work inside the first C1 milestone that touches them, not a
separate phase.

## 2. C0 code-reality check (confirmed against `main` @ `af87f1e`, not assumed)

- `feature_flags.py`: `CLINIC_SAAS = False` (fail-closed), confirmed.
- Alembic head: `c0_m9_audit_log_clinic_id`, single head, confirmed.
- Shipped: `app/models/clinic.py`, routes `clinics.py`, `clinic_branches.py`,
  `clinic_members.py`, `clinic_services.py`, `clinic_subscriptions.py`, services
  `clinic.py`, `clinic_branch.py`, `clinic_membership.py`, `clinic_service_catalog.py`,
  `clinic_subscription.py`, deps `deps_clinic_saas.py`.
- Not yet wired: `clinic_patient_relationships` table exists per `DATA_MODEL.md` design
  (migration #6, `c0_m6_clinic_patient_rel`) but no patient-facing consumer yet — that's
  M06's job (C1).
- `DoctorClinic` (legacy) is untouched and still backs `assert_doctor_assigned` for the
  Encounter/CarePlan/AI-review path, per the explicit no-cutover decision in
  `TENANT_ARCHITECTURE.md` §2.3. **Stop Gate #4 applies to touching this.**

## 3. Dependency graph

```
C0 (DONE, dormant)
 ├─ M01 Tenant ─┬─ M02 Branch ─┬─ M03 RBAC/Membership ─┬─ M04 Entitlement
 │              │              │                        │
 │              └──────────────┴────────────────────────┴─→ C1 begins
 │
C1
 M05 Services ──┬─→ M07 Appointment (price snapshot) ──┬─→ M08 Queue ──→ M09 Encounter ──┬─→ M10 Billing (price+encounter)
 M06 Patient ───┘                                       │                                 │
                                                         └─→ M15 Notifications (reminders) │
                                                                                            └─→ M16 Dashboard (C1 slice: ops+revenue)
C2
 M09 (Plan section) ──→ M11 Care Plan ──→ M12 Care Gap Queue ──→ M13 CRM ──→ M16 Dashboard (C2 slice: retention+clinical)
                          ↑                    ↑
                       M05 (package/"chương    M07 (no-show), M09 (lab-order tracking)
                       trình bệnh" — Finding 3)

C3
 M09 (AI-origin marking) + M17 (consent C3) + M04 (quota) ──→ M14 Clinical Copilot extended (ships flag-OFF)

C4 (Ecosystem — scope doc only, Stop-Gate blocked per module, see §8)
 Lab integration, Pharmacy, Payment, E-invoice, Teleconsultation, Corporate health, API partners
```

## 4. Phase scope (BRD-verbatim, §18)

- **C1 — Clinic Operations MVP**: Staff, Doctors, Patients, Services, Appointments,
  Check-in, Queue, Consultation, Clinical notes, Billing cơ bản, Dashboard.
- **C2 — Chronic Care Engine**: Care Plan, Care Gap Queue, CRM chăm sóc, Nhắc tái khám,
  Nhắc xét nghiệm, Retention dashboard, Clinical outcome dashboard.
- **C3 — AI and Automation**: Clinical Copilot mở rộng, SOAP draft, Post-consultation
  summary, Suggested outreach, AI-generated patient education, AI usage analytics.
  Ships with `FeatureFlag.CLINICAL_COPILOT` OFF; production enablement is Stop Gate #1
  territory regardless of code-merge state (M14's own BR-M14-01 makes the entire safety
  table a go-live blocker independent of this program's phase gating).
- **C4 — Ecosystem**: Lab integration, Pharmacy, Payment, E-invoice, Teleconsultation,
  Corporate health, API partners. **Not detailed at BR-Mxx level anywhere in the BRD
  v2.0 module set** (`REQUIREMENTS_TRACEABILITY.md` and `appendix-c-traceability.md`
  both stop at C3) — C4 is bullet-point scope only in `executive-brd.md` §18/§16. Per
  Stop Gate #5 (real payment/billing) and #6 (legal/insurance/e-prescription/third-party
  medical integrations), essentially every C4 item requires a PTH decision before any
  engineering work — this program treats C4 as **scope documentation only**, not an
  autonomous build target.

## 5. PR breakdown (one PR per milestone, per instruction B — no phase bundling)

| # | Branch | Milestone | Depends on |
|---|---|---|---|
| 1 | `clinic-saas/c1-m05-services-pricing` | M05 | C0 |
| 2 | `clinic-saas/c1-m06-patient-management` | M06 | M05 |
| 3 | `clinic-saas/c1-m07-appointments` | M07 | M05, M06 |
| 4 | `clinic-saas/c1-m08-checkin-queue` | M08 | M07 |
| 5 | `clinic-saas/c1-m09-encounter-notes` | M09 | M08 |
| 6 | `clinic-saas/c1-m10-billing` | M10 | M05, M09 |
| 7 | `clinic-saas/c1-m15-notifications` | M15 (Push+Email only) | M07 |
| 8 | `clinic-saas/c1-m16-dashboard-ops` | M16 (C1 slice) | M07, M08, M10 |
| 9 | `clinic-saas/c2-m11-care-plan` | M11 | M09 |
| 10 | `clinic-saas/c2-m12-care-gap-queue` | M12 | M11 |
| 11 | `clinic-saas/c2-m13-crm-outreach` | M13 | M12 |
| 12 | `clinic-saas/c2-m16-dashboard-retention` | M16 (C2 slice) | M11, M12, M13 |
| 13 | `clinic-saas/c3-m14-copilot-clinic-scope` | M14 (flag stays OFF) | M09 |

Each PR: full pipeline per instruction B.1–B.19 (audit → plan/traceability → branch →
implement → tests → Codex → PR → merge → verify → handoff → close). No two milestones
share a PR, so each is independently revertable.

## 6. Migration roadmap

Continuing the `c0_mN_...` / now `c1_mN_...` etc. naming convention
(`MIGRATION_STRATEGY.md` §1), chaining linearly off `c0_m9_audit_log_clinic_id`
(current single head). Every migration: additive-only by default (new nullable/defaulted
columns, new tables), `upgrade()`+`downgrade()` required, revision id ≤32 chars (PR #93
incident precedent), verified upgrade→downgrade→upgrade on Postgres before merge per
instruction B.10.

Anticipated per-milestone migrations (exact shape decided at each milestone's own audit
step, not pre-committed here):
- M05: `clinic_services` already exists from C0 (migration #5) — likely no new table,
  possibly a `price_history`-adjacent audit-only change (no schema) per `DATA_MODEL.md`
  §5's existing no-history-table call.
- M06: new `patients`-adjacent tables scoped by `clinic_patient_relationships` (already
  exists from C0 migration #6) — likely a dedup/import-batch tracking table.
- M07: new `appointments`-analog table scoped by clinic (the existing legacy
  `Appointment`/`BookingAppointment` tables are explicitly **not** touched —
  `CURRENT_ARCHITECTURE_AUDIT.md` §5 flags them as a "real risk of confusion"; a new
  clinic-scoped table avoids a 3-way naming collision, exact naming decided at M07's
  audit step).
- M08–M13: new tables per module, all clinic-scoped via `clinic_id` FK, no ALTER of
  pre-existing non-Clinic-SaaS tables expected.
- M14: no new tables expected — this milestone is primarily an authorization-chain fix
  (`clinical_copilot.py`'s `_authorize`) per THREAT_MODEL.md §10, not new schema.

**Destructive migrations, data backfills with risk, or touching `DoctorClinic`/legacy
`Appointment` tables are Stop Gate #3/#4 — flagged at the relevant milestone's audit
step, not pre-approved here.**

## 7. Security and tenant-isolation test matrix (mandatory per milestone, per instruction E)

Every milestone's regression suite must include, at minimum:

1. **Cross-tenant BOLA**: resource created at Clinic A, requested by an authenticated
   user with only Clinic B (or no) active membership → 403/404, never the record.
2. **`clinic_id`/`branch_id` client-trust rejection**: any endpoint accepting a
   `clinic_id`/`branch_id` in body/query must reject values outside the caller's active
   `TenantContext.branch_ids`/clinic membership, even if otherwise well-formed.
3. **Membership lifecycle**: suspended/revoked/expired membership loses access
   immediately (≤60s per BR-M03-03) on the resource type this milestone introduces.
4. **RBAC negative matrix**: every role in `RBAC_MATRIX.md` §3's row for this module
   gets both a positive and a 403 negative test.
5. **Response-schema field filtering** (not just route-level 403) for roles with `L`/`✗`
   cells — e.g. Receptionist must never see clinical fields even via a shared list
   endpoint.
6. **Audit completeness**: every state-changing action in this milestone appears in
   `audit_logs` with `clinic_id` populated, actor, before/after where applicable, zero
   PHI in `resource_id`/details.
7. **PHI-pattern scan**: any new external-facing content (notification templates, etc.)
   scanned for diagnosis/lab/medication leakage per BR-M01-05/BR-M15-01.

Milestone-specific additions layered on top of this base matrix (e.g. M09 adds the
finalized-note-immutability test, M12 adds idempotent-rerun-no-duplicate).

## 8. Staging rollout sequence

`CLINIC_SAAS` stays `False` (global default) through the entire C1–C3 program per
instruction E. Each merged PR:
1. Deploys to staging automatically via the existing `CI + Staging Auto-Deploy`
   workflow (Alembic migration → ACA backend/frontend deploy → health checks → smoke).
2. Is verified via **unauthenticated** health/smoke checks only (the module is
   flag-gated OFF, so authenticated end-to-end verification of the new surface itself
   isn't possible until a later, explicitly-approved flag-on step — consistent with how
   C0 was verified, per `project_doctor_portal_p0.md`'s memory precedent of
   health/API-check-only verification when full authenticated smoke isn't available).
3. Main CI (Backend Tests, Frontend Tests, Meto AI Deployment Gate, staging deploy) must
   be green before the phase is marked closed, matching the C0 precedent set by PR #97's
   verification.

No tenant, no real Clinic SaaS data, no flag flip happens in this rollout sequence —
enabling `CLINIC_SAAS` for even one pilot clinic is Stop Gate #1/#2 and requires a
separate PTH decision after C1 (or later) is functionally complete.

## 9. Stop Gates expected during this program (from the standing-approval list, mapped to where they'll likely trigger)

| Stop Gate | Where it's likely to trigger in C1–C4 |
|---|---|
| #1 Enable CLINIC_SAAS in production | Not attempted this program — explicit future decision |
| #2 Real tenant / real patient data | Not attempted — all seed data synthetic, local/staging only |
| #3 Destructive migration / risky backfill | Possible at the `DoctorClinic`→`ClinicMembership` backfill mentioned in `TENANT_ARCHITECTURE.md` §2.3 as "a phase-2 migration decision" — **not scheduled in this plan**; if a milestone's audit step finds it necessary, that milestone stops for approval instead of proceeding |
| #4 DoctorClinic/legacy merge or replace | Same trigger as #3 — this program's default is to leave `DoctorClinic` untouched throughout C1–C3, per the architecture docs' own explicit no-cutover decision |
| #5 Billing/payment real money | C4 Ecosystem (Payment, E-invoice) — **entire C4 blocked by default**; M10 (C1 Billing) is invoice bookkeeping only, no real payment rail, no Stop Gate trigger expected there |
| #6 Legal/insurance/e-prescription/3rd-party medical data | C4 Ecosystem (Lab integration, Pharmacy, Corporate health, API partners) — blocked by default |
| #7 RBAC/PHI model change beyond BRD | Not expected — `RBAC_MATRIX.md`/`TENANT_ARCHITECTURE.md` already resolved the two open BRD RBAC questions (Decision 1, Decision 2); any *new* deviation found mid-implementation stops for approval |
| #8 Codex P0/P1 unresolved | Per-milestone gate — no PR merges with open P0/P1, no exception |
| #9 Tenant isolation / BOLA unproven by test | Per-milestone gate — §7's test matrix is mandatory before Codex review, not optional |
| #10 BRD conflict/missing decision changing scope | **Already found** by `BRD_ANALYSIS.md`'s 14 cross-cutting findings — resolved as engineering ADRs at the relevant milestone (documented, not silently guessed) for findings 2,3,4,5,6,7,8,12; findings 9 (legal/PDPA, audit retention) explicitly **not** resolved by engineering — carried forward unchanged as a pre-existing open item, non-blocking for C1–C3 code merge (BOD's own §25 already treats it as a separate go-live gate, not a phase gate) |
| #11 Infra/vendor cost overrun | Not expected — C1–C3 adds no new vendor/infra dependency (reuses existing Azure/Postgres/GHCR pipeline) |
| #12 Unsafe-to-rollback production op | Every migration in §6 is additive per the C0 precedent; a milestone whose audit step finds a non-additive requirement stops for approval instead of proceeding |

## 10. Program completion criteria

This program (C1–C3, C4 excluded as scope-only) is complete when:

1. All 13 PRs in §5 are merged to `main`, each independently.
2. Every milestone's Codex review verdict is PASS with 0 open P0/P1 (instruction E).
3. Every milestone's §7 security/tenant-isolation test matrix passes.
4. `CLINIC_SAAS` remains `False` throughout — completion of C1–C3 is a code-readiness
   state, not a go-live event (mirrors the C0 precedent exactly: MERGED + DORMANT).
5. Program-level BRD acceptance criteria (`executive-brd.md` §22, AC #1–#14) are all
   satisfiable by the merged code — verified once at the end of C2 (per
   `appendix-c-traceability.md`'s own note that AC #8/#9 require C2, not just C1).
6. Every phase handoff (per instruction F) is recorded in
   `project_clinic_saas_phase_c0.md`'s successor memory files, one per milestone.
7. C4 remains a scope document only (`docs/clinic-saas/C4_ECOSYSTEM_SCOPE.md`, not yet
   written) — no C4 code is written under this program's standing approval; each C4
   item requires its own future PTH approval given Stop Gates #5/#6 apply almost
   universally there.
8. Legal/compliance open items (BR-M17-05 VN PDPA review, BR-M18-04 retention period)
   remain explicitly flagged as unresolved in every phase handoff — this program does
   not and cannot close them.

---

*Self-check: this plan's phase/module mapping matches `00-overview.md`'s table exactly
(§1 above is a direct transcription, not a re-derivation), its PR list matches the
dependency graph in §3, and no milestone in §5 is scheduled to touch a Stop-Gate item
without flagging it first (§9). No contradiction with the BRD found. Proceeding to C1
M05 per instruction G.*
