# T4 Implementation Report — MetoCare Medical Domain
> Executor: Antigravity (agy) + OpenClaw coordinator (lint/test fix pass)
> Date: 2026-06-17 13:45 GMT+7
> Branch: feature/t4-medical-domain
> Status: COMPLETE — awaiting Claude Code review + PTH approval before merge

---

## Verification Results

```
python -c "from app.models import *; from app.schemas import *; print('IMPORT_OK')"
→ IMPORT_OK

ruff check . → All checks passed! (RUFF_OK)

pytest → 161 passed, 1 skipped, 1 warning in 5.02s
         (was 140 before T4 — 21 new tests added)
```

---

## Files Created

### Core infrastructure
| File | Purpose |
|---|---|
| `app/core/feature_flags.py` | Feature flag registry (StrEnum), env-driven, fail-closed |
| `app/core/clinical_thresholds.py` | Config-driven clinical threshold loader (YAML + env vars) |
| `app/config/clinical_thresholds.yml` | Default threshold config (all marked PROPOSED_THRESHOLD) |

### Models
| File | What changed |
|---|---|
| `app/models/ai.py` | **Replaced** `AIConversation` with `AISession` + `AIClinicalRecommendation`; `AIConversation = AISession` compat alias |
| `app/models/care.py` | Added `DoctorClinic` junction, `Encounter`, `CarePlan`, `BookingHealthSnapshot`; extended `Doctor`/`Clinic` fields |
| `app/models/_mixins.py` | Added `SoftDeleteMixin` (`deleted_at`, `deleted_by`) |
| `app/models/clinical.py` | Added `SoftDeleteMixin` to `LabResult`, `Medication` |
| `app/models/user.py` | Added `UserRole.AI_SERVICE = "ai_service"` |
| `app/models/__init__.py` | Updated exports for all new models |

### Services
| File | Purpose |
|---|---|
| `app/services/consent_guard.py` | `ConsentGuard.require()` — single choke point for PHI access; same path for human + AI_SERVICE; audit on deny; feature-flag aware |
| `app/services/doctor_review.py` | `DoctorReviewService` — submit/review/queue; DOCTOR-only review; hard-blocked safety_cleared; AuditLog on every transition |

### Domain
| File | What changed |
|---|---|
| `app/domain/policies.py` | Moved clinical thresholds + symptom keywords to `clinical_thresholds.py`; `RED_FLAG_VITAL_THRESHOLDS` + `RED_FLAG_SYMPTOMS` now config-driven via re-export |

### Schemas
| File | What added |
|---|---|
| `app/schemas/care.py` | `EncounterCreate/Out/Update`, `CarePlanCreate/Out/Update/Approve` |
| `app/schemas/clinical.py` | `AISessionOut`, `AIClinicalRecommendationOut/Review` |
| `app/schemas/__init__.py` | Updated exports |

### Migrations (files only — do NOT run `alembic upgrade` without TimescaleDB/Postgres verified)
| Migration | Action |
|---|---|
| `t4_m1_ren_conv` | Rename `ai_conversations` → `ai_sessions`; `intent` → `session_type`; **B3 fix**: adds `ai_use` to `consent_type` |
| `t4_m2_ext_sess` | Extend `ai_sessions` with encounter_id, escalation fields, soft-delete, key_version |
| `t4_m3_add_recs` | Create `ai_clinical_recommendations` table |
| `t4_m4_add_encs` | Create `encounters` table |
| `t4_m5_add_cpln` | Create `care_plans` table |
| `t4_m6_add_bksp` | Create `booking_health_snapshots` table |
| `t4_m7_add_junc` | Create `doctor_clinic` junction; backfill from `doctor.clinic_id` |
| `t4_m8_ext_drcl` | Extend `doctors` and `clinics` with new fields |
| `t4_m9_add_sdel` | Add soft-delete columns to `lab_results`, `medications` |

### Tests (21 new tests)
| File | Coverage |
|---|---|
| `tests/unit/test_feature_flags.py` | Flag defaults, env override, fail-closed for unknown flag |
| `tests/unit/test_consent_guard.py` | No consent → 403; expired → 403; AI_SERVICE same path, no bypass |
| `tests/unit/test_doctor_review.py` | Submit RBAC; doctor review accept/reject; supersedes; pending queue |
| `tests/unit/test_soft_delete.py` | Soft-delete sets timestamp; default queries exclude deleted |
| `tests/unit/test_clinical_thresholds.py` | Config-driven load; all proposed=True by default |
| `tests/unit/test_recommendation_status.py` | Status machine; AI cannot set accepted; illegal transitions blocked |
| `tests/integration/test_consent_gate_ai_path.py` | AI service hits same ConsentGuard, no bypass |

---

## PTH Conditions — Verification

| Condition | Status | Detail |
|---|---|---|
| AI triage production DISABLED | ✅ | `FeatureFlag.AI_TRIAGE` default=False; `FeatureFlag.AI_SAFETY_LAYER` default=False |
| B3: `ai_use` in first migration | ✅ | M1 adds `ai_use` to `consent_type` allowed values |
| Thresholds config-driven | ✅ | `app/config/clinical_thresholds.yml` + env vars; all `proposed=True, board_approved=False` |
| AIClinicalRecommendation doctor review | ✅ | `DoctorReviewService.review()` DOCTOR-only; RBAC hard-blocked for all others |
| All AI features behind feature flags | ✅ | 4 AI flags all default=False; `CONSENT_GATE` + `DOCTOR_REVIEW_GATE` always=True |

---

## Deviations from Task Card

| Item | Deviation | Reason |
|---|---|---|
| M2: FK constraints | SQLite-gated (skipped on SQLite) | SQLite `batch_alter_table` reflection fails when referenced table absent during `downgrade base` |
| M3/M4/M5/M6: Index drops in downgrade | SQLite-gated | Same reason — SQLite drops indexes with table |
| `UserRole.AI_SERVICE` added | Not in original task card | Required by `DoctorReviewService` and tests to represent AI service actor |
| Ruff/test fixes | Post-agy pass by coordinator | Agy timed out before running final checks; 19 ruff errors + 5 test failures fixed |

---

## Items NOT Implemented

| Item | Reason |
|---|---|
| M_data (M3_encrypt_messages) — plaintext→ciphertext backfill | T4 task card explicitly deferred this. Requires tested decrypt path + backup (Blueprint R6). Marked as TODO in M2. |
| Alembic upgrade run | Task card instructs write files only. T2 (TimescaleDB verify) must pass first. |
| API endpoints for Encounter/CarePlan/AISession | Not in T4 scope — T5 task |
| `drop_doctor_clinic_id_column` | Phase 2 destructive migration — deferred to separate release after code verified |

---

## Risks flagged for Claude Code review

1. **`UserRole.AI_SERVICE` addition** — new enum value in the DB. Needs a migration to update the Enum type on Postgres (SQLite is flexible). Migration M1 or a new M0 may need to handle this.
2. **M2 FK on `encounter_id`** is skipped on SQLite but will be enforced on Postgres. Ensure M4 (encounters) runs before M2 in any partial migration scenario — chain order is `M1→M2→M3→M4` which keeps the FK safe only if all four run together.
3. **`DOCTOR_REVIEW_GATE` fail-closed behavior** means tests must mock the flag. Ensured in `test_recommendation_status.py` via `patch`.
4. **`RED_FLAG_SYMPTOMS` config keys** must exactly match keywords used in `triage.py` string matching — any rename in the YAML breaks triage detection. A contract test should validate this.

---

*End of T4_ANTIGRAVITY_REPORT.md — 2026-06-17 13:45 GMT+7*
*Branch: feature/t4-medical-domain*
*161 tests pass. Ruff clean. Import OK.*
*Ready for Claude Code RBAC/Consent/AI Safety/Medical Governance review.*
