"""P1-6 — the SEC-F11 column rewrite must bound its lock WAIT, not its rewrite.

`ALTER TABLE extraction_candidates ALTER COLUMN fields_json TYPE TEXT` takes an
ACCESS EXCLUSIVE lock and rewrites the table. The dangerous failure is not the
obvious one:

  1. Any transaction already holding a conflicting lock — including an
     idle-in-transaction session that ran one SELECT — makes the ALTER wait.
  2. While waiting, the ALTER sits at the HEAD of the lock queue, and every
     subsequent query on `extraction_candidates` queues behind IT. One idle
     session therefore takes document review offline for the entire application,
     for as long as that session stays open. The migration merely looks slow.

`lock_timeout` bounds the wait so the migration aborts in seconds and can be
retried in a quieter window; DDL here is transactional, so the abort rolls back
cleanly. `statement_timeout = 0` covers the opposite side — once the lock IS
held, a server-configured statement_timeout must not kill the rewrite partway.

Measured on real Postgres 5.1s abort with a blocker held vs instant acquisition
without one. That experiment needs a second concurrent session, so what is
pinned here is the property a future edit could silently drop: both settings are
issued, on both directions, and only for Postgres.
"""

from __future__ import annotations

import pathlib

import pytest

MIGRATION = pathlib.Path("alembic/versions/j4_m9_secf11_phi_encryption.py")


@pytest.fixture(scope="module")
def source() -> str:
    return MIGRATION.read_text()


def _body(source: str, fn: str) -> str:
    """Just `fn`'s own body — counting occurrences across the whole file would
    also count the `def` line and read as one more call site than exists."""
    return source.split(f"def {fn}() -> None:")[1].split("\ndef ")[0]


def test_lock_wait_is_bounded(source):
    assert "SET LOCAL lock_timeout" in source, (
        "the ALTER can queue indefinitely and block the whole table behind it"
    )


def test_the_rewrite_itself_is_not_bounded(source):
    """Bounding the rewrite instead of the wait would abort a large table
    mid-migration — the opposite of what is wanted."""
    assert "SET LOCAL statement_timeout = 0" in source


def test_both_directions_are_guarded(source):
    """upgrade() and downgrade() perform the same rewrite and carry the same
    hazard; guarding only one leaves a rollback able to stall production."""
    for direction in ("upgrade", "downgrade"):
        assert "_guard_lock_waits(conn)" in _body(source, direction), direction


def test_a_blocking_session_is_named_before_the_attempt(source):
    """"canceling statement due to lock timeout" tells an operator nothing
    actionable at 02:00; the preflight names the blocking pids."""
    assert "_preflight_locks" in source
    assert "pg_stat_activity" in source
    for direction in ("upgrade", "downgrade"):
        assert "_preflight_locks(conn," in _body(source, direction), direction


def test_the_guards_are_postgres_only(source):
    """SQLite has neither setting and goes through batch_alter_table."""
    for fn in ("_preflight_locks", "_guard_lock_waits"):
        body = source.split(f"def {fn}(")[1].split("\ndef ")[0]
        assert 'dialect.name != "postgresql"' in body
        assert "return" in body


def test_preflight_never_raises_on_a_non_postgres_connection():
    """Diagnostics must not be able to break a migration."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("secf11_mig", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class _Sqlite:
        class dialect:
            name = "sqlite"

    mod._preflight_locks(_Sqlite(), "extraction_candidates")
    mod._guard_lock_waits(_Sqlite())
