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


def _staging_workflow() -> str:
    import pathlib

    ci = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    if not ci.exists():
        pytest.skip("ci.yml not present in this checkout")
    return ci.read_text()


def _staging_smoke_block() -> str:
    """JUST the staging crypto-smoke step, bounded at the next step.

    Bounded for the same reason as the production one: splitting to end-of-file
    made every assertion satisfiable by unrelated later steps.
    """
    src = _staging_workflow()
    assert "Post-migration PHI crypto smoke" in src
    after = src.split("- name: Post-migration PHI crypto smoke", 1)[1]
    return after.split("\n      - name:", 1)[0]


def test_the_deploy_gate_runs_it_and_fails_on_it():
    """Wired into the deploy, and its failure must ABORT the deploy — otherwise
    it is a report nobody acts on."""
    assert "run_crypto_smoke.py" in _staging_workflow()
    block = _staging_smoke_block()
    assert "exit 1" in block, "a failing crypto smoke does not fail the deploy"
    assert "Remediation" in block, "no rollback instructions for the on-call"


# ── 4b. Staging must not be weaker than production ──────────────────────────
#
# On 2026-08-06 the staging gate fired correctly and staging had ALREADY been
# serving the broken build for fourteen minutes, because the staging step ran
# last while the production step ran between the migration and the first
# revision. Every property production's own tests treat as load-bearing was
# absent from staging: the ordering, this-execution polling, a fatal
# delete-before-create, and deleting a job that holds the PHI key. Drift in a
# safety gate is only ever discovered by the environment that lacks it.


def test_staging_runs_the_smoke_after_migration_and_before_any_revision():
    """Ordering IS the gate. Placed after the deploy it is a report."""
    src = _staging_workflow()
    migrate = src.index("- name: Run Alembic migration")
    smoke = src.index("- name: Post-migration PHI crypto smoke")
    deploy = src.index("- name: Deploy backend to ACA")
    assert migrate < smoke < deploy, (
        "the staging crypto smoke must sit between the migration and the first "
        "revision, as the production one does"
    )


def test_staging_reads_the_verdict_from_this_runs_execution():
    """`[0]` has no ordering guarantee: a stale `Succeeded` from an earlier
    deploy would break the poll immediately and the deploy proceed having
    verified nothing."""
    assert "--job-execution-name" in _staging_smoke_block()


def test_a_failed_delete_before_create_is_fatal_in_staging():
    block = _staging_smoke_block()
    before_create = block[: block.index("az containerapp job create")]
    assert "az containerapp job delete" in before_create
    assert "exit 1" in before_create, (
        "a failed delete-before-create is swallowed; the create then upserts "
        "onto the stale job and verifies the OLD key"
    )


def test_a_failing_or_hanging_staging_smoke_blocks_the_rollout():
    block = _staging_smoke_block()
    assert block.count("exit 1") >= 2, (
        "a timed-out smoke must FAIL, not fall through as healthy"
    )
    assert 'if [ "$ST" != "Succeeded" ]' in block


def _deploying_workflows() -> list[tuple[str, str]]:
    """Every workflow that migrates a database AND then rolls out the backend.

    Derived from the workflows' own content, not from a list. `azure-staging.yml`
    is why: it ran a migration and a rollout with NO crypto smoke at all, so a
    manual staging dispatch bypassed the gate entirely — while `ci.yml`, the path
    used every day, gated correctly. That is how a bypass survives review, and a
    hardcoded list of "the workflows we remembered" reproduces it exactly.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"
    if not root.exists():
        return []
    out = []
    for path in sorted(root.glob("*.yml")):
        src = path.read_text()
        migrates = '--command "alembic"' in src
        rolls_out = "az containerapp update" in src or "az containerapp create" in src
        if migrates and rolls_out:
            out.append((path.name, src))
    return out


@pytest.mark.parametrize("name,src", _deploying_workflows())
def test_no_deploy_path_can_bypass_the_crypto_smoke(name, src):
    """THE bypass test. Any workflow that migrates and then deploys must gate."""
    assert "run_crypto_smoke.py" in src, (
        f"{name} runs a migration and rolls out the backend with NO crypto smoke: "
        "a deploy through this path ships whatever the migration did to the "
        "encrypted columns, unverified"
    )


@pytest.mark.parametrize("name,src", _deploying_workflows())
def test_every_deploy_path_gates_in_the_right_order(name, src):
    """Ordering IS the gate.

    migration → smoke → rollout. After the migration has touched encrypted
    columns, and BEFORE a traffic-carrying revision exists, so a failure leaves
    the currently-serving revision untouched. Placed after the rollout it is a
    report: on 2026-08-06 staging served the broken build for fourteen minutes
    before its correctly-failing smoke spoke.
    """
    migrate = src.index('--command "alembic"')
    smoke = src.index("run_crypto_smoke.py")
    # Only lines that EXECUTE a rollout count. The rollback-target step echoes
    # `az containerapp update` into the run summary as the recovery command an
    # on-call is meant to copy, and that text sits before the migration — so
    # matching raw occurrences would read documentation as a rollout and fail a
    # workflow whose ordering is correct.
    rollout = len(src)
    offset = 0
    for line in src.splitlines(keepends=True):
        bare = line.strip()
        executes = not bare.startswith(("echo", "#")) and any(
            m in line for m in ("az containerapp update", "az containerapp create")
        )
        if executes:
            rollout = offset
            break
        offset += len(line)
    assert migrate < smoke, f"{name}: the smoke runs BEFORE the migration it must verify"
    assert smoke < rollout, (
        f"{name}: the smoke runs AFTER the rollout — a wrong key ships, and the "
        "gate reports on a revision that is already serving traffic"
    )


@pytest.mark.parametrize("name,src", _deploying_workflows())
def test_every_deploy_path_fails_closed_on_the_smoke(name, src):
    """A gate that cannot fail the build is a log line."""
    block = src.split("run_crypto_smoke.py", 1)[1].split("\n      - name:", 1)[0]
    # The two exits: the explicit Failed verdict, and the no-verdict timeout.
    assert block.count("exit 1") >= 2, (
        f"{name}: a failing or timed-out smoke does not abort the deploy"
    )
    assert 'if [ "$ST" != "Succeeded" ]' in block, (
        f"{name}: falling out of the poll loop without a verdict is treated as healthy"
    )


@pytest.mark.parametrize("name,src", _deploying_workflows())
def test_every_deploy_path_verifies_this_runs_execution(name, src):
    """`[0]` has no ordering guarantee: a stale `Succeeded` from an earlier
    deploy reads as this run's verdict and the rollout proceeds having verified
    nothing."""
    step = src.split("- name: Post-migration PHI crypto smoke", 1)
    assert len(step) == 2, f"{name}: no step named 'Post-migration PHI crypto smoke'"
    block = step[1].split("\n      - name:", 1)[0]
    assert "--job-execution-name" in block, f"{name}: polls an unordered [0]"


def test_production_records_a_concrete_rollback_target_before_it_changes_anything():
    """"ACA auto-rollback" is not a rollback target.

    PROD-F13 already records that the claim is unfounded without a readiness
    probe; even where it holds it does not tell an on-call WHICH revision to
    return to, and by the time they ask, the system has already changed. The
    name has to be captured before the migration, in the run's own log.
    """
    src = _prod_workflow()
    assert "- name: Record rollback target" in src, (
        "no rollback target is recorded anywhere in the production deploy"
    )
    assert src.index("- name: Record rollback target") < src.index(
        "- name: Run Alembic migration"
    ), "the rollback target is captured after the migration has already run"
    block = src.split("- name: Record rollback target", 1)[1].split("\n      - name:", 1)[0]
    assert "az containerapp ingress traffic set" in block, (
        "the recorded target has no command an on-call can actually run"
    )
    # A first deploy has no predecessor; refusing to proceed would gate nothing.
    assert "exit 0" in block, "a missing predecessor must not fail the deploy"
    assert "downgrade" in block, (
        "no warning that an Alembic downgrade is NOT the data rollback — the "
        "SEC-F11/j4_m10 migrations abort rather than decrypt with a wrong key"
    )


@pytest.mark.parametrize(
    "migration",
    ["j4_m9_secf11_phi_encryption", "j4_m10_p15_residual_phi_encryption"],
)
def test_phi_migrations_bound_how_long_they_wait_for_a_lock(migration):
    """`lock_timeout` bounds the WAIT; `statement_timeout = 0` protects the work.

    A column rewrite takes ACCESS EXCLUSIVE. Without a lock_timeout the
    migration queues behind any open transaction and blocks every reader behind
    it — a deploy that takes the site down while appearing to hang. Without
    `statement_timeout = 0` the opposite: a server-configured timeout kills the
    rewrite half-way. Both are needed, and they pull in opposite directions.
    """
    import pathlib

    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "alembic" / "versions" / f"{migration}.py"
    )
    if not path.exists():
        pytest.skip(f"{migration} not present in this checkout")
    src = path.read_text()
    assert "SET LOCAL lock_timeout" in src, f"{migration}: unbounded lock wait"
    assert "SET LOCAL statement_timeout = 0" in src, (
        f"{migration}: a server statement_timeout can kill the rewrite mid-flight"
    )


def test_no_workflow_leaves_a_job_holding_the_phi_key():
    """Generalised over EVERY workflow, not a list someone has to remember.

    Three workflows create one-off Container Apps Jobs with
    `--secrets enc-keys=...`, and a fourth added next quarter would be found by
    nobody. A job left in place holds the environment's database URL and
    MCP_ENCRYPTION_KEYS between deploys, in a resource with no monitoring,
    readable by any principal with Microsoft.App/jobs/listSecrets on the
    resource group.

    The check is deliberately coarse — "this workflow hands a job the key, so it
    must also delete a job unconditionally" — because a precise one would have
    to parse shell variables out of `-n "$JOB"` and would break on the first
    reasonable refactor. Coarse and always-true beats precise and disabled.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"
    if not root.exists():
        pytest.skip("workflows not present in this checkout")

    offenders = []
    for path in sorted(root.glob("*.yml")):
        src = path.read_text()
        if "enc-keys=" not in src:
            continue
        has_cleanup = any(
            "if: always()" in block.split("\n      - name:", 1)[0]
            and "az containerapp job delete" in block.split("\n      - name:", 1)[0]
            for block in src.split("- name: Remove ")[1:]
        )
        if not has_cleanup:
            offenders.append(path.name)
    assert not offenders, (
        f"{offenders} create a job with the PHI encryption key and never delete "
        "it; the key sits in an unwatched Container Apps Job between deploys"
    )


@pytest.mark.parametrize("name", ["ci.yml", "azure-production.yml"])
def test_every_job_holding_the_phi_key_is_deleted_after_it_runs(name):
    """Both one-off jobs are created with `--secrets enc-keys=...`. Left in
    place they park the environment's PHI master key in a resource nobody
    watches, readable by anything with Microsoft.App/jobs/listSecrets. The
    migration job only started holding the key when PR #137 gave it one — so
    the fix for the key bug would otherwise have widened the key's exposure."""
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / name
    if not path.exists():
        pytest.skip(f"{name} not present in this checkout")
    src = path.read_text()
    for step in ("Remove Alembic migration job", "Remove crypto-smoke job"):
        assert step in src, f"{name}: no cleanup step '{step}'"
        cleanup = src.split(f"- name: {step}", 1)[1].split("\n      - name:", 1)[0]
        assert "if: always()" in cleanup, (
            f"{name}: '{step}' is skipped when the deploy fails — which is "
            "exactly when the residue is left behind"
        )
        assert "az containerapp job delete" in cleanup


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


# ── 8. Empty-database verdict (MCP_CRYPTO_SMOKE_ALLOW_EMPTY) ────────────────
#
# The behavioural decision table needs a real database and lives in
# tests/integration/test_crypto_smoke_postgres.py. What is pinned here is the
# part that must hold without one: the flag defaults OFF, "unknown" never
# becomes "empty", and no deploy path but production can even ask.


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "None", " "])
def test_the_empty_override_is_off_for_anything_but_an_explicit_yes(monkeypatch, value):
    """A templating accident that yields "" or "0" must not enable the branch
    that waives legacy verification. Only an affirmative value counts."""
    monkeypatch.setenv(crypto_smoke.ALLOW_EMPTY_ENV, value)
    assert crypto_smoke.allow_empty_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", " 1 "])
def test_the_empty_override_is_on_only_when_explicitly_set(monkeypatch, value):
    monkeypatch.setenv(crypto_smoke.ALLOW_EMPTY_ENV, value)
    assert crypto_smoke.allow_empty_enabled() is True


def test_the_empty_override_defaults_off_when_unset(monkeypatch):
    monkeypatch.delenv(crypto_smoke.ALLOW_EMPTY_ENV, raising=False)
    assert crypto_smoke.allow_empty_enabled() is False


def test_a_failed_count_is_not_emptiness():
    """THE property. A census that could not read a table knows nothing about
    that table, and 'unknown' resolving to 'empty' is how an override like this
    would come to skip verification on a database it never actually read."""
    assert not crypto_smoke.Census(
        present_empty=("users",), errors=(("notifications", "OperationalError"),)
    ).proves_empty


def test_rows_found_are_not_emptiness():
    assert not crypto_smoke.Census(non_empty=(("users", 3),)).proves_empty


def test_absent_tables_alone_do_not_deny_emptiness():
    """A table whose migration has not run cannot hold rows. That is a known
    state, unlike a failed query, and must stay distinguishable from it."""
    census = crypto_smoke.Census(
        present_empty=("users", "notifications"), absent=("extraction_candidates",)
    )
    assert census.proves_empty


def test_an_all_empty_census_proves_emptiness():
    assert crypto_smoke.Census(present_empty=("users", "notifications")).proves_empty


def test_a_missing_table_is_told_apart_from_a_broken_query():
    """`_is_undefined_table` decides which bucket a failure lands in, and the two
    buckets have opposite consequences for the verdict."""
    import sqlalchemy as sa

    class _Orig(Exception):
        sqlstate = "42P01"

    undefined = sa.exc.ProgrammingError("SELECT 1", {}, _Orig())
    assert crypto_smoke._is_undefined_table(undefined)

    class _Other(Exception):
        sqlstate = "57014"  # query_canceled

    assert not crypto_smoke._is_undefined_table(
        sa.exc.OperationalError("SELECT 1", {}, _Other())
    )


def test_the_census_counts_identity_tables_not_only_phi_columns():
    """A database with accounts but NULL PHI columns is not an empty database.
    Counting only encrypted columns would call it one."""
    assert "users" in crypto_smoke.CENSUS_IDENTITY_TABLES
    assert "patient_profiles" in crypto_smoke.CENSUS_IDENTITY_TABLES


def test_the_extended_roundtrips_cover_every_required_entity():
    """The entities the owner required be exercised even on an empty database."""
    src = inspect.getsource(crypto_smoke)
    for entity in (
        "notification.title",
        "notification.body",
        "meto_message.content",
        "medication_statement.raw_drug_name",
        "extraction_candidate.fields_json",
    ):
        assert f'"{entity}"' in src, f"{entity} is not round-tripped"


def test_an_unbuildable_scaffold_fails_rather_than_skipping():
    """An entity whose parent rows could not be created is UNVERIFIED, and an
    unverified entity must not be silently dropped from the run."""
    src = inspect.getsource(crypto_smoke)
    assert "unavailable:scaffold:" in src
    assert "if model is None:" in src


# ── 9. Only production may ask for the empty-database verdict ───────────────


def test_only_the_production_workflow_mentions_the_empty_override():
    """Not enabled globally, and never for staging: staging is reseeded often,
    so an always-on override there would permanently mute the one check that
    catches a mis-rotation."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"
    for path in sorted(root.glob("*.yml")):
        src = path.read_text()
        if path.name == "azure-production.yml":
            assert crypto_smoke.ALLOW_EMPTY_ENV in src
        else:
            assert crypto_smoke.ALLOW_EMPTY_ENV not in src, (
                f"{path.name} may not enable the empty-database verdict"
            )


def test_production_derives_the_override_from_the_preflight_not_a_literal():
    """A hard-coded `=1` would still be set on the NEXT deploy, when production
    holds rows — and would then permit an unverified pass on a populated
    database. The permission must be recomputed from a live count each time."""
    src = _prod_workflow()
    assert f"{crypto_smoke.ALLOW_EMPTY_ENV}=${{{{ steps.population.outputs.allow_empty }}}}" in src
    assert f"{crypto_smoke.ALLOW_EMPTY_ENV}=1" not in src


def test_the_population_preflight_runs_before_the_smoke():
    """Derived from a count taken BEFORE the verdict it authorises, or it
    authorises nothing."""
    src = _prod_workflow()
    assert src.index("Read-only PHI population preflight") < src.index(
        "Post-migration PHI crypto smoke"
    )


def test_the_population_preflight_defaults_to_denied():
    """Written before anything can fail, so an early exit leaves it denied."""
    src = _prod_workflow()
    block = src.split("Read-only PHI population preflight", 1)[1].split(
        "- name: Remove PHI population job", 1
    )[0]
    assert 'echo "allow_empty=0" >> "$GITHUB_OUTPUT"' in block
    # And it is granted only on an affirmative Succeeded.
    assert 'if [ "$ST" = "Succeeded" ]; then' in block


def test_the_population_preflight_never_receives_the_phi_key():
    """It counts rows; it does not decrypt them. Handing it the key would put the
    production master key in one more job for no verification benefit."""
    src = _prod_workflow()
    block = src.split("Read-only PHI population preflight", 1)[1].split(
        "- name: Remove PHI population job", 1
    )[0]
    # Comments explain WHY the key is absent, so assert over executable lines
    # only — otherwise the explanation would fail the test it explains.
    code = "\n".join(
        line for line in block.splitlines() if not line.strip().startswith("#")
    )
    assert "db-url=$DB_URL" in code
    assert "enc-keys" not in code
    assert "MCP_ENCRYPTION_KEYS" not in code


def test_the_population_job_is_removed_afterwards():
    """It holds the production database URL. Same rule as every other job."""
    src = _prod_workflow()
    block = src.split("- name: Remove PHI population job", 1)[1]
    assert "if: always()" in block.split("run:", 1)[0]
    assert "az containerapp job delete" in block


def test_the_population_preflight_passes_no_dash_prefixed_arg():
    """The az `--args` nargs='*' bug, pinned for the new job too: a dash-prefixed
    token means the job is never created and the step fails on every deploy."""
    src = _prod_workflow()
    block = src.split("Read-only PHI population preflight", 1)[1].split(
        "- name: Remove PHI population job", 1
    )[0]
    args_part = block.split("--args", 1)[1].split("\n", 1)[0]
    tokens = [t.strip('"\\ ') for t in args_part.split() if t.strip('"\\ ')]
    assert tokens and not any(t.startswith("-") for t in tokens), tokens
    assert "run_phi_population.py" in args_part


def test_a_missing_column_is_a_failure_not_an_absent_table():
    """A bare "does not exist" match would also catch `column "x" does not
    exist`, and a table read as absent is a table counted as harmlessly empty —
    while it may hold every row that mattered."""
    import sqlalchemy as sa

    class _MissingColumn(Exception):
        sqlstate = "42703"  # undefined_column

        def __str__(self) -> str:
            return 'column "id" does not exist'

    assert not crypto_smoke._is_undefined_table(
        sa.exc.ProgrammingError("SELECT 1", {}, _MissingColumn())
    )
