# ADR-06 — Traditional Medicine and Supplements

**Status:** PROPOSED — Gate 3 (expansion — schema decision needed at P0)  
**Date:** 2026-07-11  
**Deciders:** PTH, Clinical Advisor

---

## Context

MetoCare hiện có `is_supplement` Boolean và `supplement_category` String trên `medications` table. Tài liệu P0 đề xuất dùng cách này.

Bệnh nhân Việt Nam, đặc biệt 45–70 tuổi với bệnh nền mãn tính, thường dùng kết hợp: thuốc kê đơn + thuốc OTC + thảo dược + TPBSK + thuốc Đông y. Đây không phải ngoại lệ — đây là pattern chính của target population.

---

## Problem

Boolean `is_supplement` không đủ vì các category khác nhau có **clinical behavior hoàn toàn khác nhau**:

| Category | Regulatory status | Interaction risk | Evidence base | Doctor disclosure required |
|----------|------------------|-----------------|---------------|--------------------------|
| Prescription drug | Full (MoH approved) | Documented | RCT evidence | Yes — by law |
| OTC drug | Partial | Documented | RCT evidence | Recommended |
| Traditional VN medicine (thuốc cổ truyền) | MoH Traditional Medicine list | Some documented | Traditional + observational | Recommended |
| Chinese Traditional Medicine (TCM formula) | Varies | Some documented (via CYP) | Traditional + limited RCT | Recommended |
| Herbal single herb | Varies | Limited, some known CYP | Very limited | Optional but important |
| Supplement (vitamin, mineral) | Not regulated as drug | Limited | Limited | Optional |
| Functional food (TPBSK) | Food regulation, not drug | Very limited | Marketing claims | Optional |
| Medical device | Device regulation | N/A | N/A | N/A |

Nếu cùng model là `is_supplement=True`, hệ thống sẽ treat warfarin + vitamin K (dangerous interaction, well-documented) the same as warfarin + ginkgo biloba (possible interaction, limited evidence) the same as warfarin + collagen powder (no clinical concern). Tất cả đều là "supplement" nhưng clinical response hoàn toàn khác.

---

## Decision Drivers

- Target user takes 2–4 traditional/herbal products concurrently with 4–6 prescription drugs
- Some herbal-drug interactions are clinically significant and well-documented (e.g., St. John's Wort + any drug metabolized by CYP3A4)
- Cannot lump all non-prescription products into one category
- AI must apply different evidence disclaimers per category
- Interaction engine must treat each category differently
- Schema must be decided at P0 even if herbal catalog is built at P3+

---

## Options Considered

### Option A — Boolean `is_supplement` (current proposal)
Simple. Inadequate. Cannot differentiate clinical behavior.

### Option B — Taxonomy enum field on `medications`
`medication_category` enum: `prescription | otc | traditional_vn | tcm | herbal | supplement | functional_food | device`

### Option C — Separate catalog per category
`drug_products` catalog for prescription/OTC.  
`herb_catalog` separate table for herbal/TCM.  
`supplement_catalog` for vitamins/TPBSK.

### Option D — Category field + separate knowledge entry per category
`medication_category` field drives which catalog/knowledge table is queried for safety data.

---

## Trade-off Table

| Criterion | A (boolean) | B (enum) | C (separate catalogs) | D (category + knowledge) |
|-----------|-------------|----------|----------------------|--------------------------|
| Differentiate clinical behavior | ❌ | ✅ | ✅ | ✅ |
| Interaction check by category | ❌ | ⚠️ Logic in code | ✅ Natural | ✅ Natural |
| Implementation complexity | ✅ None | ✅ Low | ⚠️ Medium | ⚠️ Medium |
| AI context clarity | ❌ | ✅ | ✅ | ✅ |
| Evidence disclaimer per category | ❌ | ✅ | ✅ | ✅ |
| Future herb knowledge layer | ❌ | ⚠️ Needs migration | ✅ Ready | ✅ Ready |

---

## Recommended Decision

**Option D — `medication_category` field on `medications` + separate `herb_catalog` table (introduced at P3), with category-specific clinical behavior rules coded in service layer.**

**Phase P0 (now):** Add `medication_category` enum to `medications` table. Remove `is_supplement` boolean (replace entirely).  
**Phase P3:** Build `herb_catalog` table for herbal/TCM entries. Link via `herb_catalog_id` FK nullable on `medications`.

---

## Why This Option

Option B gives the enum differentiation needed without separate catalogs. But without knowledge separation (Option C/D), the interaction engine cannot query category-specific rules separately.

Option D is Option B + preparation for separate knowledge tables. The `herb_catalog` table does not need to exist at P0 — just the category field and the behavioral rules.

---

## Consequences

**`medication_category` enum (replaces `is_supplement` boolean):**
```
prescription         — bác sĩ kê đơn, MoH approved, requires prescription
otc                  — không cần đơn, đã qua MoH clearance
traditional_vn       — thuốc y học cổ truyền Việt Nam (MoH Traditional Medicine list)
tcm                  — thuốc Đông y (formula-based, Chinese traditional medicine)
herbal_single        — thảo dược đơn vị (single herb, not formula)
supplement           — vitamin, mineral, omega-3, etc.
functional_food      — thực phẩm bảo vệ sức khỏe (TPBSK)
otc_analgesic        — paracetamol, aspirin, ibuprofen (separate because interaction risk documented)
device               — đo lường, dụng cụ y tế (tracked but no interaction check)
```

**`supplement_category` field: REMOVED.** Replaced by `medication_category`.

**`is_supplement` field: REMOVED at P0 migration.** Replace with `is_non_prescription` Boolean derived from `medication_category NOT IN ('prescription')`.

**Clinical behavior per category (hard-coded in service layer):**
```
prescription, otc, otc_analgesic:
  → Full interaction check against drug_interactions table
  → Evidence level: catalog_based or higher
  → No evidence disclaimer

traditional_vn, tcm:
  → Interaction check: herbal-drug interactions only (when herb_catalog exists)
  → Evidence disclaimer: "Thuốc y học cổ truyền — tương tác với thuốc Tây y còn ít được nghiên cứu. Báo cho bác sĩ đầy đủ."
  → AI context: include with category label

herbal_single:
  → Interaction check: check known herbal-drug pairs (limited rule set)
  → Evidence disclaimer: "Thảo dược — bằng chứng tương tác còn hạn chế. Hỏi dược sĩ trước khi dùng kết hợp."

supplement, functional_food:
  → Interaction check: only well-documented supplement interactions (e.g., Vitamin K + warfarin, Calcium + levothyroxine)
  → Evidence disclaimer: "Thực phẩm chức năng — không thay thế thuốc điều trị. Bằng chứng lâm sàng hạn chế."

device:
  → No interaction check
  → No evidence disclaimer
```

**`herb_catalog` table (introduced at P3, optional reference):**
```sql
CREATE TABLE herb_catalog (
    id                  UUID PK,
    name_vietnamese     VARCHAR(255) NOT NULL,    -- e.g., "Đinh lăng"
    name_latin          VARCHAR(255) nullable,     -- e.g., "Polyscias fruticosa"
    name_chinese        VARCHAR(255) nullable,     -- for TCM
    common_preparations JSON,                     -- decoction | powder | pill | extract
    known_cyp_effects   JSON nullable,            -- e.g., {"CYP3A4": "inducer", "strength": "moderate"}
    known_drug_interactions JSON nullable,        -- ["warfarin", "metformin"] — simplified until full interaction engine
    evidence_level      VARCHAR(16) NOT NULL,     -- A | B | C | traditional_use | anecdotal
    regulatory_status   VARCHAR(64) nullable,     -- "MoH Traditional Medicine List" | "Unlisted"
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    source              VARCHAR(255) NOT NULL,
    created_at, updated_at
);
```

**UI rules:**
- `medication_category = 'prescription'`: no badge, standard display
- `medication_category IN ('traditional_vn', 'tcm', 'herbal_single')`: "Đông y / Thảo dược" badge (purple)
- `medication_category IN ('supplement', 'functional_food')`: "TPBSK" badge (teal)
- `medication_category = 'device'`: "Thiết bị" badge (gray)
- All non-prescription categories: show evidence disclaimer on detail screen

---

## Data Model Impact

- P0: Remove `is_supplement` boolean, remove `supplement_category` String, ADD `medication_category` enum
- P0: Add `herb_catalog_id` FK nullable on `medications` (null until herb catalog exists)
- P3: CREATE `herb_catalog` table

---

## API Impact

- `MedicationCreate.medication_category` replaces `is_supplement` + `supplement_category`
- `MedicationOut` includes `medication_category` and derived `evidence_disclaimer` string
- `GET /medications/suggest` may filter/boost by category in future

---

## Security and Privacy Impact

No additional PHI considerations. `medication_category` is not sensitive.

---

## Clinical Safety Impact

Correctly categorizing `otc_analgesic` (especially aspirin and NSAIDs) is critical: these have documented interactions with anticoagulants and need full interaction check, not "supplement" treatment.

`device` category: explicitly excluded from interaction check prevents spurious alerts for blood glucose monitors, etc.

---

## Migration Impact

P0 migration:
1. ADD `medication_category` column to `medications` with DEFAULT 'prescription'
2. UPDATE existing rows: set `medication_category` based on `drug_class` from catalog linkage where available
3. DROP `is_supplement` column
4. DROP `supplement_category` column

**Risk:** Medium — existing rows with `is_supplement=True` need to be correctly re-categorized. Recommend: set to 'supplement' as safe default, patient can correct.

---

## Operational Ownership

Clinical Advisor owns the behavioral rules per category. Tech team implements.

---

## Open Questions

1. **OTC analgesics:** Should aspirin and ibuprofen get full prescription-level interaction checking? (Recommended: yes.) **[Clinical advisor confirms]**
2. **Herb catalog scope for P3:** How many herbs to seed? Vietnamese MoH Traditional Medicine list has 1,300+ entries. Suggest: seed top 50 used by metabolic patients. **[Clinical advisor + PTH decide scope]**
3. **TCM formula:** A formula (thang thuốc) has 5–15 herbs. How to model? Single record or multiple herb records grouped? **[Clinical advisor decides — architectural implication]**

---

## Approval Required From

- [ ] PTH — remove `is_supplement`, replace with `medication_category` enum
- [ ] Clinical Advisor — confirm clinical behavior per category
- [ ] Clinical Advisor — OTC analgesic interaction check level
- [ ] PTH — herb catalog scope for P3

## Implementation Gate

**Gate 3 — does not block P0/P1 safety features.**  
BUT: `medication_category` field decision must be made AT P0 schema, because removing `is_supplement` after data is populated is a destructive migration. Cost of deferring: higher migration risk later.
