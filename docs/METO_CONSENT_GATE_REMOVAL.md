# METO_CONSENT_GATE_REMOVAL.md

STATUS: PASS
Commit: d40aa3d
Branch: main → pushed to origin

## Files changed

### Backend
- `backend/app/ai/context/builder.py` — Removed consent gating from `build()`. All blocks (health_summary, care_plan, medications, recent_labs, recent_metrics, today_context) are now assembled if data exists and the screen requires them. Consent rows are no longer queried during context build. `missing_consents` is always `[]`.
- `backend/app/schemas/meto.py` — Added comment clarifying `consent_required` and `missing_consents` fields are kept for backward-compat only; always return `False`/`[]`.
- `backend/app/services/meto_chat.py` — `_save_and_return()` now always returns `consent_required=False, missing_consents=[]`. Audit log `details` no longer includes `missing_consents`.

### Backend Tests Updated
- `backend/tests/test_meto_context.py` — `TestNoConsent` rewritten: tests now verify blocks ARE included (no consent gate), `missing_consents` is always `[]`.
- `backend/tests/test_meto_quality_slice.py` — `test_metachat_response_has_consent_required_field` rewritten: tests now verify fields exist with `False`/`[]` defaults.
- `backend/tests/test_meto_db.py` — `test_consent_gating_real_db_no_consent` rewritten: verifies `missing_consents == []` and `screen_context` is included.
- `backend/tests/test_meto_integration.py` — `TestConsentGating` and `TestNoConsentBehavior` rewritten: tests verify new behavior (data included, `missing_consents == []`).

### Frontend
- `frontend/src/components/patient/meto/ChatSheet.tsx` — Removed `ConsentPrompt` import and render logic. Removed `consent_required`/`consentRequired`/`missingConsents` from `ChatMessage` type. Removed `MessageType.consent_required`. Message type now only checks `escalation` for `'safety'` type.
- `frontend/src/lib/api/meto.ts` — `consent_required` and `missing_consents` fields marked `@deprecated` with explanatory comment. Still optional in type (backward-compat).
- `frontend/src/components/patient/meto/ConsentPrompt.tsx` — **KEPT** (untouched, available for Settings page use).
- `frontend/src/components/patient/meto/index.ts` — **KEPT** ConsentPrompt export (may be used in Settings).

### Frontend Tests Updated
- `frontend/src/__tests__/meto/ChatSheet.test.tsx` — Consent-required tests inverted: now verify ConsentPrompt does NOT appear in chat and CTA chips are not rendered. Fixed `queryByText` → `queryAllByText` for greeting test.
- `frontend/src/__tests__/meto/quality-slice.test.ts` — `Consent-Required Response Shape` section renamed to `Consent gate removed`, tests updated to expect `consent_required=false`.

## Behavior before
```
1. User asks "Hôm nay tôi cần chú ý gì?"
2. Backend: context builder loads consents, finds missing → sets missing_consents
3. Backend: _save_and_return sets consent_required=True
4. Frontend: ChatSheet detects consent_required=true → renders ConsentPrompt
5. User sees 3 CTA buttons: "Mở Quyền riêng tư" / "Hỏi chung" / "Để sau"
6. User is BLOCKED from getting an answer
```

## Behavior after
```
1. User asks "Hôm nay tôi cần chú ý gì?"
2. Backend: context builder assembles ALL blocks from screen (no consent check)
3. Backend: _save_and_return always returns consent_required=False, missing_consents=[]
4. Frontend: ChatSheet receives response, renders as 'normal' message
5. User sees personalized AI answer immediately
6. (Consent management is only accessible via Settings > Quyền riêng tư)
```

## Tests
- Backend: 2327 passed, 1 skipped — all CI green
- Frontend: 332 passed — all Jest tests green
- ruff lint: clean
- TypeScript (source files): no errors

## What was kept (NOT removed)
- `ConsentPrompt.tsx` — file kept, exported from index.ts for future Settings use
- `UserAIConsent` / `MetoConsent` model/table — kept for Settings management
- `GET /meto/consent` and `POST /meto/consent` endpoints — kept for Settings page
- Safety escalation flow (emergency phrases → 115) — untouched
- All markdown rendering, personality, greeting, screen prompts — untouched

## Remaining
- Trigger staging deploy to validate end-to-end behavior
- Update Settings > Quyền riêng tư page to surface ConsentPrompt if user wants to manage what Meto accesses (cosmetic only — no functional gate)
