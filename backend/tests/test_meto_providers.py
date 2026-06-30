"""Tests for Meto AI provider abstraction layer."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from app.ai.exceptions import (
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.ai.providers.base import (
    ChatMessage,
    ChatResponse,
    ChatStreamChunk,
    ConversationProvider,
    ProviderHealthStatus,
)
from app.ai.registry import CircuitBreaker, CircuitState, ProviderRegistry

# ---------------------------------------------------------------------------
# Mock Provider
# ---------------------------------------------------------------------------

class MockConversationProvider(ConversationProvider):
    """Test mock that implements ConversationProvider."""

    _provider_name = "mock"
    _model_name = "mock-v1"
    _max_context_tokens = 10000
    _supports_streaming = True
    _supports_tool_use = False

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[dict] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def max_context_tokens(self) -> int:
        return self._max_context_tokens

    @property
    def supports_streaming(self) -> bool:
        return self._supports_streaming

    @property
    def supports_tool_use(self) -> bool:
        return self._supports_tool_use

    async def chat(
        self,
        messages,
        system_prompt,
        tools=None,
        temperature=0.3,
        max_tokens=2000,
        stream=False,
    ) -> ChatResponse:
        self.calls.append({"type": "chat", "messages": messages})
        if self.should_fail:
            raise ProviderResponseError("mock", detail="Simulated failure")
        return ChatResponse(
            content="Xin chào! Mình là Meto.",
            tool_calls=None,
            input_tokens=10,
            output_tokens=5,
            model_used="mock-v1",
            finish_reason="stop",
            latency_ms=50,
            provider="mock",
        )

    async def chat_stream(
        self, messages, system_prompt, tools=None, temperature=0.3, max_tokens=2000
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        if self.should_fail:
            raise ProviderResponseError("mock", detail="Stream failure")

        chunks = ["Xin ", "chào! ", "Mình ", "là ", "Meto."]
        for chunk in chunks:
            yield ChatStreamChunk(delta=chunk)
        yield ChatStreamChunk(delta="", is_final=True, total_tokens=15)

    async def cancel(self, request_id: str) -> bool:
        return True

    async def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def health_check(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            provider="mock",
            is_alive=not self.should_fail,
        )


# ---------------------------------------------------------------------------
# Tests: MockConversationProvider
# ---------------------------------------------------------------------------

class TestMockProvider:
    def test_implements_interface(self):
        provider = MockConversationProvider()
        assert provider.provider_name == "mock"
        assert provider.model_name == "mock-v1"
        assert provider.max_context_tokens == 10000
        assert provider.supports_streaming is True

    @pytest.mark.asyncio
    async def test_chat_returns_response(self):
        provider = MockConversationProvider()
        messages = [ChatMessage(role="user", content="Xét nghiệm HbA1c của tôi thế nào?")]
        response = await provider.chat(messages, system_prompt="You are Meto.")
        assert response.content == "Xin chào! Mình là Meto."
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.provider == "mock"
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_chat_stream_yields_chunks(self):
        provider = MockConversationProvider()
        messages = [ChatMessage(role="user", content="Hello")]
        chunks = []
        async for chunk in provider.chat_stream(messages, "system"):
            chunks.append(chunk)
        assert len(chunks) > 0
        assert chunks[-1].is_final is True
        text = "".join(c.delta for c in chunks)
        assert "Meto" in text

    @pytest.mark.asyncio
    async def test_failing_provider_raises_error(self):
        provider = MockConversationProvider(should_fail=True)
        messages = [ChatMessage(role="user", content="Test")]
        with pytest.raises(ProviderResponseError):
            await provider.chat(messages, "system")

    def test_health_check_reflects_state(self):
        provider = MockConversationProvider(should_fail=True)
        health = provider.health_check()
        assert health.is_alive is False


# ---------------------------------------------------------------------------
# Tests: ProviderRegistry + Fallback
# ---------------------------------------------------------------------------

class TestProviderRegistry:
    def test_register_and_get(self):
        registry = ProviderRegistry()
        primary = MockConversationProvider()
        registry.register(primary)
        assert registry.get("mock") is primary

    def test_get_unregistered_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ProviderUnavailableError):
            registry.get("nonexistent")

    @pytest.mark.asyncio
    async def test_call_with_fallback_success(self):
        registry = ProviderRegistry()
        primary = MockConversationProvider()
        primary._provider_name = "claude"
        registry.register(primary)

        result, provider_name, fallback = await registry.call_with_fallback(
            "chat_simple",
            lambda p: p.chat([ChatMessage(role="user", content="Hi")], "system"),
        )
        assert result.content == "Xin chào! Mình là Meto."
        assert fallback is False

    @pytest.mark.asyncio
    async def test_fallback_when_primary_fails(self):
        registry = ProviderRegistry()
        primary = MockConversationProvider(should_fail=True)
        primary._provider_name = "claude"
        fallback_p = MockConversationProvider(should_fail=False)
        fallback_p._provider_name = "openai"

        registry.register(primary)
        registry.register(fallback_p)

        result, provider_name, fallback_used = await registry.call_with_fallback(
            "chat_simple",
            lambda p: p.chat([ChatMessage(role="user", content="Hi")], "system"),
        )
        assert result.content == "Xin chào! Mình là Meto."
        assert fallback_used is True
        assert provider_name == "openai"

    @pytest.mark.asyncio
    async def test_all_providers_fail_raises(self):
        registry = ProviderRegistry()
        p = MockConversationProvider(should_fail=True)
        p._provider_name = "claude"
        registry.register(p)

        with pytest.raises(Exception):  # ProviderUnavailableError or ProviderResponseError
            await registry.call_with_fallback(
                "chat_simple",
                lambda p: p.chat([ChatMessage(role="user", content="Hi")], "system"),
            )


# ---------------------------------------------------------------------------
# Tests: CircuitBreaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.get_state("claude") == CircuitState.CLOSED
        assert cb.is_available("claude") is True

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker()
        cb.FAILURE_THRESHOLD = 3
        for _ in range(3):
            cb.record_failure("claude")
        assert cb.get_state("claude") == CircuitState.OPEN
        assert cb.is_available("claude") is False

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker()
        cb.FAILURE_THRESHOLD = 1
        cb.OPEN_TIMEOUT_SECONDS = 0  # Immediate timeout for test
        cb.record_failure("claude")
        assert cb.get_state("claude") == CircuitState.OPEN
        # After timeout, should transition to HALF_OPEN
        assert cb.is_available("claude") is True
        assert cb.get_state("claude") == CircuitState.HALF_OPEN

    def test_closes_after_successes_in_half_open(self):
        cb = CircuitBreaker()
        cb.FAILURE_THRESHOLD = 1
        cb.OPEN_TIMEOUT_SECONDS = 0
        cb.SUCCESS_THRESHOLD = 2
        cb.record_failure("claude")
        cb.is_available("claude")  # Trigger half-open
        cb.record_success("claude")
        cb.record_success("claude")
        assert cb.get_state("claude") == CircuitState.CLOSED

    def test_returns_to_open_on_failure_in_half_open(self):
        cb = CircuitBreaker()
        cb.FAILURE_THRESHOLD = 1
        cb.OPEN_TIMEOUT_SECONDS = 0
        cb.record_failure("claude")
        cb.is_available("claude")  # Trigger half-open
        cb.record_failure("claude")  # Fail in half-open
        assert cb.get_state("claude") == CircuitState.OPEN


# ---------------------------------------------------------------------------
# Tests: NineRouterProvider
# ---------------------------------------------------------------------------

class TestNineRouterProvider:
    """Unit tests for NineRouterProvider."""

    def test_nine_router_provider_implements_interface(self):
        """NineRouterProvider is a ConversationProvider."""
        from app.ai.providers.nine_router import NineRouterProvider

        assert issubclass(NineRouterProvider, ConversationProvider)

    def test_nine_router_provider_name_default(self):
        """Default provider_name contains 'nine_router'."""
        from app.ai.providers.nine_router import NineRouterProvider

        p = NineRouterProvider(
            base_url="http://localhost:9999",
            api_key="test",
            model="cc/test-model",
        )
        assert "nine_router" in p.provider_name

    def test_nine_router_provider_name_custom(self):
        """Custom provider_name is accepted."""
        from app.ai.providers.nine_router import NineRouterProvider

        p = NineRouterProvider(
            base_url="http://localhost:9999",
            api_key="test",
            model="cc/claude-sonnet-4-6",
            provider_name="nine_router_claude",
        )
        assert p.provider_name == "nine_router_claude"

    def test_nine_router_model_name(self):
        """model_name returns the configured model."""
        from app.ai.providers.nine_router import NineRouterProvider

        p = NineRouterProvider(
            base_url="http://localhost:9999",
            api_key="test",
            model="cc/claude-sonnet-4-6",
        )
        assert p.model_name == "cc/claude-sonnet-4-6"

    def test_nine_router_capabilities(self):
        """Reports correct capabilities."""
        from app.ai.providers.nine_router import NineRouterProvider

        p = NineRouterProvider(
            base_url="http://localhost:9999",
            api_key="test",
            model="cc/test",
        )
        assert p.max_context_tokens == 200_000
        assert p.supports_streaming is True
        assert p.supports_tool_use is True

    def test_nine_router_health_check_initial(self):
        """Health check starts healthy."""
        from app.ai.providers.nine_router import NineRouterProvider

        p = NineRouterProvider(
            base_url="http://localhost:9999",
            api_key="test",
            model="cc/test",
        )
        health = p.health_check()
        assert health.provider in p.provider_name or p.provider_name in health.provider
        assert health.is_alive is True

    def test_nine_router_registered_when_key_present(self, monkeypatch):
        """NineRouter providers appear in registry when key is manually registered."""
        from app.ai import registry as reg_module
        from app.ai.providers.nine_router import NineRouterProvider

        # Create a fresh registry and register NineRouterProvider directly
        # (simulates what init_registry_from_settings does when the key is set)
        fresh_registry = reg_module.ProviderRegistry()
        fresh_registry.register(
            NineRouterProvider(
                base_url="http://localhost:9999",
                api_key="test-key-for-registry",
                model="cc/claude-sonnet-4-6",
                provider_name="nine_router_claude",
            )
        )
        fresh_registry.register(
            NineRouterProvider(
                base_url="http://localhost:9999",
                api_key="test-key-for-registry",
                model="cx/gpt-5.4-mini",
                provider_name="nine_router_gpt",
            )
        )

        providers = fresh_registry.get_available_providers("chat_simple")
        names = [p.provider_name for p in providers]
        assert any("nine_router" in n for n in names), (
            f"Expected nine_router providers in {names!r}"
        )

    def test_nine_router_routing_preference(self, monkeypatch):
        """nine_router_claude is listed first in routing chain for chat_simple."""
        from app.ai.registry import RoutingPolicy

        policy = RoutingPolicy()
        chain = policy.get_provider_chain("chat_simple")
        assert chain[0] == "nine_router_claude", (
            f"nine_router_claude must be first in chat_simple chain. Got: {chain}"
        )

    def test_nine_router_fallback_in_routing_chain(self):
        """nine_router_gpt is listed as second-priority fallback."""
        from app.ai.registry import RoutingPolicy

        policy = RoutingPolicy()
        chain = policy.get_provider_chain("chat_simple")
        assert "nine_router_gpt" in chain, f"nine_router_gpt not in chain: {chain}"
        assert chain.index("nine_router_gpt") < chain.index("claude"), (
            f"nine_router_gpt should come before claude. Chain: {chain}"
        )
