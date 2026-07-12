# MEDICATION_SAFETY_RULES.md
# MetoCare — Medication Safety Rules

**Version:** 1.0  
**Date:** 2026-07-10  
**Classification:** Clinical Safety — All engineers must read before implementing any medication feature  
**Review Required:** Vietnamese doctor review required before production deployment of interaction/allergy features

---

## 1. Foundational Safety Principles

These rules are non-negotiable. They apply to every layer of the stack: AI, backend, frontend, and OCR.

| Rule ID | Rule | Enforcement Point |
|---------|------|-------------------|
| SR-001 | AI MUST NOT create, modify, or delete any medication record | Route RBAC: `AI_SERVICE` → 403 on all medication writes |
| SR-002 | AI MUST NOT recommend starting, stopping, or changing any medication dose | Guardrails: `FORBIDDEN_RESPONSE_PATTERNS` + prompt policy |
| SR-003 | AI MUST NOT interpret interaction warnings as definitive clinical diagnoses | Prompt policy + output guardrail |
| SR-004 | OCR MUST NOT auto-activate a medication record without patient confirmation | Service layer: `source_type = 'pending_ocr'` until confirmed |
| SR-005 | Brand name and generic name MUST NOT be conflated | Service: denormalize `generic_name` at creation from catalog |
| SR-006 | All interaction warnings MUST include severity + evidence source + evidence quality | Schema: `medication_warnings` requires these fields |
| SR-007 | Patient PHI MUST NOT appear in notification preview body | Notification service: body = name only, no dose/frequency |
| SR-008 | Patient PHI MUST NOT appear in logs, error messages, or analytics events | Logging middleware: medication IDs only, never names/doses |
| SR-009 | Traditional medicine and supplements MUST be categorized separately | DB: `is_supplement` + `supplement_category` + `supplement_evidence_note` required |
| SR-010 | Supplement interactions MUST be labeled with `evidence_quality = 'limited'` | Warning generation: force limited evidence for supplement pairs |
| SR-011 | No data from other patients MUST appear in any patient view | RBAC + patient_id FK on all medication tables |
| SR-012 | Doctor MUST NOT delete patient medication records | RBAC: DOCTOR role returns 403 on DELETE /medications/{id} |
| SR-013 | `CLINIC_ADMIN` MUST NOT write to patient medications | RBAC: CLINIC_ADMIN → 403 on all medication writes |

---

## 2. AI Behavior Rules

### 2.1 What Meto AI Can Say About Medications

✅ **Allowed:**
- "Metformin thường được dùng để điều trị tiểu đường type 2."
- "Thuốc này nên uống sau bữa ăn để giảm tác dụng phụ trên dạ dày."
- "Theo lịch của bạn, đã đến giờ uống thuốc Rosuvastatin."
- "Tỷ lệ tuân thủ thuốc của bạn tuần này là 80%."
- "Hệ thống phát hiện có thể có tương tác giữa Warfarin và Aspirin. Bạn nên hỏi bác sĩ."
- "Đây là thực phẩm chức năng — bằng chứng khoa học còn hạn chế."

❌ **Forbidden:**
- "Bạn nên ngừng uống [thuốc]."
- "Tăng liều [thuốc] lên [X]mg."
- "Thuốc này không cần thiết cho bạn nữa."
- "Tương tác này không nghiêm trọng, bạn có thể tiếp tục dùng."
- "Tôi chẩn đoán bạn có phản ứng với [thuốc]."
- "Thay [thuốc A] bằng [thuốc B]."
- Any definitive dosing recommendation
- Any override of a CRITICAL or HIGH interaction warning

### 2.2 Forbidden Response Patterns (extend existing list)

Add to `FORBIDDEN_RESPONSE_PATTERNS` in `app/ai/prompt/safety.py`:
```python
r"hãy dừng thuốc",          # already exists
r"ngừng uống thuốc",         # already exists
r"tăng liều",
r"giảm liều",
r"đổi thuốc",
r"thay thuốc",
r"không cần uống",
r"tương tác này không nghiêm trọng",
r"tự điều chỉnh thuốc",
r"không cần kê đơn",
r"tôi kê",
r"meto kê",
```

### 2.3 Interaction Warning Response Policy

When Meto detects or is asked about an interaction:
1. **Acknowledge** the concern without minimizing: "Đây là thông tin đáng chú ý."
2. **State the severity** clearly: "Đây là tương tác MỨC ĐỘ CAO."
3. **Recommend doctor consultation**: "Bạn nên liên hệ bác sĩ trước khi tiếp tục dùng cả hai thuốc."
4. **Do not diagnose**: "Chúng tôi không thể xác nhận tác động cụ thể lên tình trạng sức khỏe của bạn."
5. **If emergency symptoms**: trigger RED_FLAG escalation path (existing).

---

## 3. OCR Safety Rules

### 3.1 OCR Prescription Flow Safety

| Step | Rule | Enforcement |
|------|------|-------------|
| Photo upload | MUST NOT process automatically without patient consent | Upload page: explicit consent required before OCR runs |
| OCR result | MUST be stored as `pending_ocr_review` state | Service: create record with `source_type = 'pending_ocr'` — NOT `ocr_confirmed` |
| OCR review | Patient MUST confirm or reject each extracted medication individually | Frontend: per-medication confirm button required |
| Confidence | Fields with confidence < 60% MUST NOT be pre-filled | OCR review UI: show empty field with warning |
| Confirmation | Minimum required fields for confirmation: name only | Dose and frequency can be empty — but name MUST be confirmed |
| Auto-activation | STRICTLY FORBIDDEN: no medication activated without patient tap on "Xác nhận" | Service layer + frontend: double-guard |

### 3.2 OCR Confidence Display

| Confidence | Display | Background |
|------------|---------|------------|
| ≥ 90% | Pre-filled, green border | Green tint |
| 60–89% | Pre-filled, yellow border, "Vui lòng kiểm tra lại" | Yellow tint |
| < 60% | Empty field, red border, "Không thể đọc — vui lòng nhập thủ công" | Red tint |

### 3.3 OCR PHI Rules

- Raw OCR text (prescription scan) MUST be stored encrypted at rest (`EncryptedString`)
- OCR text MUST NOT be logged
- OCR text MUST NOT be sent to analytics
- If OCR fails, error message MUST NOT include the prescription image or any extracted text

---

## 4. Drug-Drug Interaction Warning Rules

### 4.1 Warning Display Requirements

Every interaction warning MUST display:
- Drug pair names (using patient's stored `name` field — may be brand name)
- Severity badge: LOW (gray) | MEDIUM (yellow) | HIGH (orange) | CRITICAL (red)
- Plain-language clinical effect (Vietnamese)
- Recommended action (e.g., "Hỏi bác sĩ trước khi tiếp tục")
- Evidence source and evidence quality label
- Disclaimer: "Đây là cảnh báo tham khảo, không phải chẩn đoán y khoa."

### 4.2 Warning Severity Definitions

| Severity | Meaning | UI Treatment |
|----------|---------|--------------|
| CRITICAL | Contraindicated: use together is generally considered unsafe | Red banner, cannot dismiss, must consult doctor |
| HIGH | Significant risk: requires medical supervision | Red badge, can dismiss with acknowledgment |
| MEDIUM | Monitor required: may need dose adjustment or monitoring | Orange badge, dismissable |
| LOW | Informational: minor interaction, generally manageable | Gray badge, dismissable |

### 4.3 Warning Dismissal Rules

- **CRITICAL warnings CANNOT be dismissed** by patient. They must be reviewed.
- HIGH warnings: patient can dismiss with a "Tôi đã hỏi bác sĩ" acknowledgment button.
- MEDIUM/LOW warnings: patient can dismiss with a single tap.
- All dismissals are logged in AuditLog with `dismissed_by` and `dismissed_at`.
- Dismissed warnings are re-evaluated when medication changes occur.

### 4.4 Warning Completeness Disclaimer

When interaction check runs but drug is not in catalog (free-text name only):
```
"Không thể kiểm tra tương tác cho thuốc '[name]' vì chưa có trong danh mục thuốc của MetoCare. 
Hãy hỏi bác sĩ hoặc dược sĩ về tương tác thuốc."
```

---

## 5. Allergy Rules

### 5.1 Allergy Check Trigger Points

1. When patient adds a new medication → check against allergy list
2. When patient adds a new allergy → check against current medication list (reverse check)
3. When OCR result is being confirmed → check before patient taps confirm
4. When doctor adds medication from portal → check (doctor sees warning, not blocked)

### 5.2 Allergy Warning Display

- Allergy matches always shown as **CRITICAL** severity
- Message: "Bạn đã ghi nhận dị ứng với [allergen]. Thuốc '[name]' có thể chứa thành phần này."
- Subtext: "Đây là cảnh báo khẩn cấp. Không dùng thuốc này khi chưa hỏi bác sĩ."
- CRITICAL allergy warning CANNOT be dismissed.
- Button: "Gọi cho bác sĩ" + "Huỷ thêm thuốc"

### 5.3 Allergy Data Entry Rules

- Patient can self-report allergies
- Allergy entry requires at minimum: `allergen_name` and `allergen_type`
- `verified_by_doctor` defaults to `False` for patient self-reports
- UI must display "Chưa xác nhận bởi bác sĩ" when `verified_by_doctor = False`
- Matching logic must use BOTH `active_ingredient` AND `drug_class` fields (class-level allergy)

---

## 6. Supplement and Traditional Medicine Rules

### 6.1 Classification Requirements

When `is_supplement = True`:
- `supplement_evidence_note` MUST be set (not null)
- Default note: "Thực phẩm chức năng/thuốc Đông y — Bằng chứng khoa học còn hạn chế. Không thay thế thuốc kê đơn. Tham khảo bác sĩ trước khi dùng cùng với thuốc điều trị."
- `supplement_category` MUST be set: `herbal` | `vitamin` | `functional_food` | `tcm`

### 6.2 UI Display Requirements for Supplements

- Supplement badge (distinct color — e.g., purple) shown on medication card
- Evidence note ALWAYS visible on detail screen
- Interaction warnings for supplement pairs use MEDIUM severity maximum (even if mechanism suggests higher)
- Evidence quality label: "Bằng chứng hạn chế" for all supplement interactions

### 6.3 Traditional Chinese Medicine (TCM)

- `supplement_category = 'tcm'`
- Additional note required: "Thuốc Đông y có thể tương tác với thuốc Tây y. Báo cho bác sĩ biết đầy đủ danh sách thuốc Đông y bạn đang dùng."
- No interaction rules are applied for TCM vs TCM pairs (insufficient evidence)
- TCM vs Western drug pairs: flag for doctor review, not auto-block

---

## 7. PHI Protection Rules

### 7.1 Logging

```python
# FORBIDDEN in any log statement:
logger.info(f"Patient {patient_id} added medication: {medication.name}")  # ❌
logger.info(f"Dose: {medication.dose}")  # ❌

# ALLOWED:
logger.info(f"Medication added: medication_id={medication.id} patient_id={patient_id}")  # ✅
```

### 7.2 Error Messages

```python
# FORBIDDEN:
raise HTTPException(400, detail=f"Medication '{medication.name}' conflicts with allergy.")  # ❌
# Name in error response = PHI leak if error is logged or visible to wrong party

# ALLOWED:
raise HTTPException(400, detail="Cannot add medication: allergy conflict detected. See warnings endpoint.")  # ✅
```

### 7.3 Notification Body

```python
# FORBIDDEN:
body = f"Đến giờ uống {medication.name} {medication.dose} — {medication.frequency}"  # ❌ dose+frequency = PHI

# ALLOWED:
body = f"Đến giờ uống thuốc"  # ✅ generic, no PHI
# OR
body = f"Nhắc nhở: {medication.name}"  # ✅ name only (borderline — acceptable for reminder utility)
```

### 7.4 Analytics Events

```python
# FORBIDDEN:
analytics.track("medication_added", {"name": medication.name, "dose": medication.dose})  # ❌

# ALLOWED:
analytics.track("medication_added", {"drug_class": medication.drug_class, "is_supplement": medication.is_supplement})  # ✅
```

---

## 8. Testing Requirements for Safety Rules

| Safety Rule | Required Test Type | Test Description |
|-------------|-------------------|-----------------|
| SR-001 (AI cannot write) | API test | POST /medications with AI_SERVICE token → 403 |
| SR-002 (AI cannot prescribe) | Guardrail test | LLM output containing dose recommendation → blocked |
| SR-004 (OCR no auto-activate) | Service test | OCR confirm endpoint called without confirmation step → rejected |
| SR-006 (warnings need severity+source) | Schema test | Create warning without evidence_source → validation error |
| SR-007 (no PHI in notification) | Unit test | Notification body for medication_reminder → no dose/frequency |
| SR-008 (no PHI in logs) | Log inspection test | Add medication → verify log contains no medication name |
| CRITICAL warning undismissable | Frontend test | Patient tries to dismiss CRITICAL warning → UI blocks |
| Allergy CRITICAL check | Integration test | Add medication with matching allergy → CRITICAL warning generated |
| Supplement note required | Service test | Add medication with is_supplement=True, no note → validation error |

---

## 9. Stop Gates — When to Escalate to PTH

STOP and get PTH approval before proceeding if:

| Condition | Reason |
|-----------|--------|
| External drug interaction database integration (DrugBank, Lexicomp, MIMS API) | Licensing cost + legal/data residency |
| Sending medication reminders via SMS/push to production users | Infrastructure approval + user consent flow |
| Enabling AI to read interaction rule data and generate recommendations | Clinical AI governance review |
| Integration with hospital e-prescription systems | Legal, HIPAA-equivalent, Vietnamese health data law |
| Using real patient medication data for testing or model training | PHI consent law |
| Any schema change that removes or renames existing medication columns | Destructive migration requires explicit approval |
| Enabling AI to automatically generate allergy warnings in AI responses | Clinical review required |
| Vietnamese doctor validation of interaction rule set | Required before production of P3 |
