# MetoCare OCR Dataset

Ground-truth benchmark and golden dataset for Vietnamese hospital lab report OCR.

---

## Why this dataset exists

MetoCare's OCR pipeline (Azure Document Intelligence + hospital-profile parsing) needs measurable accuracy targets:

- Vinmec: ≥ 95% row-level accuracy (User Editing Rate < 5%)
- Medlatec: ≥ 90% row-level accuracy (User Editing Rate < 10%)

This dataset provides the ground truth to measure those numbers. Real lab images are never collected from the internet — they come from users who upload their own reports, correct OCR errors, and (after PHI removal) contribute to the benchmark.

---

## Directory structure

```
ocr_dataset/
├── .gitignore            # Protects images/, azure_cache/, incoming/, anonymized/
├── README.md             # This file
├── USER_CORRECTION_FEEDBACK_LOOP.md
├── schema/
│   └── expected_lab_report.schema.json
├── golden/               # High-confidence reference samples (manually reviewed)
│   └── <hospital>/
│       ├── images/       # NOT committed — store locally only
│       ├── expected/     # Committed: *.expected.json ground truth
│       ├── azure_cache/  # NOT committed — Azure DI response cache
│       └── notes/        # Committed: *.md annotation notes
├── benchmark/            # Working accuracy measurement set
│   └── <hospital>/       # Same structure as golden/
├── incoming/             # NOT committed — raw uploads awaiting anonymization
├── anonymized/           # NOT committed — working copies during PHI removal
└── reports/              # Committed: benchmark run output reports
```

**Hospitals:** vinmec, medlatec, tamanh, hongngoc, bachmai, bachmai108, fv, hoanmy, thucuc, vietduc, other

---

## Sample ID convention

```
<yyyymmdd>_<hospital>_<sequence>
```

Example: `20261224_vinmec_001`

All four files for a sample share the same ID:

| File | Path |
|------|------|
| Image | `benchmark/vinmec/images/20261224_vinmec_001.jpg` |
| Ground truth | `benchmark/vinmec/expected/20261224_vinmec_001.expected.json` |
| Azure DI cache | `benchmark/vinmec/azure_cache/20261224_vinmec_001.azure.json` |
| Notes | `benchmark/vinmec/notes/20261224_vinmec_001.md` |

---

## How to add a new sample

### 1. Receive the image

Store the raw image locally (never commit):
```
benchmark/vinmec/images/20261224_vinmec_002.jpg
```

### 2. Anonymize

Remove before creating expected.json:
- Patient full name
- Date of birth (keep test_date only)
- Patient ID / CCCD / BHYT number
- Address, phone number, doctor name

Set `"anonymized": true` and `"contains_phi": false` in the expected.json.

### 3. Create expected.json

```bash
cp benchmark/vinmec/expected/20261224_vinmec_001.expected.json \
   benchmark/vinmec/expected/20261224_vinmec_002.expected.json
```

Edit to match the actual lab values from the image. See schema:
`schema/expected_lab_report.schema.json`

Rules:
- `original_test_name` = verbatim as printed (not translated)
- `value` = numeric only (not string)
- `unit` = as printed (not canonicalized)
- `reference_range` = as printed including dashes/arrows
- `mapped_metric_type` = null if uncertain

### 4. Validate

```bash
cd backend
python scripts/ocr_dataset_validate.py
```

### 5. Commit only safe files

```bash
git add ocr_dataset/benchmark/vinmec/expected/20261224_vinmec_002.expected.json
git add ocr_dataset/benchmark/vinmec/notes/20261224_vinmec_002.md  # optional
```

Never `git add ocr_dataset/*/images/` or `azure_cache/` or `incoming/` or `anonymized/`.

---

## How to run the benchmark

```bash
cd backend
export AZURE_DOC_INTEL_ENDPOINT="https://your-resource.cognitiveservices.azure.com/"
export AZURE_DOC_INTEL_KEY="your-key"

# All hospitals
python scripts/benchmark_ocr.py --bench-dir ./ocr_dataset/benchmark

# One hospital
python scripts/benchmark_ocr.py --bench-dir ./ocr_dataset/benchmark --hospital vinmec

# Use cached Azure DI responses (no API calls)
python scripts/benchmark_ocr.py --bench-dir ./ocr_dataset/benchmark --no-cache
```

---

## What not to commit

| Path | Why |
|------|-----|
| `images/*` | May contain patient PHI |
| `azure_cache/*` | Raw OCR text may reflect PHI |
| `incoming/*` | Unreviewed uploads |
| `anonymized/*` | Work-in-progress PHI removal |

---

## Ground truth sources

1. **User correction** — user corrects OCR errors in the review screen; corrected rows become ground truth
2. **Manual annotation** — admin transcribes values directly from image
3. **Synthetic samples** — fabricated rows for schema/script testing (no image required)
4. **Real samples after PHI removal** — real reports with all identifiers removed

See `USER_CORRECTION_FEEDBACK_LOOP.md` for how user corrections become benchmark samples over time.

---

## Dataset scripts

```bash
# Verify directory tree, show summary
python scripts/ocr_dataset_init.py

# Validate all expected/*.json against schema
python scripts/ocr_dataset_validate.py
```
