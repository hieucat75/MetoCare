# ADR-05 — OCR Medication Pipeline

**Status:** PROPOSED — Gate 3 (expansion — deferred to P2)  
**Date:** 2026-07-11  
**Deciders:** PTH, Tech Lead  
**Depends on:** ADR-04 (medication_statements table), ADR-01 (catalog matching)

---

## Context

MetoCare có OCR pipeline trưởng thành cho lab results (Google Cloud Vision, structured table extraction, confidence scoring). Prescription OCR là nhu cầu khác: đọc freeform prescription text, extract drug names, doses, frequencies, doctor names từ printed/handwritten Vietnamese prescriptions.

---

## Problem

Lab OCR pipeline KHÔNG thể reuse cho prescription OCR vì:
1. Lab results = structured table (test | value | unit | reference range) → table extraction
2. Prescriptions = freeform narrative text (drug name, dose, instructions in Vietnamese paragraphs) → NLP extraction
3. Vietnamese prescription format: không chuẩn, mỗi bệnh viện format khác
4. Handwritten prescriptions: phổ biến tại VN, OCR accuracy thấp hơn nhiều
5. Abbreviations: "mg", "viên", "lần", "sáng tối" — VN-specific parsing needed

OCR pipeline sai có thể cho patient nhập sai thuốc — đây là clinical safety issue.

---

## Decision Drivers

- OCR output MUST NOT go directly into `medications` table (CML)
- Patient must confirm EVERY field before medication is created
- Confidence score per field, not per document
- Low-confidence fields must be empty (not pre-filled) in review UI
- Prescription OCR is P2 — not blocking P0/P1
- Can reuse OCR infrastructure (Google Cloud Vision API), NOT the extraction logic

---

## Options Considered

### Option A — Reuse lab OCR pipeline
Wrong domain. Lab OCR reads tables. Prescription reads narrative. Sharing pipeline = bad accuracy.

### Option B — Separate prescription extraction pipeline using VLM
Use Vision Language Model (e.g., GPT-4o, Gemini Vision) to extract structured data from prescription images. Better accuracy for freeform text.

### Option C — Two-stage: traditional OCR text extraction + LLM parsing
Stage 1: Cloud Vision → raw text. Stage 2: LLM → parse raw text into structured medication fields.

### Option D — Manual entry only (skip OCR entirely)
Remove OCR from scope. Patient types all medications manually.

---

## Trade-off Table

| Criterion | A (lab OCR reuse) | B (VLM direct) | C (OCR + LLM parse) | D (manual only) |
|-----------|-------------------|----------------|---------------------|-----------------|
| Accuracy for freeform prescription | ❌ Low | ✅ High | ✅ High | N/A |
| Cost | ✅ Existing infra | ⚠️ Per-call API cost | ⚠️ Two API calls | ✅ Zero |
| Handles handwriting | ❌ | ✅ | ⚠️ Depends on OCR quality | N/A |
| Vietnamese-specific parsing | ❌ | ✅ | ✅ (LLM can handle) | N/A |
| Infrastructure reuse | ✅ | ⚠️ Partial | ✅ (OCR part) | ✅ |
| Latency | ✅ Fast | ⚠️ Slower | ⚠️ Slower | ✅ |
| PHI sent to external AI | N/A | ❌ High risk | ❌ High risk | ✅ No |
| Implementation effort | ✅ Low | ⚠️ Medium | ⚠️ Medium | ✅ Low |

---

## Recommended Decision

**Option C — Two-stage pipeline: Cloud Vision OCR text extraction + LLM parsing, with strict PHI controls and mandatory human review.**

Option B (VLM direct) có accuracy tốt nhất nhưng gửi prescription image trực tiếp cho external AI — đây là PHI exposure issue cần policy decision từ PTH.

Option D là safe fallback nếu PTH quyết định PHI risk của Option C không acceptable.

---

## Why This Option

- Stage 1 (Cloud Vision): already integrated, handles VN character recognition
- Stage 2 (LLM parse): dùng instruction-tuned model để parse raw text → structured JSON. Model KHÔNG thấy patient identity, chỉ thấy prescription text.
- PHI mitigation: strip patient name, DOB, ID number from raw text BEFORE sending to LLM

**PHI STRIPPING STEP is mandatory** before LLM parsing:
```
Raw OCR text (contains PHI):
  "Họ tên: Nguyễn Văn A, SĐT: 0901234567
   Thuốc: Metformin 500mg, uống 2 lần/ngày sau ăn..."

After PHI strip (sent to LLM):
  "[PATIENT_INFO_REDACTED]
   Thuốc: Metformin 500mg, uống 2 lần/ngày sau ăn..."
```

---

## Consequences

**Pipeline stages:**
```
1. CAPTURE
   Patient uploads image → validate file type, size (max 10MB), format (jpg/png/pdf)

2. OCR TEXT EXTRACTION (Cloud Vision)
   → raw_text (may contain PHI)
   → store raw_text ENCRYPTED in medication_statements.raw_source_encrypted
   → NEVER log raw_text

3. PHI STRIPPING (before LLM)
   → Regex-strip: phone numbers, dates of birth, patient IDs, common VN name patterns
   → stripped_text does not contain identifiers

4. LLM PARSING (Gemini/Claude with structured output)
   Input: stripped_text + prompt
   Prompt: "Extract medication list from this Vietnamese prescription text. Return JSON array:
     [{drug_name, dose_text, frequency_text, duration_text, prescriber_name}]
     For each field, include confidence: high|medium|low|unknown"
   
   → Returns: extraction_candidates[]

5. CATALOG MATCHING
   For each extraction_candidate.drug_name:
     → normalize_medication_name() against drug catalog
     → set drug_product_id if confidence >= 0.8
     → set match_confidence score

6. STATEMENT CREATION
   → INSERT INTO medication_statements (source_type='ocr_pending', ...)
   → One statement per extracted drug
   → All statements status='pending'
   → RETURN statement_ids to frontend

7. PATIENT REVIEW (mandatory — frontend)
   For each statement:
     → Show all fields with confidence indicators
     → Patient edits and confirms each field
     → Patient taps "Xác nhận" per medication
   
   High confidence (≥ 80%): pre-fill, green indicator
   Medium confidence (50-79%): pre-fill, yellow indicator + "Kiểm tra lại"
   Low confidence (< 50%): EMPTY FIELD + red indicator + "Cần nhập thủ công"
   
   SAFETY RULE: "Xác nhận" button disabled until patient interacts with every red field

8. MEDICATION CREATION (after patient confirms)
   → UPDATE medication_statements SET status='accepted'
   → INSERT INTO medications (source_type='ocr_confirmed')
   → Run CDS checks (allergy, interaction, duplicate)
   → Surface any alerts BEFORE final save confirmation
```

**Confidence per field, not per document:**
- `drug_name`: high if exact catalog match, low if fuzzy
- `dose_text`: high if contains number + unit, low if "1 viên" without mg
- `frequency_text`: high if standard pattern (BID/TID), low if freeform

**Handwritten prescriptions:**
- Accept that accuracy will be lower
- Increase minimum review interaction requirement (all fields orange/red unless patient edits)
- Consider flagging as "handwritten" → different UI warning

**Error states:**
- OCR completely fails → redirect to manual entry, no error content logged
- LLM returns malformed JSON → retry once, then fallback to manual entry
- Zero drugs extracted → "Không đọc được đơn thuốc. Vui lòng nhập thủ công."

---

## Data Model Impact

- Requires `medication_statements` table (ADR-04)
- `medication_statements.raw_source_encrypted` field for raw OCR text (EncryptedString)
- `medication_statements.extraction_session_id` for grouping statements from one OCR session

---

## API Impact

- `POST /patients/{id}/medications/ocr-upload` → returns session_id
- `GET /patients/{id}/medications/ocr-sessions/{session_id}` → extraction candidates
- `POST /patients/{id}/medications/ocr-sessions/{session_id}/confirm` → create medications from confirmed statements
- `POST /patients/{id}/medications/ocr-sessions/{session_id}/cancel` → discard all

---

## Security and Privacy Impact

- **Raw prescription image: never stored** — processed in memory, discarded after extraction
- **Raw OCR text: stored encrypted** in `medication_statements.raw_source_encrypted`
- **LLM input: PHI-stripped text only**
- **LLM provider must have data processing agreement** — NO training on submitted data. Currently: Anthropic (zero data retention policy) or Google Gemini (with DPA). **[PTH must confirm LLM provider DPA status]**
- Raw OCR text is NOT included in any log, error message, or analytics event
- Extraction session expires after 24h if not confirmed → data discarded

---

## Clinical Safety Impact

**Non-negotiable safety rules:**
1. `ocr_pending` statements NEVER appear in CML, never sent to AI context, never shown in medication list
2. Patient MUST confirm every medication individually — no "confirm all" button
3. CDS checks (allergy/interaction) run AFTER catalog match but BEFORE final save
4. If CDS finds CRITICAL alert on OCR-extracted drug: show alert on review screen, require patient to explicitly acknowledge before confirming

---

## Migration Impact

No existing data affected. New tables (ADR-04), new API endpoints. Safe.

---

## Operational Ownership

- OCR accuracy monitoring: track extraction accuracy metrics per session (post-confirmation edit rate)
- LLM prompt versioning: maintain prompt version in `medication_statements.extraction_prompt_version`
- Monthly review of most-common low-confidence extractions → improve PHI stripping or prompt

---

## Open Questions

1. **LLM provider data agreement:** Is Anthropic/Google DPA confirmed for processing Vietnamese prescription text? **[PTH must confirm before P2 start — STOP GATE]**
2. **Handwritten prescription scope:** Include or exclude handwritten prescriptions in P2? Accuracy is significantly lower. **[PTH product decision]**
3. **PDF prescriptions from hospitals:** Some Vietnamese hospitals issue PDF prescriptions. Does scope include PDF? **[PTH decides — same pipeline if so]**

---

## Approval Required From

- [ ] PTH — PHI risk acceptance for LLM-based parsing
- [ ] PTH — LLM provider DPA confirmation (stop gate before P2)
- [ ] PTH — handwritten prescription in/out of P2 scope
- [ ] Tech Lead — PHI stripping implementation review

## Implementation Gate

**Gate 3 — expansion feature. Does NOT block P0/P1.**  
ADR-04 (`medication_statements`) must be approved and implemented before this ADR can ship.  
LLM DPA confirmation is a hard stop gate before any prescription image touches external API.
