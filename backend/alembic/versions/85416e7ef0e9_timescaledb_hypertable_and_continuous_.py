"""timescaledb hypertable and continuous aggregate for health_metrics

Revision ID: 85416e7ef0e9
Revises: 2c30ffd33627
Create Date: 2026-06-12 20:43:10.381099

PostgreSQL/TimescaleDB ONLY. On any other backend (e.g. SQLite used for dev/test)
this migration is a deliberate no-op so the same migration chain runs everywhere.

TimescaleDB requires the time partitioning column to be part of every unique
index, so the primary key of `health_metrics` is widened to (id, measured_at)
before `create_hypertable`. The ORM still maps `id` as the logical key (UUID,
globally unique); the composite PK is a physical, backend-specific detail.

A single daily continuous aggregate (`health_metric_daily`) is created; the
7/30/90/365-day trends are served by querying date ranges over that aggregate —
the idiomatic TimescaleDB pattern (one fine-grained CAGG, many query windows)
rather than four separate materialized views.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "85416e7ef0e9"
down_revision: str | None = "2c30ffd33627"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CAGG_NAME = "health_metric_daily"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return  # hypertable / CAGG are TimescaleDB features; skip on SQLite et al.

    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # Widen PK to include the partitioning column (TimescaleDB requirement).
    op.execute("ALTER TABLE health_metrics DROP CONSTRAINT IF EXISTS health_metrics_pkey")
    op.execute("ALTER TABLE health_metrics ADD PRIMARY KEY (id, measured_at)")

    # Convert to a hypertable partitioned by measured_at, migrating existing rows.
    op.execute(
        "SELECT create_hypertable('health_metrics', 'measured_at', "
        "migrate_data => true, if_not_exists => true)"
    )

    # Daily continuous aggregate (avg/min/max/count per patient+metric+day).
    op.execute(
        f"""
        CREATE MATERIALIZED VIEW IF NOT EXISTS {CAGG_NAME}
        WITH (timescaledb.continuous) AS
        SELECT patient_id,
               metric_type,
               time_bucket('1 day', measured_at) AS bucket,
               avg(value)   AS avg_value,
               min(value)   AS min_value,
               max(value)   AS max_value,
               count(*)     AS sample_count
        FROM health_metrics
        GROUP BY patient_id, metric_type, bucket
        WITH NO DATA
        """
    )

    # Keep the aggregate fresh; covers windows up to 1 year.
    op.execute(
        f"""
        SELECT add_continuous_aggregate_policy('{CAGG_NAME}',
            start_offset => INTERVAL '370 days',
            end_offset   => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour',
            if_not_exists => true)
        """
    )

    # Compression + retention for raw rows (time-series hygiene).
    op.execute(
        "ALTER TABLE health_metrics SET ("
        "timescaledb.compress, "
        "timescaledb.compress_segmentby = 'patient_id, metric_type')"
    )
    op.execute(
        "SELECT add_compression_policy('health_metrics', INTERVAL '90 days', if_not_exists => true)"
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {CAGG_NAME}")
    # Drop policies are removed automatically with the objects; reset compression.
    op.execute("SELECT remove_compression_policy('health_metrics', if_exists => true)")
    # NOTE: a table cannot be un-hypertabled in place; for a full rollback restore
    # from migration 2c30ffd33627. We at least restore the original primary key.
    op.execute("ALTER TABLE health_metrics DROP CONSTRAINT IF EXISTS health_metrics_pkey")
    op.execute("ALTER TABLE health_metrics ADD PRIMARY KEY (id)")
