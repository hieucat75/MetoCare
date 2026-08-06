"""Launch-readiness hardening for the Meto AI surface.

Covers three confirmed P1 findings:

* **AI-F2** (`07-AI-SAFETY-EVALUATION.md` §7) — PHI must only ever reach an
  explicitly allow-listed provider. Fail-closed outside dev/test.
* **PROD-F10** — the provider retry budget must not outlive the gunicorn worker
  timeout; the whole call chain is bounded by `settings.meto_timeout_seconds`.
* **PROD-F11** — `/meto/chat` and `/meto/chat/stream` must be rate limited and
  capped per user per day.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.ai.exceptions import ProviderTimeoutError
from app.ai.providers.base import ConversationProvider
from app.ai.registry import ProviderRegistry
from app.core.config import get_settings


@contextlib.contextmanager
def _settings_override(**overrides):
    settings = get_settings()
    previous = {k: getattr(settings, k) for k in overrides}
    for key, value in overrides.items():
        object.__setattr__(settings, key, value)
    try:
        yield settings
    finally:
        for key, value in previous.items():
            object.__setattr__(settings, key, value)


def _fake_provider(name: str) -> ConversationProvider:
    provider = MagicMock(spec=ConversationProvider)
    provider.provider_name = name
    provider.model_name = f"{name}-model"
    return provider


def _registry_with(*names: str) -> ProviderRegistry:
    registry = ProviderRegistry()
    for name in names:
        registry.register(_fake_provider(name))
    return registry


# --------------------------------------------------------------------------- #
# AI-F2 — provider allow-list
# --------------------------------------------------------------------------- #


def test_provider_not_in_allowlist_is_never_selected():
    registry = _registry_with("nine_router_claude", "openrouter_primary", "deepseek")

    with _settings_override(ai_allowed_providers="nine_router_claude"):
        names = [p.provider_name for p in registry.get_available_providers("chat_simple")]

    assert names == ["nine_router_claude"]
    assert "deepseek" not in names


def test_allowlist_accepts_comma_separated_list_with_spaces():
    registry = _registry_with("nine_router_claude", "openrouter_primary", "deepseek")

    with _settings_override(ai_allowed_providers=" nine_router_claude , openrouter_primary "):
        names = [p.provider_name for p in registry.get_available_providers("chat_simple")]

    assert names == ["nine_router_claude", "openrouter_primary"]


def test_empty_allowlist_fails_closed_outside_dev_and_test():
    registry = _registry_with("nine_router_claude", "deepseek")

    with _settings_override(ai_allowed_providers="", env="production"):
        assert registry.get_available_providers("chat_simple") == []

    with _settings_override(ai_allowed_providers="", env="staging"):
        assert registry.get_available_providers("chat_simple") == []


def test_empty_allowlist_is_permissive_in_dev_and_test():
    registry = _registry_with("nine_router_claude", "deepseek")

    with _settings_override(ai_allowed_providers="", env="test"):
        assert len(registry.get_available_providers("chat_simple")) == 2

    with _settings_override(ai_allowed_providers="", env="dev"):
        assert len(registry.get_available_providers("chat_simple")) == 2


@pytest.mark.asyncio
async def test_allowlist_blocking_every_provider_raises_provider_unavailable():
    from app.ai.exceptions import ProviderUnavailableError

    registry = _registry_with("deepseek")

    with _settings_override(ai_allowed_providers="nine_router_claude"):
        with pytest.raises(ProviderUnavailableError):
            await registry.call_with_fallback("chat_simple", AsyncMock())


# --------------------------------------------------------------------------- #
# PROD-F10 — provider chain timeout budget
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_provider_chain_is_bounded_by_meto_timeout():
    registry = _registry_with("nine_router_claude", "nine_router_gpt")

    async def slow_call(_provider):
        await asyncio.sleep(5)
        return "never"

    with _settings_override(meto_timeout_seconds=0.1, ai_allowed_providers=""):
        started = asyncio.get_running_loop().time()
        with pytest.raises(ProviderTimeoutError):
            await registry.call_with_fallback("chat_simple", slow_call)
        elapsed = asyncio.get_running_loop().time() - started

    # Whole chain (2 providers) is bounded, not each attempt.
    assert elapsed < 2.0


@pytest.mark.asyncio
async def test_fast_provider_still_succeeds_within_timeout():
    registry = _registry_with("nine_router_claude")

    async def fast_call(_provider):
        return "ok"

    with _settings_override(meto_timeout_seconds=5, ai_allowed_providers=""):
        result, name, fallback = await registry.call_with_fallback("chat_simple", fast_call)

    assert result == "ok"
    assert name == "nine_router_claude"
    assert fallback is False


# --------------------------------------------------------------------------- #
# PROD-F11 — rate limiting + per-user daily cap
# --------------------------------------------------------------------------- #


def test_meto_chat_is_rate_limited(client, patient):
    body = {"message": "xin chào", "screen_id": "dashboard"}
    with _settings_override(ratelimit_auth_capacity=3):
        codes = [
            client.post("/api/v1/meto/chat", headers=patient["headers"], json=body).status_code
            for _ in range(8)
        ]
    assert 429 in codes


def test_meto_chat_stream_is_rate_limited(client, patient):
    body = {"message": "xin chào", "screen_id": "dashboard"}
    with _settings_override(ratelimit_auth_capacity=3):
        codes = [
            client.post(
                "/api/v1/meto/chat/stream", headers=patient["headers"], json=body
            ).status_code
            for _ in range(8)
        ]
    assert 429 in codes


def _seed_meto_messages(db, user_id: str, count: int) -> None:
    from app.models.meto import MetoConversation, MetoMessage

    conv = MetoConversation(user_id=user_id, screen_id="dashboard")
    db.add(conv)
    db.flush()
    for i in range(count):
        db.add(
            MetoMessage(
                conversation_id=conv.id,
                role="user",
                content=f"m{i}",
                created_at=dt.datetime.now(dt.UTC),
            )
        )
    db.commit()


def test_meto_chat_daily_cap_blocks_after_limit(client, db, patient):
    _seed_meto_messages(db, patient["user_id"], 2)

    with _settings_override(meto_daily_message_cap=2):
        resp = client.post(
            "/api/v1/meto/chat",
            headers=patient["headers"],
            json={"message": "xin chào", "screen_id": "dashboard"},
        )

    assert resp.status_code == 429, resp.text


def test_meto_chat_daily_cap_allows_under_limit(client, db, patient):
    _seed_meto_messages(db, patient["user_id"], 1)

    with _settings_override(meto_daily_message_cap=50):
        resp = client.post(
            "/api/v1/meto/chat",
            headers=patient["headers"],
            json={"message": "xin chào", "screen_id": "dashboard"},
        )

    assert resp.status_code != 429, resp.text
