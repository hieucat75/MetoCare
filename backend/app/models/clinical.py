"""Clinical data models: HealthMetric, LabDocument, LabResult, SymptomLog,
Medication, RiskScore (Data_Model_Overview §3.1/§3.2).

All are Sensitive health data. `HealthMetric` is designed for time-series and
will become a TimescaleDB hypertable via migration (P1); the model stays
portable so it also runs on SQLite in dev/test.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedJSON, EncryptedString
from app.core.database import Base

from ._mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey

# JSONB on Postgres (matches migration p0_m01), plain JSON on SQLite tests.
_JSON_VARIANT = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")


class HealthMetric(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "health_metrics"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    metric_type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(64))
    measured_at: Mapped[dt.datetime] = mapped_column(index=True, nullable=False)
    source: Mapped[str | None] = mapped_column(String(48))  # self_report | lab_result | …
    # Originating record id when source != self_report (e.g. the lab_result id).
    # Lets lab→metric promotion stay idempotent + traceable.
    source_ref: Mapped[str | None] = mapped_column(String(64), index=True)
    device_id: Mapped[str | None] = mapped_column(String(64))
    # P0 clinical-integrity: preserve the ORIGINAL value+unit as recorded/entered
    # (e.g. 88 µmol/L). `value`/`unit` above hold the CANONICAL/SI-converted number
    # used only for internal classification + trends; original_* is what every
    # user/AI-facing surface must display. NULL for legacy rows (backfilled).
    original_value: Mapped[float | None] = mapped_column(Float)
    original_unit: Mapped[str | None] = mapped_column(String(64))
    normal_range_min: Mapped[float | None] = mapped_column(Float)
    normal_range_max: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(String(16))  # normal/low/high/critical
    # Confirmed source-report reference range text, carried over from the
    # promoting LabResult (original_reference_range or reference_range) so
    # MetricOut can resolve the same SOURCE_REPORT provenance LabResultOut
    # does for the same confirmed result. NULL for rows with no printed range
    # and for legacy rows promoted before this field existed — those fall
    # back to CANONICAL_FALLBACK in resolve_lab_semantics, same as today.
    source_reference_text: Mapped[str | None] = mapped_column(String(128))


class LabUploadBatch(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    """One logical upload session: a patient's lab report from one visit.

    Groups all LabResults created in a single save call. Enables batch delete
    (remove report + cascade to metrics) and duplicate detection (same test_date
    + lab_name or overlapping biomarkers).
    """

    __tablename__ = "lab_upload_batches"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    source_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("lab_documents.id"), nullable=True
    )
    lab_name: Mapped[str | None] = mapped_column(String(255))
    test_date: Mapped[dt.date | None] = mapped_column(Date)
    # SHA-256 hex of raw file bytes for exact duplicate detection.
    file_hash: Mapped[str | None] = mapped_column(String(64))
    delete_reason: Mapped[str | None] = mapped_column(String(512))


class LabDocument(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "lab_documents"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    # Only a reference to object storage + metadata; the binary never lives in DB.
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(32))
    lab_name: Mapped[str | None] = mapped_column(String(255))
    # PHI: raw OCR-extracted text encrypted at rest. Nullable (OCR may not
    # have run yet) — a failed decrypt falls back to None rather than raising.
    raw_text: Mapped[str | None] = mapped_column(EncryptedString(on_decrypt_failure="none"))
    ocr_status: Mapped[str] = mapped_column(String(24), default="pending")  # pending/done/failed
    # Async pipeline state machine (P2 #3): uploaded -> ocr_pending ->
    # ocr_done|ocr_failed -> interpreted|interpretation_failed.
    status: Mapped[str] = mapped_column(String(32), default="uploaded", server_default="uploaded")
    data_classification: Mapped[str] = mapped_column(String(32), default="sensitive_health")


class LabResult(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "lab_results"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    document_id: Mapped[str | None] = mapped_column(ForeignKey("lab_documents.id"), index=True)
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("lab_upload_batches.id"), index=True, nullable=True
    )
    test_name: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_name: Mapped[str | None] = mapped_column(String(64), index=True)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(64))
    reference_range: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(16))
    test_date: Mapped[dt.date | None]
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    verified_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by_doctor: Mapped[bool] = mapped_column(Boolean, default=False)
    # OCR originals — as printed on the patient's lab report.
    original_value: Mapped[float | None] = mapped_column(Float)
    original_unit: Mapped[str | None] = mapped_column(String(64))
    original_reference_range: Mapped[str | None] = mapped_column(String(128))
    original_test_name: Mapped[str | None] = mapped_column(String(128))
    # Intelligence Engine provenance fields (t6_m1_lieng migration)
    source_type: Mapped[str] = mapped_column(
        String(32), default="manual_entry", server_default="manual_entry"
    )
    correction_history_json: Mapped[str | None] = mapped_column(Text)  # JSON array, append-only
    normalized_value_si: Mapped[float | None] = mapped_column(Float)  # SI-normalized for perf
    normalized_unit_si: Mapped[str | None] = mapped_column(String(64))  # SI unit string
    # Data quality / plausibility guardrail fields (t7_m1_dquality migration)
    data_quality_flag: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # "save" | "flag"
    data_quality_note: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # human-readable reason


class SymptomLog(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "symptom_logs"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[int | None] = mapped_column(Integer)  # 0-10 self-reported
    reported_at: Mapped[dt.datetime] = mapped_column(nullable=False)


class Medication(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "medications"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    # Record-only. AI must NEVER modify dose (enforced in guardrails/domain).
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dose: Mapped[str | None] = mapped_column(String(128))
    # PR-D: human-readable schedule, e.g. "2 lần/ngày", "sáng & tối".
    frequency: Mapped[str | None] = mapped_column(String(128))
    note: Mapped[str | None] = mapped_column(Text)

    # P0 lifecycle fields (migration p0_m01). Value sets are enforced by DB
    # CHECK constraints on Postgres; ORM mirrors the server defaults so
    # SQLite test databases behave identically.
    lifecycle_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default=text("'active'")
    )
    verification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="patient_reported",
        server_default=text("'patient_reported'"),
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="patient_manual",
        server_default=text("'patient_manual'"),
    )
    # FK to medication_category_codes(code) exists at DB level (Postgres).
    medication_category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="conventional_drug",
        server_default=text("'conventional_drug'"),
    )
    status_reason: Mapped[str | None] = mapped_column(Text)
    # FK to drug_products deferred until the P1 catalog table exists.
    drug_product_id: Mapped[str | None] = mapped_column(String(36))
    generic_name: Mapped[str | None] = mapped_column(String(255))


class MedicationStatement(UUIDPrimaryKey, Base):
    """Raw source assertion about a medication (ADR-04, migration M-03).

    Every create/edit of a canonical ``medications`` row MUST originate from a
    statement — no write path may bypass this table (P0 invariant).
    ``created_at`` only: the table is append-mostly and has no updated_at.
    """

    __tablename__ = "medication_statements"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(255))
    assertion_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="new_entry", server_default=text("'new_entry'")
    )
    related_medication_id: Mapped[str | None] = mapped_column(ForeignKey("medications.id"))
    # A drug name IS PHI: it discloses the condition being treated (an
    # antiretroviral, an antipsychotic, an oncology agent) more directly than most
    # diagnosis fields. These are the verbatim OCR strings off a prescription,
    # with the prescriber's name alongside. None is queried by value.
    # NOT NULL, so "raise" per EncryptedString's contract: a silent None here
    # would break the NOT NULL guarantee and crash response serialization, and a
    # medication statement with no drug name is not a degraded row — it is a
    # meaningless one.
    raw_drug_name: Mapped[str] = mapped_column(
        EncryptedString(on_decrypt_failure="raise"), nullable=False
    )
    normalized_name: Mapped[str | None] = mapped_column(
        EncryptedString(on_decrypt_failure="none")
    )
    drug_product_id: Mapped[str | None] = mapped_column(String(36))
    match_confidence: Mapped[float | None] = mapped_column(Float)
    raw_dose: Mapped[str | None] = mapped_column(EncryptedString(on_decrypt_failure="none"))
    raw_frequency: Mapped[str | None] = mapped_column(
        EncryptedString(on_decrypt_failure="none")
    )
    raw_prescriber: Mapped[str | None] = mapped_column(
        EncryptedString(on_decrypt_failure="none")
    )
    raw_date: Mapped[dt.date | None] = mapped_column(Date)
    effective_from: Mapped[dt.date | None] = mapped_column(Date)
    # The whole extracted prescription payload — a superset of the raw_* columns
    # above, so encrypting those and not this would leave the same data readable.
    payload_snapshot: Mapped[dict | None] = mapped_column(
        EncryptedJSON(on_decrypt_failure="none")
    )
    statement_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default=text("'pending'")
    )
    merged_into_medication_id: Mapped[str | None] = mapped_column(ForeignKey("medications.id"))
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(36))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )


class MedicationAuditLog(UUIDPrimaryKey, Base):
    """Unified medication audit trail (migration M-02, gate T-04).

    State changes carry ``before_snapshot``/``after_snapshot``; pure
    observational events (e.g. patient_reported_non_adherence) keep both NULL.
    Append-only — rows are never updated.
    """

    __tablename__ = "medication_audit_log"

    medication_id: Mapped[str] = mapped_column(
        ForeignKey("medications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    field_changed: Mapped[str | None] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(String(255))
    new_value: Mapped[str | None] = mapped_column(String(255))
    transition_reason: Mapped[str | None] = mapped_column(Text)
    event_data: Mapped[dict | None] = mapped_column(_JSON_VARIANT)
    before_snapshot: Mapped[dict | None] = mapped_column(_JSON_VARIANT)
    after_snapshot: Mapped[dict | None] = mapped_column(_JSON_VARIANT)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36))
    created_by_role: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )


class MedicationAdherence(UUIDPrimaryKey, TimestampMixin, Base):
    """One adherence record per dose event.

    A record is created when the patient marks a dose taken or skipped.
    ``scheduled_time`` is optional (patients without a fixed schedule can still
    log doses as free-form events). ``taken_at`` is null for skipped records.
    """

    __tablename__ = "medication_adherence"

    medication_id: Mapped[str] = mapped_column(
        ForeignKey("medications.id"), index=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    scheduled_time: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    taken_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class RiskScore(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "risk_scores"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    metabolic_score: Mapped[int] = mapped_column(Integer, nullable=False)
    band: Mapped[str] = mapped_column(String(24), nullable=False)
    top_risks: Mapped[str | None] = mapped_column(Text)  # serialized factors
