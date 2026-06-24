"""Clinical data models: HealthMetric, LabDocument, LabResult, SymptomLog,
Medication, RiskScore (Data_Model_Overview §3.1/§3.2).

All are Sensitive health data. `HealthMetric` is designed for time-series and
will become a TimescaleDB hypertable via migration (P1); the model stays
portable so it also runs on SQLite in dev/test.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedString
from app.core.database import Base

from ._mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class HealthMetric(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "health_metrics"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    metric_type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(24))
    measured_at: Mapped[dt.datetime] = mapped_column(index=True, nullable=False)
    source: Mapped[str | None] = mapped_column(String(48))  # self_report | lab_result | …
    # Originating record id when source != self_report (e.g. the lab_result id).
    # Lets lab→metric promotion stay idempotent + traceable.
    source_ref: Mapped[str | None] = mapped_column(String(64), index=True)
    device_id: Mapped[str | None] = mapped_column(String(64))
    normal_range_min: Mapped[float | None] = mapped_column(Float)
    normal_range_max: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(String(16))  # normal/low/high/critical


class LabDocument(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "lab_documents"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    # Only a reference to object storage + metadata; the binary never lives in DB.
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(32))
    lab_name: Mapped[str | None] = mapped_column(String(255))
    # PHI: raw OCR-extracted text encrypted at rest.
    raw_text: Mapped[str | None] = mapped_column(EncryptedString)
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
    test_name: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_name: Mapped[str | None] = mapped_column(String(64), index=True)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(24))
    reference_range: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(16))
    test_date: Mapped[dt.date | None]
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    verified_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by_doctor: Mapped[bool] = mapped_column(Boolean, default=False)


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
    taken_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
