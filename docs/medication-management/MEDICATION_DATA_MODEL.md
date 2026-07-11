# MEDICATION_DATA_MODEL.md
# MetoCare — Medication Management: Full Data Model

**Version:** 1.0  
**Date:** 2026-07-10  
**Status:** Design document — no migrations created yet

---

## 1. Current Schema (What Exists)

### medications table (current)
```sql
CREATE TABLE medications (
    id           VARCHAR(36) PRIMARY KEY,
    patient_id   VARCHAR(36) NOT NULL REFERENCES patient_profiles(id),
    name         VARCHAR(255) NOT NULL,
    dose         VARCHAR(128),
    frequency    VARCHAR(128),          -- added pr_d migration
    note         TEXT,
    created_at   DATETIME NOT NULL,
    updated_at   DATETIME NOT NULL,
    deleted_at   DATETIME               -- soft delete
);
CREATE INDEX ix_medications_patient_id ON medications(patient_id);
```

### medication_adherence table (current)
```sql
CREATE TABLE medication_adherence (
    id              VARCHAR(36) PRIMARY KEY,
    medication_id   VARCHAR(36) NOT NULL REFERENCES medications(id),
    patient_id      VARCHAR(36) NOT NULL REFERENCES patient_profiles(id),
    scheduled_time  DATETIME,
    taken_at        DATETIME,
    skipped         BOOLEAN NOT NULL DEFAULT FALSE,
    note            TEXT,
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL
);
CREATE INDEX ix_medication_adherence_medication_id ON medication_adherence(medication_id);
CREATE INDEX ix_medication_adherence_patient_id ON medication_adherence(patient_id);
```

### drug_catalog table (current)
```sql
CREATE TABLE drug_catalog (
    id                         VARCHAR(36) PRIMARY KEY,
    created_at                 DATETIME NOT NULL,
    updated_at                 DATETIME NOT NULL,
    generic_name               VARCHAR(255) NOT NULL,
    brand_names                JSON NOT NULL,
    vietnamese_common_names    JSON NOT NULL,
    aliases                    JSON NOT NULL,
    active_ingredients         JSON NOT NULL,
    drug_class                 VARCHAR(128) NOT NULL,
    metric_groups              JSON NOT NULL,
    common_indications         JSON NOT NULL,
    prescription_required      BOOLEAN NOT NULL,
    country_context            VARCHAR(10) NOT NULL DEFAULT 'VN',
    caution_flags              JSON NOT NULL,
    contraindication_keywords  JSON NOT NULL,
    renal_caution              BOOLEAN NOT NULL,
    hepatic_caution            BOOLEAN NOT NULL,
    pregnancy_caution          BOOLEAN NOT NULL,
    notes_for_matching_only    TEXT,
    is_active                  BOOLEAN NOT NULL,
    source_version             VARCHAR(32) NOT NULL
);
```

---

## 2. Target Schema — New Tables

### 2.1 medications table (enhanced — migration P0)

```sql
-- Migration: med_p0_enhance_medications
ALTER TABLE medications
    ADD COLUMN drug_catalog_id       VARCHAR(36) REFERENCES drug_catalog(id),
    ADD COLUMN generic_name          VARCHAR(255),
    ADD COLUMN active_ingredient     VARCHAR(255),
    ADD COLUMN drug_class            VARCHAR(128),
    ADD COLUMN dose_amount           NUMERIC(10,4),
    ADD COLUMN dose_unit             VARCHAR(32),
    ADD COLUMN dose_text             VARCHAR(128),
    ADD COLUMN route                 VARCHAR(64),
    ADD COLUMN frequency_code        VARCHAR(32),
    ADD COLUMN timing_instructions   TEXT,
    ADD COLUMN start_date            DATE,
    ADD COLUMN end_date              DATE,
    ADD COLUMN is_prn                BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN prn_indication        VARCHAR(255),
    ADD COLUMN indication            VARCHAR(512),
    ADD COLUMN prescribed_by         VARCHAR(255),
    ADD COLUMN prescription_ref      VARCHAR(64),
    ADD COLUMN source_type           VARCHAR(32) NOT NULL DEFAULT 'manual',
    ADD COLUMN status                VARCHAR(32) NOT NULL DEFAULT 'active',
    ADD COLUMN is_supplement         BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN supplement_category   VARCHAR(64),
    ADD COLUMN supplement_evidence_note TEXT;

-- All new columns nullable for safe migration
-- Existing rows: status defaults to 'active', source_type to 'manual'
-- No backfill required — data is sparse enough
```

**Constraints (applied after backfill):**
```sql
-- Check constraint for status enum
ALTER TABLE medications ADD CONSTRAINT chk_medication_status
    CHECK (status IN ('active', 'paused', 'completed', 'discontinued'));

-- Check constraint for source_type
ALTER TABLE medications ADD CONSTRAINT chk_medication_source_type
    CHECK (source_type IN ('manual', 'ocr_confirmed', 'doctor_added'));

-- Check constraint for frequency_code
ALTER TABLE medications ADD CONSTRAINT chk_medication_frequency_code
    CHECK (frequency_code IN ('QD','BID','TID','QID','QOD','WEEKLY','PRN','CUSTOM') OR frequency_code IS NULL);

-- Check constraint for supplement_category
ALTER TABLE medications ADD CONSTRAINT chk_supplement_category
    CHECK (supplement_category IN ('herbal','vitamin','functional_food','tcm') OR supplement_category IS NULL);
```

**Indexes (new):**
```sql
CREATE INDEX ix_medications_status ON medications(status) WHERE deleted_at IS NULL;
CREATE INDEX ix_medications_drug_catalog_id ON medications(drug_catalog_id);
CREATE INDEX ix_medications_active_ingredient ON medications(active_ingredient);
```

### 2.2 patient_allergies table (new — migration P3)

```sql
CREATE TABLE patient_allergies (
    id                 VARCHAR(36) PRIMARY KEY,
    patient_id         VARCHAR(36) NOT NULL REFERENCES patient_profiles(id),
    allergen_type      VARCHAR(32) NOT NULL,  -- drug | food | environmental | other
    allergen_name      VARCHAR(255) NOT NULL,
    drug_catalog_id    VARCHAR(36) REFERENCES drug_catalog(id),
    active_ingredient  VARCHAR(255),
    drug_class         VARCHAR(128),
    reaction_type      VARCHAR(128),          -- rash | anaphylaxis | GI | unknown
    severity           VARCHAR(16) NOT NULL DEFAULT 'unknown',
    notes              TEXT,
    verified_by_doctor BOOLEAN NOT NULL DEFAULT FALSE,
    created_at         DATETIME NOT NULL,
    updated_at         DATETIME NOT NULL,
    deleted_at         DATETIME               -- soft delete
);

CREATE INDEX ix_patient_allergies_patient_id ON patient_allergies(patient_id);
CREATE INDEX ix_patient_allergies_active_ingredient ON patient_allergies(active_ingredient);
CREATE INDEX ix_patient_allergies_drug_class ON patient_allergies(drug_class);

-- Constraints
ALTER TABLE patient_allergies ADD CONSTRAINT chk_allergy_type
    CHECK (allergen_type IN ('drug', 'food', 'environmental', 'other'));

ALTER TABLE patient_allergies ADD CONSTRAINT chk_allergy_severity
    CHECK (severity IN ('mild', 'moderate', 'severe', 'life_threatening', 'unknown'));
```

### 2.3 medication_warnings table (new — migration P3)

```sql
CREATE TABLE medication_warnings (
    id               VARCHAR(36) PRIMARY KEY,
    patient_id       VARCHAR(36) NOT NULL REFERENCES patient_profiles(id),
    medication_ids   JSON NOT NULL,          -- list of involved medication UUIDs
    warning_type     VARCHAR(64) NOT NULL,
    severity         VARCHAR(16) NOT NULL,
    title            VARCHAR(255) NOT NULL,
    body             TEXT NOT NULL,
    evidence_source  VARCHAR(255) NOT NULL,
    evidence_quality VARCHAR(32) NOT NULL DEFAULT 'catalog_based',
    is_dismissed     BOOLEAN NOT NULL DEFAULT FALSE,
    dismissed_at     DATETIME,
    dismissed_by     VARCHAR(36),
    created_at       DATETIME NOT NULL,
    updated_at       DATETIME NOT NULL
);

CREATE INDEX ix_med_warnings_patient_id ON medication_warnings(patient_id);
CREATE INDEX ix_med_warnings_severity ON medication_warnings(severity) WHERE is_dismissed = FALSE;

ALTER TABLE medication_warnings ADD CONSTRAINT chk_warning_type
    CHECK (warning_type IN ('duplicate_ingredient','duplicate_class','allergy','drug_drug','drug_lab','organ_caution'));

ALTER TABLE medication_warnings ADD CONSTRAINT chk_warning_severity
    CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL'));
```

### 2.4 drug_interaction_rules table (new — migration P3)

```sql
CREATE TABLE drug_interaction_rules (
    id               VARCHAR(36) PRIMARY KEY,
    ingredient_a     VARCHAR(255) NOT NULL,
    ingredient_b     VARCHAR(255) NOT NULL,
    interaction_type VARCHAR(64) NOT NULL,
    severity         VARCHAR(16) NOT NULL,
    mechanism        TEXT,
    clinical_effect  VARCHAR(512) NOT NULL,
    management       VARCHAR(512) NOT NULL,
    evidence_level   VARCHAR(32) NOT NULL DEFAULT 'B',
    source           VARCHAR(255) NOT NULL,
    version          VARCHAR(16) NOT NULL DEFAULT '1.0.0',
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       DATETIME NOT NULL,
    updated_at       DATETIME NOT NULL
);

CREATE INDEX ix_interaction_rules_a ON drug_interaction_rules(ingredient_a);
CREATE INDEX ix_interaction_rules_b ON drug_interaction_rules(ingredient_b);
CREATE INDEX ix_interaction_rules_active ON drug_interaction_rules(is_active);

-- Ensure pairs are stored canonically (A < B alphabetically) to avoid duplicates
ALTER TABLE drug_interaction_rules ADD CONSTRAINT chk_ingredient_order
    CHECK (ingredient_a <= ingredient_b);
```

### 2.5 medication_schedules table (new — migration P1)

```sql
CREATE TABLE medication_schedules (
    id              VARCHAR(36) PRIMARY KEY,
    medication_id   VARCHAR(36) NOT NULL REFERENCES medications(id),
    patient_id      VARCHAR(36) NOT NULL REFERENCES patient_profiles(id),
    scheduled_time  VARCHAR(5) NOT NULL,     -- HH:MM patient local time
    days_of_week    JSON,                    -- [1,2,3,4,5,6,7] = Mon-Sun; null = daily
    timezone        VARCHAR(64) NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL
);

CREATE INDEX ix_med_schedules_medication_id ON medication_schedules(medication_id);
CREATE INDEX ix_med_schedules_patient_id ON medication_schedules(patient_id);
```

### 2.6 medication_refills table (new — migration P4)

```sql
CREATE TABLE medication_refills (
    id                  VARCHAR(36) PRIMARY KEY,
    medication_id       VARCHAR(36) NOT NULL REFERENCES medications(id),
    patient_id          VARCHAR(36) NOT NULL REFERENCES patient_profiles(id),
    quantity_dispensed  INTEGER,             -- number of pills/units
    days_supply         INTEGER,             -- how many days this refill covers
    refill_date         DATE NOT NULL,
    refill_source       VARCHAR(32) NOT NULL DEFAULT 'self_purchased',
    notes               TEXT,
    created_at          DATETIME NOT NULL,
    updated_at          DATETIME NOT NULL
);

CREATE INDEX ix_med_refills_medication_id ON medication_refills(medication_id);
CREATE INDEX ix_med_refills_patient_id ON medication_refills(patient_id);

ALTER TABLE medication_refills ADD CONSTRAINT chk_refill_source
    CHECK (refill_source IN ('pharmacy','clinic','self_purchased','other'));
```

### 2.7 caregiver_assignments table (new — migration P4)

```sql
CREATE TABLE caregiver_assignments (
    id                       VARCHAR(36) PRIMARY KEY,
    patient_id               VARCHAR(36) NOT NULL REFERENCES patient_profiles(id),
    caregiver_user_id        VARCHAR(36) NOT NULL REFERENCES users(id),
    relationship             VARCHAR(64) NOT NULL DEFAULT 'other',
    can_view_medications     BOOLEAN NOT NULL DEFAULT TRUE,
    can_view_adherence       BOOLEAN NOT NULL DEFAULT TRUE,
    can_receive_reminders    BOOLEAN NOT NULL DEFAULT FALSE,
    can_add_notes            BOOLEAN NOT NULL DEFAULT FALSE,
    granted_at               DATETIME NOT NULL,
    revoked_at               DATETIME,
    created_at               DATETIME NOT NULL,
    updated_at               DATETIME NOT NULL
);

CREATE INDEX ix_caregiver_patient_id ON caregiver_assignments(patient_id);
CREATE INDEX ix_caregiver_user_id ON caregiver_assignments(caregiver_user_id);

ALTER TABLE caregiver_assignments ADD CONSTRAINT chk_relationship
    CHECK (relationship IN ('spouse','parent','child','sibling','friend','professional','other'));
```

---

## 3. Enhanced medication_adherence (P1)

Add `schedule_id` FK to link a dose event to a scheduled reminder:

```sql
-- Migration: med_p1_adherence_schedule_link
ALTER TABLE medication_adherence
    ADD COLUMN schedule_id VARCHAR(36) REFERENCES medication_schedules(id);
```

---

## 4. Enhanced drug_catalog (P3)

Add `traditional_medicine` flag and `evidence_level`:

```sql
-- Migration: med_p3_catalog_enrich
ALTER TABLE drug_catalog
    ADD COLUMN is_traditional_medicine BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN evidence_level          VARCHAR(32);
    -- evidence_level: A (RCT evidence) | B (observational) | C (expert opinion) | limited (supplement)
```

---

## 5. Migration Sequence

| Migration ID | Phase | Table | Action | Safe to Rollback |
|-------------|-------|-------|--------|-----------------|
| `med_p0_a_medications_enhance` | P0 | medications | ADD COLUMNS (all nullable) | ✅ Yes — drop columns |
| `med_p0_b_medications_constraints` | P0 | medications | ADD CONSTRAINTS | ✅ Yes — drop constraints |
| `med_p0_c_medications_indexes` | P0 | medications | CREATE INDEXES | ✅ Yes |
| `med_p1_a_schedules` | P1 | medication_schedules | CREATE TABLE | ✅ Yes |
| `med_p1_b_adherence_schedule_link` | P1 | medication_adherence | ADD COLUMN schedule_id | ✅ Yes |
| `med_p1_c_notification_type` | P1 | (application code) | Add medication_reminder type | ✅ Yes |
| `med_p3_a_allergies` | P3 | patient_allergies | CREATE TABLE | ✅ Yes |
| `med_p3_b_warnings` | P3 | medication_warnings | CREATE TABLE | ✅ Yes |
| `med_p3_c_interaction_rules` | P3 | drug_interaction_rules | CREATE TABLE + seed | ✅ Yes |
| `med_p3_d_catalog_enrich` | P3 | drug_catalog | ADD COLUMNS | ✅ Yes |
| `med_p4_a_refills` | P4 | medication_refills | CREATE TABLE | ✅ Yes |
| `med_p4_b_caregivers` | P4 | caregiver_assignments | CREATE TABLE | ✅ Yes |

**Migration Rules:**
- All new columns are nullable — no existing row breaks
- No existing column types or constraints are changed
- No destructive operations (no DROP COLUMN in any P0–P4 migration)
- Clinic SaaS migration head is not touched
- Each migration has a reversible `downgrade()` function

---

## 6. SQLAlchemy Models (Python — target)

### Medication (enhanced)
```python
class Medication(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "medications"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True, nullable=False)
    drug_catalog_id: Mapped[str | None] = mapped_column(ForeignKey("drug_catalog.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    generic_name: Mapped[str | None] = mapped_column(String(255))
    active_ingredient: Mapped[str | None] = mapped_column(String(255))
    drug_class: Mapped[str | None] = mapped_column(String(128))
    dose_amount: Mapped[float | None] = mapped_column(Numeric(10, 4))
    dose_unit: Mapped[str | None] = mapped_column(String(32))
    dose_text: Mapped[str | None] = mapped_column(String(128))
    route: Mapped[str | None] = mapped_column(String(64))
    frequency_code: Mapped[str | None] = mapped_column(String(32))
    frequency: Mapped[str | None] = mapped_column(String(128))       # existing column
    timing_instructions: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    is_prn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prn_indication: Mapped[str | None] = mapped_column(String(255))
    indication: Mapped[str | None] = mapped_column(String(512))
    prescribed_by: Mapped[str | None] = mapped_column(String(255))
    prescription_ref: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    is_supplement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supplement_category: Mapped[str | None] = mapped_column(String(64))
    supplement_evidence_note: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)                   # existing column
```

---

## 7. API Schema Changes (target Pydantic)

### MedicationCreate (enhanced)
```python
class MedicationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    drug_catalog_id: str | None = None
    generic_name: str | None = Field(None, max_length=255)
    active_ingredient: str | None = Field(None, max_length=255)
    drug_class: str | None = Field(None, max_length=128)
    dose_amount: float | None = Field(None, gt=0)
    dose_unit: str | None = Field(None, max_length=32)
    dose_text: str | None = Field(None, max_length=128)
    route: str | None = Field(None, max_length=64)
    frequency_code: str | None = Field(None, max_length=32)
    frequency: str | None = Field(None, max_length=128)
    timing_instructions: str | None = Field(None, max_length=1024)
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    is_prn: bool = False
    prn_indication: str | None = Field(None, max_length=255)
    indication: str | None = Field(None, max_length=512)
    prescribed_by: str | None = Field(None, max_length=255)
    status: Literal["active", "paused", "completed", "discontinued"] = "active"
    is_supplement: bool = False
    supplement_category: Literal["herbal", "vitamin", "functional_food", "tcm"] | None = None
    note: str | None = Field(None, max_length=1024)
```

### MedicationOut (enhanced)
```python
class MedicationOut(BaseModel):
    id: str
    patient_id: str
    drug_catalog_id: str | None
    name: str
    generic_name: str | None
    active_ingredient: str | None
    drug_class: str | None
    dose_amount: float | None
    dose_unit: str | None
    dose_text: str | None
    route: str | None
    frequency_code: str | None
    frequency: str | None
    timing_instructions: str | None
    start_date: dt.date | None
    end_date: dt.date | None
    is_prn: bool
    prn_indication: str | None
    indication: str | None
    prescribed_by: str | None
    status: str
    is_supplement: bool
    supplement_category: str | None
    supplement_evidence_note: str | None
    note: str | None
    created_at: dt.datetime
    # Derived fields (not stored, computed at read time)
    active_warnings_count: int = 0
    model_config = ConfigDict(from_attributes=True)
```
