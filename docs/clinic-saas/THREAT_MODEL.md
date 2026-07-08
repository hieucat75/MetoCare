# MetoCare Clinic SaaS — Threat Model

Companion to `TENANT_ARCHITECTURE.md` and `RBAC_MATRIX.md`. Ten threat
categories, each with a MetoCare-specific attack scenario and a concrete
mitigation tied to the entity/flow design in the other two documents. Closes
with an explicit list of product/legal/architecture decisions this design
cannot make on its own.

---

## 1. BOLA / IDOR (Broken Object-Level Authorization)

**Scenario:** A receptionist at Clinic A is authenticated and calls
`GET /patients/{patient_id}` for a `patient_id` they copy from a URL/API
response belonging to a patient actually registered only at Clinic B (e.g.
guessed sequential-looking UUID, or leaked via a shared support ticket).
Today, nothing in `patient.py`/`PatientProfile` carries a clinic column at
all (`CURRENT_ARCHITECTURE_AUDIT.md` §2), so a naive "does this patient_id
exist" check would succeed regardless of clinic.

**Mitigation:** Every patient-resource lookup joins through
`ClinicPatientRelationship` (`TENANT_ARCHITECTURE.md` §2.7) filtered by
`TenantContext.clinic_id`, not just `patient_profiles.id`. A query for a
patient with no `ClinicPatientRelationship` row at the caller's clinic
returns 404 (indistinguishable from "does not exist" — see the BOLA/leak
tradeoff note in §2 below), never the record. This generalizes the working
`assert_doctor_assigned` pattern (`rbac.py:63-105`, which already does
exactly this join-and-compare for the legacy Encounter path) to every new
Clinic SaaS resource type. Every denial is audited
(`audit.record(..., outcome="denied")`, same convention as
`consultation_access.py:171-184`).

---

## 2. Cross-clinic data leak (BR-M06-02 / Decision 2)

**Scenario:** A patient is treated at Clinic A (diabetes program) and later
registers at Clinic B (an unrelated dermatology clinic) for a skin
consultation. Clinic B's receptionist, doing normal patient search-by-phone,
pulls up the patient's profile and the response includes Clinic A's
diagnosis/lab history because the query only filtered by `patient_id`, not by
which clinic created which record.

**Mitigation:** Per Decision 2 (v2.0 BR-M06-02 is authoritative, no
"active consultation" carve-out), every clinical query is scoped by *record
provenance*: a record is visible to clinic B only if `record.clinic_id ==
clinic_B` OR an active `Consent` row (`governance.py:20-51`) has
`granted_to == clinic_B.id` and a matching `data_scope`. This must be
enforced at the query layer (a WHERE clause / repository filter), not only
at the API-response-serialization layer, so that aggregation queries
(dashboards, exports) cannot accidentally pull cross-clinic rows into a
count or CSV before the filter is applied. Test requirement: seed one
patient with `ClinicPatientRelationship` rows at both A and B and clinical
records only at A; assert B's every read surface (detail view, list,
export, dashboard aggregate) returns zero A-created clinical fields absent
an explicit `Consent` grant.

---

## 3. Privilege escalation

**Scenario:** A Receptionist (platform role `clinic_admin`'s login is not
even required here — any authenticated staff account) crafts a request to
`PATCH /memberships/{their_own_membership_id}` attempting to add `"doctor"`
or `"admin"` to their own `roles` array, or a Nurse calls the note-finalize
endpoint directly with a forged `role` claim.

**Mitigation:** Two independent layers, deliberately redundant: (a) the JWT's
`role` claim (platform axis, `deps.py:65-89`) is signed and never trusted
from any other source; (b) `ClinicMembership.roles` mutation is itself a
privileged action — only Owner/Admin at the *same clinic* may write another
user's `roles`, and **no membership-update endpoint ever allows a user to
modify their own `roles` or `status`** (self-escalation is structurally
impossible, not just role-checked). BR-M03-04's "cannot demote/lock the last
Owner" guard sits in the same service-layer check. Every role/membership
change is audited with before/after values (M03 §3.9).

---

## 4. Membership tampering

**Scenario:** An attacker with a stolen but still-valid API session for a
Nurse account attempts to directly manipulate `ClinicMembership.status` from
`suspended` back to `active` via a replay of an old accept-invite request, or
attempts to extend `left_at`/resurrect a `removed` membership by resubmitting
a stale invitation-acceptance payload.

**Mitigation:** `ClinicMembership` status transitions are a closed state
machine (`invited → active → suspended/removed`, no direct client-writable
`status` field — transitions only occur via specific service operations:
`accept_invitation`, `suspend_membership`, `restore_membership`,
`remove_membership`), each independently role-gated (Owner/Admin only for
suspend/restore/remove) and audited. `ClinicInvitation.token_hash` is
single-use (`status` flips to `accepted` atomically with the membership
creation, in one transaction) so a replayed acceptance request fails on the
second attempt (token already consumed). Suspension must additionally
trigger session/token revocation within the BR-M03-03 60-second SLA — this
is a real, currently-partially-solved problem in a stateless-JWT
architecture (see item 3 in §"Open product/legal/architecture decisions"
below, since MetoCare's existing JWT approach has no visible token-revocation
list keyed by membership).

---

## 5. Invitation hijacking

**Scenario:** An invitation email/SMS to `newdoctor@clinic.com` is
intercepted (shared inbox, SMS SIM-swap, or forwarded internal email) and the
attacker completes account creation as that invited staff member, gaining a
`doctor` or `admin` membership at the clinic.

**Mitigation:** `ClinicInvitation.token_hash` (`TENANT_ARCHITECTURE.md`
§2.4) is a high-entropy random token whose hash is stored (never the raw
token, mirroring `users.password_hash`'s existing hash-not-plaintext
discipline) — the raw token exists only in the delivered email/SMS.
`expires_at` bounds the attack window to 7 days (M03 §3.4). Acceptance
requires the token to match exactly; there is no email/phone-based
"reasonable match" auto-acceptance (M03 §3.7 explicitly forbids this even
for legitimate mismatches, a fortiori for attacker-controlled ones).
Acceptance is itself audited with the accepting `user_id`, so an
Owner/Admin reviewing new-staff activity can catch an unexpected acceptance
identity. Residual risk: if the delivery channel itself (email inbox, SMS)
is compromised before send, no application-layer control fully closes this —
flagged as inherent to any invitation-by-channel design, mitigated only by
keeping the token window short and requiring visible confirmation to the
inviting Owner/Admin (out of scope to mandate a specific UX here).

---

## 6. Inactive/suspended clinic access

**Scenario:** Clinic X falls behind on subscription payment and is moved to
`Suspended` (BR-M01-02). A Receptionist there, mid-session with a still-valid
JWT, attempts to create a new appointment or finalize an invoice, expecting
normal operation to continue since their personal session token hasn't
expired.

**Mitigation:** `Clinic.status` (`TENANT_ARCHITECTURE.md` §2.1) is checked
inside `TenantContext` resolution on **every** request, not cached
per-session — a write request against a `suspended`/`expired` clinic is
rejected (403, distinct error surfaced to the UI) regardless of how fresh
the caller's token is, per BR-M01-02. Reads continue to succeed (data is
never hidden, only new writes blocked) so in-progress patient care
information remains visible. `Deactivated` is stricter: BR-M01-03 makes it
terminal, blocking all further access including reads, until an explicitly
platform-approved restore (§5 of `TENANT_ARCHITECTURE.md`) flips it back —
this restore path is itself gated to Super/Internal Admin and audited.

---

## 7. Branch-switch manipulation

**Scenario:** A Nurse whose membership is scoped to Branch 1 only sends a
request with `branch_id=<Branch 2's id>` in the request body/query hoping the
backend trusts the client-supplied value (e.g. to view Branch 2's queue or
book an appointment there where they have no assignment).

**Mitigation:** Identical pattern to clinic-id validation
(`TENANT_ARCHITECTURE.md` §4): `branch_id` from the client is only ever used
to **select** among `TenantContext.branch_ids` (the membership's actual
assigned branches) — a value outside that set is a 403, never silently
reinterpreted or defaulted. This is the literal text of BR-M02-01. Test
requirement mirrors AC-M02-02 exactly: call any branch-scoped endpoint with
a `branch_id` outside the caller's membership → 403.

---

## 8. Mass export

**Scenario:** An Accountant (whose role legitimately has `L (financial only)`
export access per the RBAC matrix) crafts a request to the patient-list or
clinical-dashboard export endpoint with a wide/unbounded filter, attempting
to exfiltrate a full-tenant PHI dump under the guise of a "financial" export,
or a compromised Receptionist account calls `GET /patients` repeatedly with
incrementing pagination to reconstruct the full tenant patient list despite
BR-M06-06's pagination requirement.

**Mitigation:** Two independent controls: (a) BR-M06-06's mandatory
pagination with an enforced max page size (no endpoint may return the full
dataset regardless of role — this is a resource-shape rule, not just an
RBAC rule); (b) BR-M16-02's export-specific gate — every export call is
role-checked against the *specific* export type (financial vs. clinical vs.
operational), and every successful export is audited with the filter
parameters and row count (`audit.record(action="data_export", ...,
clinic_id=..., resource_type=..., severity="warning")`), enabling after-the-
fact anomaly detection (e.g. an Accountant's export row-count spiking to
"entire tenant" is a detectable pattern even if the individual request
passed authorization). Rate-limiting repeated paginated calls (Appendix B's
general rate-limit NFR) further bounds the reconstruct-via-pagination attack,
though Appendix B leaves the actual threshold unspecified (flagged in
`BRD_ANALYSIS.md` Finding 11 — not this design's to invent a number).

---

## 9. PHI leakage (logs, audit, error responses)

**Scenario:** A stack trace from a failed clinic-scoped query, or a verbose
error message on an entitlement/validation failure, includes a patient's
name, diagnosis, or lab value in the response body or application log —
either directly (an exception message interpolates a PHI field) or
indirectly (the audit log itself, meant to be PHI-free, ends up storing a
`resource_id` that is actually a raw content string instead of a reference
ID).

**Mitigation:** This design keeps `AuditLog` (`governance.py:54-70`) exactly
as PHI-free as it is today — the only schema change is the additive
`clinic_id` column (`TENANT_ARCHITECTURE.md` §2.10), which is a tenant
identifier, not PHI. Every new `audit.record()` call site for Clinic SaaS
must pass reference IDs (`patient_id`, `clinic_id`, `invoice_id`) in
`resource_id`, never note/lab/diagnosis content — same discipline already
followed by `consultation_access.py` and documented explicitly for
`DoctorReviewDecision` (`care.py:276-284`: "deliberately kept OUT of
AuditLog because AuditLog must never contain PHI"). Controlled error
responses (Appendix B P0 gate) means new Clinic SaaS exception handlers
return generic messages ("access denied", "not found") to the client and log
detail server-side only through the existing structured logger, which must
be reviewed to confirm it does not interpolate raw model field values (this
review is an implementation-phase task, not resolved by this design doc —
flagged below).

---

## 10. AI context leakage (Clinical Copilot)

**Correction (Claude Code, verified against source 2026-07-08):** the
original draft of this finding cited `backend/app/ai/context/builder.py` as
the leaking module. That file is a **different, unrelated** component — the
**patient-facing** Meto self-service assistant, whose `ContextBuilder.build()`
takes `user_id` and only ever reads the calling patient's own rows (docstring:
"Context isolation: all queries parameterized with user_id",
`context/builder.py:9`). There is no cross-user/cross-clinic exposure there
because it never reads anyone's data but the caller's own. The doctor-facing
Clinical Copilot does **not** import or call this class at all — confirmed via
grep: `services/clinical_copilot.py` has its own separate, `patient_id`-keyed
query functions (`_load_profile`, `_medication_records`, `_lab_rows`,
`_metric_rows`, `clinical_copilot.py:199-310`, one docstring explicitly says
"Mirrors `ContextBuilder._build_health_summary` but keyed by..." — i.e. a
parallel reimplementation, not a shared call path).

**Scenario (corrected):** A doctor holds active memberships at both Clinic A
and Clinic B. While in a Clinic B session (`TenantContext.clinic_id = B`),
they call `POST /doctor/patients/{patient_id}/ai-summary` for a Clinic B
patient. The route's `_authorize` gate
(`api/v1/routes/clinical_copilot.py:55-99`) does exactly one of two checks:
(a) if `consultation_id` is supplied, `assert_doctor_can_view` (consultation
ownership — clinic-agnostic by design, consultations are marketplace
bookings), or (b) otherwise `doctor_portal._require_timeline_access` →
`patients._check_read_access` → `_check_write_access`, which (confirmed by
reading `patients.py:136-166`) is a **pure consent check**: "DOCTOR —
consent-gated (active consent with `scope='profile'` required)" — no
`DoctorClinic`/clinic-membership check anywhere in this path. `governance.Consent.granted_to`
is a bare string id with no FK (`governance.py:27`), so a patient's consent
grant to "this doctor" carries no clinic dimension either. Once
`ClinicPatientRelationship` exists, a doctor holding *any* valid consent grant
for a patient — regardless of which clinic that consent was intended for —
can still pull a Clinical Copilot AI summary synthesizing that patient's full
clinical picture. The leak is real; it just lives in
`clinical_copilot.py`/`doctor_portal.py`/`patients.py`'s authorization chain,
not in `ai/context/builder.py`.

**Mitigation:** This is the **highest-severity finding in this threat
model**, both because the Clinical Copilot's entire purpose is to surface
condensed clinical detail to a doctor in seconds (i.e. it is
purpose-built to concentrate exactly the data that must not cross a tenant
boundary) and because the existing code has zero clinic-awareness to build
on (unlike, say, the Encounter path which already has
`assert_doctor_assigned`). Required design change before Clinical Copilot
(M14, already gated OFF by `FeatureFlag.CLINICAL_COPILOT`,
`feature_flags.py:34,56`) can be considered safe for Clinic SaaS use:

1. `clinical_copilot.py`'s `_authorize` helper (`api/v1/routes/clinical_copilot.py:55-99`)
   must additionally call the generalized clinic-scope check
   (`TENANT_ARCHITECTURE.md` §4's resource-validation pattern) confirming
   the target `patient_id` has a `ClinicPatientRelationship` at
   `TenantContext.clinic_id`, *before* falling through to either the
   consultation-scoped or timeline-consent branch.
2. `services/clinical_copilot.py`'s own query functions (`_load_profile`,
   `_medication_records`, `_lab_rows`, `_metric_rows`, all `patient_id`-keyed,
   `clinical_copilot.py:199-310`) must be re-scoped: each fetch needs an
   additional filter to only include records attributable to the resolving
   `clinic_id` (own-created) or covered by an active cross-clinic `Consent`
   grant — i.e. the exact same BR-M06-02/Decision 2 rule from Threat #2,
   applied to AI context assembly specifically, since an LLM prompt is a
   uniquely effective exfiltration vector (a single generated summary can
   surface an entire cross-clinic history in one readable paragraph, worse
   than a raw record leak because it's pre-synthesized and easy to act on).
   `ai/context/builder.py` (the separate patient-facing Meto assistant) needs
   no change for this threat — it is single-user by construction.
3. Until (1)+(2) are implemented, Clinical Copilot must remain
   flag-disabled for any multi-clinic-patient scenario — this is
   effectively already true today since the flag defaults OFF platform-wide,
   but the design here makes explicit that flipping it on for Clinic SaaS
   without these changes would reopen this exact leak.

---

## Open product/legal/architecture decisions (for PTH — not inferable from BRD or code)

These cannot be resolved by this design and must not be silently guessed:

1. **BR-M06-02 "consultation carve-out" removal (Decision 2, restated for
   visibility).** This design implements the stricter v2.0-only reading (no
   implicit cross-clinic access during an active consultation). This is a
   *product* decision with real clinical-safety tradeoffs — e.g. an ER-style
   walk-in at Clinic B who was recently treated at Clinic A for a related
   condition will have **zero** visibility into Clinic A's data unless the
   patient has already granted M17 consent to Clinic B, even if the
   attending doctor believes it's clinically necessary in the moment. A
   future "break-glass" feature (explicit, reason-required, heavily audited,
   probably time-boxed like `ConsultationAccessGrant`) could reintroduce a
   narrower version of the old carve-out, but that is new scope this design
   does not build — flagging for explicit accept/reject by product+clinical
   leadership before go-live, not just an engineering choice.
2. **BOLA response shape: 403 vs 404 for out-of-scope resources.** This
   design defaults to indistinguishable-from-404 responses for
   cross-clinic lookups (to avoid confirming a patient/resource's existence
   to an unauthorized caller) but BR-M01-01/AC-M01-02 explicitly say "403/404"
   without picking one — worth a deliberate security-vs-UX call (a
   receptionist fat-fingering a patient code benefits from a clear
   404/"not found" vs. a security-conscious 403 that reveals less).
3. **Session/token revocation mechanism for BR-M03-03's ≤60s suspend SLA.**
   The existing auth stack (`backend/app/core/security.py` JWT
   issue/decode, `deps.py:65-89`) was not read in enough depth by this
   design to confirm whether a revocation-list/short-TTL-refresh mechanism
   already exists that would satisfy a 60-second membership-suspend SLA, or
   whether this needs new infrastructure (e.g. a per-membership
   `token_valid_after` timestamp checked on every request). This is a
   concrete engineering question for the implementation phase, not
   resolved here.
4. **Retention/legal-review items already flagged BRD-side remain
   unresolved and apply unchanged to the new clinic-scoped `AuditLog`
   rows**: BR-M17-05 (VN PDPA-equivalent compliance) and BR-M18-04 (audit
   retention period) are still open per `BRD_ANALYSIS.md` Cross-Cutting
   Finding 9 — this design does not add new exposure but does not resolve
   these either.
5. **Whether `ClinicMembership` and `DoctorClinic` permanently coexist or
   `DoctorClinic` is retired** (`TENANT_ARCHITECTURE.md` §2.3 migration
   note) is left as a phase-2 implementation decision, since forcing an
   immediate cutover risks destabilizing the one legacy flow
   (`assert_doctor_assigned`) that currently works correctly.
