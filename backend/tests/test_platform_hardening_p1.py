"""Launch-readiness P1 platform hardening.

Covers:
- WS4-F8 — SQLAlchemy bound parameters (PHI) must never reach a log record.
- PROD-F12 — the DB engine must declare a bounded, liveness-checked pool.
- WS4-F6 — unmatched routes must not put attacker-controlled raw paths into
  metric labels or the access log.
"""

from __future__ import annotations

import io
import json
import logging
import uuid

import pytest
from app.core.database import _make_engine, engine
from app.core.logging import ContextFilter, JsonFormatter
from app.core.metrics import registry
from sqlalchemy import text
from sqlalchemy.exc import StatementError


def _format(record: logging.LogRecord) -> str:
    return JsonFormatter().format(record)


def _record(msg: str, *args) -> logging.LogRecord:
    return logging.LogRecord(
        name="test", level=logging.ERROR, pathname=__file__, lineno=1,
        msg=msg, args=args, exc_info=None,
    )


# ── WS4-F8 ──────────────────────────────────────────────────────────────────
def test_engine_hides_bound_parameters():
    """The engine must never stringify bound parameters into exception text."""
    assert engine.hide_parameters is True


def test_statement_error_text_carries_no_bound_parameter_values(db):
    """A real StatementError must not expose the PHI it was bound with."""
    phi = "0912345678-NguyenVanA"
    with pytest.raises(StatementError) as excinfo:
        db.execute(text("SELECT 1 FROM users WHERE phone = :phone"), {"phone": {"x": phi}})
    db.rollback()
    assert phi not in str(excinfo.value)


def test_json_formatter_redacts_sql_and_parameter_fragments():
    """Even if some future call site interpolates a DBAPI error into the
    message, the formatter strips the `[SQL: …] [parameters: …]` tail — the
    channel that bypasses the 7-field `extra` allow-list."""
    phi = "0912345678"
    msg = (
        "context build failed: (sqlite3.OperationalError) no such column\n"
        f"[SQL: SELECT * FROM users WHERE phone = ?]\n[parameters: ('{phi}',)]"
    )
    out = _format(_record("build failed: %s", msg))
    assert "[parameters:" not in out
    assert "[SQL:" not in out
    assert phi not in out
    payload = json.loads(out)
    assert "context build failed" in payload["message"]


def test_json_formatter_leaves_ordinary_messages_intact():
    out = json.loads(_format(_record("plain operational message")))
    assert out["message"] == "plain operational message"


# ── PROD-F12 ────────────────────────────────────────────────────────────────
def test_postgres_engine_declares_bounded_pool_with_liveness_check():
    pg = _make_engine("postgresql+psycopg2://u:p@localhost:5432/db")
    pool = pg.pool
    assert pool.size() == 20
    assert pool._max_overflow == 10
    assert pool._pre_ping is True
    assert pool._recycle == 1800


def test_sqlite_engine_still_builds_and_connects(tmp_path):
    sqlite_engine = _make_engine(f"sqlite:///{tmp_path}/pool.sqlite3")
    with sqlite_engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


# ── WS4-F6 ──────────────────────────────────────────────────────────────────
def test_unmatched_path_is_never_reflected_into_metrics_or_access_log(client):
    hostile = f"/nope-{uuid.uuid4().hex}-<script>"
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    access_logger = logging.getLogger("mcp.access")
    access_logger.addHandler(handler)
    # Pin the level for the duration. setup_logging() configures the ROOT logger,
    # so `mcp.access` has no level of its own and inherits whatever the last test
    # to touch the root left behind — which silently produced an empty buffer and
    # an IndexError below when the whole suite ran in one process.
    prev_level = access_logger.level
    access_logger.setLevel(logging.INFO)
    try:
        r = client.get(hostile)
    finally:
        access_logger.removeHandler(handler)
        access_logger.setLevel(prev_level)

    assert r.status_code == 404
    rendered = registry.render()
    assert hostile not in rendered
    assert 'path="<unmatched>"' in rendered

    lines = [ln for ln in buf.getvalue().strip().splitlines() if ln]
    rec = json.loads(lines[-1])
    assert rec["path"] == "<unmatched>"
    assert hostile not in buf.getvalue()


def test_matched_route_still_uses_the_route_template(client):
    client.get("/api/v1/health")
    # The router mounts the health route at "/health" under the /api/v1 prefix;
    # what matters is that a *template* (never the raw URL) is the label.
    assert 'path="/health"' in registry.render()
