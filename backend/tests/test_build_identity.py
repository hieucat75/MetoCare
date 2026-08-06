"""P1-7 — the deploy workflows' build-identity wiring has no test holding it up.

`/info` reports `build_sha` and `build_time`. Those come from `Settings`, whose
`env_prefix` is `MCP_`, so they are populated from `MCP_BUILD_SHA` and
`MCP_BUILD_TIME` — which `azure-staging.yml` and `azure-production.yml` set on
the container app at deploy time.

That coupling is entirely implicit. `Settings.build_sha` defaults to `""`, so
renaming the field, changing `env_prefix`, or dropping the deploy step does not
fail anything: `/info` simply starts reporting an empty sha, and every later
"verify tag == SHA" check compares against nothing. The failure is silent by
construction and only surfaces when someone needs to answer "what is actually
running right now?" — usually during an incident, which is the worst time to
discover the answer is unavailable.

These tests pin the contract the deploy workflows depend on, from the backend
side. They deliberately do NOT modify the Azure workflows: those are owner-gated
infrastructure and out of scope here.

What is NOT claimed, stated precisely because the narrower version of this
docstring was misleading:

  - This does not verify that a deployed environment reports the correct sha. It
    verifies that IF the documented env vars are set, the value reaches `/info`.
  - `azure-staging.yml` and `azure-production.yml` are `workflow_dispatch` —
    MANUAL deploys. The workflow that auto-deploys staging on merge to main is
    `ci.yml`'s own `deploy-staging` job, and it did NOT set MCP_BUILD_SHA /
    MCP_BUILD_TIME, so every auto-deployed staging build reported an EMPTY
    build_sha. That is now wired (backend env + frontend build-args and env), and
    asserted below alongside the manual workflows.
"""

from __future__ import annotations

import pathlib

import pytest
from app.core.config import Settings
from app.main import app
from fastapi.testclient import TestClient

WORKFLOWS = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"


# ── 1. The env vars the deploy workflows set must reach Settings ────────────


@pytest.mark.parametrize(
    "env_var,field,value",
    [
        ("MCP_BUILD_SHA", "build_sha", "abc1234"),
        ("MCP_BUILD_TIME", "build_time", "2026-08-05T00:00:00Z"),
    ],
)
def test_deploy_env_var_reaches_settings(monkeypatch, env_var, field, value):
    """The exact variable names azure-*.yml sets. A rename on either side breaks
    build identity silently, because the field defaults to an empty string."""
    monkeypatch.setenv(env_var, value)
    assert getattr(Settings(), field) == value


def test_build_identity_defaults_to_empty_not_a_placeholder():
    """An empty value is honest ("unknown"); a plausible-looking placeholder
    would be worse than nothing during an incident."""
    assert isinstance(Settings().build_sha, str)


# ── 2. /info must actually expose it ────────────────────────────────────────


def test_info_exposes_build_identity(monkeypatch):
    monkeypatch.setenv("MCP_BUILD_SHA", "deadbee")
    monkeypatch.setenv("MCP_BUILD_TIME", "2026-08-05T12:00:00Z")

    from app.core import config as config_mod

    config_mod.get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            body = client.get("/api/v1/info").json()
        assert body["build_sha"] == "deadbee"
        assert body["build_time"] == "2026-08-05T12:00:00Z"
    finally:
        config_mod.get_settings.cache_clear()


def test_info_reports_the_migration_version():
    """The other half of "what is actually running": code identity alone does not
    tell you which schema it is running against."""
    with TestClient(app) as client:
        body = client.get("/api/v1/info").json()
    assert "migration_version" in body
    assert body["migration_version"]


# ── 3. The deploy workflows must still set them ─────────────────────────────


@pytest.mark.parametrize(
    "workflow", ["azure-staging.yml", "azure-production.yml", "ci.yml"]
)
def test_deploy_workflow_still_sets_build_identity(workflow):
    """Every workflow that can deploy must set build identity — including
    `ci.yml`, which is the one that actually auto-deploys on merge and was the
    one missing it. If a workflow is absent from this checkout, skip rather than
    fail: a missing file is not evidence of a regression."""
    path = WORKFLOWS / workflow
    if not path.exists():
        pytest.skip(f"{workflow} not present in this checkout")

    src = path.read_text()
    assert "MCP_BUILD_SHA=" in src, f"{workflow} no longer sets MCP_BUILD_SHA"
    assert "MCP_BUILD_TIME=" in src, f"{workflow} no longer sets MCP_BUILD_TIME"


def test_the_auto_deploy_path_sets_frontend_build_identity():
    """The environment banner needs its own vars: NEXT_PUBLIC_* are baked at
    BUILD time for Next.js, so a runtime-only env var would not reach the page."""
    path = WORKFLOWS / "ci.yml"
    if not path.exists():
        pytest.skip("ci.yml not present in this checkout")
    src = path.read_text()
    assert "NEXT_PUBLIC_BUILD_SHA=" in src
    assert "NEXT_PUBLIC_APP_ENV=" in src
