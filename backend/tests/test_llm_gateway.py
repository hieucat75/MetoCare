"""LLM Gateway tests (P2 #1).

Covers: provider switch via factory, guardrail BLOCK enforcement in the gateway,
per-user cost cap -> 429, cache hit/miss, and mock determinism.
"""

from __future__ import annotations

import pytest
from app.domain import policies
from app.llm import (
    LLMConfigError,
    LLMMessage,
    LLMRateLimitError,
    get_provider,
    reset_gateway,
    reset_provider,
)
from app.llm.cache import LRUResponseCache, make_key
from app.llm.cost import CostGuard
from app.llm.gateway import LLMGateway

# --------------------------------------------------------------------------- #
# Provider switch (factory)
# --------------------------------------------------------------------------- #

def test_factory_default_is_mock():
    provider = get_provider()
    assert provider.name == "mock"


def test_factory_switch_to_openai_skeleton(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("MCP_LLM_PROVIDER", "openai")
    get_settings.cache_clear()
    reset_provider()
    provider = get_provider()
    assert provider.name == "openai"
    # Skeleton must never make a real call.
    with pytest.raises(LLMConfigError):
        provider.complete([LLMMessage(role="user", content="hi")])
    get_settings.cache_clear()


def test_factory_unknown_provider_raises(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("MCP_LLM_PROVIDER", "does-not-exist")
    get_settings.cache_clear()
    reset_provider()
    with pytest.raises(LLMConfigError):
        get_provider()
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# Mock determinism
# --------------------------------------------------------------------------- #

def test_mock_provider_is_deterministic():
    p = get_provider()
    msgs = [LLMMessage(role="user", content="Tôi nên ăn gì buổi tối?")]
    a = p.complete(msgs)
    b = p.complete(msgs)
    assert a.text == b.text
    assert a.total_tokens == b.total_tokens
    assert "bác sĩ" in a.text  # always points back to a doctor


# --------------------------------------------------------------------------- #
# Guardrail BLOCK enforcement inside the gateway
# --------------------------------------------------------------------------- #

class _UnsafeProvider:
    name = "unsafe"

    def complete(self, messages, *, system=None, max_tokens=512, temperature=0.2):
        from app.llm.base import LLMResponse

        return LLMResponse(
            text="Bạn bị tiểu đường type 2 rồi, nên uống Metformin 500mg.",
            model="unsafe-1",
            prompt_tokens=5,
            completion_tokens=10,
        )


def test_gateway_blocks_unsafe_output(monkeypatch):
    monkeypatch.setattr("app.llm.gateway.get_provider", lambda: _UnsafeProvider())
    gw = LLMGateway(
        cost_guard=CostGuard(max_rpm=100, max_tpm=100000),
        cache=None,
    )
    resp = gw.complete(
        user_id="u1",
        messages=[LLMMessage(role="user", content="Tôi bị bệnh gì?")],
    )
    assert resp.blocked is True
    assert resp.safety_flags
    # The unsafe diagnosis/prescription must NOT survive.
    assert "Metformin" not in resp.text
    assert "type 2" not in resp.text
    assert policies.DISCLAIMER_VI in resp.text


def test_gateway_safe_output_gets_disclaimer():
    gw = LLMGateway(cost_guard=CostGuard(max_rpm=100, max_tpm=100000), cache=None)
    resp = gw.complete(
        user_id="u1",
        messages=[LLMMessage(role="user", content="Tôi nên ăn gì?")],
    )
    assert resp.blocked is False
    assert policies.DISCLAIMER_VI in resp.text


# --------------------------------------------------------------------------- #
# Cost cap -> rate-limit error
# --------------------------------------------------------------------------- #

def test_cost_guard_rpm_cap_raises():
    guard = CostGuard(max_rpm=2, max_tpm=1_000_000)
    guard.check("u1", now=0.0)
    guard.record("u1", 10, now=0.0)
    guard.check("u1", now=0.0)
    guard.record("u1", 10, now=0.0)
    with pytest.raises(LLMRateLimitError) as exc:
        guard.check("u1", now=0.0)
    assert exc.value.kind == "rpm"


def test_cost_guard_tpm_cap_raises():
    guard = CostGuard(max_rpm=1000, max_tpm=50)
    guard.record("u1", 60, now=0.0)
    with pytest.raises(LLMRateLimitError) as exc:
        guard.check("u1", now=0.0)
    assert exc.value.kind == "tpm"


def test_cost_guard_window_slides():
    guard = CostGuard(max_rpm=1, max_tpm=1_000_000)
    guard.check("u1", now=0.0)
    guard.record("u1", 10, now=0.0)
    with pytest.raises(LLMRateLimitError):
        guard.check("u1", now=1.0)
    # After the 60s window the request ages out and is allowed again.
    guard.check("u1", now=61.0)


def test_gateway_cost_cap_maps_to_429(client, patient, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("MCP_LLM_MAX_REQUESTS_PER_MINUTE", "1")
    get_settings.cache_clear()
    reset_gateway()
    reset_provider()
    headers = patient["headers"]
    try:
        r1 = client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={"message": "Tôi nên ăn gì?"},
        )
        assert r1.status_code == 200
        r2 = client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={"message": "Còn buổi sáng thì sao?"},
        )
        assert r2.status_code == 429
        assert "Retry-After" in r2.headers
    finally:
        get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# Cache hit / miss
# --------------------------------------------------------------------------- #

def test_cache_hit_and_miss():
    cache = LRUResponseCache(max_entries=8, ttl_seconds=300)
    gw = LLMGateway(cost_guard=CostGuard(max_rpm=1000, max_tpm=1_000_000), cache=cache)
    msgs = [LLMMessage(role="user", content="Tôi nên ăn gì?")]

    first = gw.complete(user_id="u1", messages=msgs, now=0.0)
    assert first.cached is False
    second = gw.complete(user_id="u1", messages=msgs, now=1.0)
    assert second.cached is True
    assert second.text == first.text

    # Different user => cache miss (key includes user id).
    other = gw.complete(user_id="u2", messages=msgs, now=2.0)
    assert other.cached is False


def test_cache_ttl_expiry():
    cache = LRUResponseCache(max_entries=8, ttl_seconds=10)
    key = make_key(
        provider="mock", model="m", system="s",
        messages=[LLMMessage(role="user", content="x")],
        user_id="u", max_tokens=10, temperature=0.0,
    )
    from app.llm.base import LLMResponse

    cache.put(key, LLMResponse(text="hi", model="m"), now=0.0)
    assert cache.get(key, now=5.0) is not None
    assert cache.get(key, now=20.0) is None  # expired


def test_cache_lru_eviction():
    cache = LRUResponseCache(max_entries=2, ttl_seconds=300)
    from app.llm.base import LLMResponse

    for i in range(3):
        cache.put(f"k{i}", LLMResponse(text=str(i), model="m"), now=0.0)
    assert len(cache) == 2
    assert cache.get("k0", now=0.0) is None  # oldest evicted


def teardown_module(module):
    # Restore clean singletons for the rest of the suite.
    reset_gateway()
    reset_provider()
