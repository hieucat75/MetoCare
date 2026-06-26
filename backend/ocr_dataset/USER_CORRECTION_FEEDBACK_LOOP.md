# User Correction Feedback Loop

Design document for converting user-corrected OCR sessions into benchmark ground truth.

**Status: Design only — not yet implemented in the API.**

---

## Problem

MetoCare cannot collect real lab images from the internet due to PHI concerns. The only sustainable source of real ground truth is users themselves: they upload their own reports, the OCR pipeline produces a draft, and they correct whatever is wrong before saving.

Every correction is a signal. Capturing those signals turns every upload session into a potential benchmark sample.

---

## Future flow

```
User uploads lab report PDF/image
    │
    ▼
Azure DI extracts table rows
    │
    ▼
Hospital profile maps columns → RawLabValue list (OCR draft)
    │
    ▼
User sees OcrReviewCard:
  - Rows with requires_review=True are flagged
  - User edits incorrect values, test names, units
    │
    ▼
User clicks Save
    │
    ▼ (future — not yet implemented)
System captures CorrectionSession:
  - lab_batch_id
  - hospital_id
  - detection_confidence
  - image_sha256_prefix (8 hex chars, for dedup only)
  - ocr_draft_rows (structured JSON)
  - user_corrected_rows (structured JSON)
  - delta (list of RowDiff)
  - corrected_at
    │
    ▼
Periodic export (admin action):
  - Filter sessions with >= 1 correction
  - Admin reviews, anonymizes image, moves to ocr_dataset/incoming/
  - Creates expected.json from user_corrected_rows
  - Moves to ocr_dataset/benchmark/<hospital>/
```

---

## What is stored

| Field | Stored | Notes |
|-------|--------|-------|
| Raw image bytes | NO | Never stored at rest |
| Raw OCR text | NO | Only structured rows stored |
| Image SHA-256 prefix | YES (8 chars) | Dedup only; cannot reconstruct image |
| OCR draft rows | YES | Structured JSON |
| User-corrected rows | YES | Source of ground truth |
| Patient name / DOB / ID | NO | Stripped before save |
| Test values / units | YES | These are the ground truth |

---

## Delta format (per row)

```json
{
  "row_index": 3,
  "field": "value",
  "ocr_value": "4.7O",
  "user_value": 4.70,
  "edit_type": "ocr_digit_error"
}
```

Edit types: `ocr_digit_error`, `ocr_unit_error`, `wrong_column`, `missing_row`, `extra_row`, `test_name_error`, `user_addition`

---

## Metrics derived from corrections

**User Editing Rate (UER):**
```
UER = rows_with_any_edit / total_rows_shown
```
Targets: Vinmec < 5%, Medlatec < 10%

**Field Error Rate (FER):**
```
FER_value = value_edits / total_rows
FER_unit  = unit_edits / total_rows
```

---

## Privacy invariants

1. Raw image bytes are never stored by the application.
2. Raw OCR text (full Azure DI JSON) is never stored — only structured rows.
3. Image SHA-256 prefix (8 chars) is stored for dedup only.
4. Any `expected.json` committed to git must have `contains_phi: false`.
5. `incoming/` and `anonymized/` are in `.gitignore` and must never be staged.

---

## Implementation notes (when ready to build)

Add to existing `POST /api/v1/labs/upload` flow:

1. After `extract_and_map()` produces the OCR draft, store draft rows on `LabBatch`.
2. After `save_lab_batch()` persists corrected rows, compute delta between draft and saved.
3. Store delta in `LabBatch.ocr_correction_delta JSONB` (new column, Alembic migration needed).
4. Add admin endpoint `GET /admin/ocr/correction-sessions` to export sessions.

No ML training plumbing needed — just delta storage and export.
