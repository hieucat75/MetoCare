# T4 Task Card — Medical Domain Implementation
> Task ID: METOCARE-T4-001
> Date: 2026-06-17 12:21 GMT+7
> Authorized by: PTH
> Executor: Antigravity (agy)
> Reviewer: Claude Code (read-only gate: RBAC, Consent, AI Safety, Medical Governance)
> Branch: feature/t4-medical-domain
> Base: main (HEAD: 24cd593)

---

## PTH CONDITIONS (non-negotiable)

1. **AI triage production remains DISABLED** — all AI safety features behind feature flags
2. **B3 fix in first migration** — add `ai_use` to `Consent.consent_type`
3. **Thresholds must be configuration-driven** — no hardcoded clinical values
4. **AIClinicalRecommendation requires mandatory doctor review workflow**
5. **All AI safety features behind feature flags until Medical Board approval**

---

## Scope

Implement the Medical Domain layer as defined in:
- `docs/agent/MEDICAL_SAFETY_PACKAGE.md` (entity split, RBAC, safety matrix, escalation, red flags)
- `docs/agent/BLUEPRINT_REVIEW_RESPONSE.md` (Q1–Q8 design decisions)
- `docs/MEDICAL_DOMAIN_BLUEPRINT.md` (full domain context)

**DO NOT** generate or run migrations against a live database — write migration files only.
**DO NOT** modify existing passing tests — add new tests alongside.
**DO NOT** commit directly to main — all work on `feature/t4-medical-domain`.
**DO NOT** hardcode any clinical threshold — use `app/core/config.py` or a config-driven mechanism.

---

## Implementation sequence (in order)

### Step 1 — Feature flag infrastructure

File: `app/core/feature_flags.py`

Create a simple, config-driven feature flag registry.

```python
class FeatureFlag(str, enum.Enum):
    AI_TRIAGE         = "ai_triage"           # DISABLED until Medical Board approval
    AI_LAB_INTERPRET  = "ai_lab_interpret"    # DISABLED until Medical Board approval
    AI_CARE_PLAN_DRAFT = "ai_care_plan_draft" # DISABLED until Medical Board approval
    AI_SAFETY_LAYER   = "ai_safety_layer"     # DISABLED until Medical Board approval
    DOCTOR_REVIEW_GATE = "doctor_review_gate" # ENABLED (mandatory)
    CONSENT_GATE      = "consent_gate"        # ENABLED (mandatory)
```

- Read from env vars: `FEATURE_<FLAG_NAME>=true|false`
- Default: all AI features OFF; consent + doctor review gates always ON
- Provide `is_enabled(flag: FeatureFlag) -> bool` helper
- Guards must fail closed (unknown flag = disabled)

---

### Step 2 — Clinical threshold configuration

File: `app/core/clinical_thresholds.py`

Move ALL clinical thresholds out of `policies.py` into a config-driven module:

```python
@dataclass
class VitalThreshold:
    metric_type: str
    critical_high: float | None
    critical_low: float | None
    unit: str
    source: str           # e.g. "ADA 2024", "AHA 2023"
    board_approved: bool  # False until Medical Board signs off
    proposed: bool        # True = PROPOSED_THRESHOLD

# Load from: env vars > app/config/clinical_thresholds.yml > hardcoded defaults
# NO hardcoded production thresholds — every value must be marked proposed=True
# until board_approved=True is explicitly set via config
```

Red flag symptom lists also move here (from `policies.py`) — same config-driven pattern.

---

### Step 3 — Models: AISession + AIClinicalRecommendation

File: `app/models/ai.py` — **replace** existing `AIConversation` with the two new models.

**Keep `AIConversation` as a compatibility alias** (`AIConversation = AISession`) until migration M1 runs on a real DB. This preserves existing test references.

`AISession` fields: see `MEDICAL_SAFETY_PACKAGE.md §1.2`
`AIClinicalRecommendation` fields: see `MEDICAL_SAFETY_PACKAGE.md §1.3`

Status machine for `AIClinicalRecommendation`:
```python
class RecommendationStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    REVIEWED       = "reviewed"
    ACCEPTED       = "accepted"
    REJECTED       = "rejected"
    SUPERSEDED     = "superseded"
```

---

### Step 4 — Models: Encounter + CarePlan + BookingHealthSnapshot

File: `app/models/care.py` — new models per Blueprint Q1, Q2, Q4

`Encounter`:
- Fields: id, patient_id, doctor_id (nullable), appointment_id (nullable FK), encounter_type,
  status (pending_review/in_progress/completed/cancelled), chief_complaint, notes (EncryptedString),
  encounter_date, deleted_at, deleted_by, created_at, updated_at

`CarePlan`:
- Fields: id, patient_id, encounter_id (nullable), title, content (EncryptedString), status
  (DRAFT/PENDING_REVIEW/APPROVED/ACTIVE/SUPERSEDED/ARCHIVED/REJECTED),
  approved_by_doctor_id (nullable), approved_at (nullable), ai_generated (bool),
  version (int, default 1), deleted_at, deleted_by, created_at, updated_at
- Status machine: DRAFT→PENDING_REVIEW→APPROVED→ACTIVE. DRAFT→ACTIVE: hard-blocked.
- AI may only create DRAFT with ai_generated=True.

`BookingHealthSnapshot`:
- Fields: id, appointment_id FK, patient_id FK, payload (EncryptedString), created_at
- Append-only: NO update path at service layer

---

### Step 5 — Models: doctor_clinic junction + Doctor/Clinic extensions

File: `app/models/care.py` (or existing `_clinic.py` if it exists)

`doctor_clinic` association table:
- doctor_id FK, clinic_id FK, role_at_clinic (str), is_primary (bool), is_active (bool),
  joined_at (Date), left_at (Date nullable)
- Composite PK (doctor_id, clinic_id)

Doctor additional fields: bio, avatar_url, consultation_fee, is_verified, is_active
Clinic additional fields: email, specialty_tags, operating_hours, is_active, is_verified

---

### Step 6 — Soft-delete mixin

File: `app/models/_mixins.py`

Add `SoftDeleteMixin`:
```python
class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
```

Apply to: Encounter, CarePlan, AISession, AIClinicalRecommendation, LabResult (if not already soft-deleted), Medication

---

### Step 7 — ConsentGuard service

File: `app/services/consent_guard.py`

```python
class ConsentGuard:
    def require(
        self,
        patient_id: str,
        consent_type: str,          # "ai_use", "data_sharing", etc.
        data_scope: str,
        actor_id: str,
        actor_type: str = "user",
    ) -> None:
        """Raises ConsentDenied (→ HTTP 403) if no active matching Consent.
        Always writes AuditLog(outcome=denied) on failure.
        Always writes AuditLog(outcome=success, severity=info) on pass.
        """
```

- Single reusable dependency — inject into any service that reads patient PHI or calls AI
- Same code path for human actors AND AI_SERVICE actor_type (no bypass)
- Feature flag `CONSENT_GATE`: if disabled (dev/test only) → skip check but still log warning
- `ConsentDenied` → HTTP 403 with `ErrorResponse(code="CONSENT_DENIED")`

---

### Step 8 — Doctor review workflow service

File: `app/services/doctor_review.py`

```python
class DoctorReviewService:
    def submit_for_review(self, recommendation_id: str, actor: User) -> AIClinicalRecommendation:
        """Set status PENDING_REVIEW. Only AI_SERVICE or SUPER_ADMIN."""

    def review(
        self,
        recommendation_id: str,
        action: Literal["accept", "reject"],
        doctor: User,
        notes: str | None = None,
    ) -> AIClinicalRecommendation:
        """DOCTOR only. Sets status, reviewed_by_doctor_id, reviewed_at, safety_cleared."""

    def get_pending_queue(self, doctor: User) -> list[AIClinicalRecommendation]:
        """Returns pending_review items for doctor's clinics."""
```

- `review()` hard-blocks non-DOCTOR actors — raises `PermissionDenied`
- Sets `safety_cleared=True` only on accept, by doctor
- Writes `AuditLog` for every transition
- Feature flag `DOCTOR_REVIEW_GATE`: always ON in production (fail closed)

---

### Step 9 — Alembic migrations (files only, do not run)

Create migration files in `alembic/versions/`. Use sequential ordering prefix.

**M1** `xxxx_rename_ai_conversations_to_ai_sessions.py`
- Rename table; map `intent` → `session_type`

**M2** `xxxx_extend_ai_session_fields.py`
- Add to ai_sessions: `encounter_id`, `session_type`, `escalation_reason`, `input_blocked`,
  `output_blocked`, `total_tokens`, `key_version`, `deleted_at`, `deleted_by`

**M3** `xxxx_add_ai_clinical_recommendations.py`
- Create `ai_clinical_recommendations` table per §1.3

**M4** `xxxx_add_encounter_table.py`
- Create `encounters` table

**M5** `xxxx_add_care_plan_table.py`
- Create `care_plans` table

**M6** `xxxx_add_booking_health_snapshot.py`
- Create `booking_health_snapshots` table

**M7** `xxxx_add_doctor_clinic_junction.py`
- Create `doctor_clinic` junction table
- Backfill: one row per existing doctor from `doctor.clinic_id` with `is_primary=True`

**M8** `xxxx_extend_doctor_clinic_fields.py`
- Add fields to `doctors` and `clinics` (bio, avatar_url, etc.)

**M9** `xxxx_add_soft_delete_columns.py`
- Add `deleted_at`, `deleted_by` to: encounters, care_plans, ai_sessions,
  ai_clinical_recommendations, lab_results, medications

**⚠️ B3 fix — MUST be in M1 or a standalone first migration:**
- Add `ai_use` to `Consent.consent_type` allowed values

**DO NOT** include M_data (M3_encrypt_messages) — that is a data-touching migration requiring a separate backup/decrypt plan. Leave a `TODO` comment in M2.

---

### Step 10 — Schemas: Encounter, CarePlan, AIClinicalRecommendation

Update `app/schemas/care.py` and `app/schemas/clinical.py` with new models:
- `EncounterCreate`, `EncounterOut`, `EncounterUpdate`
- `CarePlanCreate`, `CarePlanOut`, `CarePlanUpdate`, `CarePlanApprove`
- `AIClinicalRecommendationOut`, `AIClinicalRecommendationReview`
- `AISessionOut`

Update `app/schemas/__init__.py` exports.

---

### Step 11 — Tests

File: `tests/unit/test_feature_flags.py` — flag defaults, fail-closed, env var override
File: `tests/unit/test_consent_guard.py` — no consent → 403; expired → 403; AI_SERVICE same path
File: `tests/unit/test_doctor_review.py` — non-doctor cannot review; AI cannot set accepted; status machine
File: `tests/unit/test_soft_delete.py` — default queries exclude deleted; reviewer can see deleted
File: `tests/unit/test_clinical_thresholds.py` — config-driven load; no hardcoded production values
File: `tests/unit/test_recommendation_status.py` — AI creates only pending_review; illegal transitions blocked
File: `tests/integration/test_consent_gate_ai_path.py` — AI service hits same ConsentGuard, no bypass

All existing 140 tests must continue to pass.

---

## Output expected

After implementation, run:
```bash
python -c "from app.models import *; from app.schemas import *; print('IMPORT_OK')"
ruff check . && echo "RUFF_OK"
pytest --tb=short -q && echo "TESTS_OK"
```

All three must pass. Then output a final report to:
`docs/agent/T4_ANTIGRAVITY_REPORT.md`

Include:
- Files created
- Files modified
- Migration files created (list)
- Test results
- Any deviations from this task card (with reason)
- Items NOT implemented (with reason)

---

## Hard constraints summary

- NEVER hardcode a clinical threshold — use `clinical_thresholds.py` config
- NEVER set `AIClinicalRecommendation.status` to anything other than `pending_review` from AI code path
- NEVER set `safety_cleared=True` from AI code path
- NEVER write a `CarePlan.status=APPROVED` or `ACTIVE` from AI code path
- ALWAYS write AuditLog on ConsentGuard deny
- ALWAYS fail closed on unknown feature flag
- AI_SERVICE uses the same ConsentGuard as human actors — no bypass
- Branch: `feature/t4-medical-domain` only. No commits to main.
