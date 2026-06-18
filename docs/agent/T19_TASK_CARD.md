# T19 Task Card — Triage Log Persistence + History API

**TASK_ID:** T19  
**LABEL:** Triage Log — Model + Migration + Persist + History API + Tests  
**Branch:** `feature/t19-triage-log-api`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

`POST /ai/triage` computes a triage result but does NOT persist it. There is no `TriageLog` model. This sprint adds persistence and a history endpoint — parallel to T13 (metabolic score history).

---

## Scope

### ALLOWED_FILES

- `backend/app/models/triage_log.py` — NEW: `TriageLog` model
- `backend/app/models/__init__.py` — register
- `backend/alembic/versions/t19_add_triage_log.py` — NEW migration
- `backend/app/schemas/triage_log.py` — NEW: `TriageLogOut`, `TriageLogHistoryResponse`
- `backend/app/schemas/__init__.py` — export
- `backend/app/services/triage_log.py` — NEW: `save_triage()`, `get_history()`
- `backend/app/api/v1/routes/ai.py` — persist result after triage for PATIENT callers
- `backend/app/api/v1/routes/patients.py` — new GET history endpoint
- `backend/tests/api/test_triage_log_api.py` — NEW: tests
- `docs/agent/T19_IMPLEMENTATION_REPORT.md` — NEW

### DO NOT TOUCH

- `app/domain/triage.py`
- Other models
- Other routes

---

## Model Design

`backend/app/models/triage_log.py`:

```python
class TriageLog(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "triage_logs"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True, nullable=False)
    symptom_text: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)  # low/moderate/high/emergency
    action: Mapped[str] = mapped_column(String(64), nullable=False)      # escalation action
    red_flags: Mapped[str | None] = mapped_column(Text)                  # JSON list of red flag strings
    message: Mapped[str | None] = mapped_column(Text)                    # AI message to patient
```

---

## Migration

- Down revision: `t18_add_ntrl` (T18 migration)
- Create `triage_logs` table
- Downgrade: drop table
- Run: `alembic upgrade head`

---

## API Changes

### Modified: `POST /ai/triage`

After computing result, IF caller is PATIENT (has PatientProfile):
- Save to `triage_logs` via `triage_log.save_triage(db, patient_id, payload, result)`
- If caller is not PATIENT or has no profile: skip silently

### New: `GET /patients/{patient_id}/triage-history`

- Query: `limit=20` (max 100), `offset=0`
- Response: `TriageLogHistoryResponse`
```json
{
  "patient_id": "uuid",
  "total": 5,
  "items": [
    {
      "id": "uuid",
      "symptom_text": "chest pain",
      "risk_level": "high",
      "action": "doctor_handoff",
      "red_flags": ["chest_pain"],
      "message": "...",
      "created_at": "2026-06-18T..."
    }
  ]
}
```
- RBAC: PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN/SUPER_ADMIN (any), AI_SERVICE → 403
- Order: newest first

---

## Service Layer

`backend/app/services/triage_log.py`:
- `save_triage(db, *, patient_id, symptom_text, result: TriageResult) -> TriageLog`
- `get_history(db, *, patient_id, limit, offset) -> tuple[int, list[TriageLog]]`

---

## Schemas

`backend/app/schemas/triage_log.py`:
- `TriageLogOut` — id, patient_id, symptom_text, risk_level, action, red_flags (list), message, created_at
- `TriageLogHistoryResponse` — patient_id, total, items

---

## Test Requirements (minimum 10 tests)

1. `test_triage_saved_for_patient` — after POST /ai/triage, record in DB
2. `test_triage_not_saved_for_non_patient` — doctor caller, no persistence
3. `test_patient_reads_triage_history` → 200, items list
4. `test_patient_cannot_read_another_patients_history` → 403
5. `test_doctor_reads_history_with_consent` → 200
6. `test_admin_reads_any_history` → 200
7. `test_ai_service_cannot_read_history` → 403
8. `test_empty_triage_history` → 200, empty list
9. `test_red_flags_serialized_correctly` — emergency triage, red_flags list not empty
10. `test_triage_history_ordered_newest_first` — multiple logs, newest first

---

## Acceptance Criteria

- [ ] `TriageLog` model created with correct FK
- [ ] Migration runs cleanly
- [ ] `POST /ai/triage` persists for PATIENT callers
- [ ] `GET /patients/{id}/triage-history` with RBAC + pagination
- [ ] `red_flags` serialized as JSON in DB, deserialized to list in response
- [ ] AI_SERVICE blocked on history endpoint
- [ ] 10 tests pass
- [ ] Zero regressions (391 baseline → 401+ total)
- [ ] Ruff clean

---

## Validation Commands

```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
alembic upgrade head
ruff check .
python -m pytest tests/ --tb=short
```

---

## Required Final Status

```
READY FOR CODEX REVIEW
```

---

*Task Card issued: 2026-06-18 19:30 GMT+7 | Coordinator: OpenClaw*
