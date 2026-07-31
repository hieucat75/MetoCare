"""WS9 — the startup guard must refuse committed default secrets in real envs.

Non-empty defaults slip past the missing-var check, so a staging/prod boot where
secret injection silently failed would otherwise run with a publicly-known JWT
secret and a committed Fernet PHI key. Local dev/test intentionally keep them.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings

_DEFAULT_SECRET = "dev-insecure-secret-change-me-in-production-0123456789"
_DEFAULT_ENC = "CSuRdJSn8APsbQJ3u91m71ZoHvdpn0IzMj6i7H9kMFg="
_REAL_SECRET = "x" * 48
_REAL_ENC = "0" * 43 + "="  # shape-only; guard only checks the default prefix


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="sqlite://",
        secret_key=_REAL_SECRET,
        encryption_keys=_REAL_ENC,
        # secure auth so the separate auth guard never interferes with these
        # secrets-focused assertions
        mfa_enforcement_enabled=True,
        password_min_length=8,
        password_require_complexity=True,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.mark.parametrize("env", ["staging", "production", "prod"])
def test_default_secret_key_blocks_real_env(env):
    s = _settings(env=env, secret_key=_DEFAULT_SECRET)
    with pytest.raises(RuntimeError, match="MCP_SECRET_KEY"):
        s.validate_required_env_vars()


@pytest.mark.parametrize("env", ["staging", "production"])
def test_default_encryption_key_blocks_real_env(env):
    s = _settings(env=env, encryption_keys=_DEFAULT_ENC)
    with pytest.raises(RuntimeError, match="MCP_ENCRYPTION_KEYS"):
        s.validate_required_env_vars()


def test_default_encryption_key_blocks_even_as_secondary_rotation_entry():
    s = _settings(env="staging", encryption_keys=f"{_REAL_ENC},{_DEFAULT_ENC}")
    with pytest.raises(RuntimeError, match="MCP_ENCRYPTION_KEYS"):
        s.validate_required_env_vars()


@pytest.mark.parametrize("env", ["dev", "test", "local"])
def test_defaults_allowed_in_dev_and_test(env):
    s = _settings(env=env, secret_key=_DEFAULT_SECRET, encryption_keys=_DEFAULT_ENC)
    s.validate_required_env_vars()  # must not raise


def test_real_secrets_pass_in_staging():
    s = _settings(env="staging")
    s.validate_required_env_vars()  # must not raise
