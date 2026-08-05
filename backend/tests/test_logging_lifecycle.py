"""Logging lifecycle: repeated setup, foreign handlers, and Alembic side effects.

These guard a defect that was invisible in isolation and only appeared once the
full suite ran in one process: `alembic/env.py` called `fileConfig()` with
`disable_existing_loggers` left at its default of True, which permanently set
`.disabled = True` on every application logger. Any test collected after a
migration test then asserted against an empty log buffer — which looked like
"flaky logging tests" rather than what it was.

Two independent properties are pinned here so it cannot regress:

1. Running Alembic must not disable application loggers.
2. `setup_logging()` must be idempotent AND must not evict handlers it does not
   own — `create_app()` calls it, so evicting foreign handlers silently detaches
   pytest's caplog, and would detach an embedding process's handlers too.
"""

from __future__ import annotations

import logging
from logging.config import fileConfig

import pytest
from app.core.logging import _OWNED_HANDLER_FLAG, setup_logging

APP_LOGGERS = ("mcp.access", "app.services.meto_chat", "app.core.crypto")


@pytest.fixture(autouse=True)
def _restore_logging():
    """Leave global logging exactly as found — these tests mutate it deliberately."""
    root = logging.getLogger()
    saved_level = root.level
    saved_handlers = list(root.handlers)
    saved = {
        name: (lg.level, lg.disabled)
        for name, lg in logging.Logger.manager.loggerDict.items()
        if isinstance(lg, logging.Logger)
    }
    yield
    root.setLevel(saved_level)
    root.handlers[:] = saved_handlers
    for name, (level, disabled) in saved.items():
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.disabled = disabled


def _owned(root: logging.Logger) -> list[logging.Handler]:
    return [h for h in root.handlers if getattr(h, _OWNED_HANDLER_FLAG, False)]


# ── 1. Alembic must not disable application loggers ─────────────────────────


def test_alembic_fileconfig_does_not_disable_application_loggers():
    """The exact call alembic/env.py makes, with the exact config file."""
    for name in APP_LOGGERS:
        logging.getLogger(name).disabled = False

    fileConfig("alembic.ini", disable_existing_loggers=False)

    still_enabled = {n: not logging.getLogger(n).disabled for n in APP_LOGGERS}
    assert all(still_enabled.values()), still_enabled


def test_the_default_would_have_disabled_them():
    """Pins WHY the flag is required, so nobody 'simplifies' it away later."""
    for name in APP_LOGGERS:
        logging.getLogger(name).disabled = False

    fileConfig("alembic.ini")  # default disable_existing_loggers=True

    assert all(logging.getLogger(n).disabled for n in APP_LOGGERS), (
        "fileConfig's default no longer disables existing loggers — if the stdlib "
        "changed, the explicit flag in alembic/env.py is still correct, but this "
        "test's rationale needs revisiting."
    )


def test_env_py_passes_the_flag():
    """Source-level guard: the call site must keep the argument."""
    import pathlib

    src = pathlib.Path("alembic/env.py").read_text()
    assert "disable_existing_loggers=False" in src


# ── 2. setup_logging idempotency + foreign-handler safety ───────────────────


def test_repeated_setup_does_not_accumulate_handlers():
    root = logging.getLogger()
    setup_logging("INFO")
    assert len(_owned(root)) == 1
    for _ in range(5):
        setup_logging("INFO")
    assert len(_owned(root)) == 1, "repeated setup duplicated the JSON handler"


def test_setup_does_not_evict_foreign_handlers():
    """create_app() calls setup_logging; evicting foreign handlers is what
    silently detached pytest's caplog."""
    root = logging.getLogger()
    foreign = logging.StreamHandler()
    root.addHandler(foreign)
    try:
        setup_logging("INFO")
        assert foreign in root.handlers, "setup_logging removed a handler it did not own"
    finally:
        root.removeHandler(foreign)


def test_repeated_app_creation_leaves_one_owned_handler():
    """No global logger leakage across app instances."""
    from app.main import create_app

    root = logging.getLogger()
    for _ in range(3):
        create_app()
    assert len(_owned(root)) == 1


def test_caplog_still_captures_after_app_creation(caplog):
    """The end-to-end property the three broken tests actually depended on."""
    from app.main import create_app

    create_app()
    with caplog.at_level(logging.INFO, logger="mcp.access"):
        logging.getLogger("mcp.access").info("probe_after_app_creation")
    assert any("probe_after_app_creation" in r.getMessage() for r in caplog.records)


def test_app_loggers_still_emit_after_alembic_fileconfig():
    """The end-to-end property broken by the Alembic side effect.

    Models the real boundary: Alembic runs during an EARLIER test, then a later
    test attaches its own capture. (Capturing across a `fileConfig` call in the
    same test would fail for an unrelated reason — `fileConfig` also rebuilds the
    root handler list, so it evicts any handler attached beforehand. pytest
    re-installs caplog per test, so that does not affect real runs.)
    """
    fileConfig("alembic.ini", disable_existing_loggers=False)

    access = logging.getLogger("mcp.access")
    assert not access.disabled

    captured: list[logging.LogRecord] = []

    class _Sink(logging.Handler):
        def emit(self, record):
            captured.append(record)

    sink = _Sink(level=logging.DEBUG)
    access.addHandler(sink)
    prev = access.level
    access.setLevel(logging.INFO)
    try:
        access.info("probe_after_alembic")
    finally:
        access.removeHandler(sink)
        access.setLevel(prev)

    assert any("probe_after_alembic" in r.getMessage() for r in captured)
