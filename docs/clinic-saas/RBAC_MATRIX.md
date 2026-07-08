# MetoCare Clinic SaaS — RBAC Matrix

Companion to `TENANT_ARCHITECTURE.md`. Source of truth for the matrix content
is `docs/brd/v2.0/appendix-a-rbac-matrix.md` per BR-M03-01 ("Ma trận RBAC chi
tiết ở Phụ lục A là nguồn chân lý"). Legend preserved from the BRD: **✓** full,
**R** read-only, **L** limited (scope noted), **✗** forbidden.

Both settled BRD-resolution decisions from the task brief are carried forward
here without re-litigation:

- **Decision 1**: Care Coordinator's "Hồ sơ lâm sàng (M06/M09)" row is **✗**
  (Appendix A wins over v1.0 §14's looser "Hạn chế"). Care Coordinator's only
  patient-data access is the narrower "Hồ sơ hành chính BN (M06)" row at
  **L (care context)**, i.e. the M13 CRM working-set, never note/lab/diagnosis
  content.
- **Decision 2**: cross-clinic patient data visibility is exactly BR-M06-02's
  two categories (own-created + consented) — no "active consultation"
  carve-out. This is orthogonal to the role matrix below (it governs *which
  patient* a clinic can see at all) but interacts with every "own scope" cell
  in this matrix: "own scope" always means *within the resolving clinic's
  `ClinicPatientRelationship` + consent boundary*, never "any patient
  MetoCare-wide."

---

## 1. Platform role vs. clinic role — two different axes

`UserRole` (`backend/app/models/user.py:16-23`: `patient`, `doctor`,
`clinic_admin`, `internal_admin`, `medical_reviewer`, `super_admin`,
`ai_service`) is the **platform** axis — it answers "what kind of account is
this," and gates coarse, tenant-agnostic things: which product surface a
token can even reach (`ADMIN_ROLES`/`CLINICAL_ROLES` frontend guards,
`CURRENT_ARCHITECTURE_AUDIT.md` §15), whether MFA is required
(`MFA_REQUIRED_ROLES`, `user.py:29-36`), and whether the platform-bypass
rules in `rbac.py:24-38` apply.

The **7 clinic roles** in this document (Owner, Admin, Doctor, Nurse,
Receptionist, Care Coordinator, Accountant) are a **tenant** axis — they
answer "what can this user do *at this specific clinic*," and live entirely
in `ClinicMembership.roles` (`TENANT_ARCHITECTURE.md` §2.3), resolved fresh
per request by `TenantContext` (`TENANT_ARCHITECTURE.md` §4).

**A platform role does not by itself grant any clinic access.** A user with
platform role `doctor` (`UserRole.DOCTOR`) has zero access to any clinic's
patients until an `active` `ClinicMembership` row exists for
`(user_id, clinic_id)` with `doctor` in `roles`. Conversely, `clinic_admin`
existing as a `UserRole` value (`user.py:19`) does not mean every user with
that platform role administers every clinic — today's `assert_clinic_scope`
bug (`rbac.py:108-124`, "we accept any clinic_admin role") is precisely the
mistake of collapsing these two axes into one, and is the reason it must be
replaced (`TENANT_ARCHITECTURE.md` §1).

Practically: `require_roles(UserRole.DOCTOR)` (`deps.py:96-108`) is a coarse
first gate ("is this even a doctor-type account"); `TenantContext` +
`ClinicMembership.roles` is the fine-grained gate that actually authorizes a
specific clinic action. Both must pass — neither substitutes for the other.

---

## 2. The five explicit resolution rules

1. **Two different axes, not a hierarchy.** Platform role selects product
   surface/MFA policy; clinic role (from `ClinicMembership`) selects
   permitted actions at one specific clinic. A `super_admin` platform role
   does not carry any of the 7 clinic roles — its cross-tenant power is the
   separate, always-audited override path (§5 of `TENANT_ARCHITECTURE.md`),
   not a clinic-role bypass.
2. **Multi-membership, multi-role.** One `user_id` may have multiple
   `ClinicMembership` rows (one per clinic) and, within one row, multiple
   roles (`roles` is an array — BR-M03-02/US-M03-02, e.g. Nurse +
   Care Coordinator at the same clinic). Every permission check resolves
   against the `ClinicMembership` row for the clinic in the *current*
   `TenantContext` only.
3. **Multi-clinic doctor, reusing `DoctorClinic`/`ClinicMembership`.** A
   doctor's schedule, patient list, and clinical-note access are computed
   per membership row; there is no query that returns "this doctor's
   patients" without a `clinic_id` filter — this is the same invariant
   `assert_doctor_assigned` already enforces for the legacy path
   (`rbac.py:63-105`), generalized to every doctor-facing endpoint.
4. **Zero implicit crossover.** Holding an `active` membership at clinic A
   grants exactly zero rows of access at clinic B. There is no code path
   where a clinic-role check at clinic A is reused to authorize an action
   at clinic B — each request's `TenantContext.clinic_id` is resolved once
   and every downstream check is scoped to it (`TENANT_ARCHITECTURE.md` §4).
5. **Clinic Admin does not get blanket clinical content.** Per Appendix A,
   Admin's "Hồ sơ lâm sàng (M06/M09)" cell is **L (theo quyền)** — limited,
   per explicit grant — not **✓**. Modeled the same way as
   `ConsultationAccessGrant` (`consultation.py:217-252`): an Admin needing to
   view a specific clinical record (e.g. for a billing dispute or complaint
   investigation) requires an explicit, reason-carrying, audited grant/action
   — never a standing "Admin sees all clinical data" bypass. This mirrors
   Agent B's explicit recommendation to model clinic access the same way as
   the Consultation grant pattern, not as a role-bypass
   (`REUSE_AND_GAP_MATRIX.md` row "Consultation/marketplace scoping").

Additional rule required by the task brief (folded in here since it governs
every row): **`clinic_id` is never trusted from the request body/query alone.**
Every cell in this matrix is enforced against `TenantContext.clinic_id`
(server-resolved from the caller's active membership), never against a
client-supplied `clinic_id`/`branch_id` that hasn't been validated to be a
member of the caller's active set (`TENANT_ARCHITECTURE.md` §4). A request
naming a clinic the caller has no active membership in is a 403, full stop,
regardless of what role the caller holds anywhere else.

---

## 3. Full role × resource matrix

| Resource / Action (BRD module) | Owner | Admin | Doctor | Nurse | Reception | Care Coordinator | Accountant |
|---|---|---|---|---|---|---|---|
| Clinic config (M01) | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Branches (M02) | ✓ | ✓ | R | R | R | R | ✗ |
| Staff & roles / membership (M03) | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Subscription (M04) | ✓ | R | ✗ | ✗ | ✗ | ✗ | R |
| Services & pricing (M05) | ✓ | ✓ | R | R | R | R | R |
| Patient admin record (M06) | ✓ | ✓ | R | R | ✓ | L (care context) | ✗ |
| Clinical record (M06/M09) | L (per grant) | L (per grant) | ✓ (assigned scope only) | L (S/O support only) | ✗ | ✗ | ✗ |
| Appointments (M07) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| Check-in / queue (M08) | ✓ | ✓ | ✓ (own) | ✓ | ✓ | R | ✗ |
| Clinical notes — author (M09) | ✗ | ✗ | ✓ | L (S/O only, no A/P) | ✗ | ✗ | ✗ |
| Note finalization (M09) | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Clinical Copilot (M14) | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Care plan (M11) | R | R | ✓ | R | ✗ | L (operational items only) | ✗ |
| Care Gap Queue (M12) | ✓ | ✓ | ✓ (needs-doctor-review cases) | ✓ | ✗ | ✓ | ✗ |
| CRM / outreach (M13) | ✓ | ✓ | R | ✓ | L | ✓ | ✗ |
| Invoices / billing (M10) | ✓ | ✓ | L (own-encounter view only) | ✗ | ✓ (create/collect) | ✗ | ✓ |
| Refund / price adjustment | ✓ | ✓ | ✗ | ✗ | L (within role-configured cap, e.g. ≤10%) | ✗ | R |
| Revenue reports (M16) | ✓ | ✓ | L (own numbers) | ✗ | L | ✗ | ✓ |
| Clinical dashboard (M16) | L | L | ✓ (own scope) | L | ✗ | ✗ | ✗ |
| Data export | ✓ | ✓ | L | ✗ | ✗ | ✗ | L (financial only) |
| Consent (M17) | R | R | R | R | L (counter-collection entry) | R (status only) | ✗ |
| Audit log (M18) | R (own tenant) | R (own tenant) | ✗ | ✗ | ✗ | ✗ | ✗ |

Notes tying cells back to BRD business rules:

- **Clinical record row** — Doctor's `✓` is qualified "assigned scope only":
  enforced by generalizing `assert_doctor_assigned` (`rbac.py:63-105`) via
  `ClinicMembership` + the patient's `ClinicPatientRelationship`
  (`TENANT_ARCHITECTURE.md` §2.7) — a doctor sees a clinical record only if
  it belongs to a patient within their clinic's own-created-or-consented set
  **and** they are the assigned/queue doctor (BR-M09-03). Owner/Admin's
  `L (per grant)` is the "not a bypass" rule from §2 item 5 above.
- **Note finalization** — Doctor-only per BR-M09-02; the finalized-note
  immutability invariant (BR-M09-01) is a data-layer rule (append-only,
  amendments only) independent of this RBAC matrix but interacts with it:
  even a Doctor with `✓` finalize rights cannot UPDATE/DELETE a finalized
  row through any role.
- **Care Coordinator / clinical record = ✗** is Decision 1 verbatim.
- **Receptionist / patient admin = ✓ but clinical = ✗** is BR-M06-03's
  "zero API access to clinical content," enforced at the response-schema
  level per `BRD_ANALYSIS.md`/traceability row BR-M03-06 — i.e. this is not
  just a route-level 403, the response serializer itself must never include
  clinical fields for this role (field-level filtering, not just endpoint
  gating), since a shared list endpoint returning patient+clinical fields in
  one payload would otherwise leak clinical data through an
  administratively-permitted call.
- **Accountant row** — zero clinical access anywhere (BR-M10 Accountant
  actor description, M16 BR-M16-01 "Accountant never sees clinical
  dashboard").
- **Care Coordinator / Care Gap Queue = ✓** — this is the module Care
  Coordinator exists for (M12/M13); it is not in tension with Decision 1
  because Care Gap tasks and CRM call scripts are explicitly built from the
  "care context" whitelist (BR-M13-01), never from raw clinical fields.

---

## 4. Cross-clinic and platform-override rules restated for this matrix

- Every `✓`/`R`/`L` cell above is evaluated **per clinic**, using the
  `ClinicMembership` row resolved into the current request's `TenantContext`
  (`TENANT_ARCHITECTURE.md` §4). A user with `✓` on "Appointments" at Clinic A
  has no row in this matrix at all for Clinic B unless they hold a separate,
  active membership there.
- Super Admin / Internal Admin do not appear as columns in this matrix
  because they are not clinic roles — their access to any of the above
  resources is exclusively through the platform-override path described in
  `TENANT_ARCHITECTURE.md` §5, which is a distinct, always-audited code path,
  not an implicit "super_admin passes every check" shortcut layered on top of
  this table. (Contrast with today's `_ADMIN_ROLES`/`_is_admin()`
  bypass-everything shortcut, `rbac.py:24-41` — that pattern is reused for
  legacy Encounter/CarePlan routes but is explicitly **not** the template for
  new Clinic SaaS cross-tenant access, precisely because it bypasses without
  a mandatory audit call at each site.)
