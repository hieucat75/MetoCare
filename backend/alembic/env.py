"""Alembic migration environment.

Wires Alembic to the application's settings and ORM metadata so the same
migrations run on SQLite (dev/test default) and PostgreSQL/TimescaleDB (prod).
The database URL comes from MCP_DATABASE_URL — never hardcoded here.
"""

from __future__ import annotations

import logging
from logging.config import fileConfig

# Import models so every table is registered on Base.metadata.
import app.models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.core.database import Base
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False` is REQUIRED, not a preference.
    #
    # fileConfig() defaults to True, which sets `.disabled = True` on every logger
    # not named in alembic.ini — i.e. all of `mcp.access`, `app.services.*`, and
    # anything else the application already created. The effect is process-wide
    # and permanent, so once Alembic has run in a process, that process emits no
    # application logs at all.
    #
    # In the deploy pipeline Alembic runs as its own one-shot container, so the
    # blast radius there is nil. It is NOT nil anywhere Alembic shares a process
    # with the app: the test suite (where it silently killed the access-log and
    # PHI-safety assertions in test_observability, test_platform_hardening_p1 and
    # test_meto_context_failclosed), and any future startup-migration path, which
    # would come up with logging permanently dead and no indication why.
    #
    # Proven, not assumed: fileConfig("alembic.ini") flips
    # mcp.access.disabled False -> True; with this flag it stays False.
    # Second, separate side effect: alembic.ini declares `[logger_root] level =
    # WARNING`, so fileConfig() also LOWERS the host application's root level.
    # Loggers without an explicit level of their own (mcp.access, app.services.*)
    # inherit it, so every INFO application log is filtered out for the rest of
    # the process — the access log simply stops.
    #
    # Alembic's own verbosity is unaffected either way: `[logger_alembic]` sets
    # INFO on the `alembic` logger explicitly.
    #
    # Restore the root level ONLY when the application already owns logging
    # (detected by the handler setup_logging tags). Standalone Alembic — the
    # deploy job's one-shot container — has no such handler, so its configured
    # level is left exactly as alembic.ini asks.
    _root = logging.getLogger()
    _app_owns_logging = any(
        getattr(h, "_mcp_json_handler", False) for h in _root.handlers
    )
    _prior_root_level = _root.level

    fileConfig(config.config_file_name, disable_existing_loggers=False)

    if _app_owns_logging:
        _root.setLevel(_prior_root_level)

# Inject the runtime database URL from app settings.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # batch mode is required for SQLite ALTER support.
            render_as_batch=is_sqlite,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
