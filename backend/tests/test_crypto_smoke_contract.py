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
    assert "run_crypto_smoke.py" in src
    # rsplit: the phrase appears in both the comment header and the step name,
    # and it is the STEP's body that has to abort the deploy.
    block = src.rsplit("Post-deploy PHI crypto smoke", 1)[1]
    assert "exit 1" in block, "a failing crypto smoke does not fail the deploy"
    assert "Remediation" in block, "no rollback instructions for the on-call"


# ── 5. Production wiring ────────────────────────────────────────────────────
#
# The staging gate existed and production had none — i.e. the mis-rotation
# scenario was undetected in the one environment where it takes down real
# patients' reminders. These pin the production path STATICALLY, because the
# only other way to learn it is wrong is to deploy production.


def _prod_workflow() -> str:
    import pathlib

    wf = (
        pathlib.Path(__file__).resolve().parents[2]
        / ".github" / "workflows" / "azure-production.yml"
    )
    if not wf.exists():
        pytest.skip("azure-production.yml not present in this checkout")
    return wf.read_text()


def _prod_smoke_block() -> str:
    """JUST the crypto-smoke step — bounded at the next step, not at EOF.

    Splitting to end-of-file made every assertion over this block satisfiable by
    UNRELATED later steps: `block.count("exit 1") >= 2` passed on the health
    gates' exits even with both of the smoke's own removed, and
    `"MCP_ENV=production" in block` passed on the deploy step's env. A test that
    can be satisfied by code it is not testing is not a gate.
    """
    src = _prod_workflow()
    assert "Post-migration PHI crypto smoke" in src, (
        "production deploys with NO crypto smoke — a mis-rotated key ships silently"
    )
    after = src.split("- name: Post-migration PHI crypto smoke", 1)[1]
    return after.split("\n      - name:", 1)[0]


def _all_smoke_invocations() -> list[tuple[str, str]]:
    """(workflow name, the `az containerapp job create` command) for each caller."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"
    out: list[tuple[str, str]] = []
    for wf in ("ci.yml", "azure-production.yml"):
        path = root / wf
        if not path.exists():
            continue
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines):
            if "az containerapp job create" not in line:
                continue
            # Join backslash continuations: the command spans many YAML lines and
            # the `--args` list is always on one of the later ones.
            parts = [line]
            j = i
            while lines[j].rstrip().endswith("\\") and j + 1 < len(lines):
                j += 1
                parts.append(lines[j])
            command = "\n".join(parts)
            if "crypto" in command or "run_crypto_smoke" in command:
                out.append((wf, command))
    return out


def test_production_invokes_the_smoke_and_permits_production():
    """`run()` refuses a production database unless explicitly permitted, so a
    step that omits the opt-in exits 2 and gates nothing."""
    block = _prod_smoke_block()
    assert "run_crypto_smoke.py" in block
    assert "MCP_CRYPTO_SMOKE_ALLOW_PRODUCTION=1" in block
    assert "MCP_ENV=production" in block


@pytest.mark.parametrize("workflow,command", _all_smoke_invocations())
def test_the_az_args_list_contains_no_dash_prefixed_token(workflow, command):
    """THE bug that made the gate unrunnable, pinned.

    `az containerapp job create --args` declares `nargs='*'`, and argparse stops
    collecting at the first token starting with `-`. So

        --command "python" --args "-m" "scripts.crypto_smoke" "--allow-production"

    parses to `args=[]`, all three tokens land in `extras`, and the CLI exits 2
    with UnrecognizedArgumentError — the job is never created and the smoke never
    runs. The step still fails, so it fails closed, but it fails on EVERY deploy
    in a way indistinguishable from a real wrong-key failure, which is exactly
    how a gate gets muted as "the usual broken step". Neither the staging nor the
    production invocation had ever executed.

    Verified directly against the Azure CLI's own argparse behaviour;
    `--args "upgrade" "head"` parses fine, which is why the Alembic job works.
    """
    args_part = command.split("--args", 1)[1] if "--args" in command else ""
    args_part = args_part.split("-o none", 1)[0]
    tokens = [t.strip().strip('"').strip("\\").strip() for t in args_part.split()]
    offenders = [t for t in tokens if t.startswith("-") and t]
    assert not offenders, (
        f"{workflow}: --args contains dash-prefixed token(s) {offenders}; "
        "argparse will drop the whole list and the job will never be created"
    )


@pytest.mark.parametrize("workflow,command", _all_smoke_invocations())
def test_the_smoke_job_does_not_ask_for_registry_credentials_it_lacks(workflow, command):
    """`--registry-server` on a NON-ACR registry is a hard usage error unless
    credentials accompany it: the CLI raises RequiredArgumentMissingError
    ("Registry username and password are required if not using Azure Container
    Registry"). The Alembic job pulls the same GHCR image with no
    `--registry-server` at all, which is the working precedent."""
    if "--registry-server" in command:
        assert (
            "--registry-username" in command
            or "--registry-password" in command
            or "--registry-identity" in command
        ), f"{workflow}: --registry-server without credentials is a hard CLI error"


def test_the_entrypoint_needs_no_dash_prefixed_arguments():
    """The workflow-side fix is only sound if the entrypoint really takes none."""
    import run_crypto_smoke

    assert hasattr(run_crypto_smoke, "main")
    # Strip comments and the module docstring: the prose EXPLAINS the argparse
    # rule by quoting it, and a naive substring check would fail on its own
    # documentation.
    code = "\n".join(
        line for line in inspect.getsource(run_crypto_smoke).splitlines()
        if not line.strip().startswith(("#", '"""', "*", "--command"))
    )
    for banned in ("add_argument", "ArgumentParser", "sys.argv"):
        assert banned not in code, f"{banned} reintroduces dash-prefixed arguments"
    assert "MCP_CRYPTO_SMOKE_ALLOW_PRODUCTION" in code


def test_the_entrypoint_defaults_to_refusing_production(monkeypatch):
    """Absent or unset env var must NOT permit production."""
    import run_crypto_smoke

    for value in ("", "0", "false", "no", None):
        monkeypatch.delenv("MCP_CRYPTO_SMOKE_ALLOW_PRODUCTION", raising=False)
        if value is not None:
            monkeypatch.setenv("MCP_CRYPTO_SMOKE_ALLOW_PRODUCTION", value)
        monkeypatch.setenv("MCP_ENV", "production")
        monkeypatch.setenv("MCP_ENCRYPTION_KEYS", "x")
        assert run_crypto_smoke.main() == 2, f"value {value!r} permitted production"


def test_the_smoke_job_is_removed_after_the_run():
    """It is created with `--secrets enc-keys=…`, so leaving it in place parks the
    production PHI master key in a second, unwatched resource between deploys."""
    src = _prod_workflow()
    assert "Remove crypto-smoke job" in src, (
        "the smoke job is never deleted after the run — it retains the production "
        "database URL and MCP_ENCRYPTION_KEYS as job secrets"
    )
    cleanup = src.split("- name: Remove crypto-smoke job", 1)[1].split("\n      - name:", 1)[0]
    assert "if: always()" in cleanup, "cleanup must run even when the smoke fails"
    assert "az containerapp job delete" in cleanup


def test_a_failed_delete_before_create_is_fatal():
    """A reused job runs the PREVIOUS image and secrets and would verify the OLD
    key, so the step's own load-bearing precondition may not be `|| true`."""
    block = _prod_smoke_block()
    create_at = block.index("az containerapp job create")
    before_create = block[:create_at]
    assert "az containerapp job delete" in before_create
    assert "exit 1" in before_create, (
        "a failed delete-before-create is swallowed; the create then upserts onto "
        "the stale job"
    )


def test_the_verdict_is_read_from_this_runs_execution():
    """`[0]` has no ordering guarantee, so a stale `Succeeded` from an earlier
    deploy could be read as this run's verdict and the deploy proceed having
    verified nothing."""
    block = _prod_smoke_block()
    assert "--job-execution-name" in block, (
        "the poll reads an unordered [0] rather than this run's execution"
    )


def test_production_runs_the_smoke_after_migration_and_before_any_revision():
    """Ordering IS the gate: after the migration (which has already touched
    encrypted columns) and before a traffic-carrying revision exists, so a
    failure leaves the currently-serving revision untouched."""
    src = _prod_workflow()
    migrate = src.index("- name: Run Alembic migration")
    smoke = src.index("- name: Post-migration PHI crypto smoke")
    deploy = src.index("- name: Deploy backend to ACA")
    assert migrate < smoke < deploy, (
        "the crypto smoke must sit between the migration and the first revision"
    )


def test_a_failing_or_hanging_production_smoke_blocks_the_rollout():
    block = _prod_smoke_block()
    # Both exits: the explicit Failed verdict, and the post-loop no-verdict case.
    assert block.count("exit 1") >= 2, (
        "a timed-out smoke must FAIL, not fall through as healthy"
    )
    assert 'if [ "$ST" != "Succeeded" ]' in block
    assert "Remediation" in block, "no rollback instructions for the on-call"


def test_the_production_smoke_job_cannot_be_a_stale_reused_job():
    """A reused Container Apps job runs the PREVIOUS image and secrets, so it
    would verify the OLD key and report pass."""
    block = _prod_smoke_block()
    assert "az containerapp job delete" in block
    assert block.index("az containerapp job delete") < block.index(
        "az containerapp job create"
    )


def test_the_production_smoke_defines_its_own_variables():
    """A `run:` step is a fresh shell. Referencing a variable assigned in an
    earlier step yields an empty string, and the step then fails on every deploy
    indistinguishably from a real wrong-key failure."""
    block = _prod_smoke_block().split("- name:")[0]
    # Comments are stripped: the step's prose EXPLAINS the earlier bug by naming
    # the variables it wrongly referenced, and a substring check that counted
    # those would fail on its own documentation.
    code = "\n".join(
        line for line in block.splitlines() if not line.strip().startswith("#")
    )
    for var in ("JOB=", "IMG="):
        assert var in code, f"{var} is not defined in the step's own shell"
    for undefined in ("$MIGRATE_JOB", "$ACA_ENV"):
        assert undefined not in code


def test_the_production_smoke_uses_secret_references_not_literals():
    block = _prod_smoke_block()
    assert "secretref:enc-keys" in block and "secretref:db-url" in block
    assert 'echo "$ENC_KEYS"' not in block
    assert "MCP_ENCRYPTION_KEYS=$" not in block


def test_production_deploys_only_from_main_with_explicit_confirmation():
    src = _prod_workflow()
    assert 'if [ "${{ inputs.confirm }}" != "PRODUCTION" ]' in src
    assert '"${{ github.ref }}" != "refs/heads/main"' in src


def test_no_shell_continuation_is_followed_by_a_blank_line():
    """A `\\` at end of line continues onto the NEXT line — and if that line is
    empty, the command ends there and everything after it becomes a separate
    command. Introduced accidentally while editing the env-var list, it silently
    dropped `MCP_BUILD_SHA` out of the `az containerapp job create` invocation
    and turned it into a standalone assignment. YAML does not care and neither
    does a substring assertion; only reading the line pairs catches it.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"
    offenders = []
    for wf in ("ci.yml", "azure-production.yml"):
        path = root / wf
        if not path.exists():
            continue
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines[:-1]):
            if line.rstrip().endswith("\\") and not lines[i + 1].strip():
                offenders.append(f"{wf}:{i + 1}")
    assert not offenders, f"shell continuation followed by a blank line at {offenders}"


def test_both_workflows_invoke_the_smoke_the_same_way():
    """Staging and production must not drift: the staging invocation carried the
    identical unparseable `--args` list and had therefore never run either."""
    invocations = _all_smoke_invocations()
    workflows = {wf for wf, _ in invocations}
    assert workflows == {"ci.yml", "azure-production.yml"}, (
        f"expected both workflows to invoke the smoke, found {workflows}"
    )
    for _wf, command in invocations:
        assert 'run_crypto_smoke.py' in command
