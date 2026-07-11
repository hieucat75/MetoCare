# ADR-10 — Drug Knowledge Data Sources

**Status:** PROPOSED — Gate 2 (blocks production safety features)  
**Date:** 2026-07-11  
**Deciders:** PTH (budget and licensing decisions)

---

## Context

MetoCare cần drug knowledge data cho: drug catalog, interaction rules, allergy cross-reactivity, drug class hierarchy, monitoring parameters, dose adjustment rules. Nguồn dữ liệu nào là authoritative, có thể dùng hợp pháp, đủ cho VN market?

---

## Problem

**Không có free, complete, production-ready drug database cho Vietnamese market.**

Các nguồn available có trade-offs khác nhau về: coverage, quality, licensing, update frequency, Vietnamese localization, operational cost.

Quyết định sai ở đây = either clinical gaps (incomplete data) hoặc legal risk (unlicensed data) hoặc operational cost overrun.

---

## Decision Drivers

- Production clinical safety use requires verified, citable sources
- Vietnamese brand names and Vietnamese-specific drug approvals are needed
- Update frequency: drug knowledge is not static — new interactions discovered, guidelines change
- Cost: startup budget constraint
- Operational: who is responsible for maintaining data quality?
- Licensing: cannot use data without proper license for commercial product
- Vietnamese MoH is the regulatory authority — their approval database should be source of truth for VN market

---

## Data Source Evaluation

### Source A — Internal manual curation (current approach)
41 drugs manually curated by team. No external dependency.

**Assessment:**
- Coverage: ❌ 41 drugs is insufficient for clinical safety
- Quality: ⚠️ Depends on curators' clinical knowledge
- Licensing: ✅ Own data
- Update frequency: ❌ Manual, ad-hoc
- Vietnamese localization: ✅ Can be VN-specific
- Cost: ✅ Zero (except staff time)
- Suitable for: drug catalog display, autocomplete, basic safety only

### Source B — RxNorm (US NLM, free, open)
US National Library of Medicine's drug normalization vocabulary. Provides: drug names, ingredient normalization, drug class hierarchy, NDC codes.

**Assessment:**
- Coverage: ✅ Comprehensive for US market drugs (many VN drugs are same molecules)
- Quality: ✅ Government-maintained, updated monthly
- Licensing: ✅ Free, open, no attribution required for commercial use
- Update frequency: ✅ Monthly
- Vietnamese localization: ❌ US-centric. Brand names different. Some drugs approved in VN not in RxNorm.
- Cost: ✅ Free
- Suitable for: ingredient normalization, drug class hierarchy, INN mapping

### Source C — OpenFDA (US FDA, free, open)
Drug adverse event data, label data, drug recalls. 

**Assessment:**
- Coverage: ✅ US market
- Quality: ✅ FDA-sourced
- Licensing: ✅ Public domain
- Vietnamese localization: ❌ US-centric
- Suitable for: adverse event signals, drug label information (mechanism, contraindications)

### Source D — WHO ATC classification (free)
WHO Anatomical Therapeutic Chemical classification system. Provides drug class hierarchy with codes.

**Assessment:**
- Coverage: ✅ International standard
- Quality: ✅ WHO-maintained
- Licensing: ✅ Free for non-commercial; commercial use requires contacting WHO — **[Legal review needed]**
- Vietnamese localization: ✅ ATC is international
- Suitable for: drug class hierarchy, therapeutic grouping

### Source E — DrugBank Open (free tier)
Community version. Provides: drug-drug interactions (basic), drug classes, targets, mechanisms.

**Assessment:**
- Coverage: ✅ ~14,000 drugs
- Quality: ✅ Research-grade, widely used
- Licensing: ⚠️ **CC BY 4.0 for non-commercial. Commercial use requires DrugBank license (~$5,000–$50,000/year).** This is a STOP GATE — must confirm licensing before importing.
- Update frequency: ✅ Regular
- Vietnamese localization: ❌ US/international
- Suitable for: interaction data (if licensed), drug class, ingredient data

### Source F — MIMS Vietnam
Localized VN drug database. Includes VN-approved drugs, VN brand names, VN-specific warnings.

**Assessment:**
- Coverage: ✅ VN market specific
- Quality: ✅ Clinical editorial standards
- Licensing: ❌ Paid — typically $15,000–$50,000+/year for API access
- Update frequency: ✅ Quarterly
- Vietnamese localization: ✅ Best-in-class for VN
- Suitable for: EVERYTHING — but requires budget decision

### Source G — Vietnamese Ministry of Health drug registry
MoH publishes approved drugs list at https://www.drugbank.vn (and dav.gov.vn). Primarily for checking approval status.

**Assessment:**
- Coverage: ⚠️ Lists approved drugs but minimal clinical data
- Quality: ✅ Regulatory source
- Licensing: ✅ Public government data
- Update frequency: ⚠️ Irregular
- Vietnamese localization: ✅
- Suitable for: checking if drug is MoH-approved, VN registration number

### Source H — World Health Organization Model Formulary
Free clinical information for essential medicines. Limited to WHO essential medicine list (~500 drugs).

**Assessment:**
- Coverage: ⚠️ Essential medicines only
- Quality: ✅ WHO clinical standards
- Licensing: ✅ Free
- Suitable for: limited use for essential drugs only

---

## Recommended Decision

**Tiered approach: free open sources now, MIMS Vietnam as stop gate for PTH decision at P3.**

**Tier 1 — Immediate (P0–P2), no licensing risk:**
| Use | Source | Action |
|-----|--------|--------|
| INN canonical ingredient names | RxNorm | Import ingredient normalization |
| ATC drug class codes | WHO ATC | Import — confirm commercial license |
| Drug-drug interaction mechanisms (basic) | Manual curation | Team curates ~100 critical pairs from clinical literature |
| VN brand names + common names | Internal curation | Continue manually, supplement from MoH registry |
| VN MoH approval status | VN MoH drug registry | Script to cross-reference |

**Tier 2 — P3, requires PTH licensing decision (STOP GATE):**
| Option | Cost | What it buys |
|--------|------|-------------|
| DrugBank Open (CC BY license) | Confirm commercial license requirement | ~14,000 drugs, interaction database, targets |
| MIMS Vietnam | ~$15,000–50,000/year | Full VN-localized clinical database, interaction, allergy, dose adjustment |
| Both | Highest coverage | International data + VN localization |

**Tier 3 — P4+:**
| Use | Approach |
|-----|---------|
| AI-assisted knowledge expansion | AI extracts from clinical literature → clinical advisor verifies → import |
| Hospital formulary integration | Partner with specific hospital chains |

---

## Why This Tiered Approach

Waiting for MIMS before starting = months of delay. Starting with internal curation + RxNorm provides:
- Ingredient normalization (critical for ADR-01, ADR-02)
- ATC codes for drug class hierarchy
- ~100 manual interaction rules covering MetoCare patient population
- Covers P0 through P2 without licensing risk

MIMS Vietnam at P3 is justified because P3 is when interaction/allergy features go to production — this is when clinical accuracy must be highest. Budget decision should be made when MetoCare has users to justify the cost.

**Explicit disclaimer in production (required regardless of source):**
"Thông tin tương tác thuốc trong MetoCare chỉ mang tính tham khảo và được cung cấp bởi [Source]. Không phải tất cả tương tác đều được liệt kê. Hỏi dược sĩ hoặc bác sĩ để có thông tin đầy đủ."

---

## Consequences

**Knowledge update process:**
```
1. Clinical Advisor identifies updates needed (new interaction discovered, guideline change)
2. Update submitted as PR to knowledge seed files
3. Code review + Clinical Advisor second sign-off
4. Version bump on affected rules
5. Deployment: re-seed affected tables
6. Background job: re-evaluate all active patient alerts affected by version change
7. New alerts generated if rule change affects existing patient medication combinations
```

**Vietnamese localization gap handling:**
- If drug is in VN MoH registry but not in RxNorm: add manually with `source='manual_vn'`
- If drug name in VN differs from INN: add to `drug_product_names` with `language='vi'`
- Annual review: compare VN MoH new approvals vs catalog

---

## Data Model Impact

All knowledge tables (from ADR-01) must have:
- `source` field: which database the data came from
- `source_version` or `effective_date`: when this data was imported
- `evidence_level`: A | B | C | expert_opinion | traditional_use
- `valid_until`: null = still valid; non-null = this data should be reviewed

---

## API Impact

No direct API impact. Internal data quality.

---

## Security and Privacy Impact

Drug knowledge is reference data (not PHI). However:
- Licensing compliance: using DrugBank without commercial license = legal risk
- Data provenance: audit trail of what source each rule came from (for regulatory inquiry)

---

## Clinical Safety Impact

**If data source is insufficient:** False negatives in interaction/allergy checks. Patient not warned.  
**Mitigation:** Always display coverage disclaimer. Explicitly tell patients: "Kiểm tra này chỉ cover danh mục thuốc MetoCare. Hỏi dược sĩ cho danh sách đầy đủ hơn."

**If data source has errors:** False positive alerts (over-warning). Less dangerous than false negative but erodes trust.

---

## Operational Ownership

- Tier 1 (internal + RxNorm): Tech Lead + Clinical Advisor co-own
- Tier 2 (MIMS/DrugBank): Clinical Advisor is primary owner, with vendor management support
- Annual audit: Clinical Advisor reviews data accuracy against current clinical guidelines

---

## Open Questions

1. **WHO ATC commercial license:** WHO states ATC codes are free for non-commercial. MetoCare is commercial. Does WHO grant commercial license? **[Legal advisor must clarify before ATC data import]**
2. **DrugBank Open CC BY 4.0:** Commercial use requires separate agreement with DrugBank. Cost unknown. **[PTH decides if worth pursuing vs MIMS]**
3. **MIMS Vietnam budget approval:** Budget for $15K–50K/year drug database? This is a PTH product budget decision that must be made before P3 starts. **[STOP GATE — PTH must decide]**
4. **VN MoH data quality:** Is the dav.gov.vn drug registry accessible via API or only manual download? **[Tech Lead to assess]**

---

## Approval Required From

- [ ] PTH — MIMS Vietnam licensing budget decision (stop gate for P3)
- [ ] PTH — DrugBank Open commercial license evaluation
- [ ] Legal Advisor — WHO ATC commercial use confirmation
- [ ] Clinical Advisor — Tier 1 manual curation scope and quality sign-off

## Implementation Gate

**Gate 2 — blocks production safety features.**  
Tier 1 (RxNorm + internal curation) can start immediately with no approvals beyond team agreement.  
MIMS decision must be made before P3 interaction/allergy features go to production users.  
WHO ATC legal review must complete before ATC codes are imported into production schema.
