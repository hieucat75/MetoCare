"""t10_m1: Doctor Marketplace — consultation bounded context + doctor listing fields

Creates the 5 consultation-context tables and extends the ``doctors`` table with
marketplace listing columns (SQLite-compatible via batch_alter_table).

NOTE: the plan specified down_revision="t9_m2_drug_seed", but the repository head
advanced since the plan was written (meto tables + terms consents chained off
t9_m2_drug_seed). To keep a single linear head and let ``alembic upgrade head``
apply cleanly, this migration chains off the real current head
``a1_terms_consents``. Tests build schema from model metadata (create_all), so the
revision id does not affect them.

Revision ID: t10_m1_consultation_marketplace
Revises: a1_terms_consents
Create Date: 2026-07-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t10_m1_consultation_marketplace"
down_revision: str | None = "a1_terms_consents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. consultations                                                   #
    # ------------------------------------------------------------------ #
    op.create_table(
        "consultations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("patient_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "doctor_id",
            sa.String(36),
            sa.ForeignKey("doctors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consultation_type", sa.String(16), nullable=False, server_default="CHAT"),
        sa.Column("status", sa.String(24), nullable=False, server_default="REQUESTED"),
        sa.Column("consultation_price", sa.Float, nullable=False, server_default="0"),
        sa.Column(
            "data_consent_accepted", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("data_consent_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chief_complaint", sa.Text, nullable=True),
        sa.Column("patient_note", sa.Text, nullable=True),
        sa.Column(
            "booking_appointment_id",
            sa.String(36),
            sa.ForeignKey("booking_appointments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
    )
    op.create_index("ix_consultations_patient_id", "consultations", ["patient_id"])
    op.create_index("ix_consultations_doctor_id", "consultations", ["doctor_id"])
    op.create_index(
        "ix_consultations_booking_appointment_id", "consultations", ["booking_appointment_id"]
    )

    # ------------------------------------------------------------------ #
    # 2. consultation_payments                                           #
    # ------------------------------------------------------------------ #
    op.create_table(
        "consultation_payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "consultation_id",
            sa.String(36),
            sa.ForeignKey("consultations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("consultation_price", sa.Float, nullable=False, server_default="0"),
        sa.Column("platform_fee", sa.Float, nullable=False, server_default="0"),
        sa.Column("doctor_payout", sa.Float, nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="VND"),
        sa.Column("payment_status", sa.String(16), nullable=False, server_default="UNPAID"),
        sa.Column("payment_provider", sa.String(24), nullable=False, server_default="MOCK"),
        sa.Column("provider_ref", sa.String(128), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
    )
    op.create_index(
        "ix_consultation_payments_consultation_id",
        "consultation_payments",
        ["consultation_id"],
    )

    # ------------------------------------------------------------------ #
    # 3. consultation_notes (append-only)                                #
    # ------------------------------------------------------------------ #
    op.create_table(
        "consultation_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "consultation_id",
            sa.String(36),
            sa.ForeignKey("consultations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "doctor_id",
            sa.String(36),
            sa.ForeignKey("doctors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),  # EncryptedString → TEXT ciphertext
        sa.Column("note_type", sa.String(32), nullable=False, server_default="recommendation"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
    )
    op.create_index(
        "ix_consultation_notes_consultation_id", "consultation_notes", ["consultation_id"]
    )
    op.create_index("ix_consultation_notes_doctor_id", "consultation_notes", ["doctor_id"])

    # ------------------------------------------------------------------ #
    # 4. consultation_reviews                                            #
    # ------------------------------------------------------------------ #
    op.create_table(
        "consultation_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "consultation_id",
            sa.String(36),
            sa.ForeignKey("consultations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("patient_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "doctor_id",
            sa.String(36),
            sa.ForeignKey("doctors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("feedback", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
    )
    op.create_index(
        "ix_consultation_reviews_consultation_id", "consultation_reviews", ["consultation_id"]
    )
    op.create_index("ix_consultation_reviews_patient_id", "consultation_reviews", ["patient_id"])
    op.create_index("ix_consultation_reviews_doctor_id", "consultation_reviews", ["doctor_id"])

    # ------------------------------------------------------------------ #
    # 5. consultation_access_grants                                      #
    # ------------------------------------------------------------------ #
    op.create_table(
        "consultation_access_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "consultation_id",
            sa.String(36),
            sa.ForeignKey("consultations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "doctor_id",
            sa.String(36),
            sa.ForeignKey("doctors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("patient_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
    )
    op.create_index(
        "ix_consultation_access_grants_consultation_id",
        "consultation_access_grants",
        ["consultation_id"],
    )
    op.create_index(
        "ix_consultation_access_grants_doctor_id", "consultation_access_grants", ["doctor_id"]
    )
    op.create_index(
        "ix_consultation_access_grants_patient_id", "consultation_access_grants", ["patient_id"]
    )

    # ------------------------------------------------------------------ #
    # 6. doctors — marketplace listing columns (SQLite-compatible)       #
    # ------------------------------------------------------------------ #
    with op.batch_alter_table("doctors") as batch:
        batch.add_column(
            sa.Column(
                "verification_status",
                sa.String(32),
                nullable=False,
                server_default="PENDING_VERIFICATION",
            )
        )
        batch.add_column(sa.Column("years_experience", sa.Integer, nullable=True))
        batch.add_column(sa.Column("languages", sa.String(255), nullable=True))
        batch.add_column(sa.Column("hospital_name", sa.String(255), nullable=True))
        batch.add_column(sa.Column("consultation_methods", sa.String(255), nullable=True))
        batch.add_column(
            sa.Column("rating_avg", sa.Float, nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("rating_count", sa.Integer, nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("doctors") as batch:
        batch.drop_column("rating_count")
        batch.drop_column("rating_avg")
        batch.drop_column("consultation_methods")
        batch.drop_column("hospital_name")
        batch.drop_column("languages")
        batch.drop_column("years_experience")
        batch.drop_column("verification_status")

    op.drop_table("consultation_access_grants")
    op.drop_table("consultation_reviews")
    op.drop_table("consultation_notes")
    op.drop_table("consultation_payments")
    op.drop_table("consultations")
