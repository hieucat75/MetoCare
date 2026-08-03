"""QA fixture ingestion is environment-scoped and fails loud in production.

The startup guard refuses to boot prod/production when the QA fixture path is
enabled (``MCP_QA_FIXTURE_ENABLED``). It is a dev/staging automation aid only —
dev, test, local, and staging may enable it; production never can.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings

_REAL_SECRET = "x" * 48
_REAL_ENC = "0" * 43 + "="


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="sqlite://",
        secret_key=_REAL_SECRET,
        encryption_keys=_REAL_ENC,
        # secure auth defaults so this suite isolates the QA-fixture guard.
        mfa_enforcement_enabled=True,
        skip_mfa_in_dev=False,
        password_min_length=8,
        password_require_complexity=True,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.mark.parametrize("env", ["prod", "production"])
def test_production_blocks_qa_fixture_enabled(env):
    with pytest.raises(RuntimeError, match="QA fixture path"):
        _settings(env=env, qa_fixture_enabled=True).validate_required_env_vars()


@pytest.mark.parametrize("env", ["prod", "production"])
def test_production_allows_qa_fixture_disabled(env):
    _settings(env=env, qa_fixture_enabled=False).validate_required_env_vars()  # no raise


@pytest.mark.parametrize("env", ["dev", "test", "local", "staging"])
def test_non_production_allows_qa_fixture_enabled(env):
    # Dev/staging automation builds may enable it; must not raise.
    _settings(env=env, qa_fixture_enabled=True).validate_required_env_vars()


def test_default_is_disabled():
    assert _settings(env="dev").qa_fixture_enabled is False
