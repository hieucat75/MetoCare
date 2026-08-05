"""P1-7 — the post-deploy crypto smoke must fail on a wrong-but-well-formed key.

Boot-time validation proves every MCP_ENCRYPTION_KEYS entry is a well-FORMED
Fernet key. It cannot prove it is the RIGHT one, and nothing else in the deploy
pipeline touches an encrypted column: `/health` is `SELECT 1` and the smoke suite
is unauthenticated and asserts 401s.

Reproduced on a real database before this was written: with a wrong-but-valid
key, boot PASSED, the health check PASSED, and an authenticated encrypted read
raised `UndecryptablePHIError`. `Notification.title/body` are written on every
medication reminder and `MedicationStatement.raw_drug_name` is read on every
medication timeline — both NOT NULL with `on_decrypt_failure="raise"` — so a
mis-rotated key takes both down for every patient while the deploy is green.

The three-state behaviour (correct → pass / wrong → fail / restored → pass) needs
a real database and lives in `tests/integration/test_crypto_smoke_postgres.py`.
This module pins the contract that does NOT need one: the safety properties that
keep the command from becoming a liability of its own.
"""

from __future__ import annotations

import inspect
import json

import pytest
from scripts import crypto_smoke

# ── 1. Output is PHI-free and key-free by construction ──────────────────────


def test_emitted_records_are_json_and_carry_no_value_fields(capsys):
    crypto_smoke._emit({"check": "crypto_smoke", "result": "pass", "entity": "x"})
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["result"] == "pass"
    for forbidden in ("value", "content", "body", "title", "key", "plaintext"):
        assert forbidden not in payload


def test_a_failure_reports_a_reason_code_not_a_value():
    """A mismatch means the ciphertext decrypted to something ELSE, and that
    something else may be real PHI — so neither side may be logged."""
    src = inspect.getsource(crypto_smoke.check_roundtrip)
    assert 'raise SmokeFailure(entity, "roundtrip_mismatch")' in src
    for banned in ("_emit({", "print(value", "print(got"):
        assert banned not in src


def test_the_module_never_logs_key_material():
    src = inspect.getsource(crypto_smoke)
    assert "MCP_ENCRYPTION_KEYS" in src  # it reads it…
    assert "print(os.environ" not in src  # …but never prints it
    assert '"key":' not in src


# ── 2. Sentinels are synthetic and never persisted ──────────────────────────


def test_sentinels_are_synthetic_and_unique():
    a, b = crypto_smoke._sentinel(), crypto_smoke._sentinel()
    assert a != b
    assert a.startswith(crypto_smoke.SENTINEL_PREFIX)


def test_the_run_always_rolls_back():
    """A failed run must leave nothing behind, so the rollback is in `finally`."""
    src = inspect.getsource(crypto_smoke.run)
    assert "finally:" in src
    assert "session.rollback()" in src.split("finally:")[1]


def test_legacy_verification_is_read_only_and_bounded():
    """The mis-rotation detector reads pre-existing rows: it must not write, and
    must not walk the whole table."""
    src = inspect.getsource(crypto_smoke.check_legacy)
    assert "SELECT" in src and "LIMIT :n" in src
    for write in ("INSERT ", "UPDATE ", "DELETE "):
        assert write not in src.upper()
    assert crypto_smoke.LEGACY_SAMPLE <= 20


def test_legacy_targets_cover_the_hot_paths():
    """The columns whose failure breaks reminders and the medication timeline —
    the ones a mis-rotation actually takes down."""
    tables = {t for _e, t, _c in crypto_smoke.LEGACY_TARGETS}
    assert {"notifications", "medication_statements", "meto_messages"} <= tables


# ── 3. Refusals ─────────────────────────────────────────────────────────────


def test_a_missing_key_fails_rather_than_skipping(monkeypatch, capsys):
    """Missing is a FAILURE, not a reason to pass quietly — a deploy with no key
    cannot read PHI at all."""
    monkeypatch.setenv("MCP_ENV", "staging")
    monkeypatch.setenv("MCP_ENCRYPTION_KEYS", "")
    assert crypto_smoke.run() == 1
    assert json.loads(capsys.readouterr().out.strip())["reason"] == "missing_key"


@pytest.mark.parametrize("env", ["prod", "production"])
def test_production_requires_an_explicit_flag(monkeypatch, capsys, env):
    """It WRITES sentinels, so it must not become a routine writer against real
    patient data by accident."""
    monkeypatch.setenv("MCP_ENV", env)
    monkeypatch.setenv("MCP_ENCRYPTION_KEYS", "x")
    assert crypto_smoke.run() == 2
    assert json.loads(capsys.readouterr().out.strip())["result"] == "skipped"


def test_exit_codes_are_distinct():
    """0 pass / 1 fail / 2 misconfiguration — a deploy gate must distinguish "the
    key is wrong" from "this was not configured to run"."""
    assert "0 pass, 1 fail, 2 misconfiguration" in (crypto_smoke.__doc__ or "")


# ── 4. It is a command, not an endpoint ─────────────────────────────────────


def test_no_http_route_exposes_the_smoke():
    """An endpoint that decrypts on demand is a crypto oracle: it turns "can you
    reach this URL" into "can you learn whether a key works"."""
    from app.main import create_app

    for route in create_app().routes:
        path = getattr(route, "path", "").lower()
        assert "crypto" not in path
        assert "decrypt" not in path


def test_the_deploy_gate_runs_it_and_fails_on_it():
    """Wired into the deploy, and its failure must ABORT the deploy — otherwise
    it is a report nobody acts on."""
    import pathlib

    ci = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    if not ci.exists():
        pytest.skip("ci.yml not present in this checkout")
    src = ci.read_text()
    assert "scripts.crypto_smoke" in src
    # rsplit: the phrase appears in both the comment header and the step name,
    # and it is the STEP's body that has to abort the deploy.
    block = src.rsplit("Post-deploy PHI crypto smoke", 1)[1]
    assert "exit 1" in block, "a failing crypto smoke does not fail the deploy"
    assert "Remediation" in block, "no rollback instructions for the on-call"
