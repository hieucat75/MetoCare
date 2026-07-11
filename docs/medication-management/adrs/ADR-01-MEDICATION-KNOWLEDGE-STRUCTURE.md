# ADR-01 — Medication Knowledge Structure

**Status:** PROPOSED — Gate 1 (blocks all implementation)  
**Date:** 2026-07-11  
**Deciders:** PTH (product), Tech Lead, Clinical Advisor

---

## ADR Metadata

| Field | Value |
|-------|-------|
| ADR | ADR-01 |
| Status | Accepted |
| Architecture Version | medication-architecture-v1.0 |
| Implementation Gate | Gate 1 |
| Domain | Knowledge Structure |
| Supersedes | None |
| Superseded By | None |

---


## Context

MetoCare hiện có `drug_catalog` table với 41 entries. Mỗi entry lưu `generic_name`, `active_ingredients` (JSON array), `drug_class` (String), `brand_names` (JSON array). Đây là flat table, không có relational hierarchy.

Để build Medication Intelligence (interaction check, allergy check, AI explanation, lab-drug coupling), hệ thống cần biết chính xác:
- Một drug product có chứa những ingredient nào
- Một ingredient thuộc drug class nào
- Drug class đó có ATC code gì
- Ingredient A và Ingredient B có tương tác không

Với flat table, những query này phải đi qua JSON parsing — không reliable, không indexable, không scalable.

---

## Problem

**Hiện tại:** `active_ingredients` là `["metformin hydrochloride"]` — JSON string array trên một row. Không có entity riêng cho ingredient.

**Hậu quả cụ thể:**
1. Không thể query "tất cả drugs có chứa metformin" bằng SQL join — phải parse JSON mỗi lần
2. Không thể model interaction giữa hai ingredients vì ingredient không có ID
3. Không thể add ATC code vào ingredient vì không có ingredient entity
4. Khi catalog grow lên 400+ drugs, deduplication ingredient names sẽ sai (typo, alias)
5. AI tool `explain_medication()` không có structured data để read — buộc phải hallucinate

---

## Decision Drivers

- MetoCare target: Medication Intelligence Platform, không phải reminder app
- Drug interaction check cần join ingredient A ↔ ingredient B — cần ingredient as entity
- AI Copilot KHÔNG ĐƯỢC hallucinate drug facts — cần grounded knowledge layer
- Must run on existing PostgreSQL/SQLite — không thể mandate new infrastructure
- Catalog sẽ grow từ 41 → 400+ drugs trong 12–18 tháng
- Vietnamese drug names và brand names phải searchable

---

## Options Considered

### Option A — Keep flat table, add more JSON fields
Thêm ATC code, metabolic pathways vào `drug_catalog` dưới dạng JSON.

### Option B — Normalized relational model (PostgreSQL)
Tách thành: `drug_products`, `drug_ingredients`, `drug_classes`, `drug_ingredient_map` (many-to-many).

### Option C — Graph database (Neo4j, Amazon Neptune)
Lưu Drug → Ingredient → DrugClass → Interaction như nodes và edges.

### Option D — Hybrid: relational core + JSON extension fields
Relational cho entities cần join (ingredients, drug classes). JSON cho data ít cần query (caution details, monitoring notes).

---

## Trade-off Table

| Criterion | Option A (flat JSON) | Option B (normalized relational) | Option C (graph DB) | Option D (hybrid) |
|-----------|---------------------|----------------------------------|--------------------|--------------------|
| Query ingredient cross-drug | ❌ JSON parse | ✅ SQL join | ✅ graph traversal | ✅ SQL join |
| Build interaction engine | ❌ Impossible | ✅ Feasible | ✅ Natural | ✅ Feasible |
| Infrastructure change | ✅ None | ✅ None | ❌ New infra | ✅ None |
| Migration from current | ✅ Trivial | ⚠️ Data migration needed | ❌ Full rewrite | ⚠️ Moderate |
| Operational complexity | ✅ Low | ✅ Low | ❌ High (new DB ops) | ✅ Low |
| AI grounding capability | ❌ Poor | ✅ Good | ✅ Excellent | ✅ Good |
| Long-term scalability | ❌ Dead end | ✅ Sufficient for 5 years | ✅ Best but overkill | ✅ Sufficient |
| Team knowledge | ✅ Already know | ✅ Already know | ❌ New skill | ✅ Already know |
| Time to implement | ✅ Days | ⚠️ 2–3 weeks | ❌ Months | ⚠️ 2–3 weeks |

---

## Recommended Decision

**Option D — Hybrid: normalized relational core + JSON extension fields**

**Không dùng graph database ở giai đoạn này.**

---

## Why This Option

Graph database (Neo4j) phù hợp khi: traversal qua nhiều hops là core query pattern, team có operational expertise, volume là millions of nodes. MetoCare không có điều kiện nào trong số này trong 2–3 năm tới.

Option B (pure normalized) là đúng về lý thuyết nhưng khi có 50 loại caution flags khác nhau cho từng drug, relational sẽ tạo ra hàng chục tables nhỏ không cần thiết.

Option D giải quyết core problem (ingredient entity có ID, drug class có ID, join được) trong khi cho phép JSON cho semi-structured data không cần query trực tiếp.

**Điều kiện để chuyển sang graph database trong tương lai:**
- Volume > 50,000 drug entities
- Transitive interaction traversal (A → pathway → B → pathway → C) trở thành core feature
- Team có DBA cho graph DB

---

## Consequences

**Schema target:**
```
drug_products           (id, display_name, prescription_required, country, is_active, source_version)
drug_ingredients        (id, name_inn, name_vietnamese, cas_number, drug_class_id)
drug_classes            (id, name, atc_code, atc_level, parent_class_id)  ← self-referential hierarchy
drug_product_ingredients (drug_product_id, drug_ingredient_id, is_primary, role)  ← many-to-many
drug_product_names      (drug_product_id, name, name_type, language)  ← brand/alias/common names
drug_ingredient_knowledge (drug_ingredient_id, knowledge_type, value_json, source, version, valid_from)
  ← knowledge_type: 'renal_caution' | 'pregnancy_category' | 'monitoring_parameters' | 'max_dose' | 'food_interactions'
```

**JSON fields được phép giữ (không cần query directly):**
- `drug_ingredient_knowledge.value_json` — caution details, monitoring notes, food interaction text
- `drug_product.vietnamese_context_json` — Vietnamese-specific notes không cần query

**JSON fields bị loại bỏ (phải relational):**
- `drug_catalog.active_ingredients` → migrate to `drug_product_ingredients`
- `drug_catalog.brand_names` → migrate to `drug_product_names`
- `drug_catalog.drug_class` String → migrate to `drug_classes.id` FK

---

## Data Model Impact

Migration từ `drug_catalog` sang schema mới:
- `drug_catalog` → `drug_products` (1:1 mapping, rename + split)
- `drug_catalog.active_ingredients` JSON → `drug_ingredients` + `drug_product_ingredients`
- `drug_catalog.brand_names` JSON → `drug_product_names`
- `drug_catalog.drug_class` String → `drug_classes` table + FK

`drug_catalog` table giữ nguyên trong migration transition period (backward compat). Sau khi migration validated, rename/deprecate.

---

## API Impact

- `GET /medications/suggest` hiện trả về `DrugSuggestItem` — không đổi interface, chỉ đổi query bên trong
- Add `GET /drugs/{id}` — full drug knowledge for AI tool use
- Add `GET /drug-ingredients/{id}` — ingredient detail (internal use by CDS engine)

---

## Security and Privacy Impact

Drug knowledge data: không phải PHI. Public reference data. Không cần encrypt.  
Access: read-only cho authenticated users. Write: INTERNAL_ADMIN, SUPER_ADMIN only.

---

## Clinical Safety Impact

Nếu giữ flat table: interaction check phải parse JSON → race conditions, inconsistent matching, typo sensitivity. Không an toàn cho clinical use.

Normalized model: ingredient có canonical ID → matching là exact, not string-based → fewer false negatives.

---

## Migration Impact

Alembic migrations:
1. CREATE `drug_classes`, `drug_ingredients`, `drug_products`, `drug_product_ingredients`, `drug_product_names`
2. Data migration script: parse existing `drug_catalog` JSON → insert into new tables
3. Validate: all 41 drugs correctly migrated, all ingredients normalized
4. `patient_medications.drug_catalog_id` FK → renamed to `drug_product_id`
5. Deprecate `drug_catalog` after 1 sprint validation

**Risk:** LOW — additive tables, backward compatible during transition.

---

## Operational Ownership

- Knowledge team (or designated maintainer) owns drug knowledge data quality
- New drug entries require: drug_product + drug_ingredient + drug_ingredient_map
- Annual review of drug_ingredient_knowledge data against source

---

## Open Questions

1. **ATC code source:** WHO publishes ATC codes annually (free). Need Vietnamese MoH mapping for local brand names. Is there a VN MoH drug registry API accessible? **[Requires PTH to check with clinical advisor]**
2. **Ingredient naming standard:** Use INN (International Nonproprietary Name) as canonical. Confirmed? **[Requires clinical advisor sign-off]**

---

## Approval Required From

- [ ] PTH — product direction (relational vs graph)
- [ ] Clinical Advisor — INN as canonical ingredient name standard
- [ ] Tech Lead — migration timeline and backward compat strategy

## Implementation Gate

**Gate 1 — blocks all implementation.**  
No interaction engine, no allergy engine, no AI drug tools can be built until ingredient entities exist as relational rows with IDs.
