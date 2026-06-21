# Patient Lab OCR — Azure Document Intelligence fallback (v1.4.0)

**Track:** OCR Lab Upload (provider policy E — Tesseract local primary + cloud opt-in fallback).
**Why:** Free Tesseract OCR quality on phone photos of Vietnamese lab printouts was poor
(missed/garbled biomarkers). Azure AI Document Intelligence (Form Recognizer) `prebuilt-layout`
lifts transcription quality to ~0.98 word confidence and reconstructs ruled lab tables.

## What changed

**Tesseract stays PRIMARY** (cost $0, in-container, no network). Azure is called **only** as an
opt-in fallback, in two cases — both already required by the track:

1. **Low confidence** — local Tesseract confidence `< OCR_CONFIDENCE_THRESHOLD`
   (handled in `ocr_engine.run_ocr`, pre-existing).
2. **Zero biomarkers** — local OCR returned acceptable confidence but the parser recognized
   *no* biomarkers on a tricky layout (new escalation in `lab_upload.build_draft`).

A medical image is **never** sent to Azure unless `MCP_FEATURE_OCR_CLOUD_FALLBACK=true` **and**
`MCP_OCR_CLOUD_PROVIDER=azure` **and** both `AZURE_DOC_INTEL_ENDPOINT`/`AZURE_DOC_INTEL_KEY`
are present. Any misconfiguration falls through to the local result (never crashes).

### Backend

- `app/services/ocr_engine.py` — **real `AzureDocIntelEngine`** (replaces the preview-API stub):
  - GA REST API `2024-11-30`, model `prebuilt-layout` (override via `AZURE_DOC_INTEL_MODEL`,
    e.g. `prebuilt-read` for the cheaper read model).
  - `_build_text` — document `content` (reading order) **+ one reflowed line per table row**
    so columnar lab data (test | value | unit | range) lands on a single line for the parser.
  - `_avg_word_confidence` — **real** mean of per-word confidences (not a hardcoded 0.9);
    high default only when the service returns none.
  - `_poll` — long-running-operation polling that honors the server `retry-after` backoff and
    raises cleanly on `failed`/timeout.
  - `run_cloud_ocr_if_permitted()` — new helper used by the zero-biomarker escalation; returns
    `None` (never raises) when cloud isn't permitted or the call fails.
- `app/services/lab_upload.py` — `build_draft` escalates to permitted cloud when the local
  transcription parsed zero biomarkers, adopting the cloud result **only if** it recognizes
  biomarkers; adds a warning when used.
- **No new dependency** — uses `httpx` (already runtime). No `azure-ai-documentintelligence`
  SDK: the thin REST call keeps the image lean and avoids `azure-core` bloat.
- **No DB migration** — draft is stateless; DB head stays `hmbk_backfill`.

### Workflow (`.github/workflows/azure-staging.yml`)

- Reads `azure-doc-intel-endpoint` + `azure-doc-intel-key` from Key Vault (`kv-metocare-stgd9e7`).
- Backend ACA deploy now sets (STAGING only):
  - `MCP_FEATURE_OCR_CLOUD_FALLBACK=true`
  - `MCP_OCR_CLOUD_PROVIDER=azure`
  - `AZURE_DOC_INTEL_ENDPOINT=<endpoint>` (plain env)
  - `AZURE_DOC_INTEL_KEY=secretref:doc-intel-key` (ACA secret)
- No `ANTHROPIC_API_KEY` provisioned. DigitalOcean production untouched.

## Azure resource

- **`docintel-metocare-staging`** — kind `FormRecognizer`, SKU **F0 (free)**, region
  `southeastasia`, RG `rg-metocare-staging`.
- Endpoint: `https://docintel-metocare-staging.cognitiveservices.azure.com/`
- Provider `Microsoft.CognitiveServices` registered on the subscription.
- Secrets stored in `kv-metocare-stgd9e7` (`azure-doc-intel-endpoint`, `azure-doc-intel-key`).

## Cost projection (cap $20/month — TOTAL)

| Tier | Price | Notes |
|------|-------|-------|
| **F0 (in use)** | **$0** | 500 transactions/month, 2 calls/sec. |
| S0 prebuilt-read | ~$1.50 / 1,000 pages | fallback if F0 cap exceeded. |
| S0 prebuilt-layout | ~$10 / 1,000 pages | current default model on paid tier. |

- Azure is a **rare fallback** (only low-confidence / zero-biomarker uploads), behind a
  Tesseract primary. Staging usage estimate ~10–50 calls/month → **well under the 500 free cap**.
- Even on paid S0 layout: 50 calls ≈ **$0.50/mo**; the $20 cap = ~2,000 layout pages or
  ~13,000 read pages. Large headroom.
- **Monitor:** monthly transaction count via Azure portal → Document Intelligence → Metrics.
  If F0 cap is ever hit, switch `AZURE_DOC_INTEL_MODEL` to `prebuilt-read` (cheaper) before S0.

## Verification

- **Backend pytest:** 651 passed / 1 skipped (+8 new Azure tests). Ruff clean.
- **Live Azure (real resource, real image):** `provider=azure`, confidence **0.9789**, parsed
  fasting_glucose 126 / hba1c 6.8 / total_cholesterol 210 / triglyceride 320 / ldl 145 /
  creatinine 1.1 + test_date `2024-10-15` (Ngày lấy mẫu).
- New tests: provider parse (mocked HTTP), table reflow, real avg-confidence, failed-status
  raise, low-confidence fallback → azure, no-key → skip (never called), zero-biomarker
  escalation uses/skips cloud.

## Next

Release PR v1.4.0 (no `[skip ci]`) → Azure Staging Deploy → staging smoke (`/info`
ocr=true/cloud=true/provider=azure, real upload → `provider_used`, Azure metrics tick).
