# 06 — OCR Quality Report (WS6)

**Date:** 2026-08-04 · **Assessor:** independent OCR-Quality assessor (fresh context, direct source inspection)
**Branch:** `feat/patient-platform-journey2` · **HEAD at assessment:** `bfd6735` (task brief said `6ab3b04`; `bfd6735 fix(pilot-seed): grant documents consent…` landed during the session — no OCR code changed)
**Method:** every claim below is traced to `file:line` or to a command whose verbatim output is reproduced. Nothing is taken from a prior summary, memory, or evidence doc.
**Gate:** this workstream gates **public beta** (per `TRACKING.md` §A). It does **not** block the synthetic controlled pilot, for the reasons in §8 — but §9 lists three findings that change what the pilot may claim.

> **Headline.** The OCR *engineering* is good: deterministic parsers, hospital column maps, unit-safety refusal, no-auto-canonical promotion. The OCR *quality evidence* does not exist. There is **no labelled image corpus in the repo**, so the "Vinmec ≥95% / Medlatec ≥90%" numbers that appear in `backend/ocr_dataset/README.md:11-12` are **targets that have never been measured**, and the only benchmark that runs measures test-name canonicalization with no image and no OCR. Separately, three material posture defects were found and are new P0/P1 findings (§9): cloud OCR is **on** in staging and production deploy config while every launch doc says it is off; PDFs hard-fail the document pipeline without the cloud key; and the patient-confirmation "safety net" renders **nothing** for lab and general-report candidates.

---

## 1. What "quality" means, per document type

Quality is not one number. Each document type has a different failure surface and a different clinical blast radius.

| Doc type | Pipeline | What "correct" means | Blast radius of an undetected error |
|---|---|---|---|
| **Lab report** | `mdi/extractors_lab.py` (Journey-2 documents) **and** `services/lab_parser.py` + `domain/lab_table_extractor.py` (legacy `/lab-uploads`) | For every printed analyte row: analyte identified (`normalize_biomarker`), numeric value, unit, reference range, specimen date. Original value/unit preserved verbatim (`extractors_lab.py:1-8`). | **High.** A wrong analyte or unit is classified against the wrong thresholds → false-normal / inverted advice, and feeds `HealthMetric` trends and (once confirmed) the AI context. |
| **Prescription** | `mdi/extractors_prescription.py` | Per medicine line: name, strength, form, frequency, route, duration, quantity — each an **independent** candidate with its own `dedupe_key` (`extractors_prescription.py:140-159`). | **High.** A wrong strength or frequency becomes a medication statement and drives Journey-3 dose scheduling and reminders. |
| **General report** (discharge / imaging / pathology / referral) | `mdi/extractors_general.py` | Typed free-text segments only — `diagnosis` / `procedure` / `finding` / `recommendation` / `follow_up` (`extractors_general.py:1-9`, `_LABELS` at `:34-55`). No canonical clinical fact is ever created (`promoters.py:116-127` `RecordOnlyPromoter`). | **Medium.** Text is display-only until confirmed; a mis-typed segment mislabels a record but does not silently change thresholds or dosing. |

Consequently this report scores **four** things separately, and refuses to average them:
1. **Transcription** — did the engine read the glyphs (char/word level)?
2. **Recognition** — did the parser find the right rows/entities at all (recall)?
3. **Canonicalization** — did the analyte/med name map to the right canonical key (precision of mapping)?
4. **User Editing Rate (UER)** — what fraction of extracted rows a patient had to change. This is the metric the repo's own harness targets (`scripts/benchmark_ocr.py:302-313`) and the only one that correlates with product experience.

---

## 2. The engines that actually run

`backend/app/services/ocr_engine.py` is the only bytes→text entry point used by both pipelines (`mdi/pipeline.py:20,56`; `services/lab_upload.py:33-34,182,205,252`).

| Engine | Class | Selected when | Notes |
|---|---|---|---|
| **Mock** | `MockOcrEngine` (`ocr_engine.py:153-162`) | only if `MCP_OCR_PROVIDER=mock` or `MCP_ENABLE_MOCK_OCR=true` (`:457-462`), and **hard-blocked in staging/production** (`:465-476`) | returns a fixed 15-line VN lab text (`:133-150`) |
| **Azure Document Intelligence** | `AzureDocIntelEngine` (`:229-414`) | `AZURE_DOC_INTEL_KEY` **and** `AZURE_DOC_INTEL_ENDPOINT` present (`:254-256`) | GA REST `2024-11-30`, `prebuilt-layout`; returns real per-word confidence (`:402-414`); reference-range columns are dropped from reflowed text so range numbers can't be read as results (`:327-349, 357-400`) |
| **Tesseract** | `TesseractEngine` (`:49-126`) | only when Azure is **not** configured (`:494-500`) | `lang=vie+eng` (config `:133`), `--psm 6`, greyscale + autocontrast preprocessing (`:80-88`), word-box reflow to keep `label: value` on one line (`:110-126`) |
| **Anthropic vision** | `AnthropicVisionEngine` (`:170-226`) | cloud-fallback flag ON **and** `MCP_OCR_CLOUD_PROVIDER=anthropic` **and** `ANTHROPIC_API_KEY` (`:417-431`) | never provisioned in any workflow (`azure-staging.yml:199`) |

**Selection order (`ocr_engine.py:479-505`): explicit-mock → Azure → Tesseract → raise.**

### 2.1 Hospital profiles / ColumnMap / HospitalDetector (legacy lab path only)

`backend/app/domain/hospital_profiles.py` declares **7** profiles — `vinmec` (`:145`), `medlatec` (`:177`), `tamanh` (`:226`), `hongngoc` (`:255`), `bachmai108` (`:283`), `bachmai` (`:305`), `fv` (`:340`) — plus `UNKNOWN_PROFILE` (`:365-371`). Only **vinmec** (`:167`) and **medlatec** (`:216`) carry a deterministic `ColumnMap` (`:21-35`); the other five fall back to heuristic column-role detection (`lab_table_extractor.py:451`, `_infer_column_roles_positional` `:426`).

`HospitalDetector.detect_or_unknown` (`hospital_profiles.py:91-136`) scans the first 50 OCR lines and assigns a **position-weighted** confidence — 0.9 (lines 1-10), 0.7 (11-30), 0.5 (31-50), 0.0 → `UNKNOWN_PROFILE`. Ties break on earlier line, then longer alias (`:117-131`).

`ColumnMap` is validated before use and silently abandoned when the observed table shape contradicts it (`lab_table_extractor.py:628-681`), with `skip_cols` guarding against method/instrument/price columns becoming the value column (`:712-720`) and `footer_patterns` excluding totals/signature rows (`:733-741`).

> **Scope limit that matters:** all of §2.1 is reachable **only** from the legacy `/lab-uploads` path (`lab_upload.py:229-248`). The Journey-2 document pipeline that the mobile app uses calls `run_pipeline` → `extractors_lab.LabExtractor`, which is a line-regex parser (`extractors_lab.py:22-28`) and **never** consults a hospital profile or a ColumnMap. The mobile app has no `/lab-uploads` client (`mobile/src/api/` contains no lab-upload module). **The hospital-profile investment is not on the pilot's document path.**

---

## 3. Ground truth that actually exists in the repo

```
$ cd backend && source .venv/bin/activate && python scripts/ocr_dataset_init.py
OCR Dataset: /Users/pth/Developer/Metocare/backend/ocr_dataset
.gitignore: OK — PHI-protection patterns present
Expected JSON files by tier/hospital:
  golden/  (0 total)
  benchmark/  (5 total)
    vinmec: 1
    medlatec: 1
    tamanh: 1
    hongngoc: 1
    bachmai: 1
Total expected files: 5
Directories verified/created: 92
```

```
$ python scripts/ocr_dataset_validate.py
OK    ocr_dataset/benchmark/vinmec/expected/20261224_vinmec_001.expected.json
OK    ocr_dataset/benchmark/medlatec/expected/20260626_medlatec_001.expected.json
OK    ocr_dataset/benchmark/tamanh/expected/20260626_tamanh_001.expected.json
OK    ocr_dataset/benchmark/hongngoc/expected/20260626_hongngoc_001.expected.json
OK    ocr_dataset/benchmark/bachmai/expected/20260626_bachmai_001.expected.json
Results: 5 passed, 0 failed
```

Provenance of all five, read directly from the JSON:

```
$ python -c "import json,glob; [print(p, json.load(open(p))['source']) for p in sorted(glob.glob('ocr_dataset/**/expected/*.expected.json', recursive=True))]"
…/bachmai/…    {'uploaded_by': 'synthetic', 'anonymized': True, 'contains_phi': False}
…/hongngoc/…   {'uploaded_by': 'synthetic', 'anonymized': True, 'contains_phi': False}
…/medlatec/…   {'uploaded_by': 'synthetic', 'anonymized': True, 'contains_phi': False}
…/tamanh/…     {'uploaded_by': 'synthetic', 'anonymized': True, 'contains_phi': False}
…/vinmec/…     {'uploaded_by': 'synthetic', 'anonymized': True, 'contains_phi': False}
```

- **Images: zero.** `find ocr_dataset/benchmark -path "*/images/*" -type f` returns only 11 `.gitkeep` files. Raw images are `.gitignore`d for PHI protection (`ocr_dataset/.gitignore:5-7`) — correct policy, but it means **no image ground truth is reproducible from a clone**.
- **Golden tier: empty** (0 expected files).
- **Azure response cache: empty** — so the image-mode benchmark cannot even replay cached OCR.
- No prescription or general-report ground truth exists in any form. The schema itself is lab-only (`ocr_dataset/schema/expected_lab_report.schema.json`).

`ocr_dataset/README.md:11-12` states the targets: *"Vinmec: ≥ 95% row-level accuracy (User Editing Rate < 5%); Medlatec: ≥ 90% row-level accuracy (User Editing Rate < 10%)"*. The harness's own configured targets are looser — `_EDITING_TARGETS` in `scripts/benchmark_ocr.py:302-313` sets vinmec **≤0.10**, medlatec **≤0.15**, everything else **≤0.20**. **Neither set has ever been measured against an image.**

---

## 4. MEASURED results

Everything in this section is a command I ran read-only this session, with its output.

### 4.1 The repo's own benchmark — what it really measures

`run_synthetic_benchmark` (`scripts/benchmark_ocr.py:557-683`) walks `expected/*.expected.json`, calls `normalize_biomarker(original_test_name)` and compares to `mapped_metric_type` (`:516-533`). **It never opens an image and never invokes an OCR engine.** Hospital "detection" is tested by feeding a profile's own header pattern back to the detector (`:489-513`) — a self-consistency check, not a detection measurement.

```
$ python scripts/benchmark_ocr.py --synthetic-mode --bench-dir ./ocr_dataset/benchmark
HOSPITAL: bachmai    | Rows: 10 | Mapped: 10/10 | Canonicalization accuracy: 100% | Target UER: ≤20% | Actual UER: 0% | PASS
HOSPITAL: hongngoc   | Rows: 10 | Mapped: 10/10 | Canonicalization accuracy: 100% | Target UER: ≤20% | Actual UER: 0% | PASS
HOSPITAL: medlatec   | Rows: 12 | Mapped: 12/12 | Canonicalization accuracy: 100% | Target UER: ≤15% | Actual UER: 0% | PASS
HOSPITAL: tamanh     | Rows: 10 | Mapped: 10/10 | Canonicalization accuracy: 100% | Target UER: ≤20% | Actual UER: 0% | PASS
HOSPITAL: vinmec     | Rows: 16 | Mapped: 16/16 | Canonicalization accuracy: 100% | Target UER: ≤10% | Actual UER: 0% | PASS
[bachmai108] No *.expected.json files — skipping.   [fv] …skipping.   [hoanmy] …skipping.
[other] …skipping.   [thucuc] …skipping.   [vietduc] …skipping.
  Total hospitals: 5 | Total rows: 58 | Mapped: 58/58 (100.0%)
  Passing hospitals (UER ≤ target): 5/5
  RESULT: PASS
```

> **MEASURED — name canonicalization: 58/58 rows (100.0%) across 5 synthetic samples / 5 hospitals; 0% UER; 5/5 pass.**
> **This is NOT an OCR accuracy number.** It is: "given a perfectly transcribed VN test name, does `normalize_biomarker` map it to the right canonical key?" 2 of the 7 shipped hospital profiles (`fv`, `bachmai108`) have no sample at all.

### 4.2 Local Tesseract, clean-render probe

The repo's only test that touches the real binary is `tests/test_lab_ocr.py:638-660` (`test_real_tesseract_roundtrip`), which renders three ASCII lines with PIL and asserts one biomarker is found. It passes:

```
$ python -m pytest tests/test_lab_ocr.py::test_real_tesseract_roundtrip -p no:randomly
1 passed, 1 warning in 0.39s
```

To get an actual number I rendered the repo's **own** fixture text (`ocr_engine.py:133-150`, 14 biomarker lines incl. VN diacritics) to a clean 760px PNG with a Unicode font, disabled Azure, and ran the real local path end-to-end (`run_ocr` → `lab_parser.parse_lab_text`). Probe script: `scratchpad/ocr_probe.py` (not committed; reproduced in §10).

```
engine=tesseract  tesseract_mean_word_conf=0.9211
ground_truth_biomarker_lines=14
parsed_biomarkers=13 -> ['alt','ast','creatinine','fasting_glucose','hba1c','hemoglobin',
                         'ldl','platelet','rbc','total_cholesterol','triglyceride','urea','wbc']
biomarker_recall=13/14 = 92.9%
--- raw OCR text (excerpt) ---
Creatinine: 85 mol/L [62-106]      <-- "µmol/L" transcribed as "mol/L" (µ dropped)
HDL Cholesterol: 1.2 mmol/L [>1.0] <-- transcribed correctly, MIS-MAPPED by the parser
```

> **MEASURED — local Tesseract on a clean synthetic render: mean word confidence 0.9211; biomarker recall 13/14 = 92.9%; all VN diacritics (`Hồng cầu`, `Bạch cầu`, `Tiểu cầu`, `Ngày xét nghiệm`) transcribed correctly.**
> **This is an UPPER BOUND.** It is a machine-rendered, perfectly-lit, perfectly-square, single-column image. Real inputs are phone photos of printouts. Do not present this as a phone-photo accuracy figure.

Two real defects fell out of this probe:

- The dropped `µ` on creatinine was **recovered** by the parser's unit-correction layer — the persisted row shows `original_unit='µmol/L'`, `canon=0.9615 mg/dL`. Mitigation works.
- `HDL Cholesterol` was **silently mapped to `total_cholesterol`** (see §4.3). Not recovered.

### 4.3 Confirmed parser mis-mapping (measured)

```
$ python -c "from app.domain.lab_interpreter import normalize_biomarker as n; print(n('HDL Cholesterol'))"
hdl

$ python -c "from app.services.lab_parser import parse_lab_text as p; \
  [print(repr(l),'->',[(x.raw_test_name,x.test_name,x.requires_review,x.confidence_detail.overall) for x in p(l)]) \
   for l in ['HDL Cholesterol: 1.2 mmol/L','HDL-C: 1.2 mmol/L','Cholesterol HDL: 1.2 mmol/L',
             'LDL Cholesterol: 2.8 mmol/L','Non-HDL Cholesterol: 3.3 mmol/L']]"
'HDL Cholesterol: 1.2 mmol/L'     -> [('HDL Cholesterol', 'total_cholesterol', False, 0.0)]
'HDL-C: 1.2 mmol/L'               -> [('HDL-C',            'hdl',               False, 1.0)]
'Cholesterol HDL: 1.2 mmol/L'     -> [('Cholesterol',      'total_cholesterol', False, 0.0)]
'LDL Cholesterol: 2.8 mmol/L'     -> [('LDL Cholesterol',  'ldl',               False, 1.0)]
'Non-HDL Cholesterol: 3.3 mmol/L' -> [('Non-HDL Cholesterol','total_cholesterol',False, 1.0)]

$ python -c "from app.services.mdi.extractors_lab import LabExtractor; \
  print(LabExtractor().extract(text='HDL Cholesterol: 1.2 mmol/L [1.0-2.0]', doc_type='lab_report', ocr_confidence=0.9)[0].fields)"
{'test_name': 'HDL Cholesterol', 'original_test_name': 'HDL Cholesterol', 'canonical': 'hdl', 'value': 1.2, …}
```

`normalize_biomarker` is right and the MDI extractor is right; **`lab_parser.parse_lab_text` is wrong** — it matches the bare `cholesterol` alias before the `hdl cholesterol` alias. Result: an HDL value is stored and trended as total cholesterol. It is flagged internally (`clinical=0.0`, `⚠ giá trị ngoài khoảng sinh lý`) yet `requires_review` stays `False`. → **OCR-F3**.

### 4.4 PDF handling in the document pipeline (measured)

```
$ python -c "…; oe.AzureDocIntelEngine.configured = lambda: False; run_pipeline(page_bytes=[blank_pdf], mime='application/pdf')"
TesseractEngine on PDF -> OcrEngineError: Không đọc được tệp ảnh.
run_ocr        RAISED: OcrEngineError | Không đọc được tệp ảnh.
run_pipeline   RAISED: OcrEngineError | Không đọc được tệp ảnh.
```

`mdi/service.py:331-346` passes the **whole file** as `page_bytes=[data]` with no rasterization; the legacy path *does* rasterize (`lab_upload.py:167-190`, `pdf2image` + poppler, both installed in `backend/Dockerfile:11-16`). `documents.py:220-243` catches only `mdi.MdiError` and `IntegrityError`, so `OcrEngineError` escapes as a 500 **after** the accepted blob was written (`mdi/service.py:245-250`). PDFs up to 20 pages are accepted (`config.py:96 document_max_pages: int = 20`). → **OCR-F2**.

### 4.5 Test-suite status (all OCR/MDI suites, read-only)

```
$ python -m pytest tests/test_lab_ocr.py tests/test_lab_hospital_profiles.py tests/test_synthetic_benchmark.py \
    tests/test_ocr_dataset.py tests/test_ocr_date_resolver.py tests/test_ocr_gap_analysis.py \
    tests/test_ocr_save_p0.py tests/test_ocr_case_integration.py tests/api/test_lab_ocr_api.py \
    tests/api/test_prescription_ocr_api.py tests/api/test_general_ocr_api.py \
    tests/test_mdi_lab.py tests/test_mdi_prescription.py tests/test_mdi_general.py tests/test_mdi_storage.py -p no:randomly
388 passed, 1 warning in 8.38s
```

| Suite | Tests | What it proves | What it does **not** prove |
|---|---|---|---|
| `test_lab_ocr.py` | 122 | parser, SSRF guard, PDF text layer, flags, RBAC, confirm-save, Azure mocked-HTTP contract | accuracy on real images (OCR is monkeypatched — see `:50-56`) |
| `test_lab_hospital_profiles.py` | 57 | profile/ColumnMap logic on synthetic tables | detection on real hospital headers |
| `test_synthetic_benchmark.py` | 34 | the §4.1 canonicalization harness | anything image-derived |
| `test_ocr_dataset.py` / `_date_resolver` / `_gap_analysis` / `_save_p0` / `_case_integration` | 43/37/18/17/12 | dataset schema, DOB-vs-exam-date resolver, gap math, save invariants | — |
| `api/test_{lab,prescription,general}_ocr_api.py` | 3/7/4 | route contracts + flag gating | extraction quality |
| `test_mdi_{lab,prescription,general,storage}.py` | 9/10/7/8 | extractors on **hand-written clean text** (`test_mdi_prescription.py:7-16`, `test_mdi_general.py:7-13`) | any OCR-noise robustness |

> **MEASURED — 388/388 OCR+MDI tests pass. Zero of them measure transcription accuracy on a real document image.**

### 4.6 Engine availability on the assessment host

```
tesseract_available= True   tesseract_bin= /opt/homebrew/bin/tesseract
azure_configured= True      ocr_lang= vie+eng   ocr_pdf_max_pages= 3
cloud_provider= azure       OCR_CONFIDENCE_THRESHOLD= 0.75   n_biomarkers= 28
```

---

## 5. UNMEASURED — the honest list

| Area | Status | What would have to be run |
|---|---|---|
| Lab OCR accuracy on real VN hospital images (any hospital) | **UNMEASURED** | `python scripts/benchmark_ocr.py --bench-dir ./ocr_dataset/benchmark` with ≥20 anonymized images + `ground_truth.json` per hospital and `AZURE_DOC_INTEL_*` set |
| The `≥95% / ≥90%` Vinmec/Medlatec claims (`ocr_dataset/README.md:11-12`) | **UNMEASURED — never substantiated** | same as above |
| Hospital detection rate on real headers (gate is `≥99%`, `benchmark_ocr.py:420`) | **UNMEASURED** | same |
| `fv` and `bachmai108` profiles | **UNMEASURED — no sample of any kind** | add expected JSON + image |
| **Prescription** extraction accuracy | **UNMEASURED — no corpus, no schema, no harness** | build a prescription ground-truth schema + corpus (§7) |
| **General-report** extraction accuracy | **UNMEASURED — same** | ditto |
| Phone-photo robustness (skew, glare, shadow, crumple, low light) | **UNMEASURED** | photo capture protocol (§7.1) |
| Handwritten prescriptions | **UNMEASURED**, and no code path targets them (`extractors_prescription.py:3-7` says *"of a **printed** prescription"*) | out of scope for v1 — declare it |
| Multi-page PDF documents in the MDI pipeline | **BROKEN, not merely unmeasured** — §4.4 / OCR-F2 | — |
| Azure DI F0 free-tier page/throughput limits and data-region | **UNVERIFIED** — run `az cognitiveservices account show -n docintel-metocare-staging` and check tier + region + the Azure AI data-privacy terms |
| End-to-end OCR on-device (camera → OCR → review) | **UNVERIFIED** — the Android pilot's Journey A used the QA fixture, which injects deterministic text and never invokes an OCR engine (`mdi/service.py:284, 310-315`; fixture is prescription-only, `app/fixtures/__init__.py:32-45`) | manual on-device capture of a real printout against staging |

---

## 6. Failure-mode taxonomy and the mitigations that exist in code

| # | Failure mode | Mitigation present | Where | Residual |
|---|---|---|---|---|
| 1 | **Skew / rotation** | none | — | Tesseract `--psm 6` (`ocr_engine.py:86`) assumes a uniform block; no deskew, no `--psm 3` retry, no perspective correction. Azure DI handles skew internally — so skew robustness is *entirely* a cloud-dependency. |
| 2 | **Low light / low contrast / shadow** | greyscale + `ImageOps.autocontrast` (`ocr_engine.py:80`) | local only | no adaptive/Otsu threshold, no denoise. Below-threshold results warn the patient (`:496-499`, threshold 0.75 from `lab_interpreter.OCR_CONFIDENCE_THRESHOLD`) but are still shown. |
| 3 | **Handwriting** | explicitly out of scope; every candidate still enters `needs_review` regardless of confidence (`extractors_prescription.py:6-7`, `mdi/service.py:404`) | — | no detection that a document *is* handwritten → no "we can't read this, type it in" affordance. |
| 4 | **Multi-column / ruled lab tables** | Azure DI `prebuilt-layout` + per-row reflow (`ocr_engine.py:357-400`); per-hospital `ColumnMap` with validation and `skip_cols` (`lab_table_extractor.py:628-720`); footer-row exclusion (`:733-741`); instrument-name blocklist (`:226-282`) | **legacy `/lab-uploads` only** | the MDI document path uses a single-line regex (`extractors_lab.py:22-28`) and gets none of this. Tesseract's line reflow (`ocr_engine.py:110-126`) collapses columns by line number, which merges adjacent columns on wide tables. |
| 5 | **Reference range read as the result** | ref-range columns detected by VN/EN header keywords and dropped before reflow (`ocr_engine.py:327-349, 369-383`); regex requires a separator before the value so `HbA1c`'s embedded digit isn't the value (`extractors_lab.py:22-28`) | both | keyword list is finite; an unlisted header spelling reinstates the hazard. |
| 6 | **VN diacritics** | `ocr_lang = "vie+eng"` (`config.py:133`, installed as `tesseract-ocr-vie` in `Dockerfile:15`); accent-stripped matching throughout (`hospital_profiles.py:139-140`, `lab_table_extractor.py:374`) | both | measured OK on a clean render (§4.2); unmeasured on photos. |
| 7 | **Units** (`µ` dropped, `mg/dL` vs `mmol/L`, `G/L` vs `10^9/L`) | per-hospital `ocr_corrections` (`hospital_profiles.py:47`), `_apply_unit_corrections` (`lab_table_extractor.py:875`), SI conversion with incompatibility detection (`:931-946`); **promotion refuses** when the unit can't be mapped for an analyte that has thresholds — `is_unit_convertible(...)` → `PromotionInvalid` (`promoters.py:190-197`) | both | strongest control in the system. Verified working in §4.2 (`mol/L` → `µmol/L`). |
| 8 | **Analyte mis-identification** | `normalize_biomarker` alias table (28 biomarkers) | MDI path correct | **legacy parser defective** — HDL → total cholesterol (§4.3, OCR-F3), and it does not set `requires_review` even at confidence 0.0. |
| 9 | **Multi-page PDFs** | legacy: text-layer first → Azure → rasterize, capped at `ocr_pdf_max_pages=3` (`lab_upload.py:138-197`, `config.py:141`) | legacy only | **MDI path: hard failure** (§4.4, OCR-F2). A 20-page PDF is accepted at upload (`config.py:96`) and then 500s. |
| 10 | **Wrong date (DOB read as exam date)** | `OcrDateResolver` discards DOB-looking dates and flags low-confidence ones (`lab_upload.py:266-289`; `domain/ocr_date_resolver.py`, 37 tests) | legacy | MDI path has only a plain regex (`extractors_lab.py:30, 36-47`) and `_parse_date` **never fabricates "today"** (`promoters.py:143-164`) — safe but weaker. |
| 11 | **Duplicate / re-uploaded document** | stable `dedupe_key` per candidate + live-key carry-forward guard (`mdi/service.py:380-397`), `(patient_id, sha256)` accepted-doc uniqueness | both | — |
| 12 | **Zero biomarkers parsed** | cloud escalation when permitted (`lab_upload.py:250-261`) | legacy | MDI path just yields zero candidates and a `needs_review`-less document; the patient sees an empty review screen with no "OCR failed, enter manually" affordance. |
| 13 | **Classification error (wrong doc type)** | patient's capture-type hint is authoritative (`mdi/classifier.py:40-45`); keyword vote otherwise, `unknown` at score 0 (`:56-65`) | MDI | keyword vote is crude; the hint makes it moot in the app, which always sends one (`mobile/app/(app)/add-document.tsx:20-22,35,42`). |

---

## 7. What actually protects the patient today — and where it leaks

### 7.1 The safety net as designed

Nothing OCR produces becomes a clinical fact without an explicit per-item patient action:

- Every candidate is persisted as `CAND_STATUS_NEEDS_REVIEW`, unconditionally, whatever the confidence (`mdi/service.py:404`).
- Promotion happens **only** inside `confirm_candidate` / `merge_candidate` (`mdi/service.py:459-486, 489-520`) — there is no confidence threshold, no auto-accept, and no batch-confirm anywhere in the service.
- A diagnosis becomes a record only on explicit confirmation and never gets a canonical table (`promoters.py:116-127`).
- Unit-ambiguous lab values are **refused** rather than promoted (`promoters.py:190-197`).
- Prescription `quantity` is kept in the note, never injected into the dose, because a VN prescription's quantity is usually the dispensed total (`promoters.py:38-58`, CLIN PS-2).
- The AI context reads confirmed data only (ENG-RC / `builder.py::_build_recent_labs`), so an unconfirmed OCR error cannot reach Meto.
- The whole pipeline is behind a fail-closed `documents` consent gate at the single `_resolve_patient_id` chokepoint (`api/v1/routes/documents.py:78-102`) and behind `FeatureFlag.OCR` (`:74-75`), default OFF (`feature_flags.py:78`).

**This is the correct architecture, and it is what makes an imperfect OCR acceptable for a pilot:** the worst realistic outcome of a mis-read is that a patient is shown a wrong value and declines it, not that a wrong value silently enters the record.

### 7.2 Where the net leaks (new finding)

`mobile/app/(app)/review/[documentId].tsx` renders exactly three fields — `name`, `strength`, `frequency` (`:67-69`) — with a confirm/reject pair (`:85-102`).

- `LabExtractor` emits `test_name / value / unit / reference_range / canonical` and **no `name`** (verified in §4.3). `GeneralReportExtractor` emits `text / summary / report_date`. → a lab or general-report candidate renders as **`"Mục chưa rõ tên"`** (`mobile/src/i18n/vi.ts:187`) with **no value shown at all**.
- The patient is therefore asked to confirm a **blank card** for exactly the two document types with the highest numeric risk — and the app offers all three capture types (`add-document.tsx:20-22`).
- No per-field confidence is displayed, although `field_confidence_json` is populated (`extractors_prescription.py:135-139`) and returned by the API.
- `confirmCandidate(client, candidateId)` sends **no corrections** (`mobile/src/features/documents/useDocumentReview.ts:64-68`; `mobile/src/api/documents.ts:145-153`), even though the backend accepts and audits them (`mdi/service.py:588-601`). **The patient cannot fix an OCR error — only accept it or discard the whole item.**
- The Android pilot never exposed this: its Journey A used the **prescription-only** QA fixture (`app/fixtures/__init__.py:32-45`), the one type the screen renders correctly.

→ **OCR-F5.** Until this is fixed, "mandatory patient confirmation" is a valid safety claim **for prescriptions only**.

---

## 8. Pilot verdict

| Question | Answer |
|---|---|
| Is OCR quality *measured*? | **No.** §4 is the entirety of the evidence; none of it is image-derived except a clean synthetic render. |
| Does that block the **synthetic controlled pilot**? | **No** — pilot data is synthetic, `FeatureFlag.OCR` is owner-gated, and no OCR output can become a clinical fact without confirmation (§7.1). |
| Does it block **public beta**? | **Yes.** Beta means real patients photographing real reports; shipping an unmeasured extraction pipeline onto real PHI is not defensible. §7 is the beta plan. |
| May the pilot claim "OCR works"? | **No.** Journey A exercised a deterministic fixture, not an OCR engine (§5). The claim the pilot supports is "the ingest→review→promote *workflow* works for prescriptions". |
| Is the "no PHI to cloud" claim in the launch docs true? | **No** — see OCR-F1. This is the single most important correction in this report. |

---

## 9. NEW findings (this assessment)

| ID | Sev | Finding | Evidence | Exact fix |
|---|---|---|---|---|
| **OCR-F1** | **P0** | **Cloud OCR is ON in staging *and* production deploy config, and the flag that is supposed to gate it does not gate the code path that runs.** `azure-staging.yml:211-214` and `azure-production.yml:224-227` both set `MCP_FEATURE_OCR=true MCP_FEATURE_OCR_CLOUD_FALLBACK=true MCP_OCR_CLOUD_PROVIDER=azure AZURE_DOC_INTEL_ENDPOINT=… AZURE_DOC_INTEL_KEY=secretref:doc-intel-key`, sourced from Key Vault (`azure-staging.yml:124-129`). And `run_ocr` selects Azure **first, unconditionally, whenever the two env vars are present** (`ocr_engine.py:491-492`) — it never calls `is_enabled(FeatureFlag.OCR_CLOUD_FALLBACK)`; only `_cloud_engine()` (`:417-431`) does, and that is used solely by the zero-biomarker escalation (`:434-449`). ⇒ **every uploaded medical image and PDF is sent to Azure Document Intelligence**, and setting `MCP_FEATURE_OCR_CLOUD_FALLBACK=false` would **not** stop it. This directly contradicts `00-CURRENT-STATE.md §3` ("`OCR_CLOUD_FALLBACK` **OFF** … no PHI leaves device/region until owner authorizes"), `§8` ("cloud PHI processing stays DISABLED until owner authorizes **and** supplies the key" — the key is already supplied), `TRACKING.md` R-05 and §H ("Local/mock OCR only — cloud OCR disabled (no PHI to cloud)"). The workflow's own comment (`azure-staging.yml:195-198`, "Tesseract stays PRIMARY … called ONLY when local confidence is low") is also false w.r.t. the code, and is contradicted by the repo's own tests `tests/test_lab_ocr.py:493-506` (`test_run_ocr_uses_azure_primary_ignoring_local_confidence`) and `:722` (`test_run_ocr_azure_primary_bypasses_tesseract`). | as cited | **(a)** Decide, at owner level, whether PHI-to-Azure-DI is authorized; a DPA/BAA-equivalent and the data region must be confirmed first. **(b)** If not yet authorized: remove `AZURE_DOC_INTEL_ENDPOINT`/`AZURE_DOC_INTEL_KEY`/`MCP_FEATURE_OCR_CLOUD_FALLBACK`/`MCP_OCR_CLOUD_PROVIDER` from `azure-staging.yml:211-214` and `azure-production.yml:224-227` (owner-gated file per the Azure-workflow guardrail — do not edit unilaterally). **(c)** Regardless: gate the primary branch — `ocr_engine.py:491` becomes `if is_enabled(FeatureFlag.OCR_CLOUD_FALLBACK) and AzureDocIntelEngine.configured():` — so the documented kill-switch is real, and add a regression test asserting Azure is not called with the flag off. **(d)** Correct `00-CURRENT-STATE.md §3/§8`, `TRACKING.md` R-05/§H, and the `azure-staging.yml:195-198` comment to state the true posture. |
| **OCR-F2** | **P1** | **Any PDF uploaded through the Journey-2 document pipeline hard-fails with HTTP 500 when Azure DI is unavailable**, leaving an orphan accepted blob. `mdi/service.py:331-346` passes the raw file as a single "page" with no rasterization; `TesseractEngine.run` cannot decode a PDF (measured, §4.4) and raises `OcrEngineError`, which `documents.py:220-243` does not catch. The accepted blob is written first (`mdi/service.py:245-250`), so the rolled-back transaction leaves storage garbage (feeds PROD-F6). PDFs up to 20 pages are accepted (`config.py:96`) although the OCR path caps at 3 (`config.py:141`). | measured, §4.4 | Rasterize in `_run_extraction`: when `doc.mime == "application/pdf"`, convert with `pdf2image.convert_from_bytes(..., last_page=settings.ocr_pdf_max_pages)` (already a dependency; poppler is in `Dockerfile:11-16`) and pass one entry per page to `run_pipeline(page_bytes=…)` — which already supports multi-page. Then wrap the call in `try/except OcrEngineError` → set `DOC_STATUS_FAILED` with a patient-facing "không đọc được tài liệu — vui lòng nhập tay", and sweep the accepted blob. Add a regression test for a 2-page PDF with Azure unconfigured. |
| **OCR-F3** | **P1** | **`lab_parser.parse_lab_text` maps `HDL Cholesterol` to `total_cholesterol`** (measured, §4.3) — an HDL value is stored, converted and trended as total cholesterol, and classified against total-cholesterol thresholds. `Cholesterol HDL` and `Non-HDL Cholesterol` mis-map the same way. `normalize_biomarker` gets all three right, so the defect is in the parser's alias-matching order. `requires_review` stays `False` even when the confidence detail is `clinical=0.0 / overall=0.0` with the reason *"giá trị ngoài khoảng sinh lý — có thể lỗi OCR"*. Affects the legacy `/lab-uploads` + web path (the mobile MDI path is correct). | measured, §4.3 | In `app/services/lab_parser.py`, match analyte aliases **longest-first** (or require a whole-token match anchored at the start of the label) so `hdl cholesterol` wins over `cholesterol`; and set `requires_review=True` whenever `confidence_detail.overall == 0.0`. Add regression tests for `HDL Cholesterol`, `Cholesterol HDL`, `Non-HDL Cholesterol`, `LDL Cholesterol`, `Cholesterol toàn phần`. |
| **OCR-F4** | **P1** | **The pilot's document path produces zero OCR quality telemetry.** The whole correction-feedback loop — `OCRCase` rows, `compute_gap`, dataset export, and the `Dev — OCR Gap Report` workflow (`.github/workflows/dev-ocr-report.yml`) — is wired **only** to the legacy path: `create_case` at `api/v1/routes/lab_upload.py:121` and `confirm_case` at `services/lab.py:624`. `grep -rn "ocr_case" app/services/mdi/` returns nothing. The mobile app never calls `/lab-uploads`. ⇒ a controlled pilot on the document journey will end with **no accuracy data at all**, and `scripts/ocr_accuracy_report.py` will print *"No confirmed OCRCase records found."* | as cited | On `mdi.confirm_candidate` / `merge_candidate`, emit an OCR case record from the data already captured: `candidate.corrections_json` (`mdi/service.py:588-601`) is a full before/after per confirmation. Simplest correct shape: reuse `domain/ocr_gap_analysis.compute_gap` on `{extracted: history[0].fields, corrected: candidate.fields_json}` and persist per-candidate edit counters keyed by `doc_type` + `provider`. Ship this **before** the pilot — it is the only thing that will turn the pilot into corpus. |
| **OCR-F5** | **P1** (P0 if lab/general capture is enabled for real data) | **The patient-confirmation safety net is blind for lab and general-report candidates, and offers no correction.** The review screen renders only `name`/`strength`/`frequency` (`mobile/app/(app)/review/[documentId].tsx:67-69`); lab candidates carry `test_name/value/unit` and general candidates carry `text/summary`, so both render as `"Mục chưa rõ tên"` (`vi.ts:187`) with no value. No per-field confidence is shown despite the API returning it. `confirmCandidate` sends no `corrections` (`useDocumentReview.ts:64-68`, `api/documents.ts:145-153`) although the backend supports and audits them. The Android pilot never caught this because its fixture is prescription-only (`app/fixtures/__init__.py:32-45`). | as cited | Render per-`candidate_type`: lab → `original_test_name`, `value`, `unit`, `reference_range`; general → `text` (+ type badge); prescription → current fields. Show the low-confidence fields from `field_confidence`. Add inline editing that posts `corrections` to `POST /candidates/{id}/confirm`. Add a Maestro flow for a **lab** fixture (a second `QaFixture` with `doc_type_hint="lab_report"`) so the regression is covered on-device. Until shipped, restrict capture to `prescription` in `add-document.tsx:20-22` for any non-synthetic pilot. |
| **OCR-F6** | **P2** | **Zero accuracy evidence for prescription and general-report extraction, and no way to produce any.** There is no ground-truth schema for either type (`ocr_dataset/schema/` holds only `expected_lab_report.schema.json`), no corpus, and no harness. `test_mdi_prescription.py:7-16` and `test_mdi_general.py:7-13` assert against hand-written clean text — they measure the parser, not OCR. | as cited | Part of §10's corpus plan: add `expected_prescription.schema.json` and `expected_general_report.schema.json`, and extend `benchmark_ocr.py` with per-type scoring (medication name/strength/frequency exact-match; segment-type precision/recall). Beta-scope. |
| **OCR-F7** | **P2** | **The published accuracy targets have never been measured and read as if they had.** `ocr_dataset/README.md:11-12` states "Vinmec ≥95% … Medlatec ≥90%" under a heading that implies achieved status; the harness's own thresholds are looser (`benchmark_ocr.py:302-313`: 0.10 / 0.15) and no image has ever been scored. 5 of 11 hospital directories have no expected file; `golden/` is empty; 2 of 7 shipped profiles (`fv`, `bachmai108`) have no sample at all. | §3, §4.1 | Rewrite `ocr_dataset/README.md:9-13` as **"Targets (not yet measured)"** with a link to this report, and reconcile the two threshold sets into one source of truth (`_EDITING_TARGETS`). |
| **OCR-F8** | **P2** | **Dead/confusing OCR config.** `MCP_OCR_MODE=mock` is set in both staging and production (`azure-staging.yml:206`, `azure-production.yml:220`) and looks like it enables mock OCR — it does not: `run_ocr` reads `MCP_OCR_PROVIDER` / `MCP_ENABLE_MOCK_OCR` (`ocr_engine.py:457-462`), while `ocr_mode` (`config.py:83`) belongs to the unused legacy `app/services/ocr.py` skeleton. A reader auditing the deploy config will conclude OCR is mocked in production. | as cited | Retire `app/services/ocr.py` and the `ocr_mode`/`ocr_provider_url`/`ocr_api_key` settings (`config.py:83-85`), and drop `MCP_OCR_MODE` from both workflows. Already listed as deferred debt in program memory; OCR-F1 makes it actively misleading. |

---

## 10. Beta plan — a labelled VN corpus and a real scoring harness

The infrastructure is ~70% built. The missing pieces are data and two wiring changes.

### 10.1 Corpus (target: **beta gate**)

**Sourcing.** Do not scrape. `ocr_dataset/USER_CORRECTION_FEEDBACK_LOOP.md` and `README.md:130-136` already define the lawful route: patient-uploaded reports → patient corrects → PHI removed → the corrected rows become ground truth. Two supplementary sources: staff/founder-supplied own reports, and printed reports produced by partner clinics with no patient identifiers.

**Size and shape (minimum viable for a beta gate):**

| Tier | Docs | Composition |
|---|---|---|
| `golden/` (frozen, hand-verified twice) | **50** | 10 lab reports each from vinmec + medlatec; 5 each from tamanh, hongngoc, bachmai, bachmai108, fv — currently 0 |
| `benchmark/` lab | **150** | ≥3 capture conditions per document: flat scan, handheld photo (≤10° skew), poor light |
| `benchmark/` prescription | **60** | 40 printed, 20 handwritten (handwriting scored separately and expected to fail — the goal is a reliable "we can't read this" signal, not accuracy) |
| `benchmark/` general report | **40** | discharge / imaging / pathology / referral, 10 each |
| Adversarial | **20** | crumpled, glare, partial crop, rotated 90°, two reports in one frame, non-medical photo |

**Process (unchanged from `README.md:60-110`, which is sound):** `<yyyymmdd>_<hospital>_<seq>`; strip name, DOB, patient/CCCD/BHYT id, address, phone, doctor name; keep `test_date` only; set `anonymized: true` / `contains_phi: false` **after** manual review; commit `expected/*.json` + `notes/*.md` only, never `images/`, `azure_cache/`, `incoming/`, `anonymized/` (`.gitignore:5-19`). Images live in a private, access-logged store — **not** in git, and **not** in the same account as production PHI.

**New schemas needed:** `schema/expected_prescription.schema.json` (per-medicine name/strength/form/frequency/route/duration/quantity) and `schema/expected_general_report.schema.json` (ordered typed segments). Validate both in `scripts/ocr_dataset_validate.py`.

### 10.2 Scoring harness

1. **Turn on image mode.** `benchmark_ocr.py`'s image path already exists (`:1-40` layout, `:280-345` per-hospital report, `:395-430` acceptance gates: detect ≥99%, accuracy ≥85%, avg editing <15%). It needs (a) images, (b) the `azure_cache/` replay wired so a re-run costs $0, and (c) a decision on whether it scores the **local** engine, the **cloud** engine, or both — today it implicitly assumes Azure.
2. **Score both engines, always.** Emit one row per (engine × hospital × condition). This is what makes the OCR-F1 decision quantitative: if local Tesseract is within a few points of Azure on the corpus, the PHI-to-cloud dependency can simply be dropped.
3. **Per-type scorers.** Lab: row recall, analyte precision, value exact-match, unit exact-match, range match, UER. Prescription: medicine recall, name edit distance, strength/frequency exact-match, and a **dose-safety** counter (any promoted dose differing from truth = automatic fail). General: segment-type precision/recall + `diagnosis` never mis-typed as `medication` (guards the `_MED_RE` re-typing at `extractors_general.py:31`).
4. **Close the loop (OCR-F4).** Emit an OCR case + gap on every MDI confirmation. Then `scripts/ocr_accuracy_report.py` and `.github/workflows/dev-ocr-report.yml` start producing live per-hospital UER from real usage, and `domain/ocr_dataset_export.py` (already consent- and env-gated, `:52-58`) grows the corpus automatically.
5. **CI.** Add a `--synthetic-mode` run to CI now (fast, no creds, catches alias regressions — it would **not** have caught OCR-F3, so add the §4.3 cases as unit tests too). Add the image benchmark as a manual `workflow_dispatch` job with cached Azure responses once the corpus exists.

### 10.3 Beta exit criteria (proposed)

| Metric | Gate |
|---|---|
| Lab UER, vinmec / medlatec | ≤10% / ≤15% (match `_EDITING_TARGETS`) — **measured on ≥20 real images each** |
| Lab UER, all other profiles | ≤20% |
| Hospital detection | ≥95% on real headers (relax the current `≥99%` — it is not achievable on photos) |
| Unit exact-match | ≥98%, **and** zero promoted rows with an unconvertible unit |
| Prescription dose-safety failures | **0** |
| Diagnosis mis-typed as medication | **0** |
| Documents where OCR yields nothing | <10%, and 100% of those show a "nhập tay" affordance |
| OCR-F1…F5 | closed |

### 10.4 Reproduction of the §4.2 probe

```python
# run from backend/ with the venv active; PYTHONPATH=backend
import io, app.core.config, app.services.ocr_engine as oe
oe.AzureDocIntelEngine.configured = staticmethod(lambda: False)   # force the local path
oe._is_mock_explicitly_allowed = lambda: False
from PIL import Image, ImageDraw, ImageFont
from app.services import lab_parser
TEXT = oe._MOCK_TEXT.strip().splitlines()                          # ocr_engine.py:133-150
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 22)
img = Image.new("RGB", (760, 36 + 34 * len(TEXT)), "white"); d = ImageDraw.Draw(img)
for i, ln in enumerate(TEXT): d.text((18, 18 + i * 34), ln, fill="black", font=font)
b = io.BytesIO(); img.save(b, format="PNG")
res = oe.run_ocr(b.getvalue(), "image/png")
print(res.provider, res.confidence, sorted({p.test_name for p in lab_parser.parse_lab_text(res.text)}))
```

---

## 11. Tracking deltas requested

- `TRACKING.md` §A WS6 → **🟡 ASSESSED — no measured accuracy; 1 P0 + 4 P1 open** (was ⏳).
- `TRACKING.md` §C: **R-05 is falsified** — "Cloud OCR PHI-to-cloud path exists but must stay OFF … ✅ controlled" is not the deployed state. Replace with OCR-F1.
- `TRACKING.md` §H: strike "Local/mock OCR only — cloud OCR disabled (no PHI to cloud)" until OCR-F1 is resolved.
- `00-CURRENT-STATE.md` §3 flag table (`OCR_CLOUD_FALLBACK` = OFF) and §8 ("cloud PHI processing stays DISABLED … until owner … supplies the key") need the same correction.
- `15-FINAL-LAUNCH-REVIEW.md` §2 WS6 verdict and §3 P0 register need OCR-F1 added.
