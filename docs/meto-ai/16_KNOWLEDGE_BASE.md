# Meto AI — Knowledge Base

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved
> **Phase:** 3 — Clinical Intelligence

---

## Tổng quan

Knowledge Base (KB) là nền tảng tri thức y khoa của Meto — tập hợp có cấu trúc các sự kiện, quy tắc, hướng dẫn, và bằng chứng y khoa mà Meto dùng để suy luận và giải thích. KB được thiết kế để:
- **Versioned:** Có thể update mà không cần deploy lại code
- **Traceable:** Mọi knowledge item đều có nguồn gốc rõ ràng
- **RAG-ready:** Sẵn sàng cho Retrieval-Augmented Generation trong tương lai
- **Safe:** Không chứa thông tin dẫn đến chẩn đoán hoặc kê đơn

**File backend:**
- `app/ai/knowledge_base/` — KB core modules
- `app/ai/knowledge_base/loader.py` — Load and version KB
- `app/ai/knowledge_base/resolver.py` — Lookup, normalize, resolve
- `app/ai/knowledge_base/cache.py` — In-memory cache
- `data/knowledge/` — Knowledge source files (YAML/JSON)

---

## 1. Knowledge Hierarchy

### 1.1 4-Tier Knowledge Architecture

```
TIER 4: EVIDENCE (Bằng chứng)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Trust level: HIGHEST
Source: Peer-reviewed studies, meta-analyses, RCTs
Use: Explain mechanisms, support guideline recommendations
Example: "Metformin reduces HbA1c by 1-1.5% on average (meta-analysis, n=15000)"
When Meto uses this: To explain why a lifestyle change helps
Caveat: Applied to population, not to individual patient

TIER 3: GUIDELINE (Hướng dẫn)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Trust level: HIGH
Source: WHO, ADA, ESC, JNC, Bộ Y tế VN, VNHA
Use: Reference ranges, screening intervals, escalation thresholds
Example: "ADA 2025: HbA1c target < 7% for most non-pregnant adults with T2DM"
When Meto uses this: To contextualize lab results
Caveat: Guidelines are population-level — individual patient may have different target

TIER 2: RULE (Quy tắc)
━━━━━━━━━━━━━━━━━━━━━━━
Trust level: MEDIUM-HIGH
Source: Derived from guidelines, expert consensus, clinical practice
Use: Decision rules (drug-lab interactions, escalation triggers)
Example: "Glucose > 400 mg/dL → Emergency escalation"
When Meto uses this: Automated decision logic in CRL
Caveat: Rules are conservative by design (err on side of safety)

TIER 1: FACT (Sự kiện)
━━━━━━━━━━━━━━━━━━━━━━
Trust level: MEDIUM
Source: Curated medical reference, textbooks, database
Use: Basic biological/pharmacological facts
Example: "Metformin mechanism: reduces hepatic glucose production"
When Meto uses this: Explain to patient what something means
Caveat: Simplified for patient understanding, not clinical detail
```

### 1.2 Trust Score per Tier

```python
class KnowledgeTier(str, Enum):
    EVIDENCE = "evidence"          # trust_score: 0.95
    GUIDELINE = "guideline"        # trust_score: 0.90
    RULE = "rule"                  # trust_score: 0.85
    FACT = "fact"                  # trust_score: 0.75

TIER_TRUST_SCORES = {
    KnowledgeTier.EVIDENCE: 0.95,
    KnowledgeTier.GUIDELINE: 0.90,
    KnowledgeTier.RULE: 0.85,
    KnowledgeTier.FACT: 0.75,
}

@dataclass
class KnowledgeItem:
    id: str                            # UUID
    tier: KnowledgeTier
    domain: str                        # "laboratory", "medication", "nutrition", etc.
    key: str                           # Lookup key (snake_case)
    content: str                       # The knowledge content
    content_vi: str                    # Vietnamese version
    trust_score: float                 # From tier + source adjustment
    source: KnowledgeSource
    version: str                       # Semantic version of this item
    effective_date: date               # When this became active
    expires_date: date | None          # None = no expiry
    icd10_codes: list[str]             # Associated ICD-10 codes
    snomed_codes: list[str]            # SNOMED-CT codes (for future ontology compat)
    created_at: datetime
    updated_at: datetime
    deprecated_at: datetime | None
    replacement_id: str | None         # If deprecated, what replaces it?
    ttl_days: int                      # Cache TTL in days
    tags: list[str]                    # For search/retrieval
```

---

## 2. Knowledge Versioning

### 2.1 Semantic Versioning Scheme

```
Format: MAJOR.MINOR.PATCH-YYYYMMDD

MAJOR: Breaking change — reference range shift, major guideline revision
MINOR: Non-breaking addition — new analyte, new drug
PATCH: Correction — typo, source correction

Examples:
  HbA1c_reference_adult:  2.1.0-20251015  (ADA 2025 update to targets)
  metformin_facts:         1.3.2-20240601
  nutrition_diabetes:      1.0.0-20240101

Deprecation Policy:
  - Old version kept for 90 days after new version active
  - deprecated_at set on old version
  - replacement_id points to new version
  - Audit log records which version was used for each Meto response
```

### 2.2 Version Management

```python
class KnowledgeVersionManager:

    async def publish_new_version(
        self,
        key: str,
        new_content: str,
        new_content_vi: str,
        new_source: KnowledgeSource,
        change_type: str,            # "MAJOR" | "MINOR" | "PATCH"
        effective_date: date,
        published_by: str            # Who published (admin user)
    ) -> KnowledgeItem:

        # Get current version
        current = await self.get_current(key)

        # Compute new version number
        new_version = self._bump_version(current.version, change_type)

        # Create new item
        new_item = KnowledgeItem(
            key=key,
            version=new_version,
            content=new_content,
            content_vi=new_content_vi,
            effective_date=effective_date,
            ...
        )

        # Mark current as deprecated if effective_date <= today
        if effective_date <= date.today():
            await self.deprecate(current.id, replacement_id=new_item.id)

        await db.insert("knowledge_items", new_item)

        # Invalidate cache
        await cache.invalidate(f"kb:{key}")

        # Audit log
        await audit_log.record({
            "action": "knowledge_published",
            "key": key,
            "old_version": current.version,
            "new_version": new_version,
            "published_by": published_by,
        })

        return new_item

    async def rollback(self, key: str, to_version: str, reason: str):
        """Emergency rollback if new version found to be incorrect"""
        target = await db.fetch_one(
            "SELECT * FROM knowledge_items WHERE key = :k AND version = :v",
            {"k": key, "v": to_version}
        )
        if not target:
            raise KnowledgeRollbackError(f"Version {to_version} not found for {key}")

        # Restore target version as current
        await db.execute(
            "UPDATE knowledge_items SET deprecated_at = NULL, replacement_id = NULL "
            "WHERE id = :id", {"id": target.id}
        )
        # Deprecate the erroneous current version
        current = await self.get_current(key)
        await self.deprecate(current.id, replacement_id=target.id)

        await cache.invalidate(f"kb:{key}")
        await audit_log.record({
            "action": "knowledge_rollback",
            "key": key,
            "rolled_back_to": to_version,
            "reason": reason,
        })
```

---

## 3. Knowledge Provenance

### 3.1 Source Registry

```python
@dataclass
class KnowledgeSource:
    source_id: str                     # "ADA_2025", "WHO_2024", etc.
    organization: str                  # Full name
    document_title: str
    document_version: str
    published_date: date
    url: str | None
    trust_level: SourceTrustLevel
    region: str                        # "global", "VN", "US", "EU"
    domain: str                        # "diabetes", "cardiology", "general"

class SourceTrustLevel(int, Enum):
    TIER_1_WHO_INTERNATIONAL = 5       # WHO, major international guidelines
    TIER_2_SPECIALTY_SOCIETY = 4       # ADA, ESC, AHA, VNHA
    TIER_3_LOCAL_MOH = 3               # Bộ Y tế VN, VINACENT
    TIER_4_EXPERT_CONSENSUS = 2        # Expert panel, consensus statements
    TIER_5_REVIEW_ARTICLE = 1          # Systematic reviews (when no guideline)

SOURCE_REGISTRY = {
    "WHO_2024": KnowledgeSource(
        source_id="WHO_2024",
        organization="World Health Organization",
        document_title="WHO Guidelines on Diabetes Mellitus",
        published_date=date(2024, 1, 1),
        trust_level=SourceTrustLevel.TIER_1_WHO_INTERNATIONAL,
        region="global",
        domain="diabetes"
    ),
    "ADA_2025": KnowledgeSource(
        source_id="ADA_2025",
        organization="American Diabetes Association",
        document_title="Standards of Care in Diabetes — 2025",
        published_date=date(2025, 1, 1),
        url="https://diabetesjournals.org/care/issue/48/Supplement_1",
        trust_level=SourceTrustLevel.TIER_2_SPECIALTY_SOCIETY,
        region="US",
        domain="diabetes"
    ),
    "ESC_2021_CVD": KnowledgeSource(
        source_id="ESC_2021_CVD",
        organization="European Society of Cardiology",
        document_title="ESC Guidelines on Cardiovascular Disease Prevention",
        published_date=date(2021, 9, 1),
        trust_level=SourceTrustLevel.TIER_2_SPECIALTY_SOCIETY,
        region="EU",
        domain="cardiology"
    ),
    "VN_MOH_2023_DIABETES": KnowledgeSource(
        source_id="VN_MOH_2023",
        organization="Bộ Y tế Việt Nam",
        document_title="Hướng dẫn chẩn đoán và điều trị đái tháo đường type 2 — 2023",
        published_date=date(2023, 3, 15),
        trust_level=SourceTrustLevel.TIER_3_LOCAL_MOH,
        region="VN",
        domain="diabetes"
    ),
    "VNHA_2022_HTN": KnowledgeSource(
        source_id="VNHA_2022_HTN",
        organization="Hội Tim mạch học Việt Nam",
        document_title="Khuyến cáo về chẩn đoán và điều trị tăng huyết áp — 2022",
        published_date=date(2022, 6, 1),
        trust_level=SourceTrustLevel.TIER_2_SPECIALTY_SOCIETY,
        region="VN",
        domain="cardiology"
    ),
    "AHA_ACC_2019": KnowledgeSource(
        source_id="AHA_ACC_2019",
        organization="American Heart Association / American College of Cardiology",
        document_title="ACC/AHA Guideline on the Primary Prevention of CVD",
        published_date=date(2019, 3, 17),
        trust_level=SourceTrustLevel.TIER_2_SPECIALTY_SOCIETY,
        region="US",
        domain="cardiology"
    ),
}

# Source trust ranking (for conflict resolution)
SOURCE_TRUST_RANKING = {
    "global_who": 100,
    "international_specialty": 90,
    "local_vn_moh": 80,
    "local_vn_specialty": 75,
    "expert_consensus": 60,
    "review_article": 40,
}
```

---

## 4. Medical Terminology Normalization

### 4.1 ICD-10 Mapping

```python
ICD10_MAPPING = {
    # Vietnamese common names → ICD-10 → Canonical English
    "đái tháo đường type 2": ("E11", "Type 2 diabetes mellitus"),
    "tiểu đường type 2": ("E11", "Type 2 diabetes mellitus"),
    "đái tháo đường type 1": ("E10", "Type 1 diabetes mellitus"),
    "tăng huyết áp": ("I10", "Essential hypertension"),
    "huyết áp cao": ("I10", "Essential hypertension"),
    "rối loạn mỡ máu": ("E78.5", "Hyperlipidemia, unspecified"),
    "mỡ máu cao": ("E78.0", "Pure hypercholesterolemia"),
    "suy tim": ("I50.9", "Heart failure, unspecified"),
    "suy thận mãn": ("N18.9", "Chronic kidney disease, unspecified"),
    "bệnh thận mãn tính": ("N18", "Chronic kidney disease"),
    "suy giáp": ("E03.9", "Hypothyroidism, unspecified"),
    "cường giáp": ("E05.9", "Hyperthyroidism, unspecified"),
    "thiếu máu": ("D64.9", "Anaemia, unspecified"),
    "loãng xương": ("M81.0", "Age-related osteoporosis"),
    "béo phì": ("E66.9", "Obesity, unspecified"),
    "bệnh phổi tắc nghẽn mãn tính": ("J44.1", "COPD with acute exacerbation"),
    "hen phế quản": ("J45.9", "Asthma, unspecified"),
    "viêm gan B": ("B18.1", "Chronic viral hepatitis B"),
    "viêm gan C": ("B18.2", "Chronic viral hepatitis C"),
    "xơ gan": ("K74.6", "Other and unspecified cirrhosis of liver"),
    "gout": ("M10.9", "Gout, unspecified"),
    "tăng axit uric": ("E79.0", "Hyperuricaemia without signs of inflammatory arthritis"),
}

class MedicalTermNormalizer:
    def normalize_condition(self, term: str) -> NormalizedCondition:
        """Normalize Vietnamese medical term to canonical form"""
        term_lower = term.lower().strip()

        # Direct lookup
        if term_lower in ICD10_MAPPING:
            icd10, english = ICD10_MAPPING[term_lower]
            return NormalizedCondition(
                original=term,
                canonical_vi=term_lower,
                canonical_en=english,
                icd10=icd10
            )

        # Fuzzy match (for variants)
        best_match = self._fuzzy_match(term_lower, list(ICD10_MAPPING.keys()))
        if best_match and best_match.score > 0.85:
            icd10, english = ICD10_MAPPING[best_match.key]
            return NormalizedCondition(
                original=term,
                canonical_vi=best_match.key,
                canonical_en=english,
                icd10=icd10,
                fuzzy_matched=True,
                match_score=best_match.score
            )

        return NormalizedCondition(
            original=term,
            canonical_vi=term_lower,
            canonical_en=None,
            icd10=None,
            unrecognized=True
        )
```

### 4.2 Lab Analyte Normalization

```python
LAB_ANALYTE_ALIASES = {
    # Canonical → aliases (Vietnamese + English variants)
    "HbA1c": ["HbA1c", "A1C", "Hemoglobin A1c", "glycated hemoglobin",
               "đường huyết trung bình", "hemoglobin glycat hóa", "hba1c"],
    "fasting_glucose": ["FBS", "FBG", "Fasting blood glucose", "Fasting glucose",
                        "đường huyết lúc đói", "glucose lúc đói", "G0"],
    "random_glucose": ["RBS", "RBG", "Random blood glucose", "đường huyết bất kỳ"],
    "total_cholesterol": ["TC", "Total cholesterol", "cholesterol toàn phần", "CH"],
    "LDL": ["LDL-C", "LDL cholesterol", "low-density lipoprotein",
             "cholesterol LDL", "cholesterol xấu"],
    "HDL": ["HDL-C", "HDL cholesterol", "high-density lipoprotein",
             "cholesterol HDL", "cholesterol tốt"],
    "triglycerides": ["TG", "TRIG", "triglycerid", "chất béo trung tính"],
    "TSH": ["TSH", "thyrotropin", "thyroid stimulating hormone",
             "hormone kích thích tuyến giáp"],
    "free_T4": ["FT4", "Free T4", "thyroxine tự do", "T4 tự do"],
    "free_T3": ["FT3", "Free T3", "triiodothyronine tự do", "T3 tự do"],
    "creatinine": ["Creat", "Cr", "creatinin", "creatinine huyết thanh"],
    "eGFR": ["GFR", "eGFR", "CKD-EPI", "MDRD", "mức lọc cầu thận"],
    "BUN": ["BUN", "urea nitrogen", "blood urea nitrogen", "ure máu", "urea"],
    "uric_acid": ["UA", "urate", "serum urate", "axit uric", "acid uric"],
    "hemoglobin": ["Hb", "HGB", "hemoglobin", "huyết sắc tố"],
    "hematocrit": ["Hct", "HCT", "hematocrit"],
    "WBC": ["WBC", "white blood cell", "leukocyte", "bạch cầu"],
    "RBC": ["RBC", "red blood cell", "erythrocyte", "hồng cầu"],
    "platelet": ["PLT", "platelet count", "thrombocyte", "tiểu cầu"],
    "ALT": ["ALT", "SGPT", "alanine aminotransferase", "men gan ALT"],
    "AST": ["AST", "SGOT", "aspartate aminotransferase", "men gan AST"],
    "ALP": ["ALP", "alkaline phosphatase", "phosphatase kiềm"],
    "GGT": ["GGT", "gamma-GT", "gamma-glutamyl transferase"],
    "bilirubin_total": ["TBIL", "total bilirubin", "bilirubin toàn phần"],
    "albumin": ["Alb", "albumin", "albumin huyết thanh"],
    "sodium": ["Na", "sodium", "natri huyết thanh"],
    "potassium": ["K", "potassium", "kali huyết thanh"],
    "calcium": ["Ca", "calcium", "canxi huyết thanh"],
    "phosphorus": ["P", "Phos", "phosphate", "phospho huyết thanh"],
    "magnesium": ["Mg", "magnesium", "magiê huyết thanh"],
    "iron": ["Fe", "serum iron", "sắt huyết thanh"],
    "ferritin": ["ferritin", "ferritin huyết thanh"],
    "B12": ["Vit B12", "cobalamin", "vitamin B12", "vitamin B12 huyết thanh"],
    "folate": ["folate", "folic acid", "acid folic", "vitamin B9"],
    "vitamin_D": ["25-OH-D", "25-hydroxyvitamin D", "vitamin D3", "vitamin D huyết thanh"],
    "CRP": ["CRP", "C-reactive protein", "protein phản ứng C"],
    "ESR": ["ESR", "erythrocyte sedimentation rate", "tốc độ lắng máu", "VS"],
    "PSA": ["PSA", "prostate-specific antigen", "kháng nguyên đặc hiệu tuyến tiền liệt"],
    "INR": ["INR", "international normalized ratio", "prothrombin time"],
    "HBsAg": ["HBsAg", "hepatitis B surface antigen"],
    "anti_HCV": ["Anti-HCV", "HCV antibody"],
    "microalbumin": ["microalbumin", "albumin niệu vi thể", "MAU", "UACR"],
}

class AnalyteResolver:
    def resolve(self, raw_name: str) -> str | None:
        """Returns canonical analyte name or None if unrecognized"""
        raw_lower = raw_name.lower().strip()
        for canonical, aliases in LAB_ANALYTE_ALIASES.items():
            if any(alias.lower() == raw_lower for alias in aliases):
                return canonical
        return None
```

---

## 5. Unit Conversion Library

_(Full conversion library defined in 14_CLINICAL_REASONING.md — UnitConverter class)_

Additional VN-specific units:

```python
VN_SPECIFIC_UNIT_NOTES = {
    # VN labs sometimes report:
    "glucose_mmol": "Many VN hospital labs now use mmol/L for glucose",
    "cholesterol_mmol": "HCMC major hospitals: mmol/L; some province labs: mg/dL",
    "TSH_mIU": "VN standard: mIU/L (same as µIU/mL)",
    "hemoglobin_g_per_L": "VN labs often report in g/L; convert to g/dL for reference ranges",
    "ferritin_ng_mL": "ng/mL equivalent to µg/L",
    "vitamin_D_nmol": "Some VN labs use nmol/L: divide by 2.496 to get ng/mL",
    "creatinine_umol": "VN labs increasingly use µmol/L; older labs still use mg/dL",
}
```

---

## 6. Reference Ranges — Full Catalog

```yaml
# data/knowledge/reference_ranges/glucose.yaml

analyte: fasting_glucose
display_name_vi: "Đường huyết lúc đói"
display_name_en: "Fasting Blood Glucose"
si_unit: "mmol/L"
common_vn_unit: "mg/dL"
source: ADA_2025

ranges:
  adult_general:
    normal:
      low: 3.9         # mmol/L = 70 mg/dL
      high: 5.5        # mmol/L = 99 mg/dL
    prediabetes:
      low: 5.6         # mmol/L = 100 mg/dL
      high: 6.9        # mmol/L = 125 mg/dL
    diabetes:
      low: 7.0         # mmol/L = 126 mg/dL
    critical_low: 2.8  # mmol/L = 50 mg/dL
    critical_high: 22.2 # mmol/L = 400 mg/dL

  elderly_65plus:
    normal:
      low: 3.9
      high: 6.1         # Slightly higher normal upper in elderly per geriatric guidelines
    note: "Tăng huyết áp nhẹ hơn có thể chấp nhận ở người rất cao tuổi — tham khảo bác sĩ"

  pregnant:
    normal:
      high: 5.0         # Tighter control needed in GDM
    source: ADA_2025_GDM
    note: "Thai kỳ có ngưỡng khác — phải tham khảo bác sĩ sản khoa"

fasting_required: true
clinical_significance: "Đo lường đường huyết sau ít nhất 8 giờ không ăn. 
  Phản ánh khả năng kiểm soát đường huyết cơ bản."
interpretation_for_patient:
  normal: "Đường huyết lúc đói trong giới hạn bình thường."
  prediabetes: "Đường huyết hơi cao — trong vùng tiền đái tháo đường. Cần theo dõi."
  high: "Đường huyết lúc đói cao hơn ngưỡng bình thường."
  critical: "Đường huyết ở mức nguy hiểm — cần đánh giá y tế ngay."
```

```yaml
# data/knowledge/reference_ranges/HbA1c.yaml

analyte: HbA1c
display_name_vi: "HbA1c (Đường huyết trung bình)"
si_unit: "%"
source: ADA_2025

ranges:
  adult_general:
    normal:
      high: 5.6
    prediabetes:
      low: 5.7
      high: 6.4
    diabetes_threshold: 6.5
    well_controlled_diabetic:
      low: 0.0
      high: 7.0          # ADA target for most adults
    poorly_controlled:
      low: 8.0
    very_high: 10.0      # High risk complications
    critical_high: 14.0  # Severe — escalate
  elderly_65plus:
    target_acceptable: 7.5  # Less aggressive target in elderly
    note: "Ở người cao tuổi ≥65, mục tiêu HbA1c có thể nới lỏng hơn — bác sĩ quyết định"
  pregnant:
    target: 6.0            # Tighter control in GDM
    source: ADA_2025_GDM

average_glucose_equivalent:
  formula: "(HbA1c% × 28.7) - 46.7"
  unit: "mg/dL"
  description: "Công thức ước tính đường huyết trung bình từ HbA1c (eAG)"

clinical_significance: "Phản ánh mức đường huyết trung bình trong 2-3 tháng qua.
  1% HbA1c ≈ 28.7 mg/dL trung bình. 
  Giảm HbA1c 1% giúp giảm ~20% nguy cơ biến chứng mạch máu nhỏ."

fasting_required: false
analyte_notes:
  - "Có thể không chính xác trong bệnh lý hemoglobin (thalassemia, thiếu máu hồng cầu hình liềm)"
  - "Thiếu máu sắt có thể làm tăng HbA1c giả tạo"
  - "Tan máu có thể làm giảm HbA1c giả tạo"
  - "Biotin liều cao ảnh hưởng một số phương pháp đo"
```

---

## 7. Drug Knowledge

### 7.1 Drug Catalog Schema

```yaml
# data/knowledge/drugs/metformin.yaml

drug_id: metformin
generic_name: Metformin
generic_name_vi: Metformin (Metformin HCl)
brand_names_vn:
  - Glucophage
  - Metformin-Stada
  - Diabetex
  - Tiamett

drug_class: Biguanide
drug_class_vi: Nhóm biguanide (hạ đường huyết uống)

mechanism_simple_vi: "Metformin giúp giảm lượng đường gan sản xuất và giúp tế bào 
  sử dụng insulin hiệu quả hơn, không gây hạ đường huyết khi dùng đơn độc."

common_indications_vi:
  - "Đái tháo đường type 2 (điều trị đầu tay)"
  - "Tiền đái tháo đường (phòng ngừa)"
  - "Hội chứng buồng trứng đa nang (PCOS)"

common_side_effects_patient_friendly:
  - vi: "Buồn nôn, tiêu chảy, khó chịu bụng (thường giảm sau vài tuần, uống trong bữa ăn giúp giảm)"
  - vi: "Giảm nhẹ B12 sau dùng lâu dài (thường > 4 năm)"

lab_interactions:
  - analyte: B12
    effect: decrease
    mechanism: "Ức chế hấp thu B12 qua thụ thể ileum"
    timeline: "Sau dùng > 4 năm"
    clinical_note: "Nên kiểm tra B12 mỗi 1-2 năm khi dùng lâu dài"
  - analyte: folate
    effect: decrease_mild
    mechanism: "Có thể giảm nhẹ hấp thu"

# NOT INCLUDED (cần doctor):
# - Specific dosing information
# - Dose adjustment for renal impairment
# - Contraindication details (defer to prescriber)
# - Drug-drug interactions beyond lab effects

safety_note: "Thông tin này chỉ để giải thích về thuốc, không thay thế hướng dẫn 
  của bác sĩ kê đơn. Không tự ý thay đổi liều hoặc ngừng thuốc."
```

### 7.2 Drug Knowledge Scope Boundaries

```python
DRUG_KNOWLEDGE_SCOPE = {
    "INCLUDED": [
        "generic_name",
        "brand_names_VN",
        "drug_class",
        "mechanism_simple_patient_friendly",
        "common_indications_general",
        "common_side_effects_patient_friendly",
        "lab_interactions",
        "storage_instructions",
        "general_adherence_tips",
    ],
    "EXCLUDED": [
        "specific_dosing",              # Never in KB
        "dose_adjustments",             # Never in KB
        "detailed_contraindications",   # Defer to doctor/pharmacist
        "drug_drug_interactions",       # Only safety flags, no guidance
        "pregnancy_drug_safety",        # Always defer
        "pediatric_dosing",             # Never
        "off_label_use",                # Never
    ]
}
```

---

## 8. Laboratory Knowledge Catalog

```yaml
# data/knowledge/laboratory/creatinine.yaml

analyte: creatinine
display_name_vi: "Creatinine huyết thanh"
display_name_en: "Serum Creatinine"

clinical_significance_vi: "Creatinine là chất thải từ chuyển hóa cơ bắp, 
  được lọc qua thận. Nồng độ creatinine trong máu phản ánh chức năng lọc của thận.
  Creatinine tăng thường gặp khi thận hoạt động kém hiệu quả hơn."

common_causes_high_vi:
  - "Giảm chức năng thận (suy thận, bệnh thận mãn tính)"
  - "Mất nước (dehydration)"
  - "Tập thể dục cường độ cao gần đây"
  - "Chế độ ăn nhiều thịt đỏ"
  - "Một số thuốc (NSAIDs lâu dài, trimethoprim)"

common_causes_low_vi:
  - "Khối lượng cơ ít (người cao tuổi, suy dinh dưỡng)"
  - "Thai kỳ (do tăng GFR)"

what_patient_should_know_vi:
  - "Creatinine một mình không đủ đánh giá thận — bác sĩ thường dùng kết hợp với eGFR"
  - "Một lần xét nghiệm không đủ kết luận — cần theo dõi theo thời gian"
  - "Tập thể dục nặng trước khi xét nghiệm có thể tăng tạm thời"

related_analytes:
  - eGFR
  - BUN
  - uric_acid
  - potassium
  - microalbumin

affected_by_drugs:
  - metformin: "Metformin theo dõi thận để điều chỉnh — tham khảo bác sĩ"
  - NSAIDs: "NSAIDs lâu dài có thể ảnh hưởng thận — báo bác sĩ nếu dùng thường xuyên"
```

---

## 9. Nutrition Knowledge

### 9.1 Food-Condition Mapping

```yaml
# data/knowledge/nutrition/diabetes_nutrition.yaml

condition: diabetes_type2
source: ADA_2025_nutrition

principles_vi:
  - "Ưu tiên thực phẩm có chỉ số đường huyết (GI) thấp đến trung bình"
  - "Kiểm soát khẩu phần carbohydrate (không cần loại bỏ hoàn toàn)"
  - "Tăng chất xơ từ rau củ, đậu, ngũ cốc nguyên hạt"
  - "Đạm nạc (cá, đậu phụ, thịt gà không da)"
  - "Chất béo lành mạnh (dầu ô liu, cá, quả bơ, các loại hạt)"

foods_to_prioritize:
  vi_examples:
    - "Gạo lứt, ngũ cốc nguyên hạt (thay cơm trắng một phần)"
    - "Rau xanh các loại (rau muống, rau cải, bắp cải)"
    - "Cá (cá thu, cá hồi, cá tra)"
    - "Đậu phụ, đậu các loại"
    - "Trái cây ít ngọt (ổi, thanh long, bưởi, táo)"

foods_to_limit:
  vi_examples:
    - "Cơm trắng, bánh mì trắng, bún, phở (kiểm soát lượng)"
    - "Đường, nước ngọt, trái cây ngọt nhiều (xoài chín, nhãn, vải)"
    - "Thức ăn chiên rán"
    - "Thức ăn chế biến sẵn nhiều muối và đường"

disclaimer: "Chế độ ăn cụ thể cần được lập theo hướng dẫn của bác sĩ hoặc 
  chuyên gia dinh dưỡng. Thông tin này là hướng dẫn chung."
```

### 9.2 VN Food Database Subset

```python
VN_FOOD_GLYCEMIC_INDEX = {
    # Common VN foods with GI values
    # Source: FAO/WHO food composition tables adapted for VN
    "cơm trắng": {"gi": 72, "category": "high", "serving_100g_carb_g": 28},
    "cơm gạo lứt": {"gi": 55, "category": "medium", "serving_100g_carb_g": 23},
    "bún": {"gi": 65, "category": "medium_high", "serving_100g_carb_g": 22},
    "phở": {"gi": 60, "category": "medium", "serving_100g_carb_g": 18},
    "bánh mì": {"gi": 70, "category": "high", "serving_100g_carb_g": 49},
    "khoai lang": {"gi": 44, "category": "low", "serving_100g_carb_g": 20},
    "khoai tây": {"gi": 78, "category": "high", "serving_100g_carb_g": 17},
    "ngô": {"gi": 52, "category": "medium", "serving_100g_carb_g": 18},
    "chuối": {"gi": 48, "category": "low_medium", "serving_100g_carb_g": 23},
    "xoài chín": {"gi": 56, "category": "medium", "serving_100g_carb_g": 15},
    "ổi": {"gi": 20, "category": "low", "serving_100g_carb_g": 14},
    "bưởi": {"gi": 25, "category": "low", "serving_100g_carb_g": 10},
    "thanh long": {"gi": 40, "category": "low", "serving_100g_carb_g": 11},
    "đậu đỏ": {"gi": 29, "category": "low", "serving_100g_carb_g": 21},
    "đậu nành": {"gi": 15, "category": "very_low", "serving_100g_carb_g": 9},
    "rau muống": {"gi": 5, "category": "very_low", "serving_100g_carb_g": 2},
    "nước ngọt có ga": {"gi": 65, "category": "high", "serving_250ml_carb_g": 27},
}

GI_CATEGORIES = {
    "very_low": (0, 20),
    "low": (21, 40),
    "low_medium": (41, 50),
    "medium": (51, 60),
    "medium_high": (61, 70),
    "high": (71, 100),
}
```

---

## 10. Exercise Knowledge

```yaml
# data/knowledge/exercise/condition_guidance.yaml

exercise_knowledge:
  general_principles_vi:
    - "Hoạt động thể chất đều đặn có lợi cho hầu hết người trưởng thành"
    - "WHO khuyến nghị ít nhất 150 phút hoạt động aerobic vừa phải mỗi tuần"
    - "Bắt đầu từ từ và tăng dần là an toàn nhất"
    - "Tham khảo bác sĩ trước khi bắt đầu chương trình tập mới nếu có bệnh nền"

intensity_levels:
  light:
    vi: "Nhẹ — đi bộ chậm, yoga nhẹ, kéo giãn"
    heart_rate_target_percent: "50-60% max HR"
  moderate:
    vi: "Vừa phải — đi bộ nhanh, bơi lội, đạp xe chậm"
    heart_rate_target_percent: "60-70% max HR"
  vigorous:
    vi: "Mạnh — chạy, aerobics, thể thao"
    heart_rate_target_percent: "70-85% max HR"
    caution: "Cần đánh giá y tế trước ở người có bệnh lý"

condition_specific:
  diabetes_type2:
    recommended: [light, moderate]
    special_notes:
      - "Đi bộ 10-30 phút sau bữa ăn giúp kiểm soát đường huyết sau ăn"
      - "Kiểm tra đường huyết trước tập nếu đang dùng insulin"
      - "Mang theo đồ ăn ngọt nhỏ khi tập phòng hạ đường huyết"
    avoid_without_clearance: "Tập cường độ cao khi đường huyết > 14 mmol/L (250 mg/dL)"

  hypertension:
    recommended: [light, moderate]
    special_notes:
      - "Aerobic đều đặn có thể giảm huyết áp nhẹ-vừa"
      - "Tránh các động tác làm tăng huyết áp đột ngột (Valsalva)"
    avoid_without_clearance: "Lifting nặng, tập rất mạnh khi huyết áp chưa kiểm soát"

  heart_failure:
    recommended: [light]
    mandatory_clearance: true
    note: "Mọi chương trình tập cho suy tim đều cần cardiac clearance"

  osteoporosis:
    recommended: ["weight_bearing_low_impact", "balance_training"]
    special_notes:
      - "Đi bộ, leo cầu thang, tập cân bằng giúp mật độ xương và giảm ngã"
    avoid: "Các hoạt động nguy cơ va chạm cao hoặc ngã"
```

---

## 11. Evidence Grading & Uncertainty Communication

### 11.1 Evidence Grading System

```python
class EvidenceGrade(str, Enum):
    A = "A"    # Strong evidence — multiple large RCTs or meta-analyses
    B = "B"    # Moderate evidence — fewer/smaller RCTs or well-designed cohort
    C = "C"    # Limited evidence — case series, expert opinion with consensus
    D = "D"    # Very limited — expert opinion only, no systematic evidence
    E = "E"    # Extrapolated — inferred from related evidence

EVIDENCE_LANGUAGE = {
    EvidenceGrade.A: {
        "certainty": "cao",
        "template": "Bằng chứng mạnh cho thấy {finding}.",
    },
    EvidenceGrade.B: {
        "certainty": "khá tốt",
        "template": "Bằng chứng cho thấy {finding}.",
    },
    EvidenceGrade.C: {
        "certainty": "hạn chế",
        "template": "Theo một số nghiên cứu, {finding}. Cần thêm bằng chứng để xác nhận.",
    },
    EvidenceGrade.D: {
        "certainty": "rất hạn chế",
        "template": "Theo ý kiến chuyên gia, {finding}. Nghiên cứu trực tiếp còn hạn chế.",
    },
    EvidenceGrade.E: {
        "certainty": "suy luận",
        "template": "Dựa trên các bằng chứng liên quan, có thể {finding}. Chưa có nghiên cứu trực tiếp.",
    },
}

def format_with_uncertainty(finding: str, grade: EvidenceGrade) -> str:
    template = EVIDENCE_LANGUAGE[grade]["template"]
    return template.format(finding=finding)
```

---

## 12. Knowledge Freshness & Cache

### 12.1 TTL per Knowledge Type

```python
KNOWLEDGE_TTL_DAYS = {
    "reference_ranges": 365,           # Annual guideline updates
    "drug_facts": 180,                 # 6 months
    "drug_lab_interactions": 180,
    "condition_overview": 365,
    "nutrition_guidelines": 365,
    "exercise_guidelines": 365,
    "screening_schedules": 180,
    "vaccination_schedules": 90,       # More frequent updates possible
    "unit_conversions": 3650,          # Rarely change
    "icd10_mappings": 365,
    "analyte_catalog": 365,
}

# Cache invalidation strategy
class KnowledgeCache:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.prefix = "meto:kb:"

    async def get(self, key: str) -> KnowledgeItem | None:
        raw = await self.redis.get(f"{self.prefix}{key}")
        if not raw:
            return None
        item = KnowledgeItem.parse_raw(raw)
        # Check if still within version TTL
        if item.expires_date and item.expires_date < date.today():
            await self.invalidate(key)
            return None
        return item

    async def set(self, key: str, item: KnowledgeItem):
        ttl_seconds = KNOWLEDGE_TTL_DAYS.get(item.domain, 365) * 86400
        await self.redis.setex(
            f"{self.prefix}{key}",
            ttl_seconds,
            item.json()
        )

    async def invalidate(self, key: str):
        await self.redis.delete(f"{self.prefix}{key}")
        await self.redis.delete(f"{self.prefix}{key}:version")

    async def invalidate_domain(self, domain: str):
        """Invalidate all cached items for a domain"""
        pattern = f"{self.prefix}{domain}:*"
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)
```

### 12.2 Update Pipeline

```
Knowledge Update Flow:
━━━━━━━━━━━━━━━━━━━━━

Medical Expert / Admin
        │
        ▼
[1. Draft new knowledge item]
        │ (YAML/JSON in data/knowledge/)
        ▼
[2. Automated validation]
        ├─ Schema validation
        ├─ Source verification (source_id exists in SOURCE_REGISTRY)
        ├─ Version bump check
        ├─ Language check (both vi and en required)
        └─ Effective date check (cannot be past)
        │
        ▼
[3. Medical review (human)]
        │ (required for GUIDELINE and RULE tier)
        ▼
[4. Staging deployment]
        │ (test with synthetic cases)
        ▼
[5. Production publish]
        │ (KnowledgeVersionManager.publish_new_version())
        ▼
[6. Cache invalidation]
        │
        ▼
[7. Audit log + notification]
```

---

## 13. Fallback Strategy

### 13.1 Knowledge Not Found

```python
class KnowledgeFallbackHandler:

    async def handle_not_found(
        self,
        query: str,
        analyte: str | None = None,
        domain: str | None = None
    ) -> KnowledgeFallback:

        # Attempt fuzzy match
        fuzzy_result = await self._fuzzy_search(query, domain)
        if fuzzy_result and fuzzy_result.confidence > 0.7:
            return KnowledgeFallback(
                found=True,
                item=fuzzy_result.item,
                was_fuzzy=True,
                confidence=fuzzy_result.confidence
            )

        # Nothing found
        return KnowledgeFallback(
            found=False,
            response_vi=(
                f"Meto chưa có thông tin về '{query}'. "
                f"Bác sĩ hoặc dược sĩ là người phù hợp nhất để giải đáp câu hỏi này."
            ),
            log_for_review=True  # Flag for KB team to add
        )

UNKNOWN_KNOWLEDGE_POLICY = """
Khi không có trong Knowledge Base:
1. KHÔNG đoán mò
2. KHÔNG sử dụng training knowledge của AI model để claim về bệnh cụ thể của user
3. Trả lời: "Meto chưa có thông tin về điều này"
4. Gợi ý: Hỏi bác sĩ, dược sĩ, hoặc nhân viên y tế
5. Log để KB team xem xét thêm
"""
```

---

## 14. Future RAG Compatibility

### 14.1 Chunk Format cho RAG

```python
@dataclass
class KnowledgeChunk:
    """
    Format chuẩn để index vào vector database cho RAG.
    Thiết kế tương thích với LlamaIndex, LangChain, và Azure AI Search.
    """
    chunk_id: str                      # Unique ID
    knowledge_item_id: str             # Links to KnowledgeItem
    domain: str
    tier: str
    chunk_text: str                    # Text to embed (Vietnamese)
    chunk_text_en: str                 # English version
    metadata: dict = field(default_factory=lambda: {
        "analyte": None,
        "condition_icd10": None,
        "drug_generic": None,
        "source_id": None,
        "trust_score": None,
        "effective_date": None,
        "version": None,
    })
    estimated_tokens: int              # Pre-computed for budget planning

class RAGChunker:
    MAX_CHUNK_TOKENS = 512             # Optimal for most embedding models
    OVERLAP_TOKENS = 50

    def chunk(self, item: KnowledgeItem) -> list[KnowledgeChunk]:
        """Split long knowledge items into overlapping chunks"""
        text = item.content_vi
        chunks = self._sliding_window_split(text, self.MAX_CHUNK_TOKENS, self.OVERLAP_TOKENS)

        return [
            KnowledgeChunk(
                chunk_id=f"{item.id}:chunk_{i}",
                knowledge_item_id=item.id,
                domain=item.domain,
                tier=item.tier,
                chunk_text=chunk,
                metadata={
                    "source_id": item.source.source_id,
                    "trust_score": item.trust_score,
                    "effective_date": str(item.effective_date),
                    "version": item.version,
                }
            )
            for i, chunk in enumerate(chunks)
        ]
```

### 14.2 Embedding Strategy

```python
class EmbeddingStrategy:
    """
    Strategy pattern — swap embedding provider without changing KB logic.
    Implemented via ProviderAbstractionLayer (see 20_PROVIDER_ABSTRACTION.md).
    """

    EMBEDDING_CONFIG = {
        "model": "text-embedding-3-small",  # Default OpenAI — swappable
        "dimensions": 1536,
        "batch_size": 100,                   # Items per embedding API call
        "language": "vi_en_bilingual",       # Embed both VI and EN texts
        "normalize": True,                   # L2 normalize for cosine similarity
    }

    RETRIEVAL_CONFIG = {
        "top_k": 5,                          # Number of chunks to retrieve
        "min_similarity": 0.7,              # Minimum cosine similarity
        "rerank": True,                     # Apply reranking after retrieval
        "trust_weight": 0.3,               # Factor trust_score into final ranking
        "recency_weight": 0.1,             # Factor version date into ranking
    }
```

### 14.3 Future Vector Search Schema

```sql
-- Future: Migrate to pgvector or Azure AI Search
-- Schema design for vector compatibility

CREATE TABLE knowledge_embeddings (
    id                  UUID PRIMARY KEY,
    knowledge_item_id   UUID REFERENCES knowledge_items(id),
    chunk_index         INTEGER,
    chunk_text          TEXT NOT NULL,
    chunk_text_en       TEXT,
    embedding           vector(1536),      -- pgvector extension
    embedding_model     TEXT,              -- "text-embedding-3-small"
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON knowledge_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Future query:
-- SELECT k.*, 1 - (e.embedding <=> $1::vector) AS similarity
-- FROM knowledge_embeddings e
-- JOIN knowledge_items k ON k.id = e.knowledge_item_id
-- ORDER BY similarity DESC
-- LIMIT 5;
```

---

## 15. Future Medical Ontology Compatibility

### 15.1 SNOMED-CT Readiness

```python
@dataclass
class OntologyMapping:
    """
    Sẵn sàng cho tích hợp UMLS / SNOMED-CT trong tương lai.
    Current: lưu code nhưng chưa active validation.
    Future: validate against live UMLS API.
    """
    icd10: str | None              # Current primary mapping
    snomed_ct: str | None          # SNOMED-CT concept ID (future)
    umls_cui: str | None           # UMLS Concept Unique Identifier (future)
    rxnorm: str | None             # For medications (future)
    loinc: str | None              # For lab tests (future)

# Current LOINC codes for common analytes (for future lab data integration)
ANALYTE_LOINC_CODES = {
    "HbA1c": "4548-4",
    "fasting_glucose": "1558-6",
    "total_cholesterol": "2093-3",
    "LDL": "2089-1",
    "HDL": "2085-9",
    "triglycerides": "2571-8",
    "creatinine": "2160-0",
    "eGFR": "62238-1",
    "TSH": "3016-3",
    "free_T4": "3024-7",
    "hemoglobin": "718-7",
    "ALT": "1742-6",
    "AST": "1920-8",
    "potassium": "2823-3",
    "sodium": "2951-2",
    "calcium": "17861-6",
}
```

---

## 16. Admin Interface Spec

```
Knowledge Base Admin (Internal Tool — not user-facing):

1. BROWSE — List all knowledge items by domain/tier/version
2. SEARCH — Full-text search across all KB items
3. COMPARE — Diff between two versions of same item
4. PUBLISH — Create new version of a knowledge item
5. DEPRECATE — Mark item as deprecated with replacement
6. ROLLBACK — Emergency rollback to previous version
7. AUDIT — View all changes to knowledge base
8. GAP ANALYSIS — Items flagged "not found" by users (aggregated, no PII)
9. SOURCE STATUS — Which guidelines are due for update?
10. COVERAGE MAP — Which conditions/analytes have KB coverage?
```

---

## 17. Acceptance Criteria

### AC-KB-001: Hierarchy
- [ ] All knowledge items have tier assigned (evidence/guideline/rule/fact)
- [ ] Trust score derived from tier + source
- [ ] Source ID references exist in SOURCE_REGISTRY

### AC-KB-002: Versioning
- [ ] Every knowledge update creates new versioned item
- [ ] Old version deprecated with 90-day retention
- [ ] Version history queryable for any item
- [ ] Rollback completes within 5 minutes

### AC-KB-003: Terminology
- [ ] Common VN lab terms resolve to canonical analyte names
- [ ] Common VN condition names resolve to ICD-10 codes
- [ ] Unknown terms return graceful fallback

### AC-KB-004: Unit Conversion
- [ ] Glucose mg/dL ↔ mmol/L accurate (±0.1%)
- [ ] Creatinine mg/dL ↔ µmol/L accurate
- [ ] All conversions in UNIT_CONVERSIONS tested with known values

### AC-KB-005: Cache
- [ ] Cache hit rate > 90% for common analytes
- [ ] Cache invalidation propagates within 30 seconds
- [ ] Stale cache served with staleness flag when DB unavailable

### AC-KB-006: RAG Readiness
- [ ] All knowledge items have chunk_text field populated
- [ ] Chunk size ≤ 512 tokens
- [ ] Metadata fields complete (source, trust_score, version, effective_date)

### AC-KB-007: Coverage
- [ ] Reference ranges for all analytes in ANALYTE_LOINC_CODES
- [ ] Drug facts for top 20 medications in VN diabetes/hypertension care
- [ ] Nutrition guidance for diabetes, hypertension, dyslipidemia, renal disease

---

*Xem thêm: 14_CLINICAL_REASONING.md (KB cung cấp reference ranges và drug-lab patterns), 15_RECOMMENDATION_ENGINE.md (KB cung cấp nutrition và exercise guidance), 20_PROVIDER_ABSTRACTION.md (EmbeddingProvider cho future RAG)*
