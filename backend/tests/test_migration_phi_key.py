"""P0 — a migration job must never encrypt PHI with the repository's default key.

Found by the post-deploy crypto smoke on its first ever real execution, against
staging build `3fd813a3`:

    {"check":"crypto_smoke","entity":"meto_message.content",
     "reason":"legacy_row_undecryptable","result":"fail"}
    … and the same for extraction_candidate.fields_json,
      medication_statement.raw_drug_name, notification.body
    {"entities_checked":2,"failures":4,"legacy_rows_total":0,…}

The round-trips PASSED — the deployed key encrypts and decrypts its own writes —
while every PRE-EXISTING row failed. That is the mis-rotation signature, and the
cause sat upstream of any key rotation:

`Settings.encryption_keys` carries a hardcoded default committed to this
repository. The Alembic migration Container Apps Job was created with only
`MCP_DATABASE_URL` and `MCP_ENV`, so `_cipher()` fell back to that default, and
the SEC-F11 / P1-5 data migrations — which convert previously-plaintext PHI
columns to ciphertext — encrypted all of staging's Meto messages, OCR candidate
fields, medication statements and notification bodies with a public key. The
application then started with the real Key Vault key and could not read any of
it.

`warn_if_insecure` already knew about this key, but it only WARNS, only when
`is_prod`, and only at application startup — so it could not see a migration job
running in staging. The production workflow's migration job had the identical
definition, so the next production deploy would have done this to real patients'
records.

Two fixes, tested here: the workflows now hand the key to the migration job, and
`_cipher()` refuses the committed default outside a development environment so no
future job can reintroduce the failure by forgetting an environment variable.
"""

from __future__ import annotations

import pathlib

import pytest
from app.core import crypto
from app.core.config import Settings


def _workflow(name: str) -> str:
    path = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / name
    if not path.exists():
        pytest.skip(f"{name} not present in this checkout")
    return path.read_text()


def _migration_job_command(workflow: str) -> str:
    """The `az containerapp job create` invocation for the Alembic job."""
    lines = workflow.splitlines()
    for i, line in enumerate(lines):
        if "az containerapp job create" not in line:
            continue
        parts, j = [line], i
        while lines[j].rstrip().endswith("\\") and j + 1 < len(lines):
            j += 1
            parts.append(lines[j])
        command = "\n".join(parts)
        if "alembic" in command:
            return command
    raise AssertionError("no Alembic migration job found in this workflow")


# ── 1. The workflows hand the real key to the migration ─────────────────────


@pytest.mark.parametrize("name", ["ci.yml", "azure-production.yml"])
def test_the_migration_job_receives_the_encryption_key(name):
    """Without it the job silently uses the committed default and encrypts PHI
    with a key the application does not have."""
    command = _migration_job_command(_workflow(name))
    assert "MCP_ENCRYPTION_KEYS=secretref:enc-keys" in command, (
        f"{name}: the Alembic job has no MCP_ENCRYPTION_KEYS — the SEC-F11/P1-5 "
        "data migrations will encrypt PHI with the repository's default key"
    )
    assert "enc-keys=$ENC_KEYS" in command, (
        f"{name}: the secret referenced by MCP_ENCRYPTION_KEYS is not defined"
    )


@pytest.mark.parametrize("name", ["ci.yml", "azure-production.yml"])
def test_the_key_is_passed_by_secret_reference_not_as_a_literal(name):
    command = _migration_job_command(_workflow(name))
    assert "MCP_ENCRYPTION_KEYS=$ENC_KEYS" not in command
    assert 'MCP_ENCRYPTION_KEYS="$ENC_KEYS"' not in command


# ── 2. The default key cannot be used outside development ───────────────────


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from app.core.config import get_settings

    # `_cipher` is lru_cached on no arguments, so a cipher built by an earlier
    # test survives a monkeypatched `get_settings` and the guard never runs.
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


@pytest.mark.parametrize("env", ["staging", "production", "prod", ""])
def test_the_committed_default_key_is_refused_outside_development(monkeypatch, env):
    """The exact condition that produced the staging failure: a process with no
    MCP_ENCRYPTION_KEYS, in a non-development environment."""
    monkeypatch.setattr(crypto, "get_settings", lambda: Settings(env=env))
    with pytest.raises(crypto.EncryptionConfigError) as excinfo:
        crypto.encrypt("some phi")
    message = str(excinfo.value)
    assert "development default" in message
    # The message names the environment and the remedy — never the key itself.
    assert crypto._DEV_DEFAULT_KEY_PREFIX not in message


@pytest.mark.parametrize("env", ["dev", "development", "local", "test", "ci"])
def test_development_environments_still_work_with_the_default(monkeypatch, env):
    """The default exists so a developer can run the app without provisioning a
    key. Breaking that would push people toward disabling the check."""
    monkeypatch.setattr(crypto, "get_settings", lambda: Settings(env=env))
    assert crypto.decrypt(crypto.encrypt("some phi")) == "some phi"


def test_a_real_key_is_accepted_in_staging(monkeypatch):
    from cryptography.fernet import Fernet

    real = Fernet.generate_key().decode()
    monkeypatch.setattr(
        crypto, "get_settings", lambda: Settings(env="staging", encryption_keys=real)
    )
    assert crypto.decrypt(crypto.encrypt("some phi")) == "some phi"


def test_the_default_is_refused_even_as_a_secondary_rotation_key(monkeypatch):
    """MultiFernet accepts a list; a decrypt-only secondary is still a key whose
    ciphertext anyone holding this repository can read."""
    from cryptography.fernet import Fernet

    keys = f"{Fernet.generate_key().decode()},{Settings().encryption_keys}"
    monkeypatch.setattr(
        crypto, "get_settings", lambda: Settings(env="production", encryption_keys=keys)
    )
    with pytest.raises(crypto.EncryptionConfigError):
        crypto.encrypt("some phi")
