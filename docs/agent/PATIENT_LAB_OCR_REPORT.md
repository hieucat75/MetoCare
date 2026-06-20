# OCR Lab Upload + Auto-Extract — Implementation Report

> Track: **OCR Lab Upload + Auto-Extract** · Provider policy **E** (Tesseract local default + cloud fallback opt-in)
> Branch: `feat/patient-lab-ocr-tesseract-local` · **PR not auto-merged** (awaiting PTH review)
> DigitalOcean production, Azure infra/workflow/PG firewall, admin/doctor theme — **untouched**.

## STATUS
**Phase A (backend) + Phase B (frontend) + Phase C (verification) COMPLETE.** Feature ships behind
`MCP_FEATURE_OCR=false` (off by default — pipeline is real but gated until staging sign-off).

## Summary
End-to-end lab-result upload with local OCR. A patient uploads a photo/PDF or pastes a URL → the
backend runs **Tesseract locally** (cost $0), parses recognised biomarkers into a **review-only draft**,
and returns it with per-value confidence + warnings. The patient reviews/edits in a mint/glass form and
**confirms** before anything is written — confirm-save reuses the existing manual-entry endpoint, so OCR
output never auto-writes to the medical record. Cloud OCR (Anthropic/Azure) is an **opt-in fallback**
only, gated by a separate flag + provider key; medical images are never sent out silently.

## Files changed
**Backend**
- `app/api/v1/routes/lab_upload.py` (new) — `POST /api/v1/lab-uploads` draft endpoint (flag-gated, patient RBAC).
- `app/services/lab_upload.py` (new) — orchestrator: MIME-sniff → validate → OCR/PDF → parse → interpret → draft.
- `app/services/ocr_engine.py` (new) — bytes-based Tesseract engine + Anthropic/Azure opt-in adapters.
- `app/services/lab_parser.py` (new) — OCR text → canonical `RawLabValue` (VN+EN, accent-tolerant).
- `app/core/ssrf.py` (new) — URL allow-list guard (private/loopback/link-local/IMDS block, no redirects, caps).
- `app/schemas/lab_upload.py` (new) — draft response schema.
- `app/domain/lab_interpreter.py` — taxonomy extended (eGFR, urea, GGT, FT4, FT3, basic CBC).
- `app/core/feature_flags.py` — `OCR_CLOUD_FALLBACK` flag (default off).
- `app/core/config.py` — `ocr_lang`, `ocr_cloud_provider`, `ocr_max_upload_mb`, `ocr_url_fetch_timeout_seconds`, `ocr_pdf_max_pages`.
- `app/api/v1/router.py` — register the new router.
- `requirements.txt` — `python-multipart`, `pytesseract`, `Pillow`, `pypdf`, `pdf2image`, `httpx`.

**Docker**
- `backend/Dockerfile` — `tesseract-ocr`, `tesseract-ocr-vie` (~5MB VN pack), `poppler-utils`.

**Migration** — **none.** The draft is stateless and confirm-save reuses existing `lab_results`; DB head stays `pauth_user_phone`.

**Frontend**
- `src/app/(patient)/labs/upload/page.tsx` (new) — camera/file/URL modes + review/edit + confirm.
- `src/app/(patient)/labs/page.tsx` — real mint CTA → `/labs/upload` when OCR on, else "Sắp ra mắt".
- `src/lib/api/client.ts` — `apiUpload()` multipart helper (401-retry).
- `src/lib/api/patient.ts` — `uploadLabDraft()` + draft types.

**Tests**
- `backend/tests/test_lab_ocr.py` (new) — 33 tests.

## OCR pipeline architecture
`upload (file|URL)` → `validate_upload` (magic-byte MIME sniff, size cap) → text extraction
( image: **Tesseract** `image_to_data` greyscale+autocontrast, per-word confidence; PDF: **pypdf** text
layer first, **pdf2image** rasterize+OCR fallback ) → `lab_parser.parse_lab_text` (label-after-value,
accent-tolerant, VN decimal comma) → `lab_interpreter.interpret_panel` (status/reference/verification) →
**draft** (`provider_used`, `confidence_avg`, `parsed_values[]`, `warnings[]`, `raw_text_sha256`,
`low_confidence`, `manual_fallback`). Nothing persisted. Cloud escalation only when
`OCR_CLOUD_FALLBACK` on **AND** provider key present **AND** local confidence < 0.75; a cloud failure
falls back to the local result (never crashes).

## Canonical mapping coverage
Glucose, HbA1c · Total Cholesterol, Triglyceride, HDL, LDL · Creatinine, **eGFR**, **Urea** ·
ALT, AST, **GGT** · TSH, **FT4**, **FT3** · basic CBC (**Hemoglobin, WBC, Platelet, RBC, Hematocrit**).
Bold = added this track. Each carries screening reference ranges + critical thresholds (not diagnostic).

## Security / SSRF guards
- URL paste: scheme ∈ {http,https}; **every** resolved A/AAAA must be public unicast — private (RFC1918),
  loopback, link-local incl. **169.254.169.254 IMDS** (+ `metadata.google.internal`), unique-local,
  multicast, reserved, IPv4-mapped — all rejected. Redirects disabled (3xx → reject), size + timeout caps.
- Upload validation: size ≤ 10MB (413), content-type by **magic bytes** not extension (415).
- Privacy: raw image bytes & raw OCR text are never stored or logged — only a 16-char SHA-256 prefix for
  audit. URL/filename are not logged. Audit records `ocr_draft` with the hash only.

## Feature flags
- `MCP_FEATURE_OCR` — gates the endpoint (`503` when off). **Default off.**
- `MCP_FEATURE_OCR_CLOUD_FALLBACK` — gates cloud fallback. **Default off.**
- `MCP_OCR_CLOUD_PROVIDER` = `anthropic|azure` (read only when fallback on).
- `ANTHROPIC_API_KEY` / `AZURE_DOC_INTEL_KEY`+`AZURE_DOC_INTEL_ENDPOINT` (read at call time; absent → local only).

## Verification
- **pytest** — new suite **33/33**; full backend **611 passed / 1 skipped** (baseline 578/1 + 33).
- **ruff** — clean.
- **Frontend** — `tsc` clean · `eslint` clean · prod `build` OK (`/labs/upload` 4.36 kB).
- **Live local OCR** (real Tesseract, generated VN lab PNG) — **6/6 metrics** extracted at conf **0.94**
  (Glucose 126 `high`, HbA1c 6.8 `high`, TG 320 `high`, Cholesterol 210 `high`, ALT 45, Creatinine 1.1).
- **SSRF (live)** — `http://169.254.169.254/latest/meta-data/` → **400**.
- **Flag-off (live)** — `MCP_FEATURE_OCR=false` → **503**.
- **Playwright iPhone 14 Pro (live local FE+BE)** — `/labs/upload` 3 tabs render → upload image → review
  form (5 metrics, confidence badges) → confirm → `/labs` shows saved entries.

## Screenshots
`/tmp/ocr_ui/iphone_*.png`: `labs_cta`, `upload_camera`, `upload_url`, `upload_file_selected`,
`review_form`, `labs_after_save`.

## Self-eval gate
| # | Gate | Result |
|---|------|--------|
| 1 | Local OCR JPG → ≥3 metrics conf>0.7 | ✅ 6 metrics @ 0.94 |
| 2 | Review UI renders + edit works | ✅ (review_form screenshot) |
| 3 | SSRF `169.254.169.254` → 400 | ✅ |
| 4 | Flag off → 503 | ✅ |
| 5 | Test suite full PASS | ✅ 611/1 |

## Risks / notes
- **No tesseract binary in CI host** → OCR-success tests monkeypatch the engine; one real-binary test
  skips when absent (passed locally with brew tesseract). The Docker image installs the binary, so staging
  runs real OCR.
- **DNS-rebinding** is mitigated by pre-fetch resolution + validation + no-redirects; full connect-time IP
  pinning is a known residual (acceptable behind the flag; can harden in a follow-up).
- **Backend image size** grows ~50–100MB (tesseract + vie pack + poppler) — within GHCR/ACR limits.
- `python-magic` from the proposed plan was dropped in favour of dependency-free magic-byte sniffing.

## Recommended next action
PTH review of the screenshot bundle + diff. On approval: merge → release bump → **Azure Staging Deploy**
(image rebuild installs tesseract) → staging smoke with `MCP_FEATURE_OCR=true` to exercise real
in-container OCR, then decide whether to leave the flag on for staging.
