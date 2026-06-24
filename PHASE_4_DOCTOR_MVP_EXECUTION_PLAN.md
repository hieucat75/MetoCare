# Phase 4 — Doctor MVP Execution Plan

**Status:** Pre-flight approved. Seed safety and production guard delivered (Tasks A+B). Implementation not yet started.

**Stop condition:** Do not ship any Doctor UI code until the Codex review of this plan passes.

---

## 1. What the Backend Already Has

The backend is substantially complete for doctor functionality. No greenfield API work is needed for the core read/review flows.

### Authentication
- `POST /auth/login` — email-based login for doctors (phone-based for patients)
- MFA mandatory for `DOCTOR` role: `POST /auth/login` returns a *partial token* that does not satisfy any dependency requiring the `DOCTOR` role. Only after `POST /auth/mfa/verify` completes does the backend issue a full DOCTOR-scoped token. Any doctor-role endpoint called with a partial (pre-MFA) token must return `403 Forbidden`. This enforcement must live in the auth dependency, not in the frontend redirect.
- No public doctor registration — `POST /auth/register` hardcodes `PATIENT`; doctor accounts require admin promotion via `PATCH /admin/users/{id}/role`

### Patient Data (all consent-gated)
| Endpoint | Access |
|---|---|
| `GET /patients/{id}/profile` | DOCTOR (consent scope: `profile`) |
| `GET /patients/{id}/metabolic-score/live` | DOCTOR (scope: `health_metric`) |
| `GET /patients/{id}/insights` | DOCTOR (scope: `health_metric`) |
| `GET /patients/{id}/summary` | DOCTOR only (pre-visit summary) |
| `GET /patients/{id}/summary.pdf` | DOCTOR only (PDF export) |
| `GET /patients/{id}/metrics` | DOCTOR (scope: `health_metric`) |
| `GET /patients/{id}/metrics/trend` | DOCTOR |
| `GET /patients/{id}/lab-results` | DOCTOR (scope: `lab`) |
| `GET /patients/{id}/lab-documents` | DOCTOR (scope: `lab`) |
| `GET /patients/{id}/medications` | DOCTOR |
| `GET /patients/{id}/medications/adherence-summary` | DOCTOR |
| `POST /patients/{id}/medications` | DOCTOR |
| `PATCH /patients/{id}/medications/{mid}` | DOCTOR |
| `GET /patients/{id}/symptoms` | DOCTOR |
| `GET /patients/{id}/triage-history` | DOCTOR |
| `GET /patients/{id}/health-summary` | DOCTOR |

### AI Review Workflow
| Endpoint | Access |
|---|---|
| `GET /review/queue` | DOCTOR (own queue via encounter/consent) |
| `POST /review/{rec_id}/review` | DOCTOR (accept/reject/request-info) |
| `GET /review/{rec_id}` | DOCTOR (assignment or consent check) |

### Booking
| Endpoint | Access |
|---|---|
| `POST /doctors/{id}/availability` | DOCTOR (own) |
| `GET /doctors/{id}/availability` | PATIENT, DOCTOR, ADMIN |
| `GET /doctors/me/appointments` | DOCTOR only |
| `PATCH /appointments/{id}` | DOCTOR (confirm/cancel/complete) |
| `GET /patients/{id}/appointments` | DOCTOR (own patients) |

### Care Plans
| Endpoint | Access |
|---|---|
| `POST /care_plans` | DOCTOR, ADMIN |
| `GET /care_plans/{id}` | DOCTOR (assigned), PATIENT (own), ADMIN |
| `GET /care_plans` | DOCTOR (scoped) |
| `PATCH /care_plans/{id}` | DOCTOR (assigned), ADMIN |
| `POST /care_plans/{id}/approve` | DOCTOR only (C2 invariant enforced) |

### Encounters
| Endpoint | Access |
|---|---|
| `POST /encounters` | DOCTOR, CLINIC_ADMIN, ADMIN |
| `GET /encounters/{id}` | DOCTOR (assigned), PATIENT (own), ADMIN |
| `GET /encounters` | DOCTOR (own), ADMIN |
| `PATCH /encounters/{id}` | DOCTOR (assigned), ADMIN |

---

## 2. Missing APIs (Must Build in Phase 4)

### P0 — Blocking MVP

**Doctor Profile**
- `GET /doctors/me` — own Doctor record (bio, specialty, clinic, avatar, license_no)
- `PATCH /doctors/me` — update bio, avatar_url, consultation_fee, specialty
- `GET /doctors/{doctor_id}` — public profile (patient discovery, before consent grant)

**Patient Discovery for Doctor**
- `GET /doctors/me/patients` — list patients with active encounters or care plans
  - Response: patient_id, full_name, risk_level, last_seen, pending_items count
  - Filters: `?risk=high`, `?has_pending_review=true`

**Doctor Dashboard Aggregate**
- `GET /doctors/me/dashboard`
  - Returns: appointments_today (count), pending_reviews (count), pending_approvals (count), recent_alerts (list of high-risk patient flags)

### P1 — Required Before Pilot

**Doctor Onboarding (Admin-Assisted)**
- `POST /admin/doctors` — SUPER_ADMIN-only (INTERNAL_ADMIN must be rejected with 403). Creates `User` (email, password hash, role=DOCTOR) + `Doctor` row (specialty, license_no, clinic_id). Must require a valid MFA-complete SUPER_ADMIN token.

**Patient Timeline**
- `GET /patients/{id}/timeline` — chronological activity: encounters, care plans, lab uploads, AI recommendations, booking history

### P2 — Nice-to-Have for Phase 4

- `GET /clinics/me` — clinic details (if doctor is clinic admin)
- `GET /clinics/{id}/patients` — patient roster for clinic
- Doctor-specific notification subscriptions (new lab upload, patient high-risk flag, new appointment)

---

## 3. RBAC Summary

| Role | Patient Data | AI Review | Care Plans | Booking | Admin |
|---|---|---|---|---|---|
| PATIENT | Own only | None | Own (read) | Own bookings | None |
| DOCTOR | Consent-gated | Own queue | Assigned (read+approve) | Own schedule | None |
| CLINIC_ADMIN | Consent-gated | None | Read only | None | Clinic-scoped |
| MEDICAL_REVIEWER | Read-only | Read-only | Read-only | None | None |
| INTERNAL_ADMIN | Full | None | Full | None | User mgmt |
| SUPER_ADMIN | Full | Full | Full | Full | Full |

Doctor access always requires either:
1. Active `Consent` row from patient (`consent_type`, `data_scope`, `granted_to=doctor_id`, not revoked, within time window)
2. OR direct assignment (encounter, care plan, review record points to this doctor)

---

## 4. Consent Flow (Patient to Doctor)

**Current state:** Fully implemented at API level. No patient UI to grant consent.

**Flow:**
```
Patient opens "Privacy & Sharing" screen
→ Searches for doctor by name/phone (needs GET /doctors/{id} public endpoint)
→ Selects data scope: profile / health_metric / lab / * (full)
→ Sets optional expiry date
→ POST /patients/{patient_id}/consents
   { consent_type: "doctor_access", data_scope: "*", granted_to: doctor_id, valid_until: ... }
→ Doctor can now read patient data within granted scope
```

**What needs to be built:**
1. Patient-side consent grant UI (Privacy & Sharing screen — Add Doctor)
2. Doctor public profile endpoint (for patient to search and find doctor)
3. Doctor-side view of which patients have granted consent
4. Backend: `POST /patients/{pid}/consents` must validate that `granted_to` (doctor_id) exists in the `doctors` table before insert. A non-existent doctor_id must return 400 or 404, never 201.

---

## 5. AI Review Workflow (End-to-End)

**Current state:** Backend complete. No doctor UI.

**Flow:**
```
1. AI generates clinical recommendation → AIClinicalRecommendation (status: PENDING_REVIEW)
2. Doctor calls GET /review/queue → sees pending recommendations
3. Doctor reads recommendation details: GET /review/{rec_id}
4. Doctor calls POST /review/{rec_id}/review
   { verdict: "accepted" | "rejected" | "request_info", notes: "..." }
5. Accepted recommendations become visible in patient's InsightCards
```

---

## 6. Screens (Phase 4 Doctor MVP)

### Screen D1 — Doctor Login
- Email + password field
- MFA TOTP entry (mandatory)
- "Set up MFA" flow for new accounts
- **API:** `POST /auth/login`, `POST /auth/mfa/enroll`, `POST /auth/mfa/verify`
- **AC:** Doctor can log in; redirected to dashboard

### Screen D2 — Doctor Dashboard
- Appointments today (count + list)
- Pending AI reviews (count badge)
- High-risk patient alerts (name, risk flag, last metric date)
- Recent patient activity
- **API:** `GET /doctors/me/dashboard` (NEW), `GET /doctors/me/appointments`
- **AC:** All counts accurate; alerts link to patient chart

### Screen D3 — Patient List
- Search by name / phone
- Filter by risk level (HIGH / MEDIUM / LOW)
- Sort by last activity / risk
- **API:** `GET /doctors/me/patients` (NEW)
- **AC:** Only patients with active consent or encounter assignment visible

### Screen D4 — Patient Chart
- Header: name, age, risk badge, last seen
- Tabs: Summary / Metrics / Labs / Medications / Care Plans / Timeline
- Summary tab: live metabolic score + AI insights
- **API:** `GET /patients/{id}/summary`, `/metrics`, `/lab-results`, `/medications`, `/insights`
- **AC:** All tabs load without 403; data matches patient app

### Screen D5 — AI Review Queue
- List pending recommendations with patient name, date, excerpt
- Tap to expand full recommendation
- Accept / Reject / Request Info buttons with optional notes
- **API:** `GET /review/queue`, `GET /review/{id}`, `POST /review/{id}/review`
- **AC:** Accepting a recommendation makes it visible in patient's InsightCards

### Screen D6 — Care Plan Editor
- Create / edit care plan (linked to encounter)
- Status lifecycle: DRAFT → PENDING_REVIEW → APPROVED → ACTIVE
- Approve button (transitions to ACTIVE)
- **API:** `POST /care_plans`, `PATCH /care_plans/{id}`, `POST /care_plans/{id}/approve`
- **AC:** C2 safety: AI-generated DRAFT cannot be auto-approved; doctor must explicitly approve via `POST /care_plans/{id}/approve`. `PATCH /care_plans/{id}` must reject any body that attempts to set `status: "APPROVED"` directly (return 422). The only valid path to APPROVED is the `/approve` endpoint.

### Screen D7 — Doctor Profile
- View/edit specialty, bio, consultation_fee, avatar
- License number (read-only)
- Clinic affiliation
- **API:** `GET /doctors/me`, `PATCH /doctors/me` (NEW)
- **AC:** Changes persist; avatar upload works

### Screen D8 — Patient Consent Grant (Patient Side)
- "Privacy & Sharing" — Add Doctor
- Search doctor by name
- Select data scope + optional expiry
- **API:** `GET /doctors/{id}` (NEW, public profile), `POST /patients/{pid}/consents`
- **AC:** After grant, doctor can access patient data within selected scope

---

## 7. Dependencies

### Backend (must complete before frontend)
1. `GET /doctors/me` + `PATCH /doctors/me` — doctor profile endpoints
2. `GET /doctors/{id}` — public profile (for patient consent grant flow)
3. `GET /doctors/me/patients` — patient list
4. `GET /doctors/me/dashboard` — dashboard aggregate
5. `POST /admin/doctors` — doctor account creation (admin-assisted onboarding)
6. `GET /patients/{id}/timeline` — patient activity timeline

### Frontend
- Next.js route group `/doctor/` separate from `/` (patient app)
- Doctor-specific layout (sidebar with different nav items)
- Shared components: PatientCard, MetricBadge, InsightCard (reuse from patient app)
- Auth guard: redirect to `/doctor/login` if role != DOCTOR

### Infrastructure
- No new infra needed; staging already handles doctor role
- MFA works for DOCTOR; test TOTP enrollment flow manually

---

## 8. Acceptance Criteria (Phase 4 CLOSED)

| # | Criterion |
|---|---|
| AC-1 | Doctor can log in via email + MFA on staging |
| AC-2 | Doctor dashboard loads with correct appointment count and pending review count |
| AC-3 | Doctor can see patient list (only consented patients) |
| AC-4 | Doctor can view a patient chart across all tabs with real data |
| AC-5 | Doctor can accept/reject an AI recommendation; patient InsightCards update |
| AC-6 | Doctor can create and approve a care plan (C2 invariant: no auto-approve) |
| AC-7 | Patient can grant doctor consent via Privacy & Sharing screen |
| AC-8 | After consent revocation, doctor gets 403 on patient data |
| AC-9 | Doctor profile editable; changes persist |
| AC-10 | All doctor routes return 403 for PATIENT tokens |
| AC-11 | `POST /patients/{pid}/consents` with a non-existent `granted_to` doctor_id returns 400 or 404, not 201 |
| AC-12 | `POST /admin/doctors` called by INTERNAL_ADMIN returns 403 |
| AC-13 | DOCTOR login without completed MFA returns 403 on any doctor-role endpoint; partial token must not grant access |
| AC-14 | `PATCH /care_plans/{id}` with `status: "APPROVED"` in body returns 422 |

---

## 9. Deployment Strategy

**Phase 4A — Backend only (no UI, no migration risk):**
- Add missing endpoints (doctor profile, patient list, dashboard)
- Add `POST /admin/doctors` for onboarding
- Deploy to staging; verify all AC-1–AC-10 at API level with curl/Postman

**Phase 4B — Doctor frontend:**
- Build screens D1–D8 in feature branch `feat/doctor-mvp`
- Use existing staging backend from Phase 4A
- Playwright E2E: login → dashboard → patient chart → review → care plan

**Phase 4C — Consent UI (patient side):**
- Add "Privacy & Sharing — Add Doctor" flow to patient app
- E2E: patient grants consent → doctor verifies access → patient revokes → doctor 403

**No new migrations required** (Doctor, DoctorClinic, Consent, Encounter, CarePlan tables all exist).

---

## 10. Codex Review Required

Before Phase 4A implementation starts, the following must be reviewed:

- [ ] Missing API specs (doctor profile, patient list, dashboard) — endpoint contracts, RBAC, response schemas
- [ ] `POST /admin/doctors` — security: only SUPER_ADMIN, MFA required, no public exposure
- [ ] Consent grant UI — patient must not be able to grant consent to a non-existent doctor_id (validate FK before insert)
- [ ] MFA enforcement — DOCTOR login without MFA must return 403 with clear error, not allow access
- [ ] Care plan C2 safety preserved in doctor UI — approve button must call `/approve` not `/status` patch

**Phase 4 implementation begins only after this checklist is signed off.**
