"""WS9 §C — MFA/password policy is environment-scoped and fails loud.

The startup guard refuses to boot staging/production with relaxed authentication
(MFA off or a weak password policy). Production never permits it; staging may
during the build phase only via an explicit MCP_ALLOW_RELAXED_AUTH override.
Dev/test may run relaxed. The password validator enforces the active policy.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.core.password import PasswordPolicyError, validate_password_policy

_REAL_SECRET = "x" * 48
_REAL_ENC = "0" * 43 + "="


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="sqlite://",
        secret_key=_REAL_SECRET,
        encryption_keys=_REAL_ENC,
        # secure auth defaults; individual tests relax specific knobs
        mfa_enforcement_enabled=True,
        skip_mfa_in_dev=False,
        password_min_length=8,
        password_require_complexity=True,
    )
    base.update(overrides)
    return Settings(**base)


# ---- startup guard: relaxed auth in real environments -----------------------

@pytest.mark.parametrize("env", ["prod", "production"])
def test_production_blocks_mfa_off(env):
    with pytest.raises(RuntimeError, match="relaxed authentication"):
        _settings(env=env, mfa_enforcement_enabled=False).validate_required_env_vars()


@pytest.mark.parametrize("env", ["prod", "production"])
def test_production_blocks_weak_password_policy(env):
    with pytest.raises(RuntimeError, match="relaxed authentication"):
        _settings(env=env, password_min_length=6).validate_required_env_vars()
    with pytest.raises(RuntimeError, match="relaxed authentication"):
        _settings(env=env, password_require_complexity=False).validate_required_env_vars()


def test_production_ignores_relaxed_override():
    # The staging escape hatch must NEVER let production run relaxed.
    with pytest.raises(RuntimeError, match="Production never permits"):
        _settings(
            env="production", mfa_enforcement_enabled=False, allow_relaxed_auth=True
        ).validate_required_env_vars()


def test_staging_blocks_relaxed_without_override():
    with pytest.raises(RuntimeError, match="MCP_ALLOW_RELAXED_AUTH"):
        _settings(env="staging", mfa_enforcement_enabled=False).validate_required_env_vars()


def test_staging_allows_relaxed_with_explicit_override():
    # Explicit build-phase override: boots (logs a loud warning), does not raise.
    _settings(
        env="staging", mfa_enforcement_enabled=False, allow_relaxed_auth=True
    ).validate_required_env_vars()


def test_staging_secure_auth_passes():
    _settings(env="staging").validate_required_env_vars()  # secure → no raise


@pytest.mark.parametrize("env", ["dev", "test", "local"])
def test_dev_test_allow_relaxed_auth(env):
    _settings(
        env=env,
        mfa_enforcement_enabled=False,
        password_min_length=6,
        password_require_complexity=False,
    ).validate_required_env_vars()  # must not raise


# ---- password validator (policy enforcement) --------------------------------

def test_password_validator_rejects_short(monkeypatch):
    monkeypatch.setattr("app.core.password.get_settings", lambda: _settings())
    with pytest.raises(PasswordPolicyError, match="ít nhất 8"):
        validate_password_policy("ab1")


def test_password_validator_requires_complexity(monkeypatch):
    monkeypatch.setattr("app.core.password.get_settings", lambda: _settings())
    with pytest.raises(PasswordPolicyError, match="chữ và số"):
        validate_password_policy("abcdefgh")  # letters only, no digit


def test_password_validator_accepts_strong(monkeypatch):
    monkeypatch.setattr("app.core.password.get_settings", lambda: _settings())
    validate_password_policy("abcdef12")  # 8 chars, letter+digit → ok


def test_password_validator_relaxed_env(monkeypatch):
    monkeypatch.setattr(
        "app.core.password.get_settings",
        lambda: _settings(password_min_length=6, password_require_complexity=False),
    )
    validate_password_policy("simple")  # relaxed dev/test policy → ok
