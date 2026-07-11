"""P0-M01: Add lifecycle, verification and category fields to medications.

Also creates the medication_category_codes lookup table (M-01b),
medication_audit_log (M-02), medication_statements (M-03), and
drug_product_id / generic_name on medications (M-04).

All migrations are bundled in a single file as they form one atomic unit of
the P0 foundation — they must all succeed or all roll back together.

Revision ID: p0_m01_med_lifecycle
Revises: c0_m9_audit_log_clinic_id
Create Date: 2026-07-11

Design notes:
  - M-01: Adds 5 new columns to medications. NOT NULL columns use safe defaults
    so no row scan is required by Postgres (catalog-level default).
  - Soft-delete mapping: rows with deleted_at IS NOT NULL get
    lifecycle_status='entered_in_error' via targeted UPDATE (PTH decision
    2026-07-11, MEDICATION_P0_PRE_VALIDATION.md §RISK-3).
  - is_supplement block: REMOVED — column does not exist in current schema.
    Adding it would cause a migration failure (PTH decision confirmed by
    MEDICATION_SOFT_DELETE_AUDIT.md).
  - M-01b: Creates medication_category_codes lookup table with 2 P0 seed rows.
  - M-02: Creates medication_audit_log (unified event + snapshot table).
  - M-03: Creates medication_statements (raw source assertions, Q-OQ-1 fields).
  - M-04: Adds drug_product_id (nullable FK placeholder) and generic_name.

Rollback: Reverse order — M-04 → M-03 → M-02 → M-01b → M-01.
  DROP COLUMN / DROP TABLE safe because no app code has been deployed yet
  that writes to these new columns/tables.

IMPORTANT: Do NOT run this migration against staging or production until:
  - MEDICATION_P0_BLOCKER_REPORT.md shows READY FOR STAGING
  - Pre-migration backup gate in CI has run and verified backup Succeeded
  - PTH has approved this file after Codex read-only review
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "p0_m01_med_lifecycle"
down_revision: str | None = "c0_m9_audit_log_clinic_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # M-01b FIRST: create medication_category_codes lookup table so the FK
    # on medications.medication_category can be added in the same transaction.
    # -----------------------------------------------------------------------
    op.create_table(
        "medication_category_codes",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("label_vi", sa.String(128), nullable=False),
        sa.Column("label_en", sa.String(128), nullable=False),
        sa.Column(
            "interaction_risk_level",
            sa.String(16),
            nullable=True,
            comment="high | medium | low | unknown — used by CDS at P3",
        ),
        sa.Column(
            "requires_clinician_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            # SQLite does not have now(); use CURRENT_TIMESTAMP which both dialects support.
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("code"),
    )

    # Seed P0 values — only 2 categories needed for P0 (full taxonomy at Gate 3 / ADR-06)
    # ON CONFLICT is Postgres-only; use dialect-aware insert instead.
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.execute(
            sa.text(
                """
                INSERT INTO medication_category_codes
                    (code, label_vi, label_en, interaction_risk_level,
                     requires_clinician_review, display_order)
                VALUES
                    ('conventional_drug', 'Thuốc điều trị', 'Conventional Drug',
                     'high', false, 1),
                    ('supplement', 'Thực phẩm bổ sung', 'Supplement / OTC',
                     'low', false, 2)
                ON CONFLICT (code) DO NOTHING;
                """
            )
        )
    else:
        # SQLite: simple INSERT OR IGNORE
        op.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO medication_category_codes
                    (code, label_vi, label_en, interaction_risk_level,
                     requires_clinician_review, display_order)
                VALUES
                    ('conventional_drug', 'Thuoc dieu tri', 'Conventional Drug',
                     'high', 0, 1),
                    ('supplement', 'Thuc pham bo sung', 'Supplement / OTC',
                     'low', 0, 2);
                """
            )
        )

    # -----------------------------------------------------------------------
    # M-01: Add 5 new columns to medications.
    #
    # Strategy for NOT NULL columns with defaults:
    #   Postgres ≥ 11: ADD COLUMN NOT NULL DEFAULT <val> is a catalog-only
    #   operation — zero row scan. Safe for any table size.
    #
    # Soft-delete mapping (PTH decision 2026-07-11):
    #   After ADD COLUMN sets all rows to 'active' via default, immediately
    #   UPDATE rows with deleted_at IS NOT NULL to 'entered_in_error'.
    #   This targeted UPDATE only touches soft-deleted rows.
    # -----------------------------------------------------------------------
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        # SQLite does not support multiple ADD COLUMN in one ALTER TABLE,
        # and does not support CHECK constraints in the same way. Use batch
        # mode (already configured in env.py for SQLite).
        with op.batch_alter_table("medications", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "lifecycle_status",
                    sa.String(32),
                    nullable=False,
                    server_default=sa.text("'active'"),
                )
            )
            batch_op.add_column(
                sa.Column(
                    "verification_status",
                    sa.String(32),
                    nullable=False,
                    server_default=sa.text("'patient_reported'"),
                )
            )
            batch_op.add_column(
                sa.Column(
                    "source_type",
                    sa.String(32),
                    nullable=False,
                    server_default=sa.text("'patient_manual'"),
                )
            )
            batch_op.add_column(
                sa.Column(
                    "medication_category",
                    sa.String(64),
                    nullable=False,
                    server_default=sa.text("'conventional_drug'"),
                )
            )
            batch_op.add_column(
                sa.Column("status_reason", sa.Text(), nullable=True)
            )
            # SQLite: skip CHECK constraints and FK (not enforced at DB level)
    else:
        # PostgreSQL — add all 5 columns atomically
        op.execute(
            sa.text(
                """
                ALTER TABLE medications
                  ADD COLUMN IF NOT EXISTS lifecycle_status
                      VARCHAR(32) NOT NULL DEFAULT 'active',
                  ADD COLUMN IF NOT EXISTS verification_status
                      VARCHAR(32) NOT NULL DEFAULT 'patient_reported',
                  ADD COLUMN IF NOT EXISTS source_type
                      VARCHAR(32) NOT NULL DEFAULT 'patient_manual',
                  ADD COLUMN IF NOT EXISTS medication_category
                      VARCHAR(64) NOT NULL DEFAULT 'conventional_drug',
                  ADD COLUMN IF NOT EXISTS status_reason
                      TEXT NULL;
                """
            )
        )

        # Soft-delete mapping: set entered_in_error for all soft-deleted rows.
        # Runs immediately after ADD COLUMN so no SELECT ever sees an incorrect value.
        op.execute(
            sa.text(
                """
                UPDATE medications
                SET lifecycle_status = 'entered_in_error'
                WHERE deleted_at IS NOT NULL;
                """
            )
        )

        # CHECK constraints — closed value sets enforced at DB level
        op.execute(
            sa.text(
                """
                ALTER TABLE medications
                  ADD CONSTRAINT chk_lifecycle_status CHECK (
                    lifecycle_status IN (
                      'active','paused','on_hold','completed',
                      'discontinued','expired','entered_in_error'
                    )
                  );
                """
            )
        )
        op.execute(
            sa.text(
                """
                ALTER TABLE medications
                  ADD CONSTRAINT chk_verification_status CHECK (
                    verification_status IN (
                      'patient_reported','clinician_confirmed',
                      'ocr_extracted','system_inferred'
                    )
                  );
                """
            )
        )
        op.execute(
            sa.text(
                """
                ALTER TABLE medications
                  ADD CONSTRAINT chk_source_type CHECK (
                    source_type IN (
                      'patient_manual','doctor_prescribed','ocr_confirmed',
                      'pharmacy_import','fhir_import','entered_in_error'
                    )
                  );
                """
            )
        )

        # FK: medication_category → medication_category_codes(code)
        # Enforces that only seeded/valid categories can be used.
        op.execute(
            sa.text(
                """
                ALTER TABLE medications
                  ADD CONSTRAINT fk_medication_category
                    FOREIGN KEY (medication_category)
                    REFERENCES medication_category_codes(code);
                """
            )
        )

        # NOTE: is_supplement migration block intentionally omitted.
        # Column does not exist in current schema (confirmed 2026-07-11).
        # Adding it would cause: ERROR: column "is_supplement" does not exist.

    # -----------------------------------------------------------------------
    # M-02: Create medication_audit_log
    # Unified table: business events + technical before/after snapshots.
    # JSONB columns: use postgresql.JSONB on Postgres, JSON on SQLite.
    # -----------------------------------------------------------------------
    jsonb_type = postgresql.JSONB(astext_type=sa.Text()) if not is_sqlite else sa.JSON()

    op.create_table(
        "medication_audit_log",
        sa.Column(
            "id",
            sa.String(36),
            nullable=False,
            server_default=sa.text("gen_random_uuid()") if not is_sqlite else None,
        ),
        sa.Column("medication_id", sa.String(36), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        # Business event fields
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("field_changed", sa.String(64), nullable=True),
        sa.Column("old_value", sa.String(255), nullable=True),
        sa.Column("new_value", sa.String(255), nullable=True),
        sa.Column("transition_reason", sa.Text(), nullable=True),
        sa.Column("event_data", jsonb_type, nullable=True),
        # Technical audit snapshots
        sa.Column("before_snapshot", jsonb_type, nullable=True),
        sa.Column("after_snapshot", jsonb_type, nullable=True),
        # Actor
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_by_role", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["medication_id"],
            ["medications.id"],
            name="fk_medaudit_medication_id",
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "idx_medaudit_medication_id",
        "medication_audit_log",
        ["medication_id"],
    )
    op.create_index(
        "idx_medaudit_patient_id",
        "medication_audit_log",
        ["patient_id"],
    )
    op.create_index(
        "idx_medaudit_event_type",
        "medication_audit_log",
        ["event_type"],
    )
    op.create_index(
        "idx_medaudit_created_at",
        "medication_audit_log",
        ["created_at"],
        postgresql_ops={"created_at": "DESC"} if not is_sqlite else {},
    )
    if not is_sqlite:
        # Partial index for state-change events (only Postgres supports WHERE on index)
        op.execute(
            sa.text(
                """
                CREATE INDEX idx_medaudit_state_changes
                    ON medication_audit_log(medication_id, created_at DESC)
                    WHERE before_snapshot IS NOT NULL;
                """
            )
        )

    # -----------------------------------------------------------------------
    # M-03: Create medication_statements
    # Raw source assertions + Q-OQ-1 expired re-review fields.
    # -----------------------------------------------------------------------
    op.create_table(
        "medication_statements",
        sa.Column(
            "id",
            sa.String(36),
            nullable=False,
            server_default=sa.text("gen_random_uuid()") if not is_sqlite else None,
        ),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(255), nullable=True),
        # Q-OQ-1: assertion type for expired re-review routing
        sa.Column(
            "assertion_type",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'new_entry'"),
        ),
        # FK to prior canonical record (required for assertion_type='continued_use')
        sa.Column("related_medication_id", sa.String(36), nullable=True),
        # Raw statement fields
        sa.Column("raw_drug_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=True),
        sa.Column("drug_product_id", sa.String(36), nullable=True),
        sa.Column("match_confidence", sa.Float(), nullable=True),
        sa.Column("raw_dose", sa.Text(), nullable=True),
        sa.Column("raw_frequency", sa.Text(), nullable=True),
        sa.Column("raw_prescriber", sa.Text(), nullable=True),
        sa.Column("raw_date", sa.Date(), nullable=True),
        # Temporal fields for continued_use flow (Q-OQ-1)
        sa.Column("effective_from", sa.Date(), nullable=True),
        # Snapshot of related medication at time of assertion
        sa.Column("payload_snapshot", jsonb_type, nullable=True),
        # Status
        sa.Column(
            "statement_status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("merged_into_medication_id", sa.String(36), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patient_profiles.id"],
            name="fk_medstmt_patient_id",
        ),
        sa.ForeignKeyConstraint(
            ["related_medication_id"],
            ["medications.id"],
            name="fk_medstmt_related_medication_id",
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_medication_id"],
            ["medications.id"],
            name="fk_medstmt_merged_into_medication_id",
        ),
    )

    op.create_index(
        "idx_medstmt_patient_id",
        "medication_statements",
        ["patient_id"],
    )
    op.create_index(
        "idx_medstmt_status",
        "medication_statements",
        ["statement_status"],
    )
    op.create_index(
        "idx_medstmt_source_type",
        "medication_statements",
        ["source_type"],
    )
    op.create_index(
        "idx_medstmt_assertion_type",
        "medication_statements",
        ["assertion_type"],
    )
    op.create_index(
        "idx_medstmt_created_at",
        "medication_statements",
        ["created_at"],
        postgresql_ops={"created_at": "DESC"} if not is_sqlite else {},
    )
    if not is_sqlite:
        # Partial index for continued_use assertions (FK lookups)
        op.execute(
            sa.text(
                """
                CREATE INDEX idx_medstmt_related_medication
                    ON medication_statements(related_medication_id)
                    WHERE related_medication_id IS NOT NULL;
                """
            )
        )

    # -----------------------------------------------------------------------
    # M-04: Add drug_product_id and generic_name to medications.
    # Both nullable — FK to drug_products deferred until catalog table at P1.
    # -----------------------------------------------------------------------
    if is_sqlite:
        with op.batch_alter_table("medications", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("drug_product_id", sa.String(36), nullable=True)
            )
            batch_op.add_column(
                sa.Column("generic_name", sa.String(255), nullable=True)
            )
    else:
        op.execute(
            sa.text(
                """
                ALTER TABLE medications
                  ADD COLUMN IF NOT EXISTS drug_product_id VARCHAR(36)  NULL,
                  ADD COLUMN IF NOT EXISTS generic_name    VARCHAR(255) NULL;
                """
            )
        )


def downgrade() -> None:
    """Rollback sequence: M-04 → M-03 → M-02 → M-01 → M-01b (reverse of upgrade).

    Safe to run only when no application code using the new columns/tables
    has been deployed. Destructive for any data written to new tables.
    """
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # -----------------------------------------------------------------------
    # Rollback M-04: remove drug_product_id and generic_name from medications
    # -----------------------------------------------------------------------
    if is_sqlite:
        with op.batch_alter_table("medications", schema=None) as batch_op:
            batch_op.drop_column("generic_name")
            batch_op.drop_column("drug_product_id")
    else:
        op.execute(
            sa.text(
                """
                ALTER TABLE medications
                  DROP COLUMN IF EXISTS drug_product_id,
                  DROP COLUMN IF EXISTS generic_name;
                """
            )
        )

    # -----------------------------------------------------------------------
    # Rollback M-03: drop medication_statements
    # -----------------------------------------------------------------------
    op.drop_index("idx_medstmt_created_at", table_name="medication_statements")
    op.drop_index("idx_medstmt_assertion_type", table_name="medication_statements")
    op.drop_index("idx_medstmt_source_type", table_name="medication_statements")
    op.drop_index("idx_medstmt_status", table_name="medication_statements")
    op.drop_index("idx_medstmt_patient_id", table_name="medication_statements")
    if not is_sqlite:
        op.execute(
            sa.text(
                "DROP INDEX IF EXISTS idx_medstmt_related_medication;"
            )
        )
    op.drop_table("medication_statements")

    # -----------------------------------------------------------------------
    # Rollback M-02: drop medication_audit_log
    # -----------------------------------------------------------------------
    if not is_sqlite:
        op.execute(
            sa.text(
                "DROP INDEX IF EXISTS idx_medaudit_state_changes;"
            )
        )
    op.drop_index("idx_medaudit_created_at", table_name="medication_audit_log")
    op.drop_index("idx_medaudit_event_type", table_name="medication_audit_log")
    op.drop_index("idx_medaudit_patient_id", table_name="medication_audit_log")
    op.drop_index("idx_medaudit_medication_id", table_name="medication_audit_log")
    op.drop_table("medication_audit_log")

    # -----------------------------------------------------------------------
    # Rollback M-01: remove 5 new columns from medications
    # -----------------------------------------------------------------------
    if is_sqlite:
        with op.batch_alter_table("medications", schema=None) as batch_op:
            batch_op.drop_column("status_reason")
            batch_op.drop_column("medication_category")
            batch_op.drop_column("source_type")
            batch_op.drop_column("verification_status")
            batch_op.drop_column("lifecycle_status")
    else:
        # Drop FK and CHECK constraints before dropping columns
        op.execute(
            sa.text(
                """
                ALTER TABLE medications
                  DROP CONSTRAINT IF EXISTS fk_medication_category,
                  DROP CONSTRAINT IF EXISTS chk_source_type,
                  DROP CONSTRAINT IF EXISTS chk_verification_status,
                  DROP CONSTRAINT IF EXISTS chk_lifecycle_status;
                """
            )
        )
        op.execute(
            sa.text(
                """
                ALTER TABLE medications
                  DROP COLUMN IF EXISTS status_reason,
                  DROP COLUMN IF EXISTS medication_category,
                  DROP COLUMN IF EXISTS source_type,
                  DROP COLUMN IF EXISTS verification_status,
                  DROP COLUMN IF EXISTS lifecycle_status;
                """
            )
        )

    # -----------------------------------------------------------------------
    # Rollback M-01b: drop medication_category_codes lookup table
    # -----------------------------------------------------------------------
    op.drop_table("medication_category_codes")
