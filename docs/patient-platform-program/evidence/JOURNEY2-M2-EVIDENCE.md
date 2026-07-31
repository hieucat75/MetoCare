# Journey 2 — M2 Foundation Evidence (Object Storage + MDI)

**Milestone:** M0 (CI single-head gate) + M2 (Object Storage §1.7 + Medical Document
Intelligence foundation §1.5/§1.4)
**Branch:** `feat/patient-platform-journey2` (off Journey 1 tip)
**Date:** 2026-07-31
**Governance:** Charter 2 (vertical slice), Charter 4 (no debt), Charter 6 (reuse), Charter 9 (evidence).

M2 is the document-first foundation that unblocks the rest of Journey 2 (2a prescription →
2b lab → 2c general report). Its exit criterion (Master Plan §9): *upload-session → accepted →
classified → needs_review; authorized read only.* **Met.**

---

## What a patient can now do (Charter 1)

The backend can now: take a photographed medical document through a **secure upload
session** (write-only signed URL → quarantine → validate + magic-byte MIME + sha256 +
size + page-limit + scan-posture → accept), **classify** it (prescription / lab / general),
run the **staged OCR pipeline** into a set of **independently-reviewable candidates**
(`needs_review`), and let the patient **confirm / reject / merge** each candidate — with
promotion into a canonical record recorded once and only once. The mobile Add-Document UI
and the real prescription extractor land in M3 (sub-slice 2a).

---

## Deliverables

### M0 — CI single-head Alembic gate
- `.github/workflows/ci.yml`: new `Alembic single-head gate` step in `test-backend` — fails
  the build unless `alembic heads` returns exactly one head. Verified locally: 1 head
  (`mdi_s0_medical_documents`).

### Object Storage abstraction (§1.7) — `app/services/storage/`
- `StorageBackend` interface + `LocalDiskStorage` (dev/CI/staging) + `AzureBlobStorage`
  (DIST-RC, fails loud until credentialed).
- Server-generated quarantine/accepted keys (`<container>/<patient>/<YYYYMM>/<uuid>.<ext>`) —
  clients never choose keys.
- HMAC-signed blob tokens (`signing.py`): write-only vs read-only op binding, single-object,
  short-lived, constant-time signature compare.
- Path-traversal defense on the local adapter.

### MDI models + migration (§1.5) — `app/models/medical_document.py`, `alembic/…mdi_s0_medical_documents.py`
- 5 tables: `medical_documents`, `document_pages`, `document_extractions` (immutable),
  `extraction_candidates` (one-to-many core), `promotion_links`.
- Idempotency at the DB layer: `uq_promotion_candidate_once(candidate_id)` (a candidate
  promotes at most once), `uq_extraction_dedupe_key(extraction_id, dedupe_key)`,
  `uq_document_page_no`.
- Additive, reversible; revision id ≤ 32 chars (Postgres `alembic_version` limit).

### Staged OCR pipeline (§1.4) — `app/services/mdi/`
- `Preprocessor → OcrEngine → EntityExtractor → Normalizer → ConfidenceScorer → ReviewGate
  → Promoter` framework; reuses the existing `ocr_engine.run_ocr`.
- VN-first `classifier` (patient's capture-type hint wins), extractor registry (mock default;
  real prescription/lab/report extractors register in M3/M4/M7), promoter registry
  (medication promoter lands in M3 — confirm on an unregistered type returns a clean 409,
  never a fabricated canonical id).

### MDI API (§2) — `app/api/v1/routes/documents.py`
- `POST /documents/upload-session`, `POST /documents/{id}/finalize`, `GET /documents`,
  `GET /documents/{id}`, `GET /documents/{id}/file` (per-request authorized signed read),
  `GET /documents/{id}/extraction`, `GET /documents/{id}/candidates`,
  `POST /candidates/{id}/confirm|reject|merge`, `POST /documents/{id}/reprocess`,
  `PUT|GET /documents/blob/{token}` (local blob transport).
- Every route BOLA-scoped to `PatientProfile.id`, gated by `FeatureFlag.OCR`, rate-limited,
  audited (no PHI).

### Reuse (Charter 6)
- `lab_upload.validate_upload` / `sniff_mime` (magic-byte MIME + size), `ocr_engine` engines,
  `audit.record`, `deps` auth/rate-limit, `is_enabled(FeatureFlag.OCR)`, `EncryptedString`.
- **Deferred (documented):** retirement of the `ocr.py:OCRProvider` skeleton and unification
  of the two OCR stacks happens in M4 when the lab pipeline is touched — retiring it now
  would break the live lab flow (Charter 6: reuse, no gratuitous rewrite).

---

## Test evidence

- **Full backend suite:** `3475 passed, 11 skipped, 195 deselected` (`pytest -m "not integration"`).
- **New MDI tests:** `tests/test_mdi_storage.py` (10) + `tests/api/test_documents_api.py` (12) — all green.
  Covers: full ingestion→needs_review, per-candidate confirm→promote, **double-confirm 409**,
  **reprocess carries forward / no double-promotion**, confirm-without-promoter 409, corrections
  history, reject, duplicate detection 409, sha256-mismatch / unsupported-bytes rejects, the
  **BOLA matrix** (patient B → 403 read/confirm; list excludes foreign docs), OCR-flag-off 503,
  unauthenticated 401, blob PUT-token-cannot-GET 403.
- **Postgres migration integration** (`tests/integration/test_mdi_migration.py`, wired into CI's
  postgres job): upgrade→downgrade→re-upgrade roundtrip, JSONB parity, unique-constraint presence.
  Skips locally without `POSTGRES_TEST_URL`; runs for real in CI.
- **Lint:** `ruff check .` clean.
- **Single Alembic head:** `mdi_s0_medical_documents`.
- **Migration roundtrip (SQLite):** upgrade→downgrade→re-upgrade verified locally.

---

## Independent review (§4) — findings + resolutions

A fresh-context security/correctness review ran against the M2 code. **All P0 and P1
findings were fixed in-slice** (Charter 4); the material P2s were also addressed.

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| P0-1 | Critical | Non-transactional storage `move` + no in-batch dedupe → a mid-pipeline error could strand a PHI blob and permanently brick the upload | Accept now **copies the validated in-memory bytes** to a fresh accepted key (never `move`); quarantine survives until a post-commit sweep, so finalize stays retryable. Candidate drafts are **deduped within the batch** before insert. |
| P0-2 | Critical | Re-PUT to the quarantine key between read and move could serve unvalidated bytes | Accepted object is the validated in-memory buffer (TOCTOU-safe); quarantine blob endpoint is now **write-once** (rejects re-PUT). |
| P1-1 | High | Duplicate-within-patient check was check-then-act with no DB backing | Added a **partial unique index** `(patient_id, sha256) WHERE accepted & not-deleted`; finalize maps the resulting `IntegrityError` to 409. |
| P1-2 | High | Confirm/reject had no row lock → concurrent lost-update | Candidate mutation paths now load `SELECT … FOR UPDATE` (real lock on Postgres, no-op on SQLite). |
| P1-3 | High | `blob_get` missing the container guard its sibling `blob_put` has | Added `container == accepted` check to `blob_get`. |
| P1-4 | High | Forward-looking BOLA on `merge_target_id` (unreachable until promoters land) | Documented as a hard requirement in the `Promoter` contract for M3/M4 implementers. |
| P1-5 | High | An all-rejected document was mislabeled `confirmed` | `_recompute_doc_status` now returns `rejected` when nothing was promoted. |
| P2 | — | Shared HMAC secret; unconstrained `declared_mime` | Blob tokens now use a **derived** key (`derive_blob_secret`, key separation from JWT); upload-session validates `declared_mime` (JPG/PNG/PDF) and fails fast. |

Regression tests were added for P0-1 (in-batch dedupe), P1-3 (quarantine-key GET token), P1-5
(all-rejected status), and the MIME guard. Deferred (documented) P2s: quarantine TTL sweep job,
adversarial-PDF parse guard, `document_scan_mode` must move to `hold`/`clamav` before real PHI.

## Known limitations (carried into M3+)
- Real prescription extractor + mobile Add-Document UI = M3 (sub-slice 2a).
- Medication/lab/diagnosis promoters register in M3/M4/M7; until then confirm on those types
  returns 409 (no fabricated canonical id — Charter 4).
- Multi-page PDF page-splitting/rasterization for per-page OCR = M4+ (M2 treats a document as a
  single OCR unit; page_count is still recorded).
- ClamAV adapter is DIST-RC; ENG-RC uses an explicit, audited `document_scan_mode=skip`
  (never a silent accept); `hold` posture available.
- `ocr.py:OCRProvider` skeleton retirement deferred to M4 (see Reuse note above).
