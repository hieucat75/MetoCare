"""The production workflow must satisfy every production boot guard.

2026-08-10: production rolled out and the backend would not start —
`validate_required_env_vars` refused `MFA enforcement off`, because
`azure-production.yml` never set `MCP_MFA_ENFORCEMENT_ENABLED`. The guard was
tested. The workflow's compliance with it was not, and nothing connected the
two, so the gap could only ever surface as a failed production rollout.

Fixing that one variable in isolation would have moved the failure exactly one
guard down: `document_scan_mode` defaults to `"skip"`, which production also
refuses. So the test that matters is not "is this one variable set" — it is
**build a Settings out of what the workflow actually declares, and boot it**.
Any future production guard is then covered on the day it is written, without
anyone remembering to add a case here.

All values here are non-secret placeholders.
"""

from __future__ import annotations

import os
import pathlib
import re
from unittest import mock

import pytest
from app.core.config import Settings

_REAL_SECRET = "x" * 48
_REAL_ENC = "0" * 43 + "="

_WORKFLOWS = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"
_PRODUCTION = _WORKFLOWS / "azure-production.yml"

# Values the workflow supplies at runtime rather than literally. They cannot be
# resolved here, so the corresponding Settings field keeps its test placeholder.
_UNRESOLVABLE = ("secretref:", "${{", "$(", "${")


def _production_workflow() -> str:
    if not _PRODUCTION.exists():
        pytest.skip("azure-production.yml not present in this checkout")
    return _PRODUCTION.read_text()


def _backend_rollout_block() -> str:
    """JUST the backend rollout step — bounded at the next step.

    Bounded because the migration and smoke jobs also set `MCP_ENV=production`,
    and asserting over the whole file would let one of those satisfy an
    assertion about what the SERVING container receives.
    """
    src = _production_workflow()
    marker = "- name: Deploy backend to ACA"
    assert marker in src, "the backend rollout step was renamed"
    return src.split(marker, 1)[1].split("\n      - name:", 1)[0]


def _declared_env(block: str) -> dict[str, str]:
    """Every `MCP_KEY=value` the block declares, minus the unresolvable ones."""
    found: dict[str, str] = {}
    for key, value in re.findall(r"\b(MCP_[A-Z0-9_]+)=(\S*)", block):
        if not value or value.startswith(_UNRESOLVABLE):
            continue
        found[key] = value.rstrip("\\").strip('"')
    return found


def _settings_from_workflow(**overrides) -> Settings:
    """A Settings built from what the production rollout actually declares.

    Constructed in an ISOLATED environment. `Settings` reads `.env` and the
    process environment, and this repository's `.env` carries the build-phase
    relaxed password policy — so without isolation this test would report that
    production cannot boot because of a file that is never deployed, and would
    equally hide a real gap behind a developer's local override. Production sees
    exactly two things: what the workflow declares, and the code defaults.
    """
    declared = _declared_env(_backend_rollout_block())
    kwargs: dict[str, object] = {
        "database_url": "sqlite://",
        "secret_key": _REAL_SECRET,
        "encryption_keys": _REAL_ENC,
    }
    reserved = {"database_url", "secret_key", "encryption_keys"}
    valid = set(Settings.model_fields)
    for key, value in declared.items():
        field = key[len("MCP_") :].lower()
        if field in valid and field not in reserved:
            kwargs[field] = value
    kwargs.update(overrides)
    with mock.patch.dict(os.environ, {}, clear=True):
        return Settings(_env_file=None, **kwargs)


def _validate_from_workflow(**overrides) -> None:
    """Build AND validate the declared production config under one isolation.

    Validation has to happen inside the cleared environment for the same reason
    construction does. A guard that reads the process environment — the OCR
    data-boundary check reads ``AZURE_DOC_INTEL_ENDPOINT`` — would otherwise see
    the developer's ``.env``, which is never deployed, so this test would report
    on a local machine's state instead of on what production declares.
    """
    with mock.patch.dict(os.environ, {}, clear=True):
        _settings_from_workflow(**overrides).validate_required_env_vars()


# ── The test the 2026-08-10 failure would have failed ───────────────────────


def test_the_production_workflow_config_actually_boots():
    """Generic by design: it names neither MFA nor the scan mode.

    Any production guard added later is covered the day it is written, because
    this asserts the whole declared configuration passes startup validation
    rather than spot-checking the variables someone remembered.
    """
    _validate_from_workflow()


def test_production_sets_mfa_enforcement():
    assert _declared_env(_backend_rollout_block()).get("MCP_MFA_ENFORCEMENT_ENABLED") == "true"


def test_production_does_not_ship_an_unscanned_document_pipeline():
    """`skip` accepts uploads and parses them server-side with no AV."""
    mode = _declared_env(_backend_rollout_block()).get("MCP_DOCUMENT_SCAN_MODE")
    assert mode and mode.lower() != "skip", mode


def test_production_declares_no_relaxed_auth_override():
    """`MCP_ALLOW_RELAXED_AUTH` is a staging build-phase escape hatch. Production
    ignores it, but declaring it would tell the next reader the opposite."""
    block = _backend_rollout_block()
    assert "MCP_ALLOW_RELAXED_AUTH" not in block
    assert "MCP_SKIP_MFA_IN_DEV" not in block


# ── Fail-closed is preserved, not traded away ───────────────────────────────


def test_mfa_off_still_refuses_to_start_in_production():
    """The remediation adds a variable. It must not have softened the guard."""
    with pytest.raises(RuntimeError, match="relaxed authentication"):
        _validate_from_workflow(mfa_enforcement_enabled=False)


def test_a_skipped_document_scan_still_refuses_to_start_in_production():
    with pytest.raises(RuntimeError, match="MCP_DOCUMENT_SCAN_MODE"):
        _validate_from_workflow(document_scan_mode="skip")


def test_staging_is_configured_independently_of_production():
    """Staging deliberately runs relaxed during the build phase. Production must
    not inherit that, and staging must not silently inherit production's
    tightening either — each is set where it is deployed."""
    ci = _WORKFLOWS / "ci.yml"
    if not ci.exists():
        pytest.skip("ci.yml not present")
    staging = ci.read_text()
    assert "MCP_MFA_ENFORCEMENT_ENABLED=true" in _backend_rollout_block()
    assert "MCP_ENV=production" not in staging


# ── Rollback must describe what actually happens ────────────────────────────


def _rollback_block() -> str:
    src = _production_workflow()
    return src.split("- name: Record rollback target", 1)[1].split(
        "- name: Pre-migration soft-delete audit", 1
    )[0]


def test_no_workflow_claims_automatic_revision_rollback():
    """The sentence that was printed while production was down and the previous
    revision had already been destroyed."""
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        code = "\n".join(
            line
            for line in path.read_text().splitlines()
            if not line.strip().startswith("#")
        )
        assert "auto-rollback" not in code, f"{path.name} still claims auto-rollback"
        assert "keeps previous healthy revision" not in code, path.name


def test_the_rollback_target_records_both_tiers():
    """The frontend was never recorded, so after the failed run its previous
    image was unknown and it could not be rolled back at all."""
    block = _rollback_block()
    assert "$BACKEND_APP" in block and "$FRONTEND_APP" in block
    assert "PREV_IMG" in block and "FE_PREV_IMG" in block


def test_the_rollback_strategy_reflects_the_actual_revision_mode():
    """In Single mode the rollout DESTROYS the previous revision, so
    `ingress traffic set` targets something that no longer exists. The recorded
    IMAGE survives; the command must use it."""
    block = _rollback_block()
    assert "activeRevisionsMode" in block, "the mode is never read"
    assert 'if [ "$MODE" = "Single" ]; then' in block, "the mode is read but not used"
    single = block.split('if [ "$MODE" = "Single" ]; then', 1)[1].split("else", 1)[0]
    assert "containerapp update" in single and "--image" in single
    # The prose explains WHY traffic-shifting fails here, so match the command
    # form rather than the phrase — otherwise the explanation fails the test.
    assert "az containerapp ingress traffic set" not in single, (
        "Single mode cannot roll back by shifting traffic"
    )


# ── Frontend build args must actually reach the build ───────────────────────


def _frontend_dockerfile() -> str:
    df = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "Dockerfile"
    if not df.exists():
        pytest.skip("frontend/Dockerfile not present")
    return df.read_text()


def test_every_next_public_build_arg_is_declared_in_the_dockerfile():
    """An undeclared ARG is silently DISCARDED by Docker.

    All three workflows passed `--build-arg NEXT_PUBLIC_APP_ENV` for months and
    every one was dropped, because the Dockerfile never declared it. Nothing
    failed: the build succeeded, the value was empty, and `EnvironmentBanner`
    fell back to non-production — so production told real users on
    app.metocare.me that their data was not real.

    Generic on purpose: the next NEXT_PUBLIC_* variable someone adds to a
    workflow is covered without anyone remembering this test exists.
    """
    dockerfile = _frontend_dockerfile()
    declared = set(re.findall(r"^ARG\s+(NEXT_PUBLIC_[A-Z0-9_]+)", dockerfile, re.M))

    for path in sorted(_WORKFLOWS.glob("*.yml")):
        src = path.read_text()
        if "build-args:" not in src:
            continue
        for block in src.split("build-args:")[1:]:
            # The build-args block ends at the next key at lower indentation.
            head = block.split("\n          tags:", 1)[0]
            for name in re.findall(r"^\s*(NEXT_PUBLIC_[A-Z0-9_]+)=", head, re.M):
                assert name in declared, (
                    f"{path.name} passes --build-arg {name}, but frontend/Dockerfile "
                    f"never declares it — Docker discards it silently. Declared: {sorted(declared)}"
                )


def test_the_environment_banner_variable_is_declared():
    """The specific one that reached users, pinned by name as well as by rule."""
    assert re.search(r"^ARG\s+NEXT_PUBLIC_APP_ENV", _frontend_dockerfile(), re.M)


def _frontend_rollout_block() -> str:
    src = _production_workflow()
    marker = "- name: Deploy frontend to ACA"
    assert marker in src, "the frontend rollout step was renamed"
    return src.split(marker, 1)[1].split("\n      - name:", 1)[0]


def test_production_frontend_sets_the_environment_at_runtime():
    """`EnvironmentBanner` is a Server Component, so it reads process.env at
    RUNTIME for dynamically rendered pages. Staging set this on its container;
    production did not, which is why the banner said "không xác định" rather
    than nothing at all. Build-time declaration alone is not sufficient."""
    block = _frontend_rollout_block()
    assert "NEXT_PUBLIC_APP_ENV=production" in block, (
        "the production frontend container does not receive NEXT_PUBLIC_APP_ENV"
    )
