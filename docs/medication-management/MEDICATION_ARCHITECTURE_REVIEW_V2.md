# MEDICATION_ARCHITECTURE_REVIEW_V2.md
# MetoCare — Medication Platform Architecture Review

**Version:** 2.0  
**Date:** 2026-07-11  
**Reviewer Role:** Principal Software Architect · Clinical Informatics Architect · Healthcare SaaS Architect · AI Platform Architect  
**Review Scope:** All 10 documents in `/docs/medication-management/`  
**Directive:** Phản biện không nể. Đánh giá khả năng đi xa 5–10 năm.

---

## 1. Executive Summary

Tập tài liệu hiện tại mô tả một **CRUD application với safety wrapper**, không phải một **Medication Intelligence Platform**.

Nếu MetoCare muốn trở thành Digital Health Platform trong 5–10 năm — với AI Clinical Copilot, Medication Reconciliation, Lab Intelligence, Doctor Portal, Telemedicine — thì **kiến trúc thuốc hiện tại không đủ nền**. Không phải vì thiếu tính năng. Mà vì thiếu đúng **domain model, bounded context, và knowledge layer**.

Điểm mạnh: safety guardrails tốt, RBAC nghiêm, adherence tracking đúng hướng.

Điểm yếu cốt lõi: toàn bộ thiết kế hiện tại xử lý thuốc như một danh sách text. Drug Catalog chưa phải Knowledge Graph. Interaction Engine chưa tồn tại. Prescription chưa là domain. Medication Reconciliation hoàn toàn vắng mặt.

**Kết luận:** Cần thiết kế lại domain model và knowledge layer trước khi viết bất kỳ dòng code production nào. Schema hiện tại có thể migrate được — nhưng bounded context thì không.

---

## 2. Điểm Mạnh — Ghi Nhận Trước Khi Phản Biện

| Điểm mạnh | Đánh giá |
|-----------|----------|
| RBAC nghiêm — AI_SERVICE bị block khỏi medication writes | ✅ Thiết kế đúng về clinical safety |
| Soft delete thay vì hard delete | ✅ Cần thiết cho audit trail |
| `source_type` field được đưa vào từ đầu | ✅ Đây là quyết định đúng — biết dữ liệu từ đâu là nền tảng của reconciliation |
| Allergy check trước OCR confirm | ✅ Safety-first thinking |
| Guardrail regex cho AI output | ✅ Một trong những phần được thiết kế tốt nhất |
| Adherence tracking có streak calculation | ✅ Working, tested |
| Drug catalog với caution_flags, renal/hepatic/pregnancy_caution | ✅ Hướng đúng — nhưng chưa đủ depth |
| Evidence quality labeling cho warnings | ✅ Đúng về clinical epistemology |
| Stop Gate pattern | ✅ Đúng — nhưng chưa đủ |

---

## 3. Điểm Yếu — Phân Tích Không Nể

### 3.1 Thiết Kế Thiên Về CRUD, Không Phải Intelligence

**Câu hỏi 1: Kiến trúc có đang thiên về CRUD thay vì Medication Intelligence Platform không?**

**Trả lời: Có. Hoàn toàn.**

Bằng chứng:
- `medications` table lưu `name` là String — đây là lưu trữ mức grocery list, không phải clinical record
- Drug catalog 41 drugs được lưu như một reference table, không phải một Knowledge Graph
- Intelligence layer (Layer 2) được thiết kế như "add a table of warnings" — không có engine, không có reasoning
- Interaction rules được đề xuất là "static rule table, 50 pairs" — đây là hardcode disguised as architecture

Một Medication Intelligence Platform cần:
- Drug entity model với hierarchy (Brand → Generic → Ingredient → Drug Class → ATC → Pharmacodynamic Group)
- Knowledge Graph thay vì rule table
- Reasoning engine, không phải regex match trên ingredient pairs

### 3.2 Drug Catalog Không Đủ Để Mở Rộng

**Câu hỏi 4: Drug Catalog có đủ để mở rộng không?**

**Trả lời: Không.**

Current `drug_catalog` table là **flat lookup table**. Nó lưu:
```
generic_name: "Metformin"
active_ingredients: ["metformin hydrochloride"]
drug_class: "biguanide"
```

Nhưng một drug catalog đúng nghĩa cần:

```
Drug (product entity)
  └── has active ingredient(s): DrugIngredient
        └── belongs to drug class: DrugClass
              └── belongs to pharmacodynamic group: TherapeuticGroup
                    └── ATC code: ATC (Anatomical Therapeutic Chemical)
                          └── linked to clinical knowledge: DrugKnowledge
                                ├── contraindications
                                ├── interactions (with mechanism)
                                ├── monitoring parameters
                                ├── dose adjustments (renal/hepatic/age)
                                ├── food/alcohol interactions
                                └── pregnancy categories
```

Vấn đề cụ thể:
- `active_ingredients` là JSON array trên một row — không thể join, không thể query theo ingredient, không thể build interaction graph
- `drug_class` là String — không có hierarchy, không có code system (ATC)
- `caution_flags` là JSON array of strings — không structured, không queryable, không versioned
- Không có `contraindications` as structured entity — chỉ có `contraindication_keywords` là JSON string array
- Không có `drug-drug interaction` data trong catalog — nó được đặt vào một bảng riêng `drug_interaction_rules` chưa có gì
- Không có monitoring parameters (e.g., metformin cần theo dõi eGFR — đây là clinical knowledge, không phải caution_flag)
- Không có max dose, pediatric dose, elderly dose adjustment
- Không có food interaction (e.g., warfarin + rau xanh; grapefruit + statin)
- Không có alcohol interaction

Kết quả: sau 1–2 năm, khi cần build AI drug explanation hoặc drug-lab interaction, team sẽ phải refactor toàn bộ catalog schema.

### 3.3 Interaction Engine Thiết Kế Sai

**Câu hỏi 5: Interaction Engine nên thiết kế như thế nào?**

Tài liệu đề xuất: `drug_interaction_rules` table với 50 hardcoded pairs (ingredient_a, ingredient_b).

Đây là **worst-case design** cho một platform muốn đi 5–10 năm.

Lý do:
1. **50 pairs không đủ.** Một bệnh nhân THA + ĐTĐ + mỡ máu + gút trung bình dùng 6–8 thuốc. Số cặp tương tác tiềm năng là n*(n-1)/2. FDA Adverse Event database có hàng trăm nghìn pair.
2. **Hardcoded pairs không scale.** Khi catalog grow từ 41 lên 400 drugs, phải manually add pairs. Không sustainable.
3. **Pairs không capture transitive interaction.** Nếu drug A inhibits CYP3A4 và drug B is CYP3A4 substrate, thì A+B tương tác — nhưng không thể detect nếu chỉ lưu pairs.
4. **Không có mechanism reasoning.** Khi AI cần giải thích interaction, nó cần mechanism (pharmacokinetic vs pharmacodynamic), không chỉ "severity=HIGH".
5. **Thiếu temporal context.** Interaction severity có thể thay đổi theo dose, theo renal function, theo thời gian dùng. Static pairs không capture điều này.

Interaction Engine đúng cho platform scale:

**Option A — Knowledge Graph (recommended cho 5-year horizon):**
- Drug → Ingredient → Metabolic Pathway (CYP enzymes, transporters)
- Ingredient A inhibits Pathway X, Ingredient B is substrate of X → interaction detected by reasoning
- Leverage open data: DrugBank Open, RxNorm, OpenFDA (free tier)

**Option B — Rule Engine (pragmatic for 2-year horizon):**
- Separate `interaction_rules` từ `drug_catalog`
- Rules có type: `ingredient_pair | class_pair | pathway | transitive`
- Rules có mechanism field dùng structured enum, không free text
- Versioned rule sets — có thể import từ DrugBank/MIMS với version control

**Option C — External API (stop gate, cost):**
- DrugBank, Lexicomp, MIMS Vietnam API
- Accurate nhất nhưng costly và dependency risk

**Đề xuất:** Option B now → migrate toward Option A at scale. Không nên start với Option A vì quá expensive upfront. Không nên stay với hardcoded 50 pairs vì dead end.

### 3.4 Allergy Model Thiếu Clinical Depth

**Câu hỏi 6: Allergy model hiện tại đã đủ chưa?**

**Trả lời: Chưa đủ cho clinical use.**

Schema đề xuất trong `MEDICATION_DATA_MODEL.md`:
```
patient_allergies:
  allergen_name, drug_catalog_id, active_ingredient, drug_class,
  reaction_type, severity, notes, verified_by_doctor
```

Thiếu:
- `onset` — khi nào phản ứng xảy ra (lần đầu dùng? lần thứ N?)
- `last_occurrence` — lần cuối xảy ra reaction
- `reaction_onset_time` — phản ứng sau bao lâu (phút, giờ, ngày — phân biệt IgE vs non-IgE)
- `certainty` — confirmed | probable | suspected | unlikely (quan trọng cho clinical decision)
- `cross_reactivity` — penicillin allergy → likely cephalosporin cross-reactivity — này là clinical knowledge, không phải just data
- `source` — patient_reported | clinician_confirmed | hospital_record | OCR
- `evidence` — có hồ sơ y tế không? có xét nghiệm không?
- `status` — active | resolved | unknown (dị ứng thời thơ ấu có thể không còn relevant)
- `drug_allergy_type` — IgE-mediated (anaphylaxis risk) vs non-IgE (rash, GI) — khác nhau hoàn toàn về management

Cross-reactivity là blind spot lớn nhất: nếu patient dị ứng sulfonamide antibiotic và được kê sulfonamide diuretic (furosemide không phải sulfonamide nhưng có sulfur moiety), hệ thống cần biết rule này. Không thể detect nếu chỉ match ingredient string.

### 3.5 Medication Status Lifecycle Chưa Đủ

**Câu hỏi 7: Status lifecycle có đủ không?**

Tài liệu đề xuất: `active | paused | completed | discontinued`

**Thiếu:**

| Status | Ý nghĩa lâm sàng | Tại sao quan trọng |
|--------|-----------------|-------------------|
| `planned` | Bác sĩ đã kê nhưng bệnh nhân chưa lấy thuốc | Reconciliation — patient chưa start không có nghĩa là không được kê |
| `starting` | Đang titration/uptitration (e.g., insulin dose adjustment giai đoạn đầu) | Dose adjustment tracking |
| `on_hold` | Tạm dừng theo y lệnh cụ thể (e.g., ngừng metformin trước phẫu thuật) | Khác `paused` theo ý bệnh nhân |
| `expired` | End date đã qua nhưng patient chưa review | Giúp identify thuốc cũ chưa được review |
| `unknown` | OCR extracted nhưng status chưa xác nhận | Quan trọng cho reconciliation |
| `transferred` | Thuốc được chuyển sang bác sĩ khác quản lý | Provider transitions |

Thứ quan trọng hơn: **lifecycle transitions cần event log**, không chỉ current status. Biết rằng một thuốc hiện tại là `discontinued` không đủ — cần biết nó được discontinued khi nào, bởi ai, lý do gì, và medication trước đó là gì. Đây là nền tảng của Medication Timeline.

### 3.6 Thiếu Medication Timeline và Event Sourcing

**Câu hỏi 8: Có cần Medication Timeline? Versioning? Event Sourcing?**

**Trả lời: Cần. Và đây là một trong những lỗ hổng nghiêm trọng nhất.**

Tài liệu hiện tại: `updated_at` timestamp trên medications table. Soft delete.

Vấn đề: khi patient edit `name` từ "Metformin 500mg" thành "Metformin 1000mg" — lịch sử cũ biến mất. Không có gì lưu lại rằng dose đã được tăng gấp đôi.

**Tại sao Medication Timeline quan trọng với MetoCare:**

1. **Doctor Portal:** Bác sĩ cần biết lịch sử đầy đủ — thuốc nào đã dùng, từ khi nào đến khi nào, tại sao ngừng
2. **AI Clinical Copilot:** Để reason về "tại sao HbA1c không cải thiện", AI cần biết metformin được tăng liều cách đây 3 tháng
3. **Drug Adverse Event Detection:** Nếu bệnh nhân report triệu chứng mới, AI cần biết thuốc nào được add gần đây
4. **Longitudinal Health Record:** 10 năm sau, patient cần full medication history

**Giải pháp:** Không nhất thiết phải full Event Sourcing ngay. Minimum viable:
- `medication_history` table: lưu snapshot mỗi khi medication được modified
- Fields: `medication_id`, `changed_by`, `changed_at`, `change_reason`, `previous_values` (JSON), `new_values` (JSON)
- Đây khác với AuditLog (which is security-focused) — đây là clinical history

### 3.7 Medication Reconciliation Hoàn Toàn Vắng Mặt

**Câu hỏi 9: Medication Reconciliation có cần thành bounded context riêng?**

**Trả lời: Có. Và đây là bounded context quan trọng nhất bị bỏ sót.**

Medication Reconciliation là quá trình **hợp nhất danh sách thuốc từ nhiều nguồn** thành một "Current Medication List" chính xác.

Trong context MetoCare, nguồn dữ liệu thuốc có thể đến từ:
- Patient self-report (manual)
- OCR prescription từ bệnh viện A
- OCR prescription từ bệnh viện B (có thể trùng tên khác)
- Doctor added từ portal
- AI extracted từ lab notes
- Future: pharmacy integration
- Future: HL7 FHIR import từ bệnh viện

**Vấn đề:** Không có gì trong tài liệu hiện tại giải quyết câu hỏi: nếu patient có hai records cho "Metformin" — một từ OCR của bệnh viện A và một từ manual entry — đây là hai thuốc khác nhau hay một thuốc trùng lặp?

**Current design assumption:** Mỗi record trong `medications` table là một entry độc lập. Không có deduplication, không có merge, không có confidence score cho từng record.

**Hậu quả:** Khi MetoCare có Doctor Portal + OCR + pharmacy integration, `medications` table sẽ có duplicates. AI context sẽ bị nhiễu. Drug interaction check sẽ cho false positives (same drug detected twice as "interaction").

**Reconciliation Bounded Context cần:**
- `medication_statements` — raw records từ mỗi source (chưa reconciled)
- `medication_reconciliation_sessions` — mỗi lần reconcile (trigger: hospital discharge, doctor visit, new OCR)
- `reconciled_medications` — verified current medication list
- Reconciliation engine: detect duplicates, merge with human confirmation, track provenance

### 3.8 Lab Intelligence ↔ Medication Coupling Quá Yếu

**Câu hỏi 10: Lab Intelligence nên kết nối Medication như thế nào?**

Tài liệu hiện tại mô tả drug-lab interaction như một "warning type" trong `medication_warnings` table. Đây là **biểu hiện** đúng nhưng **kiến trúc** sai.

Drug-lab relationship cần được model ở knowledge layer, không phải warning layer:

```
LabTest (eGFR)
  └── has clinical significance for: DrugKnowledge
        ├── threshold_rule: eGFR < 30 → Metformin: CONTRAINDICATED
        ├── threshold_rule: eGFR 30-45 → Metformin: dose_reduction_required
        ├── threshold_rule: eGFR 45-60 → Metformin: CAUTION + monitor
        └── monitoring_rule: patient on Metformin → check eGFR every 6 months

LabTest (Potassium)
  └── has clinical significance for:
        ├── K+ > 5.0 → ACEi/ARB: CAUTION (risk of hyperkalemia)
        ├── K+ > 5.5 → ACEi/ARB + K-sparing diuretic: HOLD
        └── K+ < 3.5 → Loop diuretic: dose review
```

Nếu MetoCare muốn build AI Copilot có thể nói "HbA1c của anh tháng này là 9.2%, xem xét với danh sách thuốc hiện tại..." thì AI cần **structured knowledge** về mối liên hệ lab → medication, không chỉ một warning table.

### 3.9 Đông Y và Thực Phẩm Bảo Vệ Sức Khỏe — Model Không Đủ

**Câu hỏi 12: Đông y và TPBSK nên model như thế nào?**

Tài liệu hiện tại: thêm `is_supplement` Boolean và `supplement_category` String vào medications table.

**Vấn đề:** Đây là categorization, không phải modeling.

Đông y (TCM) và TPBSK cần clinical behavior riêng vì:

1. **Evidence model khác:** Western drugs có RCT evidence. TCM có observational evidence, traditional use evidence, expert opinion. Hệ thống cần lưu evidence type, không chỉ "limited".
2. **Interaction mechanism khác:** TCM-drug interactions thường qua CYP enzyme induction/inhibition (e.g., St. John's Wort induces CYP3A4 → giảm hiệu quả của rất nhiều thuốc) — đây là pharmacokinetic fact, không phải opinion.
3. **Ingredient complexity:** Một thang thuốc Đông y có 5–15 thảo dược. Mỗi thảo dược có multiple active compounds. Không thể model như một drug với một active_ingredient.
4. **Dose flexibility:** Liều Đông y thường flexible, theo thang/ngày, không phải mg.
5. **Safety oversight khác:** Thảo dược không qua FDA/Ministry of Health approval — cần label rõ regulatory status.

**Đề xuất structural approach:**
- `traditional_medicine_entries` — separate catalog từ `drug_catalog`
- Each entry: `herb_name` (Vietnamese + Latin), `preparation_type` (decoction, powder, pill), `known_interactions` (JSON với CYP pathway if known), `evidence_level`, `regulatory_status`
- Patient record: `is_traditional_medicine` flag + FK to `traditional_medicine_entries` (if matched) hoặc free text
- Warning system: separate pass cho TCM-drug interactions, clearly labeled "Tương tác thảo dược — độ tin cậy: Quan sát lâm sàng"

### 3.10 AI Copilot Thiếu Knowledge Layer

**Câu hỏi 11 & 13: AI Copilot cần Knowledge Layer gì?**

Tài liệu `MEDICATION_AI_BEHAVIOR.md` mô tả đúng WHAT AI can/cannot say. Nhưng không mô tả HOW AI reasons.

Hiện tại Meto AI nhận context:
```json
{"name": "Metformin", "dose": "500mg", "frequency": "2 lần/ngày"}
```

Để AI có thể reasoning:
- "Tại sao bệnh nhân dùng Metformin?" — cần `indication`
- "Liều này có phù hợp với chức năng thận không?" — cần `eGFR + renal_dose_adjustment_rules`
- "Có thuốc nào tương tác không?" — cần `interaction_rules` với mechanism
- "Có cần monitor gì không?" — cần `monitoring_parameters`

Không có cái nào trong số này tồn tại trong knowledge layer.

**AI drug explanation hiện tại là hallucination risk.** Nếu AI được hỏi về một drug không có trong 41-drug catalog, nó sẽ dùng training data — không kiểm soát được, không factual-grounded.

---

## 4. Các Giả Định Sai

| # | Giả định trong tài liệu | Tại sao sai |
|---|--------------------------|-------------|
| A1 | "Drug catalog link is a bonus, not a requirement" | Sai về long-term. Không có catalog FK = không thể build intelligence. Nên là: required for structured drugs, free-text for unknowns |
| A2 | "50 interaction pairs là MVP" | Sai về sustainability. 50 pairs hardcode sẽ không maintain được. Cần rule engine, không phải pair list |
| A3 | "OCR reuse existing lab OCR pipeline" | Sai về domain. Lab OCR đọc table structure. Prescription OCR đọc freeform text với drug names, không cùng pipeline |
| A4 | "AI context 300 tokens là đủ" | Sai về scale. 10 active medications với generic_name, drug_class, warnings = dễ vượt 300 tokens. Cần smart context compression |
| A5 | "is_supplement Boolean là đủ để classify" | Sai về clinical completeness. TCM, TPBSK, vitamin, herbal cần separate clinical behavior |
| A6 | "Medication warnings table là đủ cho interaction results" | Sai về architecture. Warning storage ≠ interaction engine. Cần decouple |
| A7 | "Allergy verified_by_doctor Boolean là đủ" | Sai về clinical nuance. Cần certainty score, reaction type, evidence, source, cross-reactivity |
| A8 | "status = active|paused|completed|discontinued là đủ" | Sai về clinical lifecycle. Thiếu planned, on_hold, expired, unknown |
| A9 | "Không cần Medication Reconciliation" | Sai. Khi có OCR + doctor portal + multiple sources, duplicates sẽ xảy ra |
| A10 | "Denormalize generic_name at creation time là immutable" | Sai về knowledge management. Nếu catalog cập nhật ingredient information, old records không benefit |

---

## 5. Bounded Context Còn Thiếu

**Câu hỏi 3: Thiếu những bounded context nào?**

Dưới đây là domain map đầy đủ cho một Medication Platform. Tài liệu hiện tại chỉ cover 2 trong 12 bounded contexts:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MEDICATION PLATFORM — DOMAIN MAP                   │
├──────────────────────┬──────────────────────────────────────────────┤
│ BOUNDED CONTEXT      │ STATUS IN CURRENT DOCS                       │
├──────────────────────┼──────────────────────────────────────────────┤
│ 1. Medication Record │ ✅ Partially covered (P0 schema)             │
│    (Patient's list)  │   Missing: lifecycle, history, versioning    │
├──────────────────────┼──────────────────────────────────────────────┤
│ 2. Medication        │ ⚠️ Flat table only. Not a Knowledge Graph.   │
│    Knowledge         │   Missing: ATC, ingredient hierarchy,        │
│                      │   monitoring, food interaction, max dose,    │
│                      │   pregnancy categories (FDA A/B/C/D/X)      │
├──────────────────────┼──────────────────────────────────────────────┤
│ 3. Prescription      │ ❌ Not a domain. Treated as metadata field.  │
│                      │   Missing: prescription lifecycle,           │
│                      │   prescriber, validity, partial fill,        │
│                      │   dispensing record                          │
├──────────────────────┼──────────────────────────────────────────────┤
│ 4. Medication        │ ❌ Completely absent.                        │
│    Reconciliation    │   No deduplication, no provenance merging,  │
│                      │   no source conflict resolution              │
├──────────────────────┼──────────────────────────────────────────────┤
│ 5. Drug Safety /     │ ⚠️ Warning table designed but engine absent. │
│    Allergy Engine    │   Missing: cross-reactivity, certainty,     │
│                      │   reaction onset, IgE vs non-IgE            │
├──────────────────────┼──────────────────────────────────────────────┤
│ 6. Interaction       │ ⚠️ 50-pair static table proposed.           │
│    Engine            │   Missing: mechanism reasoning, pathway,    │
│                      │   transitive interactions, dose-dependent   │
├──────────────────────┼──────────────────────────────────────────────┤
│ 7. Clinical Decision │ ❌ Not mentioned as a domain.               │
│    Support (CDS)     │   "Warnings" are not CDS.                   │
│                      │   CDS = rule + patient data + context →     │
│                      │   recommendation with explanation           │
├──────────────────────┼──────────────────────────────────────────────┤
│ 8. Adherence &       │ ✅ Best-covered domain. Working.             │
│    Medication Loop   │   Missing: schedule engine, smart reminders, │
│                      │   behavioral insights                        │
├──────────────────────┼──────────────────────────────────────────────┤
│ 9. Medication        │ ❌ Not modeled. "Refill" is a lightweight   │
│    Supply / Pharmacy │   field, not a domain.                      │
│                      │   Missing: pharmacy integration,            │
│                      │   dispensing record, out-of-stock alert     │
├──────────────────────┼──────────────────────────────────────────────┤
│ 10. Medication       │ ❌ Not a domain. Mentions OCR in passing.   │
│     Capture          │   Missing: capture → staging → review →     │
│                      │   reconciliation pipeline                   │
├──────────────────────┼──────────────────────────────────────────────┤
│ 11. Traditional      │ ⚠️ Boolean flag only. Not a domain.         │
│     Medicine / TPBSK │   Missing: herb catalog, preparation,       │
│                      │   evidence level, CYP interaction rules     │
├──────────────────────┼──────────────────────────────────────────────┤
│ 12. Medication       │ ❌ Not mentioned at all.                    │
│     Timeline /       │   Missing: full longitudinal view,          │
│     History          │   change event log, clinical narrative      │
└──────────────────────┴──────────────────────────────────────────────┘
```

**10 trong 12 bounded contexts hoặc không tồn tại hoặc chỉ được cover một phần.**

---

## 6. Đề Xuất Domain Model Mới

### 6.1 Core Domain Objects

```
PatientMedication (Aggregate Root)
├── identity: MedicationId (UUID)
├── patient: PatientId
├── drugReference: DrugReference  ← either CatalogLink OR FreeTextDrug
│     ├── CatalogLink
│     │     ├── drug_catalog_id: DrugCatalogId
│     │     ├── ingredient_snapshot: [IngredientRef]  ← denormalized at creation
│     │     └── catalog_version: String
│     └── FreeTextDrug
│           ├── name: String
│           └── user_supplied: true
├── dosing: DosingSpec
│     ├── amount: Quantity (value + unit)
│     ├── route: RouteOfAdministration (enum)
│     ├── form: DosageForm (enum: tablet | capsule | liquid | injection | patch | inhaler)
│     ├── frequency: FrequencySpec
│     │     ├── code: FrequencyCode (QD | BID | TID | PRN | CUSTOM)
│     │     ├── display: String
│     │     └── structured_schedule: [ScheduledTime] nullable
│     └── instructions: String nullable
├── lifecycle: MedicationLifecycle
│     ├── status: MedicationStatus (planned|starting|active|on_hold|paused|completed|discontinued|expired|unknown)
│     ├── start_date: Date nullable
│     ├── end_date: Date nullable
│     ├── is_prn: Boolean
│     └── events: [MedicationEvent]  ← status changes with reason and actor
├── clinical: ClinicalContext
│     ├── indication: String nullable
│     ├── prescribed_by: ProviderReference nullable
│     ├── prescription_id: PrescriptionId nullable
│     └── care_plan_ref: CarePlanId nullable
├── source: MedicationSource
│     ├── type: SourceType (manual | ocr_confirmed | doctor_added | pharmacy_import | ai_extracted)
│     ├── confidence: Float nullable
│     └── raw_input_ref: String nullable
└── supplement: SupplementInfo nullable  ← only if is_supplement
      ├── category: SupplementCategory
      ├── herb_catalog_id: HerbCatalogId nullable
      └── evidence_note: String

MedicationEvent (Value Object)
├── event_type: (status_changed | dose_changed | schedule_changed | note_added | reviewed_by_doctor)
├── occurred_at: DateTime
├── actor: ActorRef (patient | doctor | system | ai)
├── previous_value: JSON nullable
├── new_value: JSON nullable
└── reason: String nullable
```

### 6.2 Drug Knowledge Domain (Separate Bounded Context)

```
DrugKnowledge (Aggregate Root — separate bounded context)
├── DrugProduct
│     ├── brand_name: [String]
│     ├── generic_name: String
│     └── ingredients: [DrugIngredient]  ← One-to-many, not JSON

DrugIngredient
├── name: String (INN — International Nonproprietary Name)
├── cas_number: String nullable
├── drug_class: DrugClass
├── atc_code: ATCCode  ← WHO Anatomical Therapeutic Chemical
├── metabolic_pathways: [MetabolicPathway]
│     ├── pathway_name: (CYP3A4 | CYP2D6 | P-gp | UGT | ...)
│     ├── role: (substrate | inhibitor | inducer)
│     └── potency: (strong | moderate | weak)
└── knowledge: DrugIngredientKnowledge
      ├── contraindications: [Contraindication]
      │     ├── condition_code: String (ICD-10 or local)
      │     ├── severity: (absolute | relative)
      │     └── evidence_level: (A | B | C)
      ├── monitoring_parameters: [MonitoringParameter]
      │     ├── lab_code: String
      │     ├── frequency: String
      │     └── threshold_rules: [ThresholdRule]
      ├── dose_adjustments: [DoseAdjustment]
      │     ├── adjustment_type: (renal | hepatic | age | weight)
      │     └── rules: [DoseAdjustmentRule]
      ├── food_interactions: [FoodInteraction]
      ├── pregnancy_category: (A | B | C | D | X | N)
      └── max_dose: Quantity nullable

DrugInteraction (between two DrugIngredient entities)
├── ingredient_a_id, ingredient_b_id
├── mechanism_type: (pharmacokinetic | pharmacodynamic | unknown)
├── mechanism_detail: String nullable
├── severity: (contraindicated | major | moderate | minor)
├── clinical_effect: String
├── management: String
├── evidence_level: (A | B | C | expert_opinion)
├── source: String
└── version: String
```

### 6.3 Medication Reconciliation Domain

```
ReconciliationSession
├── patient_id
├── trigger: (hospital_discharge | doctor_visit | ocr_import | patient_request)
├── triggered_at: DateTime
├── status: (pending | in_progress | completed | cancelled)
├── medication_statements: [MedicationStatement]  ← raw inputs
│     ├── source_type: (patient | doctor | ocr | pharmacy | fhir_import)
│     ├── source_ref: String
│     ├── confidence: Float
│     └── raw_data: JSON
├── reconciliation_decisions: [ReconciliationDecision]
│     ├── statement_ids: [String]
│     ├── decision: (keep | merge | discard | defer)
│     ├── merged_to: MedicationId nullable
│     └── decided_by: ActorRef
└── resulting_medication_ids: [MedicationId]
```

---

## 7. Đề Xuất Data Model Mới — Migration Path

Không đề xuất rewrite toàn bộ. Đề xuất **layered migration** từ current schema:

### Layer 0 — Preserve (giữ nguyên)
- `medications` table core fields (id, patient_id, name, dose, note, created_at, deleted_at)
- `medication_adherence` table
- `drug_catalog` table (rename to `drug_products` in v2)

### Layer 1 — Enhance (P0–P1, safe)
- ADD nullable columns to `medications` (đã đề xuất đúng)
- ADD `medication_events` table thay vì chỉ `updated_at` — đây là critical change
- ADD `medication_statements` table (raw inputs before reconciliation)

### Layer 2 — Restructure Knowledge (P2–P3)
- CREATE `drug_ingredients` table — extract from `drug_catalog.active_ingredients` JSON
- CREATE `drug_classes` table — extract from `drug_catalog.drug_class` String
- CREATE `drug_ingredient_map` (many-to-many: drug_products ↔ drug_ingredients)
- CREATE `drug_interactions` table — properly structured (replace planned `drug_interaction_rules`)
- CREATE `metabolic_pathways` table
- CREATE `drug_ingredient_pathways` (many-to-many)

### Layer 3 — Reconciliation (P3–P4)
- CREATE `reconciliation_sessions`
- CREATE `medication_statements`
- ADD `source_reconciliation_id` FK to `medications`

### Migration Notes
- Layer 1 migrations: backward compatible (all nullable columns)
- Layer 2: requires data migration from JSON arrays to relational tables — plan carefully
- Layer 3: new tables, no modification to existing

---

## 8. Đề Xuất Medication Knowledge Layer

```
Knowledge Layer Architecture
────────────────────────────

TIER 1 — FOUNDATION (build first)
  drug_products          → reference catalog (current drug_catalog, enhanced)
  drug_ingredients       → normalized ingredient entities
  drug_classes           → class hierarchy with ATC codes
  drug_ingredient_map    → product ↔ ingredient many-to-many

TIER 2 — SAFETY (build after foundation)
  drug_interactions      → ingredient-pair interactions with mechanism
  allergy_rules          → ingredient → cross-reactive ingredients
  contraindications      → ingredient → condition contraindications
  organ_adjustments      → dose adjustment rules by eGFR/LFT/age

TIER 3 — INTELLIGENCE (build after safety)
  metabolic_pathways     → CYP/P-gp pathway data
  monitoring_parameters  → which labs to check for which drugs
  food_interactions      → drug-food pairs
  lab_drug_thresholds    → specific lab value + drug = action

TIER 4 — TRADITIONAL MEDICINE (parallel track)
  herb_catalog           → TCM and functional food catalog
  herb_ingredients       → active compounds
  herb_drug_interactions → known interactions with evidence level

KNOWLEDGE UPDATE STRATEGY:
  - All knowledge tables have: source, source_version, valid_from, valid_until
  - Rule sets are versioned — patient warnings can be recalculated on rule update
  - Open data sources: RxNorm (free), DrugBank Open (free tier), OpenFDA (free)
  - MIMS Vietnam: evaluate for P3+ (cost vs completeness tradeoff)
```

---

## 9. Đề Xuất Clinical Decision Support Architecture

CDS không phải chỉ là "bảng warnings". CDS là một subsystem có input, processing, output, explainability.

```
CDS Engine (Clinical Decision Support)
═══════════════════════════════════════

INPUT:
  PatientContext
  ├── medications: [PatientMedication] (active, with catalog links)
  ├── allergies: [PatientAllergy]
  ├── lab_results: [LabResult] (recent, relevant)
  ├── conditions: [Condition] (if structured — currently not in MetoCare)
  └── demographics: {age, sex, pregnancy_status}

PROCESSING PIPELINE:
  1. Allergy Check
     ├── Match active_ingredient vs allergy.active_ingredient
     ├── Match drug_class vs allergy.drug_class (class-level allergy)
     └── Check cross_reactivity_rules (e.g., penicillin → cephalosporin)

  2. Duplicate Detection
     ├── Same active_ingredient in ≥ 2 active medications
     └── Same drug_class in ≥ 2 active medications (therapeutic duplication)

  3. Interaction Check
     ├── For each medication pair: check drug_interactions table
     ├── If ingredient has metabolic pathway: check transitive interactions
     └── Apply dose + timing context to severity

  4. Lab-Drug Check
     ├── For each active medication with monitoring_parameters
     ├── Fetch most recent relevant lab value
     └── Apply threshold_rules → generate actionable alert

  5. Organ Function Check
     ├── eGFR-based renal dose adjustment rules
     └── LFT-based hepatic caution rules

OUTPUT:
  ClinicalAlert
  ├── alert_id
  ├── alert_type: (allergy | interaction | duplication | lab_drug | organ_caution)
  ├── severity: (critical | high | medium | low | informational)
  ├── medications_involved: [MedicationId]
  ├── title: String (Vietnamese)
  ├── body: String (Vietnamese — plain language)
  ├── mechanism: String nullable (for AI explanation)
  ├── recommended_action: String
  ├── evidence_level: (A | B | C | limited)
  ├── source: String
  ├── can_be_dismissed: Boolean
  └── requires_doctor_review: Boolean

PERSISTENCE:
  ClinicalAlert → stored in medication_alerts table
  AlertDismissal → stored with actor, timestamp, acknowledgment_text

EXPLAINABILITY:
  Each alert has machine-readable + human-readable explanation
  AI Copilot can USE this explanation in context, not generate its own
```

---

## 10. Đề Xuất AI-Ready Architecture

**Câu hỏi 14: Kiến trúc hiện tại có đủ để AI kê đơn hỗ trợ, AI review, AI reconciliation, AI adverse event detection không?**

**Trả lời: Không. Cần thay đổi cơ bản về context design.**

### 10.1 Context Strategy

Hiện tại: dump medication list vào prompt (300 tokens).

AI-ready approach: **structured context với multi-tier retrieval**

```
Tier 1 — Always-present (compact)
  current_medications_summary:
    count: 5
    critical_alerts: 1
    drug_classes: ["biguanide", "statin", "ARB", "antiplatelet"]
    has_supplements: false
    last_adherence_rate: 0.86

Tier 2 — Screen-specific (medium)
  medications_detail:  (on /medications screen only)
    - full list with generic_name, drug_class, dose, schedule, status
    - active_alerts summary (title only)

Tier 3 — On-demand (for AI tools)
  medication_knowledge_for_drug(id):
    - full drug knowledge: interactions, monitoring, contraindications
    - retrieved dynamically when AI needs to reason about a specific drug
```

### 10.2 AI Tool Layer (Missing Entirely)

Tài liệu `09_TOOLS_AND_ACTIONS.md` đề cập `explain_medication`, `create_reminder` nhưng không implement. Cần:

```
MEDICATION AI TOOLS:
  explain_medication(drug_catalog_id) → DrugExplanation (from knowledge layer)
  check_interactions(medication_ids: []) → [ClinicalAlert] (from CDS engine)
  get_adherence_summary(patient_id, days=30) → AdherenceSummary
  get_medication_timeline(patient_id, from_date, to_date) → [MedicationEvent]
  explain_interaction(interaction_id) → InteractionExplanation (from knowledge layer)
```

Key principle: **AI tools read from knowledge layer and CDS results. AI does NOT generate clinical facts from training data.** Nếu AI nói về tương tác thuốc, nó phải cite từ `drug_interactions` table — không phải từ hallucination.

### 10.3 AI Use Cases — Readiness Assessment

| AI Capability | Current Readiness | What's Missing |
|---------------|------------------|----------------|
| Drug explanation (general) | 30% | Knowledge layer, AI tool implementation |
| Adherence coaching | 60% | Schedule engine, behavior insights |
| Interaction warning explanation | 10% | Interaction engine, AI tool, mechanism data |
| Lab-drug alert | 5% | Lab-drug knowledge, CDS trigger |
| Medication reconciliation | 0% | Entire bounded context missing |
| Adverse event detection | 0% | Event log, timeline, ML pipeline |
| AI medication review | 5% | Knowledge layer, timeline, CDS results |
| AI-assisted prescription | 0% | Not in scope — correctly excluded |

---

## 11. Roadmap Triển Khai Theo Kiến Trúc Đúng

Đây KHÔNG phải Schema → UI → API. Đây là **Foundation → Knowledge → Intelligence → Platform**.

### Epoch 0 — Domain Foundation (2–3 weeks, không ship feature)

**Quyết định kiến trúc trước khi code:**
- Xác nhận bounded context map
- Xác nhận domain model (PatientMedication aggregate)
- Xác nhận knowledge tier strategy (open data vs licensed)
- Xác nhận reconciliation approach
- Design ADRs (Architecture Decision Records) cho mỗi major decision

### Epoch 1 — Medication Record (4–5 weeks)

Mục tiêu: Patient có thể quản lý medication list với đầy đủ clinical fields + lifecycle + history.

```
E1-A: Schema foundation
  - migrations: enhance medications table (P0 columns — đã đúng)
  - ADD medication_events table (critical — đây là history layer)
  - ADD medication_statements table (prepare for reconciliation)

E1-B: Medication Record domain
  - PatientMedication aggregate với lifecycle
  - MedicationEvent logging on every state change
  - MedicationLifecycle: planned → starting → active → paused → on_hold → completed → discontinued

E1-C: Frontend
  - Medication detail screen
  - Lifecycle UI (status change with reason)
  - History view (medication timeline)
```

### Epoch 2 — Drug Knowledge (4–6 weeks)

Mục tiêu: Drug catalog trở thành Knowledge Graph.

```
E2-A: Knowledge schema
  - drug_ingredients table (from drug_catalog.active_ingredients JSON)
  - drug_classes table (hierarchy with ATC)
  - drug_ingredient_map (many-to-many)
  - metabolic_pathways table

E2-B: Knowledge seed
  - Extract + normalize 41 existing drugs into new schema
  - Import from RxNorm (open, free) for ATC codes and ingredient IDs
  - Identify and flag gaps for manual review

E2-C: Herb/TCM catalog
  - herb_catalog table (separate from drug_products)
  - Initial seed: top 20 herbs used by VN metabolic patients
```

### Epoch 3 — Safety Engine (6–8 weeks)

Mục tiêu: Real-time allergy, duplicate, interaction detection.

```
E3-A: Allergy domain
  - patient_allergies table with full clinical fields
  - Cross-reactivity rules (curated, ~50 pairs)
  - Allergy check service

E3-B: Interaction Engine
  - drug_interactions table (structured, not pair strings)
  - Initial seed: ~100 priority interactions from open sources
  - Interaction Engine service: pair check + class check + pathway check

E3-C: CDS Pipeline
  - ClinicalAlert generation on: add medication, new lab result, allergy add
  - Alert persistence: medication_alerts table
  - Alert UI: list, detail, dismiss with acknowledgment

E3-D: Vietnamese Doctor Clinical Review
  - Required STOP GATE before production
  - Doctor review of all generated alerts on test cases
```

### Epoch 4 — Care Loop (4–5 weeks)

```
E4-A: Reminder system
  - medication_schedules + notification engine
  - PHI protection in notification body

E4-B: OCR Capture
  - Prescription OCR pipeline (separate from lab OCR)
  - Review + confirm flow

E4-C: Refill + Supply
  - medication_refills table
  - Refill alert logic

E4-D: Caregiver
  - caregiver_assignments + RBAC
```

### Epoch 5 — AI Integration (4–6 weeks)

```
E5-A: AI Tool implementation
  - explain_medication tool (reads from knowledge layer)
  - check_interactions tool (calls CDS engine)
  - get_medication_timeline tool

E5-B: Enhanced AI context
  - Multi-tier context: summary + detail + on-demand
  - Medication alerts included in context

E5-C: Medication Reconciliation
  - reconciliation_sessions + statements
  - Manual reconciliation UI
  - AI-assisted reconciliation (AI suggests duplicates, human confirms)
```

**Total: ~6–8 months for full foundation. P0 feature delivery starts at week 3–4.**

---

## 12. Risk Nếu Giữ Nguyên Thiết Kế Hiện Tại

| Risk | Probability | Impact | Mô tả |
|------|------------|--------|-------|
| **Technical Debt Cliff** | HIGH | CRITICAL | Sau 12–18 months với 3,000+ patients, refactor drug catalog schema thành knowledge graph sẽ require migration của tất cả denormalized data |
| **False Safety Confidence** | HIGH | CRITICAL | 50 hardcoded interaction pairs cho team cảm giác "interaction check done" — nhưng 80% clinically relevant interactions không được phát hiện |
| **Reconciliation Debt** | HIGH | HIGH | Mỗi OCR prescription, mỗi doctor portal entry sẽ tạo duplicate records — không có cơ chế dedup |
| **AI Hallucination Risk** | MEDIUM | HIGH | Không có knowledge layer = AI dùng training data để explain drugs = factual errors không được detect |
| **Interaction Engine Dead End** | HIGH | HIGH | Pair table không scale. Sau 200 drugs, sẽ cần rewrite engine từ đầu |
| **Timeline Loss** | HIGH | MEDIUM | `updated_at` không capture history. Sau 1 năm không biết lịch sử medication của patient |
| **Supplement/TCM Misclassification** | MEDIUM | MEDIUM | Boolean flag không đủ — không detect CYP interactions của thảo dược |
| **Platform Lock-in** | MEDIUM | HIGH | Nếu MetoCare muốn integrate FHIR, SMART on FHIR, hospital APIs — flat table không import được |

---

## 13. Kiến Trúc Bắt Buộc Thay Đổi Trước Khi Code

Đây là danh sách các **Architecture Decision Records (ADRs)** phải được ký duyệt trước khi team bắt đầu implementation:

| ADR# | Quyết định | Options | Recommended |
|------|-----------|---------|-------------|
| ADR-01 | Drug knowledge structure | Flat table vs Relational hierarchy vs Graph | **Relational hierarchy** (drug_ingredients table, drug_classes, drug_ingredient_map) |
| ADR-02 | Interaction engine strategy | Hardcoded 50 pairs vs Rule engine vs External API | **Rule engine** với structured rules và versioning — import từ open sources |
| ADR-03 | Medication history strategy | updated_at only vs Snapshot table vs Event sourcing | **Event table** (medication_events) — minimum viable history |
| ADR-04 | Reconciliation approach | Ignore now vs Reconciliation bounded context | **Stage statements separately** from day 1 (medication_statements table) |
| ADR-05 | OCR pipeline | Reuse lab OCR vs New prescription OCR | **Separate pipeline** — different domain, different confidence model |
| ADR-06 | Traditional medicine | Boolean flag vs Separate catalog | **Separate catalog** (herb_catalog) with own clinical behavior |
| ADR-07 | AI knowledge source | Training data vs Knowledge layer | **Knowledge layer only** — AI never cites drug facts from training data |
| ADR-08 | Allergy cross-reactivity | Not handled vs Curated rules | **Curated cross-reactivity rules** (at minimum, top 20 clinical pairs) |
| ADR-09 | CDS placement | Frontend validation vs API middleware vs Domain service | **Domain service** — CDS runs at service layer, not frontend, not DB |
| ADR-10 | Open data vs Licensed | Build manual vs OpenFDA/RxNorm vs MIMS | **OpenFDA + RxNorm now, MIMS evaluate at P3** |
| ADR-11 | Medication status lifecycle | 4 states vs 8 states | **8 states** (planned, starting, active, on_hold, paused, completed, discontinued, expired) |
| ADR-12 | PHI encryption | At rest plaintext vs Column encryption vs DB encryption | **Column-level encryption** for name, dose, indication before scale |

---

## 14. Kết Luận

Kiến trúc hiện tại đủ để ship một **medication reminder app** cho vài trăm bệnh nhân trong 6 tháng tới.

Kiến trúc hiện tại **không đủ** để làm nền tảng cho:
- AI Clinical Copilot cần drug knowledge
- Doctor Portal cần medication history và reconciliation
- Lab Intelligence cần drug-lab coupling
- Telemedicine cần structured prescription domain
- Hospital integration cần FHIR-compatible medication records

**Khuyến nghị:**

1. Dành 2–3 tuần để thiết kế lại domain model và ra ADRs (12 quyết định nêu trên)
2. Không cần rewrite schema hiện tại — nhưng cần bổ sung `medication_events`, `medication_statements`, và refactor `drug_catalog` thành `drug_products + drug_ingredients`
3. Interaction engine: không hardcode pairs — build rule engine với versioned rule sets
4. OCR prescription: separate pipeline từ lab OCR
5. Traditional medicine: herb_catalog separate, không phải Boolean flag
6. Allergy: extend schema với certainty, cross-reactivity, reaction_onset_type
7. Tất cả drug facts mà AI nói phải trace về knowledge layer — không từ training data

**Thời gian đầu tư thêm trước khi code: 2–3 tuần thiết kế.**  
**Rủi ro nếu bỏ qua: 12–18 tháng technical debt + refactor lớn khi platform cần scale.**
