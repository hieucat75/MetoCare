# MetoCare Medication — K2 Implementation Plan
## Approved Medication Knowledge API Exposure

**Status:** DRAFT — planning only. No route, schema, service, migration, frontend, or test
code written by this document. Requires explicit PTH GO before implementation, per this
program's standing two-step gate (see `MEDICATION_K1_5_APPROVAL_WORKFLOW_IMPLEMENTATION_PLAN.md`
§2, Phase 5 and `MEDICATION_K1_EXIT_CRITERIA.md` EC-08). **Governance update (2026-07-23):**
PTH changed the governance decision for Medication K2 — implementation of the fields and
capabilities listed in § Governance Decision Update below is **unblocked** and no longer
waits on Clinical Advisor, Legal, or Tech Lead sign-off. Clinical, legal, and content review
are post-implementation hardening milestones, not coding blockers (mirrors
`ADR-15-MEDICATION_KNOWLEDGE_EXTERNAL_VOCABULARY.md` § Governance Decision). This status
change does not itself constitute the program's separate "explicit PTH GO" convention
(§17 gate 6) — that remains its own, distinct procedural step.

**Date:** 2026-07-22 (revision 3, same day as revisions 1-2, per PTH's Phase A/B/C roadmap);
governance update 2026-07-23 (revision 5, see § Governance Decision Update, Revision summary)
**Author:** Drafted by Claude Code session, revised per explicit PTH decisions below. Response-
field implementation for the fields ADR-15 governs is unblocked (2026-07-23); the program's
own explicit-PTH-GO / Tech Lead / Codex review convention for this specific engineering plan
still applies — see §17.

**Revision note (rev 3 — Phase A "Plan Fix Round"):** PTH resequenced the remaining K2 work
into three gated phases before any coding: **Phase A** (this revision — close 8 named
plan-correctness gaps), **Phase B** (a dedicated vocabulary ADR locking `frequency`,
`action_level`, `evidence_level`, `source_type`, `patient_context`, `condition_type`, `theme`
— tracked separately, not authored by this document), **Phase C** (Codex review of this plan
until READY FOR IMPLEMENTATION). K2 coding starts only after all three phases close. This
revision closes Phase A's 8 items: endpoint identity, statement-vs-medication identifier,
product→ingredient resolution, locale filtering, audience filtering, doctor auth threshold,
audit-endpoint-2 decision, and concrete response examples. Everything else carries over from
revision 2 unchanged unless called out below.

---

## 0. Where this sits in the existing roadmap

`MEDICATION_ROADMAP.md` and the K1.5 plan name this milestone **"K2 — Knowledge API
Exposure"**, gated by **EC-08** ("No public/internal API route reads from or writes to the
new knowledge tables... requires its own separate GO"). K1.6 (merged, `c0cd746`) built the
internal read contract (`backend/app/services/knowledge_retrieval.py`) that this plan's
routes call — K1.6 wired nothing FastAPI-visible and its own plan says "Do not proceed to
K2 (API wiring) without a separate, explicit GO."

**Correction carried over from the first draft:** `MEDICATION_ROADMAP.md`'s K1.5 plan §2
Phase 5 says K2 would read "via `knowledge_repository.list_published()`" — that line
predates K1.6. K1.6's own module docstring is unambiguous: `knowledge_retrieval.py` is "the
only sanctioned read surface for the 5 ADR-13 knowledge tables." **K2 calls
`knowledge_retrieval.py`, not `knowledge_repository.list_published()`.**

**This revision closes the roadmap's original ambiguity** (a single `GET
/medications/{id}/knowledge` endpoint serving both patient and doctor) **in favor of two
separate, narrower endpoints** — see §2.

---

## 1. Current-state audit

### 1.1 What K1.6 already provides (verified directly from `knowledge_retrieval.py`)

| Function | Shape | Notes |
|---|---|---|
| `get_current_by_business_key(db, model_cls, **key)` | single row or `None` | exact business-key lookup |
| `list_current_for_ingredient(db, model_cls, drug_ingredient_id)` | `list[Model]` | all approved rows for one ingredient — **filters only by `status='approved'` and `drug_ingredient_id`; does NOT filter by `locale`/`audience`, and only 2 of the 5 models (`DrugUsage`, `DrugPatientEducation`) even have those columns** (§1.3 fact 4, §2.3) |
| `list_current_for_drug_class(db, model_cls, drug_class_id)` | `list[Model]` | non-recursive, direct FK only — **not used by either K2 v1 endpoint** (no named consumer, §3) |
| `get_current_batch(db, model_cls, drug_ingredient_ids)` | `dict[str, list[Model]]` | batch form — **not used in K2 v1** (§9, no batch endpoint) |
| `list_references_for(db, model_cls, row_id)` | `list[DrugReference]` | identity-based, no approved-status re-check — **only ever called server-side with `row_id`s this same request already resolved**, never with a client-supplied id (§7) |
| `list_references_for_batch(db, model_cls, row_ids)` | `dict[str, list[DrugReference]]` | batch form of the above — **not exposed as its own endpoint** (§2) |

All six raise `UnsupportedKnowledgeModelError` for a non-supported `model_cls`; the
business-key functions additionally raise `UnknownBusinessKeyFieldError` /
`MissingBusinessKeyFieldError` / `MultipleApprovedRowsError`. **No RBAC inside this module** —
by design, deferred to the route layer, which is why object-level authorization is this
plan's central concern (§4, §12).

### 1.2 What does not exist yet

- No API route, no Pydantic response schema, no frontend wiring, no AI wiring for these 5
  tables (EC-08/EC-09/EC-10 all still hold as of K1.6).
- No `approved` content in any environment (EC-07) — Phase 4 (real content authoring) has
  not started.
- No controlled external vocabulary for `frequency`/`action_level` — resolved by a separate
  Phase B vocabulary ADR (§5), not by this document: both fields stay excluded from K2 v1 as
  a scope decision, independent of the 2026-07-23 governance update.

### 1.3 Data-model facts this revision adds (verified directly against `app/models/`)

Revision 2 assumed a clean "resolve the ingredient server-side" step without documenting how.
Direct inspection of `app/models/clinical.py` and `app/models/drug_knowledge_core.py` surfaces
four facts that materially change §2/§4/§6/§8:

1. **`medications` (canonical) vs `medication_statements` (raw log) are not interchangeable.**
   `MedicationStatement` (`app/models/clinical.py:202`) is documented as "raw source assertion
   about a medication... append-mostly," and one canonical `Medication` row can have many
   `MedicationStatement` rows over time via `related_medication_id`/`merged_into_medication_id`
   (both FK to `medications.id`). A patient-facing "knowledge about the medication I'm
   currently taking" lookup means the canonical `Medication` row, not one specific historical
   statement — so **endpoint #1 keys off `medication_id` (the canonical `medications.id`), not
   `medication_statement_id`** (§2.1 fix).
2. **`drug_product_id` is nullable and has no DB-enforced FK, on both tables.** Both
   `Medication.drug_product_id` and `MedicationStatement.drug_product_id` are plain
   `String(36)` columns — the code comment on `Medication.drug_product_id` reads "FK to
   drug_products deferred until the P1 catalog table exists," and was never backfilled to a
   real FK after `drug_products` shipped. A medication row can have `drug_product_id = NULL`
   (patient-manual entry never matched to a catalog product) or, in principle, a stale id.
   Endpoint #1 must treat a null/unmatched product as "valid medication, no approved
   knowledge" (200, empty categories — §8), never a 404 or 500.
3. **Product→ingredient is many-to-many, not 1:1.** `DrugProductIngredient` (`app/models/
   drug_knowledge_core.py:83`) is a join table with `is_primary`/`role` columns — a
   combination-drug product maps to more than one ingredient. Endpoint #1 must resolve *all*
   ingredients for the patient's product, not assume exactly one (§2.1, §6.1, §7 fix).
4. **`list_current_for_ingredient` does not filter by `locale`/`audience`, and only 2 of the 5
   knowledge tables even have those columns — corrected 2026-07-23, see Revision 6.**
   `locale`/`audience` exist only on `DrugUsage` and `DrugPatientEducation`
   (`app/models/drug_knowledge_content.py` lines 100-101, 125-126: `locale String(10) default
   "vi"`, `audience String(32) default "patient"`) — they are part of *those two tables'*
   business key, not all five. `DrugSideEffect`, `DrugMonitoring`, and `DrugContraindication`
   have **no `locale` or `audience` column at all**; their business keys are
   `drug_ingredient_id` + their own content-specific fields only (e.g.
   `(drug_ingredient_id, concept_code)` for `DrugSideEffect`). This was verified directly
   against `app/models/drug_knowledge_content.py` during Slice 1 implementation — the original
   revision-3 claim that "both fields are part of the 5 knowledge tables' business key" was
   wrong for 3 of the 5 tables and is corrected here, not merely superseded.

   For `DrugUsage`/`DrugPatientEducation`, a patient-audience row and a doctor-audience row can
   both be `status='approved'` for the same ingredient simultaneously, and `list_current_for_
   ingredient` returns both unfiltered — without an explicit post-filter in the route layer,
   endpoint #1 could return doctor-audience content (clinical codes, doctor-facing language) to
   a patient and vice versa for these two categories. **This is a content-correctness gap, not
   a documentation nit** — see §2.3, §6, §13 for the fix.

   For `DrugSideEffect`/`DrugMonitoring`/`DrugContraindication`, no such gap exists and none is
   possible: with no `locale`/`audience` column, there is no doctor-specific or
   patient-specific duplicate row to leak in the first place. Every approved row for these
   three tables already applies identically to both audiences (and to the single locale
   currently authored). **A missing `locale`/`audience` column must never be treated as an
   implicit `"vi"`/`"patient"` default, and must never be inferred** — the correct route-layer
   behavior for these three tables is to skip the locale/audience filter entirely, not to
   assume or backfill a value that does not exist on the row (§2.3).

---

## 2. Scope & objective

**Objective:** Wire two narrow, purpose-specific read-only HTTP endpoints over the 5 ADR-13
knowledge tables, both calling exclusively through `knowledge_retrieval.py`, both returning
only `status='approved'` content. `usage`/`patient_education` are additionally filtered to a
single `locale`/`audience` before being grouped into a response — the only 2 of the 5
categories where a `locale`/`audience` column exists to filter on (§1.3 fact 4, §2.3).

### 2.1 Endpoint table (revision 3 — identifiers and naming fixed)

| # | Endpoint | Method | Role | Object-level check | PHI/patient context |
|---|---|---|---|---|---|
| 1 | `/api/v1/patient/medications/{medication_id}/knowledge` | GET | `PATIENT` | **mandatory** — `medication_id` must belong to the authenticated patient | Yes — ingredient(s) resolved server-side from the patient's own canonical medication record |
| 2 | `/api/v1/doctor/ingredients/{drug_ingredient_id}/knowledge` | GET | `DOCTOR` **and** `verification_status == VERIFIED` (§4) | none — no patient object in this route at all | No — general clinical reference, ingredient id is not patient-scoped |

**Changes from revision 2:**
- Path parameter for endpoint #1 changed from `medication_statement_id` to `medication_id` —
  it now resolves against the canonical `medications` table, not the raw, append-only
  `medication_statements` log (§1.3 fact 1). The object-level ownership check (§4, §12) is
  unchanged in kind: `medication_id` must resolve to a row whose `patient_id` is the
  authenticated caller's own `patient_profile.id`.
- Path for endpoint #2 renamed from `/api/v1/doctor/medication-knowledge/ingredients/{id}` to
  `/api/v1/doctor/ingredients/{drug_ingredient_id}/knowledge` — both endpoints now share the
  same `.../{id}/knowledge` shape (endpoint identity fix). No behavior change, naming only.

Both resolve their target ingredient(s) **server-side only**:
- **Endpoint #1:** `medication_id` → row's `drug_product_id` (may be `null` — §8) → all
  `drug_ingredient_id`s via `drug_product_ingredients` (may be more than one — §1.3 fact 3) →
  for each ingredient, call `list_current_for_ingredient` per knowledge model → **for `usage`
  and `patient_education`, filter results to `locale='vi'` and `audience='patient'`; for
  `side_effects`, `monitoring`, and `contraindications`, no locale/audience filter is applied
  — those 3 tables have no such columns (§1.3 fact 4, §2.3)** → merge across ingredients.
- **Endpoint #2:** `drug_ingredient_id` (the only input, taken as-is) → call
  `list_current_for_ingredient` per knowledge model → **for `usage` and `patient_education`,
  filter results to `locale='vi'` and `audience='doctor'`; the other 3 categories are returned
  unfiltered, same reasoning as endpoint #1** (§2.3).

Neither endpoint accepts a client-supplied knowledge-table name, knowledge row id, ingredient
list, or locale/audience override.

### 2.2 Explicitly NOT built in K2 v1

- **No public/global knowledge API.** Every request is role-gated; there is no
  unauthenticated or any-authenticated-role catalog endpoint.
- **No table-name-based route.** The client never passes `drug_usage`/`drug_side_effects`/
  etc. as a path or query parameter — the server always resolves and returns all five
  categories together, grouped by fixed response keys (`usage`, `patient_education`,
  `side_effects`, `monitoring`, `contraindications`).
- **No row-id provenance endpoint.** There is no `GET .../references/{row_id}`-shaped route.
  Citations are only ever returned nested inside the main response, resolved server-side
  from rows that same response already returned as approved (§7).
- **No patient-specific doctor endpoint.** A doctor viewing *a specific patient's* medication
  knowledge (combining consent + that patient's medication record) is a different,
  BOLA-relevant shape deferred to a future slice with its own authorization design — not
  bolted onto endpoint #2, which stays a pure, patient-context-free reference lookup.
- **No caregiver access** (§3).
- **No batch/list-all endpoint** (§9).
- **No locale other than `vi`.** Both endpoints hardcode `locale='vi'` for v1 (patient-facing
  content is Vietnamese-first, per existing platform convention); there is no
  `?locale=`/`Accept-Language`-driven behavior. A future non-Vietnamese locale is a separate,
  later slice.
- Frontend consumption, AI/Meto wiring, `drug_interactions`, and any write endpoint — all
  unchanged from the first draft's exclusions.

**Migration:** None for K2 Slice 1's own endpoints — still true; they are a
pure read API over existing tables/indexes and write nothing. **Corrected
2026-07-23 (Revision 7):** this claim does not extend to the program as a
whole. K2 Slice 1's own PostgreSQL verification gate found that ADR-15
§D's locked `evidence_level` vocabulary does not fit the pre-existing
`evidence_level VARCHAR(16)` column (`clinical_guideline` and
`peer_reviewed_literature` both exceed 16 characters) — a K1/ADR-13 schema
compatibility prerequisite, not a K2/AI/provenance expansion, closed by
migration `k2_s1_widen_evidence_level` (widens to `VARCHAR(32)`, additive,
no rename/vocabulary/default change — see § Revision 7 and the migration's
own docstring for the full account). K2 Slice 1's endpoints still require
no migration of their own; the vocabulary they read from now does.

### 2.3 Locale/audience filtering (new — closes the gap in §1.3 fact 4)

**Corrected 2026-07-23 (Revision 6):** this filter applies to **only 2 of the 5 knowledge
tables — `DrugUsage` and `DrugPatientEducation`** — the only two that actually carry `locale`/
`audience` columns (§1.3 fact 4). `DrugSideEffect`, `DrugMonitoring`, and `DrugContraindication`
have neither column; there is no locale/audience value on those rows to filter by, and
implementation code must not invent, default, or infer one. The earlier text below describing
"this filter runs identically across all 5 knowledge models" was wrong and is corrected here.

Because `list_current_for_ingredient` does not filter by `locale`/`audience` (for the two
models that have them), the route handler — not the service module — is responsible for
filtering its return value before any response is built, **conditionally, only for
`DrugUsage`/`DrugPatientEducation`**:

```
rows = list_current_for_ingredient(db, ModelCls, ingredient_id)
if ModelCls in (DrugUsage, DrugPatientEducation):
    rows = [r for r in rows if r.locale == "vi" and r.audience == target_audience]
# else: DrugSideEffect / DrugMonitoring / DrugContraindication have no locale/audience
# column — every approved row already applies to every audience/locale, use `rows` as-is.
```

where `target_audience` is `"patient"` for endpoint #1 and `"doctor"` for endpoint #2 —
never a caller-supplied value. This filter runs **only for the 2 audience/locale-aware
models** and must run **before** any `list_references_for` call (§7) for those models, so
citations are only ever resolved for rows that already passed both the approved-status filter
(K1.6) and this audience/locale filter (K2) where applicable. `knowledge_retrieval.py` itself
is not modified — it stays a generic, audience-agnostic read surface; the audience/locale
contract is a K2 route-layer concern, matching this module's own stated design ("no RBAC
inside this module... deferred to the route layer").

**Why the other 3 tables need no filter, and why that's safe, not an oversight:** the
audience-leak risk this section defends against (doctor-facing clinical language reaching a
patient, or vice versa) can only occur where a doctor-audience and patient-audience row can
both exist for the same ingredient — which requires an `audience` column to distinguish them.
`DrugSideEffect`/`DrugMonitoring`/`DrugContraindication` have no such column, so no such
duplicate can exist; every approved row for these three tables is, by construction, the single
authoritative fact for that ingredient, shown identically to both audiences. Skipping the
filter here is not a gap being tolerated — it is the correct behavior for tables where the
distinction the filter enforces does not exist.

**Combination products (§1.3 fact 3):** when a patient's medication resolves to more than one
`drug_ingredient_id`, endpoint #1 calls the filter above once per ingredient and **merges (not
intersects, not primary-only) the results per category** — e.g. all approved `side_effects`
rows across every ingredient in the product appear in the response's `side_effects` list. This
errs toward showing more real safety content rather than silently dropping a non-primary
ingredient's side effects/contraindications; `is_primary`/`role` are not used as an exclusion
filter in v1 (may inform future display ordering, not scope).

---

## 3. Consumers

| Consumer | In K2 v1? | Notes |
|---|---|---|
| Patient App (own medication) | **Yes** | endpoint #1 |
| Doctor Portal (general drug reference, not tied to a specific patient) | **Yes** | endpoint #2, verified doctors only (§4) |
| Doctor Portal (a specific consented patient's medication knowledge) | **No** | deferred — see §2.2 |
| Frontend cards actually calling either endpoint | **No** | route exists and is tested; wiring `frontend/` is a separate, later PR |
| Meto / AI context builder (ADR-07/ADR-14) | **No** | separate, later GO; must not import either route or call `knowledge_retrieval.py` directly from `app/ai` |
| Internal authoring/QA tooling | **No** | non-approved content stays on its own internal surface, out of scope per K0-K3 |
| **Caregiver** | **No — explicit, permanent for this slice** | see §4 |
| `INTERNAL_ADMIN` / `SUPER_ADMIN` | **No implicit access** | see §4 |

---

## 4. Authorization matrix (revision 3 — doctor verification threshold added)

| Role | Endpoint #1 (patient) | Endpoint #2 (doctor) | Mechanism |
|---|---|---|---|
| `PATIENT` | ✅ **only if** `medication_id` belongs to this patient | ❌ 403 | role check (`require_roles`) **plus** an object-level ownership check — see below |
| `DOCTOR`, `verification_status == VERIFIED` | ❌ 403 | ✅ | role check **plus** verification-status check — see below |
| `DOCTOR`, `verification_status != VERIFIED` (e.g. `PENDING_VERIFICATION`) | ❌ 403 | ❌ 403 | **new in rev 3** — role alone is not sufficient for endpoint #2 either |
| `CLINIC_ADMIN` | ❌ 403 | ❌ 403 | — |
| `CAREGIVER` | ❌ 403 — **not added to `require_roles` for either endpoint** | ❌ 403 | see below |
| `INTERNAL_ADMIN` / `SUPER_ADMIN` | ❌ 403 — **no implicit admin access** | ❌ 403 | if platform-admin access is ever needed, it must be added explicitly and justified in its own review, never inherited by default |
| `AI_SERVICE` | ❌ 403 | ❌ 403 | AI wiring is a separate, later GO |

**`require_roles` alone is not sufficient for endpoint #1 and must not be treated as the
whole authorization check.** A role check only proves "this caller is *a* patient" — it does
not prove "this caller is *the* patient who owns this specific `medication_id`." Two different
`PATIENT`-role users are otherwise indistinguishable to `require_roles`, so endpoint #1
requires an explicit **object-level authorization** step, evaluated after the role check and
before any ingredient resolution: the `medication_id` path parameter must resolve to a row
whose owning patient is the authenticated caller's own `patient_profile.id`. This is the same
class of check `GET /patients/{id}/medications/{mid}` already performs today (reused, not
reinvented) — see §12 for the threat this defends against and why it's a first-class
requirement here, not an implementation detail.

**Doctor verification threshold (PTH decision, Phase A):** `require_roles(DOCTOR)` alone is
also not sufficient for endpoint #2. `Doctor.verification_status` (`app/models/care.py:110`,
source of truth over the legacy `is_verified` mirror) can be `PENDING_VERIFICATION` for a
doctor account that exists (e.g. admin-created, per the doctor-onboarding flow) but has not
yet completed admin verification. **PTH decided (2026-07-22): endpoint #2 requires
`verification_status == VERIFIED`** — a pending-verification doctor account gets `403`, the
same as any other unauthorized role, even though the content itself is generic and non-PHI.
This is a new dependency, evaluated after the role check, analogous in shape (though not in
purpose — no BOLA is involved) to endpoint #1's object-level check: two checks, not one, gate
endpoint #2.

Endpoint #2 still has **no object-level check**: `drug_ingredient_id` is not owned by any
specific patient — there is no per-caller object to authorize against, only the role and
verification status.

**Caregiver — explicitly out of scope for this slice.** `CAREGIVER` is not added to
`require_roles` on either endpoint, and no code path today grants a caregiver any access to
medication knowledge content. `MEDICATION_RBAC_AND_PRIVACY.md` §3.4/§5.1 already scopes
caregiver permissions to medication *instance* data (dose, adherence) — knowledge content is
a new resource type not covered by any existing caregiver permission flag, and this plan does
not add one. **Any future caregiver access to medication knowledge is a separate, later
decision** that would need: a delegated-authorization model (not a blanket role check), an
explicit consent/permission scope naming knowledge content specifically (distinct from
`can_view_medications`), expiry/revocation semantics matching the existing
`caregiver_assignments` model, and its own audit trail — none of which this plan designs.

**Rate limit:** unchanged from the first draft's proposal — 30-60/min, matching the existing
convention for medication-detail-shaped GETs (`MEDICATION_RBAC_AND_PRIVACY.md` §8).

---

## 5. Side-effect vocabulary gate (blocking pre-implementation decision — Phase B)

`frequency` (DB: `common/uncommon/rare/unknown`) and `action_level` (DB:
`self_monitor/contact_clinician/urgent_medical_help`) are real, independent DB columns today
(`drug_knowledge_content.py`'s `ck_drug_side_effects_frequency` /
`ck_drug_side_effects_action_level` CHECK constraints) — but **they must not be exposed
through this API as unstable free text** before their *external* contract is separately
decided. The DB enum is an internal storage decision; an API consumer needs a vocabulary
that is guaranteed stable across DB-level changes, which does not exist yet.

**This is Phase B of PTH's roadmap. It has been authored and approved by PTH as its own
artifact: `ADR-15-MEDICATION_KNOWLEDGE_EXTERNAL_VOCABULARY.md` (APPROVED FOR IMPLEMENTATION BY
PTH — clinical and legal governance deferred, 2026-07-23) — not by this document.**
Response-field implementation for the fields ADR-15 newly governs is **unblocked** as of PTH's
2026-07-23 governance decision (ADR-15 § Approval Record, Implementation Gate, §K) — Clinical
Advisor, Legal, and Tech Lead review are recommended, non-blocking future reviews (ADR-15
§ Recommended Future Reviews), not preconditions for writing this code.
Before either `frequency` or `action_level` value is ever returned by this API, the following
must be settled (ADR-15 §B/§C locks the answers for these two specifically; both remain
excluded from K2 v1 as an independent scope decision, not a governance-blocking one):

1. **Controlled vocabulary** — the exact external string set for each axis, independent of
   (though presumably derived from) the DB's current CHECK-constraint values.
2. **Clinical owner** — a named clinical/product owner accountable for what each value means
   to a patient or doctor reading it (mirrors ADR-13's Clinical Advisor review role for
   the underlying content itself — recommended, non-blocking per the 2026-07-23 governance
   decision).
3. **Source mapping** — an explicit table from DB value → external value for both axes; no
   implicit 1:1 assumption.
4. **Unknown semantics** — what `frequency='unknown'` actually communicates to a reader
   (absence of data vs. genuinely variable/unclassified rate) must be defined, not left to be
   inferred.
5. **Versioning** — the external vocabulary needs its own version identifier so a future
   remapping doesn't silently change meaning for existing API consumers without a version
   bump.
6. **Localization** — patient-facing content is Vietnamese-first (`locale='vi'`); the
   vocabulary needs a defined label-translation approach, not ad hoc per-response string
   formatting.

Phase B additionally locks `evidence_level`, `source_type`, `patient_context`,
`condition_type`, and `theme` — the remaining content-vocabulary axes this plan's response
contracts expose as opaque strings (§6) — under the same six-point discipline. **ADR-15 has
completed and locked all seven fields** (see §6.1/§6.2 below for the resulting per-field
treatment).

**Decision for K2 v1 (locked by ADR-15 §A/§B/§C): omit `frequency` and `action_level` from
both response contracts entirely** (patient §6.1 and doctor §6.2). `DrugSideEffectOut` in K2
v1 carries `concept_code` (doctor only), `label`, `description`, and provenance fields —
nothing on the frequency/action-level axes. Adding them back is a scoped, separately-reviewed
follow-up requiring a future ADR amendment, not part of this slice. **When `frequency` is
eventually exposed, ADR-15 §B locks its external JSON key as `side_effect_frequency`, not
bare `frequency`** — the codebase already uses the bare word "frequency" for an unrelated
concept (medication dosing-schedule frequency), and ADR-15 explicitly decided not to rename
the underlying DB column as part of that change, only the API-level name.

`frequency` and `action_level` are independent axes (this is the entire reason ADR-13 split
them out of the old single `level` enum — see A1b-F1 revision note in
`MEDICATION_KNOWLEDGE_TEMPLATE_V1.md`). **No consumer of this API, now or in the future, may
infer `action_level` from `frequency`** (e.g. "rare implies self-monitor") — if a value is
exposed, both axes must always be the real, explicit DB-sourced values; no derived shortcut
is ever permitted (ADR-15 §C reaffirms this as permanent, not a temporary modeling artifact).

**Additional ADR-15-locked rules that carry forward into K2 implementation (not decided by
this document, only reflected here). These are PTH's product/mechanics decisions; Tech Lead
review of the mechanics below (envelope versioning, telemetry, validation semantics, the
item-type matrix, legacy-data handling) is recommended but, per the 2026-07-23 governance
decision, is not a precondition for writing the code that implements them (ADR-15 § Recommended
Future Reviews):**

- **`knowledge_vocabulary_version`:** a single string field, initial value `"1.0"`, placed
  once at **response-envelope scope** on both contracts (§6.1, §6.2) — not repeated per
  knowledge item. Independent of the `/api/v1` route version. Label/translation changes never
  bump it; additive canonical-value changes bump the minor version; removals/remappings/
  semantic changes bump the major version (ADR-15 §H).
- **No `evidence_level` DB `CHECK` constraint in K2 v1.** ADR-15 §D locks a required five-step
  sequence (app-level validation + telemetry → inventory → backfill/quarantine → staging
  validation → constraint migration) that must complete, in order, before any such migration —
  none of which is part of K2 v1's implementation scope.
- **`action_level` fail-closed scope is item-level only.** An invalid `action_level` value
  drops the single affected knowledge item — never the whole medication, the whole response,
  or any unrelated item — and must emit mandatory PHI-free structured telemetry
  (`knowledge_vocabulary_version`, the knowledge record identifier, the invalid value, and the
  validation reason; never patient free text or PHI) (ADR-15 §C).
- **Field-required-by-item-type matrix — required before implementation.** Whether a *missing*
  `action_level` value causes item omission depends on whether that specific knowledge-item
  type treats `action_level` as required-for-display at all. Before any route or response-model
  code touching `action_level`-bearing item types is written, a matrix documenting which of the
  five knowledge-item types require `action_level` (vs. not-applicable) must exist, so "missing"
  and "not applicable" are never conflated (ADR-15 §C, Implementation Gate). This matrix is not
  authored by ADR-15 or by this plan — it is a required K2 implementation-planning deliverable.
  It gates `action_level`-bearing work specifically (which stays excluded from K2 v1 regardless,
  §5); it does not gate the other four fields ADR-15 governs, which are unblocked for
  implementation as of the 2026-07-23 governance decision.

---

## 6. Response contracts (separate patient and doctor shapes)

### 6.1 Patient contract (`PatientMedicationKnowledgeOut`)

Plain-language, bounded-provenance, no internal identifiers. `usage`/`patient_education` rows
are filtered to `locale='vi'`, `audience='patient'`; `side_effects`/`monitoring`/
`contraindications` rows carry no `locale`/`audience` column and are not filtered (§1.3 fact 4,
§2.3). All categories are merged across every ingredient of the patient's medication's product
(§2.3, combination-product case):

```
knowledge_vocabulary_version: str -- ADR-15 §H, e.g. "1.0"; envelope-level, once per response
usage (single object or null): content, evidence_level, last_reviewed_at
patient_education (list):      theme, content, evidence_level, last_reviewed_at
side_effects (list):           label, description, evidence_level, last_reviewed_at
monitoring (list):              guidance, evidence_level, last_reviewed_at
contraindications (list):      condition_detail, evidence_level, last_reviewed_at
safety_notice: {code, text, locale, version}   -- §10, mandatory, non-overridable
```

`evidence_level` values are the six-value canonical list locked by ADR-15 §D (experimental
status — no DB `CHECK` constraint yet, fail-soft field-level omission on an out-of-vocabulary
value). `theme` values are the six-value canonical list locked by ADR-15 §F (also
experimental; fail-soft field-level omission only — the rest of the item is unaffected).
Neither field's raw code may be shown to a patient without resolving it to its localized
display label first (ADR-15 §D, §G) — VN labels themselves are a separate, not-yet-authored
content task (ADR-15 Open Questions).

**Explicitly excluded from the patient contract:** `concept_code`, `condition_key`,
`condition_type`, `parameter`, `patient_context` — both are opaque internal authoring keys
per ADR-15 §F with no vocabulary-stability guarantee, doctor-only, never patient-facing —
`source`/`version` raw strings, any citation/reference list (bounded provenance =
`evidence_level` + `last_reviewed_at` only, nothing deeper — a patient does not need a
formulary citation to read a side-effect warning), `frequency`/`action_level` (§5, ADR-15
§B/§C), and every governance/workflow field (`authored_by`, `status_changed_by`,
`artifact_hash`, `knowledge_review_specialties` reviewer identity — ADR-13 frames these as
internal governance metadata).

**Example — medication with one matched ingredient, some approved content (200):**

```json
{
  "knowledge_vocabulary_version": "1.0",
  "usage": {
    "content": "Uống 1 viên vào buổi sáng, sau ăn.",
    "evidence_level": "clinical_guideline",
    "last_reviewed_at": "2026-06-01T00:00:00Z"
  },
  "patient_education": [
    {
      "theme": "why_this_matters",
      "content": "Thuốc này giúp kiểm soát đường huyết trong ngày.",
      "evidence_level": "clinical_guideline",
      "last_reviewed_at": "2026-06-01T00:00:00Z"
    }
  ],
  "side_effects": [
    {
      "label": "Buồn nôn nhẹ",
      "description": "Có thể xảy ra trong tuần đầu, thường tự hết.",
      "evidence_level": "product_label",
      "last_reviewed_at": "2026-06-01T00:00:00Z"
    }
  ],
  "monitoring": [],
  "contraindications": [],
  "safety_notice": {
    "code": "medication_knowledge_reference_only_v1",
    "text": "Thông tin này chỉ mang tính tham khảo, không thay thế chỉ định của bác sĩ.",
    "locale": "vi",
    "version": "1"
  }
}
```

**Example — medication exists, no `drug_product_id` match / no approved content (200):**

```json
{
  "knowledge_vocabulary_version": "1.0",
  "usage": null,
  "patient_education": [],
  "side_effects": [],
  "monitoring": [],
  "contraindications": [],
  "safety_notice": {
    "code": "medication_knowledge_reference_only_v1",
    "text": "Thông tin này chỉ mang tính tham khảo, không thay thế chỉ định của bác sĩ.",
    "locale": "vi",
    "version": "1"
  }
}
```

**Example — `medication_id` not found or belongs to another patient (404):**

```json
{ "detail": "Not found" }
```

### 6.2 Doctor contract (`DoctorIngredientKnowledgeOut`)

Structured clinical content, richer provenance, still no workflow metadata.
`usage`/`patient_education` rows are filtered to `locale='vi'`, `audience='doctor'`;
`side_effects`/`monitoring`/`contraindications` rows carry no `locale`/`audience` column and
are not filtered (§1.3 fact 4, §2.3):

```
knowledge_vocabulary_version: str -- ADR-15 §H, e.g. "1.0"; envelope-level, once per response
usage (single object or null): content, source, version, evidence_level, last_reviewed_at
patient_education (list):      theme, content, source, version, evidence_level, last_reviewed_at
side_effects (list):           concept_code, label, description, source, version, evidence_level, last_reviewed_at, references[]
monitoring (list):              parameter, patient_context, guidance, source, version, evidence_level, last_reviewed_at, references[]
contraindications (list):      condition_type, condition_key, condition_detail, source, version, evidence_level, last_reviewed_at, references[]
safety_notice: {code, text, locale, version}   -- §10, separate contract from patient's
```

`patient_context` (monitoring rows) and `condition_type` (contraindications rows) are opaque
internal authoring keys per ADR-15 §F — visible to doctors because they are load-bearing for
clinical correctness (they disambiguate which population/category a row applies to), but they
carry **no vocabulary-stability guarantee**: no enumerated value list, no localization, and no
enum-style badge/color/filter UI treatment implying a governed value set. Clients must render
them as plain opaque text.

`references[]` (per row, via `list_references_for`, §7): `publisher`, `title`, `source_type`,
`url`, `document_identifier`, `publication_date`, `source_version`. This is a
doctor-contract-only feature in v1 — the patient contract does not include citations at all
(§6.1's "bounded provenance"). **This `source_type` is `DrugReference.source_type`
exclusively** (ADR-15 §E's five-value stable vocabulary: `formulary`/`clinical_guideline`/
`product_label`/`peer_reviewed`/`other`) — it must never be confused with the unrelated
`medications.source_type` field (ADR-04's reconciliation-provenance category, a different
table/domain entirely), and no future PR may introduce a `source_type`-named field anywhere
outside `DrugReference` without its own vocabulary review (ADR-15 §E).

**Explicitly excluded from the doctor contract too, "unless separately justified":**
`authored_by`, `status_changed_by`, `artifact_hash`, `knowledge_review_specialties` reviewer
identity, and (per §5, ADR-15 §B/§C) `frequency`/`action_level`. If a future, specific
clinical need arises for any of these, it is a separate, named decision requiring an ADR-15
amendment — not a default inclusion just because the audience is a clinician.

**Example — ingredient with approved content (200):**

```json
{
  "knowledge_vocabulary_version": "1.0",
  "usage": {
    "content": "Metformin: khởi đầu 500mg x1-2 lần/ngày, chỉnh liều theo eGFR.",
    "source": "vidal_vn",
    "version": "2026.1",
    "evidence_level": "clinical_guideline",
    "last_reviewed_at": "2026-06-01T00:00:00Z"
  },
  "patient_education": [],
  "side_effects": [
    {
      "concept_code": "GI_NAUSEA",
      "label": "Buồn nôn",
      "description": "Thường gặp khi khởi đầu điều trị, giảm dần theo thời gian.",
      "source": "vidal_vn",
      "version": "2026.1",
      "evidence_level": "product_label",
      "last_reviewed_at": "2026-06-01T00:00:00Z",
      "references": [
        {
          "publisher": "VIDAL Vietnam",
          "title": "Metformin — Thông tin sản phẩm",
          "source_type": "product_label",
          "url": "https://example.invalid/vidal/metformin",
          "document_identifier": "VIDAL-VN-METFORMIN-2026",
          "publication_date": "2026-01-15",
          "source_version": "2026.1"
        }
      ]
    }
  ],
  "monitoring": [
    {
      "parameter": "renal_function",
      "patient_context": "ckd_stage_3_or_worse",
      "guidance": "Kiểm tra eGFR mỗi 3-6 tháng.",
      "source": "vidal_vn",
      "version": "2026.1",
      "evidence_level": "clinical_guideline",
      "last_reviewed_at": "2026-06-01T00:00:00Z",
      "references": []
    }
  ],
  "contraindications": [],
  "safety_notice": {
    "code": "medication_knowledge_clinical_reference_only_v1",
    "text": "Nội dung tham khảo lâm sàng, không thay thế thông tin kê đơn đầy đủ.",
    "locale": "vi",
    "version": "1"
  }
}
```

**Example — `drug_ingredient_id` not found (404):**

```json
{ "detail": "Not found" }
```

### 6.3 Envelope / not-found shape

- Endpoint #1: `usage` is `null` when no approved row exists for that business key (the
  business key is per-ingredient-per-locale-per-audience, i.e. at most one row); the four
  list fields are `[]` when empty. This is a normal `200`, not a `404` — see §8. This
  includes the case where the medication's `drug_product_id` is `null` or unmatched (§1.3
  fact 2) — no product/ingredient resolution possible, so every category is empty, but the
  medication itself is a valid, owned resource.
- Endpoint #2: same shape, keyed by the requested `drug_ingredient_id` directly (no
  medication wrapper, since there's no patient object involved).

---

## 7. Provenance invariant

**All citation `row_id`s used to call `list_references_for`/`list_references_for_batch` must
originate from rows this same server-side request already resolved through an approved-only,
audience/locale-filtered K1.6 lookup** (`list_current_for_ingredient` + the §2.3 filter, in
this plan's case) — never from a client-supplied value. Concretely:

- The client **never** supplies `knowledge_table`, `knowledge_row_id`, `locale`, or
  `audience` (or any equivalent) as a request parameter, on either endpoint. There is no
  field in either request shape that could carry one (§2.2 — no row-id provenance endpoint at
  all, no locale override).
- The route handler's only legitimate sequence is: resolve ingredient(s) → call
  `list_current_for_ingredient` per model class → apply the §2.3 audience/locale filter → for
  exactly the rows that survive both filters, call `list_references_for` (doctor contract
  only, §6.2) using those rows' own `id` — never any other identifier.
- This closes the misuse case K1.6's own docstring already warns about ("a future K2 API
  route... that calls this function directly with an externally-supplied `row_id`... would
  surface citations for non-approved or nonexistent content") **by construction, not by
  validation** — there is no client-facing parameter to validate in the first place, since
  no such endpoint or field exists (§2.2).

---

## 8. Error semantics

| Condition | Endpoint | Status | Notes |
|---|---|---|---|
| `medication_id` doesn't exist, **or** exists but belongs to another patient | #1 | **404** | Same code for both cases, deliberately — see §12 (anti-enumeration; a 403 vs 404 split would itself leak whether the id exists) |
| `drug_ingredient_id` doesn't exist | #2 | **404** | No ownership ambiguity here — ingredient ids aren't patient-scoped, so a plain 404 carries no extra privacy risk |
| `medication_id` valid and owned, but `drug_product_id` is `null` or does not resolve to any `drug_product_ingredients` row | #1 | **200** | Not a 404 — the medication itself is a valid, owned resource; empty/`null` categories (§6.3, §1.3 fact 2). Never surfaced as an error. |
| Valid target, zero approved knowledge across all 5 tables (post audience/locale filter, §2.3) | #1, #2 | **200** | Empty/`null` category collections (§6.3) — this is a normal, expected outcome, not an error |
| Persisted `evidence_level`/`theme`/`source_type` value outside ADR-15's locked lists (§5, ADR-15 §D/§F/§E) | #1, #2 | **200** | **Field-level fail-soft, never whole-request** — the offending field is omitted from that item's response, the rest of the item and every other item is unaffected (ADR-15 §G) |
| Persisted `action_level` value invalid, on an item type that requires it (ADR-15 §C — pending the field-required-by-item-type matrix; dormant while `action_level` stays excluded per §5) | #1, #2 | **200** | **Item-scoped fail-closed only** — the single affected knowledge item is omitted; never the whole medication or the whole response; mandatory PHI-free structured telemetry (`knowledge_vocabulary_version`, knowledge record identifier, invalid value, validation reason — no patient free text/PHI) |
| `DOCTOR` role but `verification_status != VERIFIED` | #2 | **403** | Same status code as any other unauthorized role (§4) — not distinguished in the response body, to avoid leaking verification state to a caller who shouldn't have access at all |
| Invalid filter/category value | #1, #2 | **422** | **Dormant in v1** — neither endpoint accepts a category/filter query parameter (§2.2, "no table-name-based route"); this row exists so that if a filter parameter is ever added later, an unrecognized value fails closed with 422 rather than silently matching nothing or everything |
| `MultipleApprovedRowsError` (data-integrity violation) on any one of the 5 tables | #1, #2 | **500**, whole-request failure | **Fail closed, no partial response** — the entire request fails if *any* single table's query hits this invariant violation; the response must never silently return the 4 categories that were fine while omitting/erroring only the broken one, since that would look like an incomplete-but-successful `200` |
| Any other internal exception | #1, #2 | **500**, generic body | No stack trace, no internal exception message, no PHI, no table/model internals in the response — same discipline as every existing PHI-adjacent endpoint in this codebase |

---

## 9. Pagination / batch semantics (no batch endpoint in v1)

- **No public batch endpoint in the initial K2 slice.** Both endpoints are bounded to
  exactly one object: one `medication_id` (#1) or one `drug_ingredient_id` (#2) per request.
- **No list-all endpoint.** There is no "every approved row across every ingredient" route —
  no named consumer, no natural page size (unchanged reasoning from the first draft).
- **Future batch shape — documented, not implemented:** if a patient's-active-medication-list
  batch call (the shape ADR-07's future context-builder would need, via K1.6's
  `get_current_batch`/`list_references_for_batch`) is ever built, it must define, at minimum,
  before it ships:
  - An explicit, enforced maximum id count per request (not just an assumption that "typical"
    lists stay small — K1.6's own docstring only says "not validated or chunked for
    arbitrarily large lists," which is a gap a batch *API* endpoint cannot inherit unchanged).
  - **No-silent-omission semantics**, carried over from `get_current_batch`'s own contract:
    every requested id must appear as a key in the response (empty collection if it has no
    approved content), never silently dropped.
  - Its own authorization design — a batch endpoint would need to prove the caller owns (or
    has consent for) *every* id in the batch, not just the first — a materially different
    and harder authorization shape than either endpoint in this plan, and out of scope here.
  - The same §2.3 audience/locale filter this plan requires — a batch route inherits this
    gap identically and must not skip it.

---

## 10. Safety notice (server-controlled, versioned)

```
SafetyNotice:
  code:    str   -- stable identifier, e.g. "medication_knowledge_reference_only_v1"
  text:    str   -- localized display text
  locale:  str   -- e.g. "vi"
  version: str   -- bumped whenever the text changes materially
```

- **Patient notice is mandatory on every endpoint #1 response and non-overridable** — no
  request parameter can suppress it, change its locale, or pin an older version. Exact
  Vietnamese copy is not authored by this plan (needs a clinical/product-content pass) —
  placeholder only (see §6.1/§6.2 examples for placeholder copy).
- **Doctor notice may have a separate contract** (different `code`/`text` — e.g. framed as
  "clinical reference only, not a substitute for full prescribing information" rather than
  the patient's plain-language caution) — also mandatory, also non-overridable, on endpoint
  #2.
- Implementation note (non-binding): a versioned constant in code is sufficient for v1 — this
  does not need its own DB table, but the `code`/`text`/`locale`/`version` shape must be
  present regardless of storage mechanism, so a future content update is traceable.

---

## 11. Caching / privacy / audit

- **Endpoint #1 (patient-scoped):** responses must be marked non-cacheable in any shared
  layer — `Cache-Control: private, no-store` (or an equivalent no-shared-cache directive).
  This endpoint reveals a specific patient's medication-ingredient association (condition-
  adjacent PHI, §12), so it must never be served from a CDN or any cache shared across
  users, even though the underlying knowledge *content* is itself generic.
- **Endpoint #2 (doctor general reference):** **only bounded caching, and only if approved-
  version semantics are proven sound** — content can change when a newer row supersedes the
  current approved one (K1.5's `_deprecate_superseded`, atomic per business key), so any
  cache must not serve stale/deprecated content past a safe TTL. **Not decided in this
  plan** — v1 should ship with caching off (safe default); enabling it is a separate,
  later sign-off once that soundness is demonstrated, not an implicit optimization bundled
  into this slice.
- **Audit — endpoint #1 follows the existing medication-access audit policy**
  (`MEDICATION_RBAC_AND_PRIVACY.md` §7): every read produces an audit entry recording
  `medication_id` (or the resolved `drug_ingredient_id`(s)), requester role, and
  `action="read_medication_knowledge"`. **PHI-minimized, matching existing convention**: the
  audit entry never includes the knowledge body/content text, side-effect descriptions,
  usage narrative, or any other clinical prose — ids and metadata only, same as
  `add_medication`/`update_medication` audit rows today.
- **Audit — endpoint #2: decided (PTH, Phase A, 2026-07-22) — no audit log.** No PHI, no
  patient object; the plan's original open question (rev 2 §16) is resolved: K2 v1 ships
  without any usage/security log for endpoint #2. Revisiting this later (e.g. for security
  monitoring) is a separate, later decision, not tracked as an open item in this plan anymore.

---

## 12. Threat model — Broken Object-Level Authorization (BOLA)

This section exists because §4 states plainly that `require_roles` alone is insufficient —
this is the concrete threat that requirement defends against (OWASP API Security Top 10,
API1:2023 — Broken Object Level Authorization).

**Attack scenario:** An authenticated `PATIENT`-role user enumerates or guesses another
patient's `medication_id` values against endpoint #1. Even though the *knowledge content*
returned is generic (identical for every patient on that ingredient), the **fact of
association** — "this `medication_id` resolves to ingredient X" — is itself condition-adjacent
PHI (per `MEDICATION_RBAC_AND_PRIVACY.md` §6.1, active ingredient / drug class is HIGH/MEDIUM
PHI, "reveals condition"). A BOLA vulnerability here would let one patient learn what class of
medication another patient is on.

**Mitigation:**
- Mandatory object-level check, evaluated immediately after the role check and *before* any
  ingredient resolution: `medication_id` must resolve to a row owned by the authenticated
  caller's own `patient_profile.id`.
- On failure — whether the id doesn't exist at all, or exists but belongs to someone else —
  return the **same** `404` (§8). A split (`403` for "exists but not yours,"  `404` for
  "doesn't exist") would itself leak existence of another patient's record purely from the
  status code, independent of the response body.
- Standard rate limiting (§4) throttles brute-force id enumeration as a second, independent
  layer — not a substitute for the object-level check itself.

**Why endpoint #2 has no BOLA surface:** `drug_ingredient_id` is not owned by any individual
patient — it is a shared reference entity, structurally closer to a public catalog id than to
a per-user object. There is no ownership dimension to check, so `require_roles(DOCTOR)` plus
the verification-status check (§4) is sufficient on its own. **This is exactly why the
patient-specific doctor lookup is deferred** (§2.2): combining doctor-consent access with a
specific patient's medication record would reintroduce a patient-scoped object into the route,
requiring the same class of check as endpoint #1 (does this doctor have active, unrevoked,
unexpired consent for the patient who owns this `medication_id`) — that is a materially
different, harder authorization design than a role check, and is explicitly not designed in
this slice.

**IDOR on citations — closed by construction, not by validation:** because no endpoint
accepts a client-supplied `knowledge_table`/`knowledge_row_id` at all (§2.2, §7), there is no
parameter surface for an insecure-direct-object-reference attack on citations to exploit in
the first place — the mitigation is removing the parameter, not validating it.

---

## 13. Test plan

- **Authorization / BOLA:**
  - Endpoint #1: patient A requests patient B's `medication_id` → `404` (not `403`, proving
    the anti-enumeration design, §12).
  - Endpoint #1: nonexistent `medication_id` → `404`, response indistinguishable from the
    "belongs to someone else" case.
  - Endpoint #1: `DOCTOR`, `CLINIC_ADMIN`, `CAREGIVER`, `INTERNAL_ADMIN`, `SUPER_ADMIN`,
    `AI_SERVICE`, unauthenticated → all `403`/`401` as appropriate (explicit regression test
    per role, not just "any non-patient role" — so a future accidental role addition is
    caught by name).
  - Endpoint #2: `PATIENT`, `CLINIC_ADMIN`, `CAREGIVER`, `INTERNAL_ADMIN`, `SUPER_ADMIN`,
    `AI_SERVICE`, unauthenticated → all `403`/`401`.
  - Endpoint #2: `DOCTOR` with `verification_status == VERIFIED` → `200`, regardless of which
    verified doctor (no patient-context parameter exists to vary — proving the "no PHI, no
    patient context" property, not just asserting it).
  - Endpoint #2: `DOCTOR` with `verification_status == PENDING_VERIFICATION` (and any other
    non-`VERIFIED` value) → `403` — **new regression test (Phase A)**, named specifically so
    a future change that drops this check is caught.
- **Product/ingredient resolution (new, Phase A):**
  - Endpoint #1: medication with `drug_product_id = null` → `200`, all categories
    empty/`null` (§8), never `404`/`500`.
  - Endpoint #1: medication whose `drug_product_id` maps to a combination product (2+ rows in
    `drug_product_ingredients`) → response merges approved content across all mapped
    ingredients, per category (§2.3) — regression test asserting no ingredient's content is
    silently dropped.
- **Locale/audience filter (new, Phase A):** seed one approved `audience='patient'` row and
  one approved `audience='doctor'` row for the same ingredient/business-key-otherwise-equal —
  assert endpoint #1 returns only the patient row's content and endpoint #2 returns only the
  doctor row's, never both, never the wrong one. Same shape for a non-`vi` `locale='en'`
  approved row (if seeded) — asserted absent from both endpoints in v1.
- **Approved-only filter:** draft/clinical_review/deprecated/retired rows never appear, even
  when they share a business key with an approved row (regression guard mirroring K1.6's own
  invariant tests).
- **Not-found vs. empty:** valid target with zero approved rows → `200`, empty/`null`
  categories (§6.3); invalid/foreign `medication_id` → `404` (§8) — both cases covered so they
  can't be confused with each other in review.
- **Vocabulary gate:** schema-introspection test asserting `frequency`/`action_level` are
  **absent as fields**, not merely `null`-valued, on both `PatientMedicationKnowledgeOut` and
  `DoctorIngredientKnowledgeOut` — catches an accidental future re-introduction even before
  the vocabulary ADR exists.
- **Governance-field exclusion:** schema-introspection test asserting `authored_by`,
  `status_changed_by`, `artifact_hash`, and any reviewer-identity field are absent from both
  contracts.
- **Data-integrity fail-closed:** simulated `MultipleApprovedRowsError` on one of the 5
  tables → whole-request `500`, generic body; assert the response is *not* a `200` with the
  other 4 categories populated (proving "no partial response," §8).
- **Provenance invariant:** doctor contract's `references[]` only ever contains citations for
  `row_id`s present in that same response's `side_effects`/`monitoring`/`contraindications`
  lists — no test path can construct a request that fetches citations for an unreturned or
  non-approved row (§7, closed by construction).
- **Caching header:** endpoint #1 response includes the private/no-store directive (§11).
- **Audit:** one PHI-minimized `AuditLog` row per endpoint #1 read; assert the row's fields
  never include content/description/guidance/narrative text. Endpoint #2: assert **no**
  `AuditLog` row is produced (§11 — explicit non-requirement, tested so a future accidental
  addition or removal is a deliberate change, not a silent drift).
- **No AI/frontend regression:** grep guard (same convention as K1/K1.6) — `app/ai` and
  `frontend/src` still have zero references to the 5 knowledge tables after this PR.

---

## 14. Implementation sequence

1. Vocabulary decision documented (§5, Phase B) — `ADR-15-MEDICATION_KNOWLEDGE_EXTERNAL_
   VOCABULARY.md` exists and is approved for implementation by PTH (2026-07-23); this gate is
   cleared (§17).
2. Route + authorization contract reviewed and approved (this document, plus any addendum
   needed to close §16's remaining open questions).
3. Response schema draft + concrete examples (§6) reviewed and approved by Tech Lead/PTH.
4. Error mapping (§8) reviewed and approved.
5. Clinical safety review (recommended, non-blocking per the 2026-07-23 governance decision) —
   disclaimer copy (§10), evidence-level display wording, and confirmation that the patient
   contract's plain-language framing has been checked by whoever owns clinical content review.
   Deferred to post-implementation hardening (§ Governance Decision Update); does not gate
   steps 6-7 below.
6. Explicit, separate PTH GO (§17) — this program's own two-step convention, distinct from the
   governance decision above.
7. **Only then:** implementation — Pydantic schemas → product→ingredient resolution helper
   (§2.1) → object-level authorization dependency (endpoint #1) + verification-status
   dependency (endpoint #2) → route handlers calling `knowledge_retrieval.py` plus the §2.3
   audience/locale filter → tests (§13) → Codex review rounds to 0 P0/P1 (this program's
   standing convention) → merge.

---

## 15. Risks

| Risk | Mitigation |
|---|---|
| Vocabulary ADR (Phase B) treated as optional since v1 omits the fields, silently skipped | §14 lists it as a gate regardless of the omission; §17 restates it as blocking |
| Object-level check on endpoint #1 implemented as an afterthought, or accidentally reuses a role-only dependency | §4/§12 name this as the central authorization requirement, with a named test (§13) proving 404-not-403 behavior specifically |
| Doctor verification-status check silently dropped or bypassed in a future refactor | §13 names a specific regression test for `PENDING_VERIFICATION` → 403 |
| §2.3 audience/locale filter forgotten because `list_current_for_ingredient` "looks like" it already returns exactly the right rows | §1.3 fact 4 documents the gap explicitly; §13 names a specific mixed-audience regression test |
| Combination-product ingredients silently dropped (only "primary" ingredient's content shown) | §2.3 states merge-not-intersect explicitly; §13 names a specific combination-product test |
| Doctor endpoint quietly grows a patient-context parameter later without re-running the BOLA analysis | §2.2/§12 explicitly frame the patient-specific doctor lookup as its own, separately-designed future slice — not an incremental addition to endpoint #2 |
| Caching enabled on endpoint #2 before version-supersession semantics are actually verified sound | §11 explicitly defaults caching off pending separate sign-off |
| Route accidentally becomes the AI context builder's entry point (import creep) | Routes live under `app/api/v1/routes/`, never imported by `app/ai/*`; grep-guard test (§13) |
| Scope creep into frontend/AI wiring under the same PR | §2.2 explicit exclusions; Codex review gate should check `frontend/`/`app/ai` diffs are empty |
| Building against zero real approved content makes the routes effectively untestable end-to-end | Accepted — synthetic fixtures are sufficient for K2's own test suite (§13); a real staging smoke test waits for Phase 4 content |

---

## 16. Open questions

- Exact safety-notice copy (Vietnamese, both patient and doctor variants) — needs a clinical/
  product-content pass, not authored by this plan.
- Vietnamese display labels for `frequency` and `evidence_level` codes — needs a content-team
  pass; not invented by this plan or by ADR-15 (ADR-15 Open Questions).
- Field-required-by-item-type matrix for `action_level` (§5, ADR-15 §C) — must exist before
  any `action_level`-bearing response-field code is written; not authored by this plan.
- Future patient-specific doctor lookup shape (§2.2/§12) — explicitly deferred, not designed
  here.
- Future batch endpoint shape/limits (§9) — directions documented, not decided in full.

**Closed in this revision (previously open):** endpoint #2 audit logging (§11 — decided: no),
doctor verification threshold (§4 — decided: `VERIFIED` required), endpoint identifier
(§2.1/§1.3 — decided: `medication_id`, not `medication_statement_id`), endpoint naming
consistency (§2.1 — decided: both `.../{id}/knowledge`), product→ingredient resolution
mechanics (§1.3/§2.1/§2.3), locale/audience filtering (§2.3).

**Closed by ADR-15, PTH decision, and unblocked for implementation (2026-07-23 governance
decision, see §17 gate 1):** vocabulary ADR format and existence (§5 — resolved: standalone
ADR, `ADR-15-MEDICATION_KNOWLEDGE_EXTERNAL_VOCABULARY.md`, approved for implementation by PTH),
the six per-field vocabulary classifications and canonical code lists (§A–§F), `evidence_level`
DB-constraint timing (§D — decided: not in K2 v1), `knowledge_vocabulary_version` placement and
scope (§H — decided: response-envelope level, initial `"1.0"`), and whether a GRADE-style tier
belongs inside `evidence_level` (§D — decided: no, `evidence_quality` reserved as a separate
future field). **These are both product-decision closures and implementation clearances** — the
corresponding response-field code is unblocked; Clinical Advisor, Legal, and Tech Lead review
are recommended, non-blocking future reviews (ADR-15 § Recommended Future Reviews), required
before Release Stage 3 (broad patient production release), not before coding.

---

## Governance Decision Update (2026-07-23)

**PTH changed the governance decision for Medication K2.** The product strategy is to build
the full AI and medication-knowledge capability using currently available sources, then
progressively review, clean, constrain, and govern it — rather than waiting for Clinical
Advisor or Legal sign-off before implementation. This section is the operational counterpart,
for this plan's scope, of `ADR-15-MEDICATION_KNOWLEDGE_EXTERNAL_VOCABULARY.md` § Governance
Decision (§K) — read that section for the full rationale and the fields/mechanics it
specifically governs.

**Unblocked for implementation, effective 2026-07-23:** `evidence_level`, `theme`,
`source_type`, `patient_context`, `condition_type` response-field code (this document, §5-§6);
medication knowledge ingestion; AI normalization; AI synthesis; doctor-facing knowledge
responses; patient-facing knowledge responses behind feature flags. **Unchanged, excluded from
K2 v1 by an independent scope decision:** `frequency`, `action_level` (§5) — unless a separate
approved implementation slice explicitly adds them. This document's own endpoints (§2) remain
retrieval-only over already-approved content; medication knowledge ingestion, AI normalization,
and AI synthesis are separate implementation slices that this governance update authorizes to
proceed but does not itself design — each requires its own implementation plan, which must
conform to the controls below.

**Mandatory reversible controls (feature flags) — required for any of the above before it is
enabled anywhere:**

- medication knowledge retrieval
- external-source ingestion
- AI synthesis
- doctor-facing AI content
- patient-facing AI content
- experimental vocabulary fields (`evidence_level`, `theme` — ADR-15 §A)

Each flag must be independently controllable. **Disabling a flag must stop new processing and
suppress API/UI exposure for that capability, without deleting stored knowledge or
provenance.**

**Provenance (non-negotiable) — every knowledge item and AI-generated output must preserve:**
exact source identity; source URL or stable identifier; publication date (when available);
retrieval date; source/version metadata; the relevant citation or source span; normalization
version; model identifier and prompt/template version and generation timestamp (for
AI-generated content); review status; supersession/deprecation history. This plan's own §7
Provenance invariant governs citation-lookup construction for the two read endpoints; ADR-15
§K.2 and this list govern the full record shape ingestion/normalization/synthesis must persist.
**AI-generated content must never overwrite raw source content.** Raw source data, normalized
knowledge, AI synthesis, reviewed content, and patient-display content are separate layers,
never collapsed into one mutable field.

**Origin and review state — every response and stored record must distinguish:**
source-extracted vs. rule-derived vs. AI-synthesized content (origin), and unreviewed vs.
reviewed vs. rejected vs. deprecated (review state). **Experimental or unreviewed AI content
must never be represented as clinician-verified** — in response payloads, UI copy, or logs.

**Safety boundary.** AI may retrieve, summarize, explain, compare sources, identify conflicts,
and generate review suggestions. **Without a separate, explicit approval, AI must not
autonomously:** stop or change a medication; change a dosage; replace a prescribed medication;
declare a serious interaction safe; determine that medical evaluation is unnecessary; or
suppress or downgrade serious safety warnings. This boundary holds regardless of which feature
flags above are enabled.

**Release stages** (ADR-15 §K.5): (1) Implementation approval — approved by PTH, 2026-07-23,
this section and ADR-15 §K; (2) Internal experimental release — requires technical tests,
provenance integrity verification, observability, feature flags, and kill-switch verification,
all passing; (3) Broad patient production release — separately controlled by PTH; clinical,
legal, and content hardening may be required before expansion. Reaching Stage 2 does not imply
Stage 3 is automatically approved.

---

## 17. Implementation gates

**Before any route, schema, service, migration, frontend, or test code is written:**

1. **Vocabulary ADR** (§5, Phase B) — **FULLY CLEARED 2026-07-23**:
   `ADR-15-MEDICATION_KNOWLEDGE_EXTERNAL_VOCABULARY.md` is **APPROVED FOR IMPLEMENTATION BY
   PTH — clinical and legal governance deferred** (ADR-15 § Approval Record, § Governance
   Decision). Response-field implementation for `evidence_level`, `theme`, `source_type`,
   `patient_context`, and `condition_type` is **unblocked**. Clinical Advisor, Legal, and Tech
   Lead review are recommended, non-blocking future reviews (ADR-15 § Recommended Future
   Reviews) required before Release Stage 3, not before coding. `frequency`/`action_level`
   remain excluded from K2 v1 regardless (ADR-15 §B/§C, an independent scope decision), and
   `action_level`-bearing item types additionally need the field-required-by-item-type matrix
   (ADR-15 §C) whenever that exclusion is later lifted.
2. **Route and authorization contract approved** — this document (§2-§4, §12), including the
   object-level-authorization requirement for endpoint #1 and the verification-status
   requirement for endpoint #2.
3. **Response examples approved** (§6) — concrete patient and doctor payload shapes (now
   drafted in full, §6.1/§6.2) signed off, including the empty-category and citation-bounding
   decisions.
4. **Error mapping approved** (§8).
5. **Clinical safety review** (§10, §14 step 5) — recommended, non-blocking per the
   2026-07-23 governance decision (§ Governance Decision Update); deferred to
   post-implementation hardening (Release Stage 3), does not gate this document's coding gate.
6. **Explicit, separate PTH GO** — per EC-08's own requirement and this program's standing
   two-step gate. Distinct from, and not satisfied by, the 2026-07-23 governance decision above.

**This document alone does not satisfy gates 2, 3, 4, or 6 above.** It is the artifact those
gates are performed against — they still require separate, recorded sign-off. Gate 1 (vocabulary
ADR) is fully cleared as of 2026-07-23. Gate 5 (clinical safety review) is no longer a
precondition for gates 2-4 or 6. Per PTH's Phase A/B/C roadmap: this revision is Phase A's
output; **Phase B (vocabulary ADR) is fully cleared**, superseding the prior "PTH sub-gate
cleared but not fully cleared" framing; Phase C (Codex review of this document to READY FOR
IMPLEMENTATION) is still outstanding before gate 6 (PTH GO) can be sought.

---

## Revision summary

### Revision 7 (this revision) — Compatibility migration + final hardening round

Closes the four remaining pre-merge findings from the 2026-07-23 final
hardening round, on top of Revision 6's schema correction:

1. **`evidence_level` PostgreSQL incompatibility — FIXED, not just
   documented.** Migration `k2_s1_widen_evidence_level` widens
   `evidence_level` from `VARCHAR(16)` to `VARCHAR(32)` on all 5 knowledge
   tables (additive, no rename, no vocabulary change, no default change).
   This is a **K1/ADR-13 schema compatibility prerequisite that K2 Slice
   1's own PostgreSQL verification gate discovered**, not an AI/
   ingestion/provenance scope expansion — §2.1's "Migration: None" claim
   is corrected above to make this distinction explicit: K2 Slice 1's own
   endpoints still add no migration; the vocabulary they read now needs
   one that predates K2 entirely. Downgrade refuses (raises `RuntimeError`)
   rather than silently truncating if any persisted value would no longer
   fit — verified on both PostgreSQL and SQLite, plus a dedicated
   migration test file
   (`tests/integration/test_medication_k2_widen_evidence_level_migration.py`)
   and a regression test proving the existing K1.5 approval path
   (`approve_row`) accepts both long ADR-15 §D values end-to-end on
   Postgres.
2. **Doctor authorization hardened.** `require_verified_doctor`
   (`app/api/deps_medication_knowledge.py`) now requires both
   `verification_status == VERIFIED` **and** `Doctor.is_active == True`,
   matching the established defense-in-depth pattern already used by
   `consultation.py`/`consultation_access.py` for the same threat model
   (a suspended/deactivated doctor must not retain clinical-content
   access). Same generic 403 regardless of which check fails.
3. **Reference-loading N+1 removed.** `build_doctor_response`
   (`app/services/medication_knowledge_response.py`) now batch-loads
   references once per category (`side_effects`/`monitoring`/
   `contraindications`) via K1.6's existing `list_references_for_batch`,
   instead of calling `list_references_for` once per approved row inside
   each response-list comprehension. Deterministic ordering, response
   schema, and field-level fail-soft behavior are all unchanged — only the
   query count changed. Proven by a live query-count regression test
   (`tests/test_medication_knowledge_routes.py`,
   `TestReferenceQueryCountDoesNotScaleWithRowCount`), not just code
   inspection.
4. **Rate-limit identity — documented as an open follow-up, explicitly not
   fixed.** `docs/medication-management/
   MEDICATION_K2_FOLLOWUP_RATE_LIMIT_IDENTITY.md` records that
   `enforce_rate_limit` (pre-existing, unmodified) keys on client IP, not
   authenticated principal identity, for both of K2 Slice 1's endpoints —
   per PTH's explicit instruction, this round does not redesign the
   app-wide rate limiter.

No AI, ingestion, or frontend scope was added by any of the four items
above. `frequency`, `action_level`, and
`medication_knowledge_import/schema.py`'s `ai_generated: Literal[False]`
remain untouched.

### Revision 6 (carried over) — Corrected §1.3 fact 4: locale/audience exist on only 2 of 5 tables

**Documentation defect found and corrected 2026-07-23, during K2 Slice 1 pre-merge review
(Gate 2).** Verified directly against `app/models/drug_knowledge_content.py` while implementing
and then reviewing Slice 1: revision 3's §1.3 fact 4 claimed "`locale`/`audience`... are part
of the 5 knowledge tables' business key" — this was wrong. Only `DrugUsage` and
`DrugPatientEducation` have `locale`/`audience` columns. `DrugSideEffect`, `DrugMonitoring`,
and `DrugContraindication` have neither column at all; their business keys never included
`locale`/`audience` and never claimed to elsewhere in this document except via this one wrong
general statement.

No route, schema, service, migration, frontend, or test code was written or changed as part of
this documentation revision — only the factual corrections below:

- §1.3 fact 4 rewritten to state which 2 of 5 tables actually carry `locale`/`audience`, and to
  explicitly forbid treating a missing column as an implicit `"vi"`/`"patient"` default or
  inferring a value that doesn't exist on the row.
- §1.1's function-table row for `list_current_for_ingredient` updated to name the 2 tables.
- §2 (Objective) and §2.1 (both endpoints' resolution steps) updated to state the filter
  applies only to `usage`/`patient_education`, not uniformly to all 5 categories.
- §2.3 rewritten: the filter pseudocode is now conditional on `model_cls`, and a new paragraph
  explains why `DrugSideEffect`/`DrugMonitoring`/`DrugContraindication` correctly need no
  filter (no audience-specific duplicate can exist without an `audience` column) rather than
  being an accepted gap.
- §6.1/§6.2 response-contract descriptions updated from "all rows filtered to locale/audience"
  to name which categories are filtered and which are not.

This correction does not change ADR-15 — ADR-15 governs vocabulary content
(`evidence_level`/`theme`/`source_type`/`patient_context`/`condition_type`), not the
`locale`/`audience` schema fact this revision corrects, and nothing in ADR-15 asserts or
depends on the now-corrected claim.

### Revision 5 (carried over) — Governance decision update: implementation unblocked

PTH changed the governance decision for Medication K2 (2026-07-23, same day as revision 4):
implementation no longer waits for Clinical Advisor, Legal, or Tech Lead review. This revision
reflects that decision, without writing any route, schema, service, migration, frontend, or
test code:

- Header status updated to record the governance change and distinguish it from this program's
  separate explicit-PTH-GO convention (§17 gate 6), which still applies.
- New § Governance Decision Update section added: unblocked-capability list, mandatory
  reversible controls (feature flags), provenance non-negotiables, origin/review-state
  distinctions, the AI safety boundary, and the three release stages — mirroring
  `ADR-15-MEDICATION_KNOWLEDGE_EXTERNAL_VOCABULARY.md` §K for this document's scope.
- §5 updated: ADR-15 cited as "APPROVED FOR IMPLEMENTATION BY PTH — clinical and legal
  governance deferred"; response-field implementation for the five ADR-15-governed fields
  described as unblocked, not blocked; Clinical Advisor/Tech Lead reframed as recommended,
  non-blocking future reviews.
- §14 step 1 (vocabulary decision) marked cleared; step 5 (clinical safety review) marked
  recommended/non-blocking, deferred to post-implementation hardening.
- §16 "Closed by ADR-15" paragraph updated: these are now both product-decision closures and
  implementation clearances.
- §17 gate 1 marked FULLY CLEARED; gate 5 marked recommended/non-blocking; the "does not
  satisfy" paragraph updated to drop gate 1 and gate 5 from the still-blocking list.
- "Remaining blockers" updated: item 1 (vocabulary ADR) resolved; item 4's Clinical
  Advisor/Tech Lead sign-off dependency removed (only the VN-labels and item-type-matrix
  deliverables remain, and neither blocks coding).

No route, schema, service, migration, frontend, or test code was written or changed as part of
this revision.

### Revision 4 (carried over) — ADR-15 vocabulary lock applied

Phase B's PTH product-decision sub-gate cleared: `ADR-15-MEDICATION_KNOWLEDGE_EXTERNAL_VOCABULARY.md`
Approved by PTH on 2026-07-23 — Clinical Advisor and Tech Lead sign-off still pending, not yet
recorded (this was revision 4's state; see revision 5 above for the same-day governance update
that superseded it). This revision reflects ADR-15's PTH-approved decisions, without
implementing any of them and without claiming sign-off that has not happened:

- §5 now cites ADR-15 by name instead of "the vocabulary ADR above"; locked the future
  `side_effect_frequency` external field name for `frequency` and the "no DB rename" decision.
- §6.1/§6.2 gained `knowledge_vocabulary_version` (envelope-level, initial `"1.0"`) in both the
  shape description and every JSON example; `evidence_level`/`theme` annotated as
  ADR-15-locked/experimental; `patient_context`/`condition_type` annotated as opaque internal
  authoring keys with no vocabulary-stability guarantee; `references[].source_type`
  disambiguated from the unrelated `medications.source_type` (ADR-04).
- §8 gained two new rows: field-level fail-soft for out-of-vocabulary `evidence_level`/
  `theme`/`source_type`, and item-scoped fail-closed (never whole-request) for invalid
  `action_level`, with mandatory PHI-free telemetry.
- §16 removed the now-resolved "vocabulary ADR format" question; added the two still-open
  ADR-15-required deliverables (VN labels, field-required-by-item-type matrix).
- §17 gate 1 marked cleared, citing ADR-15 by name and status.
- "Remaining blockers" updated to reflect gate 1 cleared and the two outstanding deliverables.

No route, schema, service, migration, frontend, or test code was written or changed as part
of this revision.

### Revision 3 (carried over) — Phase A "Plan Fix Round"

Closed 8 named gaps, all verified directly against `app/models/`/`app/services/`:

- **Endpoint identity:** unified both routes to a `.../{id}/knowledge` naming shape (§2.1).
- **Statement vs medication:** endpoint #1 now keys off canonical `medication_id`
  (`medications.id`), not `medication_statement_id` — `medication_statements` is a raw,
  append-only edit log with potentially many rows per canonical medication, not a stable
  patient-facing identifier (§1.3 fact 1, §2.1).
- **Product→ingredient:** documented as many-to-many via `drug_product_ingredients`
  (combination products), with both `Medication.drug_product_id` and
  `MedicationStatement.drug_product_id` being nullable and *not* DB-enforced FKs (§1.3 facts
  2-3); added explicit resolution steps and a null/unmatched-product → 200-empty rule (§2.1,
  §8) and a merge-not-intersect rule for combination products (§2.3).
- **Locale:** documented that `list_current_for_ingredient` does not filter by `locale`, and
  added an explicit route-layer filter to `locale='vi'` (§1.3 fact 4, §2.3).
- **Audience:** same gap and fix for `audience` — route-layer filter to `patient`/`doctor`
  per endpoint, preventing doctor-audience content leaking to patients or vice versa (§2.3).
- **Doctor auth:** added a `verification_status == VERIFIED` requirement on endpoint #2
  (PTH decision), on top of the existing role check (§4).
- **Audit:** closed the rev-2 open question — endpoint #2 will not be audit-logged in v1
  (PTH decision) (§11).
- **Response examples:** added full concrete JSON examples for both contracts' success,
  empty, and 404 cases (§6.1, §6.2), satisfying gate 3's "concrete... signed off" requirement
  in substance (still needs the actual sign-off).

### Revision 2 (carried over)

- Replaced the single ambiguous `GET /medications/{id}/knowledge` endpoint with two narrow,
  role-specific endpoints (§2.1).
- Made object-level authorization the central authorization requirement for the patient
  endpoint, with a dedicated BOLA threat-model section (§4, §12).
- Took `CAREGIVER` fully out of scope; removed implicit `INTERNAL_ADMIN`/`SUPER_ADMIN` access.
- Turned the side-effect vocabulary mismatch into a named, blocking pre-implementation gate
  (§5), later formalized as Phase B of PTH's roadmap.
- Split the single response schema set into separate patient and doctor contracts (§6).
- Tightened the provenance invariant into a closed-by-construction guarantee (§7).
- Added a full error-semantics table (§8), a caching/privacy/audit section (§11), and the BOLA
  threat-model section (§12).
- Expanded the test plan (§13) and replaced the informal verdict with a six-item implementation
  gate list (§17).

## Remaining blockers (as of the 2026-07-23 governance update)

1. ~~Vocabulary ADR (§5, Phase B) does not exist yet~~ — **FULLY CLEARED 2026-07-23**:
   `ADR-15-MEDICATION_KNOWLEDGE_EXTERNAL_VOCABULARY.md` exists and is approved for
   implementation by PTH (§17 gate 1, ADR-15 § Approval Record). Clinical Advisor, Legal, and
   Tech Lead review remain outstanding but are recommended, non-blocking future reviews — they
   no longer block response-field implementation for the five fields ADR-15 governs.
2. This document itself has not yet been through Tech Lead or Codex review — that review is
   Phase C (gates 2-4 in §17), not satisfied by drafting, even with Phase A's gaps closed and
   Phase B fully cleared.
3. No PTH GO has been given for implementation — explicitly required (§17 gate 6) before any
   code is written. This is this program's own explicit-GO convention, distinct from and not
   satisfied by the 2026-07-23 governance decision.
4. One ADR-15-related pre-implementation deliverable remains outstanding and gates
   `action_level`-bearing work specifically (not the other four ADR-15-governed fields, which
   are unblocked): the field-required-by-item-type matrix for `action_level` (§5, ADR-15 §C).
   Vietnamese display labels for `frequency`/`evidence_level` codes (content-team task) remain
   outstanding but are a content deliverable, not a code blocker.
5. Open questions in §16 (safety-notice copy, future batch/doctor-patient-lookup shapes) are
   unresolved and do not block starting implementation once gates 1-4 and 6 clear, but should
   be tracked so they aren't silently forgotten.

**No route, schema, service, migration, frontend, or test code has been written. No commit,
no PR. Stopping at this planning checkpoint per instruction. Phase B (vocabulary ADR, ADR-15)
is fully cleared — PTH's 2026-07-23 governance decision unblocked response-field implementation
for the five fields ADR-15 governs, ahead of Clinical Advisor, Legal, and Tech Lead review,
which are now recommended, non-blocking future reviews (ADR-15 § Recommended Future Reviews;
§ Governance Decision Update above). Next: Phase C (Codex review of this document to READY FOR
IMPLEMENTATION) and this program's own explicit PTH GO (§17 gate 6) — both still outstanding
and unaffected by the governance update.**
