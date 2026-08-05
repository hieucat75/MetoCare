"""Structured JSON logging — no PHI/PII (Technical_Architecture.md §4.8).

Logs only operational metadata: timestamp, level, logger, message, request_id,
user_id (opaque UUID), and a curated set of safe extra fields. Request/response
bodies, emails, names, health data are NEVER logged here.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re

from .context import request_id_var, user_id_var

# Fields allowed on a log record's `extra`; anything else is dropped to prevent
# accidental PHI leakage through ad-hoc logging.
_SAFE_EXTRA_FIELDS = frozenset(
    {"method", "path", "status_code", "duration_ms", "action", "resource_type", "event"}
)

# WS4-F8 — the log `message` is the one channel the `extra` allow-list cannot
# protect: `record.getMessage()` interpolates `%s` args *before* any filter
# runs, so a call site that logs an exception can smuggle DBAPI detail (and with
# it bound parameters — i.e. PHI) into stdout. `hide_parameters=True` on the
# engine (app/core/database.py) removes the values at the source; this is the
# belt-and-braces second line: strip the whole `[SQL: …] [parameters: …]` tail
# from every message, whatever produced it.
_SQL_DETAIL_RE = re.compile(r"\[(?:SQL|parameters):.*", re.DOTALL)
_SQL_DETAIL_PLACEHOLDER = "[sql-detail-redacted]"


def redact_sql_detail(message: str) -> str:
    """Remove any SQLAlchemy statement/bound-parameter tail from a log message."""
    return _SQL_DETAIL_RE.sub(_SQL_DETAIL_PLACEHOLDER, message)


class ContextFilter(logging.Filter):
    """Inject request_id / user_id from context vars onto every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": dt.datetime.now(dt.UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sql_detail(record.getMessage()),
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
        }
        for field in _SAFE_EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, ensure_ascii=False)


#: Marks the root handler this module owns, so repeated setup can replace exactly
#: that one and nothing else.
_OWNED_HANDLER_FLAG = "_mcp_json_handler"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging to emit JSON with context. Idempotent.

    Removes only the handler THIS function installed. It previously cleared every
    root handler, which made it idempotent for its own purposes but destructive to
    anyone else's: `create_app()` calls it, so importing the app inside a test
    silently detached pytest's `caplog` handler, and any embedding process (an
    ASGI host, a worker, a notebook) lost its own logging the moment the app was
    constructed. Owning one tagged handler keeps double-logging impossible while
    leaving foreign handlers — which we did not add and cannot reason about —
    alone.
    """
    root = logging.getLogger()
    root.setLevel(level)

    for h in list(root.handlers):
        if getattr(h, _OWNED_HANDLER_FLAG, False):
            root.removeHandler(h)
            h.close()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    setattr(handler, _OWNED_HANDLER_FLAG, True)
    root.addHandler(handler)
