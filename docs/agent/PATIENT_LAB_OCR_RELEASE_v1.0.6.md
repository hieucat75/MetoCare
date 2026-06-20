# Patient App — OCR Lab Upload + Auto-Extract v1.0.6

> **Release:** v1.0.6 · **Target:** Azure Container Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #31 (`feat/patient-lab-ocr-tesseract-local`, squash-merged `fd27424`).

## What ships

The OCR Lab Upload + Auto-Extract feature (provider policy **E** — Tesseract local default, cloud OCR
opt-in only). A patient uploads a lab photo/PDF or pastes a URL → backend OCR → **review-only draft** →
edit/confirm → confirm-save reuses the existing manual-entry endpoint. OCR never auto-writes to the record.

- `POST /api/v1/lab-uploads` — synchronous, stateless draft (flag-gated, patient RBAC).
- Local **Tesseract** engine (`tesseract-ocr` + `tesseract-ocr-vie` + `poppler-utils` baked into the image).
- Cloud OCR (Anthropic/Azure) adapters — **opt-in fallback only**, OFF this release.
- SSRF-guarded URL paste; raw image/text never stored or logged (16-char SHA-256 audit hash only).
- Canonical taxonomy: Glucose, HbA1c, lipids, LFTs, Creatinine, **eGFR, Urea, GGT, FT4, FT3, basic CBC**.
- Frontend `/labs/upload` — camera/file/URL modes + review/edit + confirm; mint/glass v6 styling.

**Frontend + backend feature — no DB migration** (draft is stateless; DB head stays `pauth_user_phone`).

## Deploy / config change

This release **persists a workflow env change** (precedent: v1.0.1 CORS env, not a manual hotfix):

- `.github/workflows/azure-staging.yml` backend `COMMON_ENV` adds:
  - `MCP_FEATURE_OCR=true` — **staging only**; enables the lab-upload pipeline. Tesseract runs locally
    in-container, **cost $0**.
  - `MCP_FEATURE_OCR_CLOUD_FALLBACK=false` — explicit; cloud OCR stays off.
- **No cloud keys provisioned** (`ANTHROPIC_API_KEY` / `AZURE_DOC_INTEL_*` absent) → no medical image
  ever leaves the container.
- **Production enablement is a separate decision.** DigitalOcean prod is opt-in (`[deploy-do]`) and is not
  touched; its OCR flag remains default-off.

> First deploy that bakes the Tesseract binary + VN language pack + poppler into the backend image — the
> Docker build is ~3–5 min longer and the image ~50–100MB larger (within GHCR/ACR limits).

## Quality gates (local)

- Backend `pytest` **611 passed / 1 skipped**; new OCR suite **33/33**; `ruff` clean.
- Frontend `tsc` / `eslint` / `build` clean (`/labs/upload` 4.36 kB).
- Live real-Tesseract: generated VN lab PNG → **6/6 metrics @ conf 0.94**; SSRF `169.254.169.254` → 400;
  flag-off → 503; Playwright iPhone 14 Pro upload→review→confirm→/labs.

## Feature flags after this release (staging)

| Flag | Value | Effect |
|------|-------|--------|
| `MCP_FEATURE_OCR` | **true** (staging) | lab-upload draft endpoint live |
| `MCP_FEATURE_OCR_CLOUD_FALLBACK` | false | cloud OCR off |
| `ANTHROPIC_API_KEY` / `AZURE_DOC_INTEL_*` | unset | no cloud calls possible |
