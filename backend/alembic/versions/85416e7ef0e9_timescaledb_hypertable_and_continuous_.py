"""timescaledb hypertable and continuous aggregate for health_metrics

Revision ID: 85416e7ef0e9
Revises: 2c30ffd33627
Create Date: 2026-06-12 20:43:10.381099

PostgreSQL/TimescaleDB ONLY. On any other backend (e.g. SQLite used for dev/test)
this migration is a deliberate no-op so the same migration chain runs everywhere.

On Azure Database for PostgreSQL Flexible Server, TimescaleDB is not in the
allow-list for azure_pg_admin, so CREATE EXTENSION raises FeatureNotSupported.
This migration detects that at runtime and skips gracefully — health_metrics
remains a plain PostgreSQL table.

TimescaleDB requires the time partitioning column to be part of every unique
index, so the primary key of `health_metrics` is widened to (id, measured_at)
before `create_hypertable`. The ORM still maps `id` as the logical key (UUID,
globally unique); the composite PK is a physical, backend-specific detail.

A single daily continuous aggregate (`health_metric_daily`) is created; the
7/30/90/365-day trends are served by querying date ranges over that aggregate —
the idiomatic TimescaleDB pattern (one fine-grained CAGG, many query windows)
rather than four separate materialized views.

License awareness: continuous aggregates and compression are TimescaleDB
*community (TSL)* features. They are unavailable on the *Apache-2* build shipped
by some managed providers (e.g. Azure Database for PostgreSQL Flexible Server),
where calling them raises `functionality not supported under the current
"apache" license`. The hypertable itself is Apache-licensed and always created.
This migration therefore detects the active license and applies CAGG +
compression only on a `timescale` (TSL) build, so the same chain runs on:
  - SQLite / non-Postgres  -> full no-op
  - Apache TimescaleDB     -> hypertable only (CAGG/compression skipped)
  - TSL  TimescaleDB       -> hypertable + CAGG + compression (full)
"""
from __future__ import annotations

import warnings
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "85416e7ef0e9"
down_revision: str | None = "2c30ffd33627"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CAGG_NAME = "health_metric_daily"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _try_create_timescaledb_extension() -> bool:
    """Attempt to CREATE EXTENSION timescaledb.

    Returns True if the extension is now installed, False if the server
    does not support it (e.g. Azure Flexible Server deny-list, Homebrew PG
    without TimescaleDB package).

    Uses a SAVEPOINT so a failure does not abort the surrounding transaction.
    """
    conn = op.get_bind()
    try:
        conn.execute(sa.text("SAVEPOINT _tsdb_check"))
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        conn.execute(sa.text("RELEASE SAVEPOINT _tsdb_check"))
        return True
    except Exception as exc:  # noqa: BLE001
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT _tsdb_check"))
        warnings.warn(
            f"TimescaleDB extension could not be installed ({exc}). "
            "health_metrics will remain a plain PostgreSQL table on this instance. "
            "This is expected on Azure Database for PostgreSQL Flexible Server.",
            RuntimeWarning,
            stacklevel=2,
        )
        return False


def _timescale_license() -> str:
    """Return the active TimescaleDB edition: 'timescale' (TSL), 'apache', or ''.

    `timescaledb.license` is set once the extension is loaded; it reads 'apache'
    on the Apache-2 build (no CAGG/compression) and 'timescale' on the community
    TSL build. Returns '' if the GUC is unavailable (extension not loaded yet).
    """
    try:
        import sqlalchemy as sa

        row = op.get_bind().execute(
            sa.text("SELECT current_setting('timescaledb.license', true)")
        ).fetchone()
        return (row[0] or "").strip() if row else ""
    except Exception:
        return ""


def upgrade() -> None:
    if not _is_postgres():
        return  # hypertable / CAGG are TimescaleDB features; skip on SQLite et al.

    if not _try_create_timescaledb_extension():
        # TimescaleDB not available on this server — skip all hypertable setup.
        # health_metrics stays as a plain table; queries still work, just without
        # time-series partitioning / compression / continuous aggregates.
        return

    # Widen PK to include the partitioning column (TimescaleDB requirement).
    op.execute("ALTER TABLE health_metrics DROP CONSTRAINT IF EXISTS health_metrics_pkey")
    op.execute("ALTER TABLE health_metrics ADD PRIMARY KEY (id, measured_at)")

    # Convert to a hypertable partitioned by measured_at, migrating existing rows.
    # (Apache-licensed — always available.)
    op.execute(
        "SELECT create_hypertable('health_metrics', 'measured_at', "
        "migrate_data => true, if_not_exists => true)"
    )

    # Continuous aggregates + compression are TSL (community) features. On an
    # Apache build (e.g. Azure PG Flexible) they raise; skip them and keep the
    # plain hypertable. Trends are served by querying the hypertable directly.
    if _timescale_license() != "timescale":
        import warnings

        warnings.warn(
            "TimescaleDB Apache license -- skipping continuous aggregate "
            f"'{CAGG_NAME}' and compression policy (TSL-only features). "
            "health_metrics remains a plain hypertable on this instance.",
            RuntimeWarning,
            stacklevel=2,
        )
        return

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

    # CAGG + compression only exist on a TSL build; on Apache they were skipped,
    # and `remove_compression_policy` itself is TSL-only (would raise on Apache).
    # `_timescale_license()` returns '' when the extension is absent or not loaded
    # (current_setting(..., true) -> NULL), so this is False on plain PG too.
    if _timescale_license() == "timescale":
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {CAGG_NAME}")
        # Drop policies are removed automatically with the objects; reset compression.
        op.execute("SELECT remove_compression_policy('health_metrics', if_exists => true)")
    # NOTE: a table cannot be un-hypertabled in place; for a full rollback restore
    # from migration 2c30ffd33627. We at least restore the original primary key.
    op.execute("ALTER TABLE health_metrics DROP CONSTRAINT IF EXISTS health_metrics_pkey")
    op.execute("ALTER TABLE health_metrics ADD PRIMARY KEY (id)")
