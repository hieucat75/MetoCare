"""Meto AI — Provider registry, routing, and circuit breaker.

Implements:
- ModelRegistry: register providers + capabilities
- RoutingPolicy: task_type → provider selection order
- CircuitBreaker: per-provider open/half-open/closed states
- ProviderRegistry: get concrete provider instances by name
"""

from __future__ import annotations

import enum
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.ai.exceptions import CircuitBreakerOpenError, ProviderUnavailableError
from app.ai.providers.base import ConversationProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------

@dataclass
class ModelRegistration:
    model_id: str
    provider: str
    capabilities: list[str]
    context_window: int
    input_cost_per_1k_tokens: float
    output_cost_per_1k_tokens: float
    supports_streaming: bool
    supports_tool_use: bool
    supports_vision: bool
    tier: str  # "primary" | "fallback" | "tertiary" | "local"
    is_active: bool


MODEL_REGISTRY: dict[str, ModelRegistration] = {
    "claude-sonnet-4-5": ModelRegistration(
        model_id="claude-sonnet-4-5",
        provider="claude",
        capabilities=["conversation", "reasoning", "tool_use"],
        context_window=200_000,
        input_cost_per_1k_tokens=0.003,
        output_cost_per_1k_tokens=0.015,
        supports_streaming=True,
        supports_tool_use=True,
        supports_vision=False,
        tier="primary",
        is_active=True,
    ),
    "gpt-4o": ModelRegistration(
        model_id="gpt-4o",
        provider="openai",
        capabilities=["conversation", "vision", "tool_use"],
        context_window=128_000,
        input_cost_per_1k_tokens=0.0025,
        output_cost_per_1k_tokens=0.010,
        supports_streaming=True,
        supports_tool_use=True,
        supports_vision=True,
        tier="fallback",
        is_active=True,
    ),
}


# ---------------------------------------------------------------------------
# Routing Policy
# ---------------------------------------------------------------------------

class RoutingPolicy:
    """Rules-based routing: task type → provider selection order."""

    TASK_TYPE_RULES: dict[str, list[str]] = {
        "chat_simple": ["nine_router_claude", "nine_router_gpt", "claude", "openai"],
        "chat_complex_reasoning": ["nine_router_claude", "nine_router_gpt", "claude", "openai"],
        "chat_tool_use": ["nine_router_claude", "nine_router_gpt", "claude", "openai"],
        "clinical_reasoning": ["nine_router_claude", "nine_router_gpt", "claude", "openai"],
        "content_moderation": ["nine_router_gpt", "nine_router_claude", "openai", "claude"],
        "medical_scope_check": ["nine_router_claude", "claude"],
        "simple_qa": ["nine_router_claude", "nine_router_gpt", "claude", "openai"],
    }

    def get_provider_chain(self, task_type: str) -> list[str]:
        return self.TASK_TYPE_RULES.get(task_type, ["claude", "openai"])


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitState(enum.StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _ProviderCircuit:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    open_since: float = 0.0


class CircuitBreaker:
    """Classic circuit breaker per provider.

    CLOSED  → normal operation
    OPEN    → provider failing; reject all calls for OPEN_TIMEOUT seconds
    HALF_OPEN → test if provider recovered
    """

    FAILURE_THRESHOLD = 5
    SUCCESS_THRESHOLD = 2
    OPEN_TIMEOUT_SECONDS = 60

    def __init__(self) -> None:
        self._circuits: dict[str, _ProviderCircuit] = {}

    def _get_circuit(self, provider: str) -> _ProviderCircuit:
        if provider not in self._circuits:
            self._circuits[provider] = _ProviderCircuit()
        return self._circuits[provider]

    def is_available(self, provider: str) -> bool:
        circuit = self._get_circuit(provider)
        if circuit.state == CircuitState.CLOSED:
            return True
        if circuit.state == CircuitState.OPEN:
            elapsed = time.monotonic() - circuit.open_since
            if elapsed >= self.OPEN_TIMEOUT_SECONDS:
                logger.info("Circuit HALF_OPEN for provider: %s", provider)
                circuit.state = CircuitState.HALF_OPEN
                circuit.success_count = 0
                return True
            return False
        # HALF_OPEN: allow limited traffic
        return True

    def record_success(self, provider: str) -> None:
        circuit = self._get_circuit(provider)
        if circuit.state == CircuitState.HALF_OPEN:
            circuit.success_count += 1
            if circuit.success_count >= self.SUCCESS_THRESHOLD:
                logger.info("Circuit CLOSED for provider: %s", provider)
                circuit.state = CircuitState.CLOSED
                circuit.failure_count = 0
                circuit.success_count = 0
        elif circuit.state == CircuitState.CLOSED:
            circuit.failure_count = max(0, circuit.failure_count - 1)

    def record_failure(self, provider: str) -> None:
        circuit = self._get_circuit(provider)
        circuit.failure_count += 1
        if circuit.state == CircuitState.HALF_OPEN:
            # Failed in half-open → go back to OPEN
            circuit.state = CircuitState.OPEN
            circuit.open_since = time.monotonic()
            logger.warning("Circuit re-OPENED for provider: %s (half-open failed)", provider)
        elif circuit.failure_count >= self.FAILURE_THRESHOLD:
            circuit.state = CircuitState.OPEN
            circuit.open_since = time.monotonic()
            logger.warning("Circuit OPENED for provider: %s (failures: %d)", provider, circuit.failure_count)

    def get_state(self, provider: str) -> CircuitState:
        return self._get_circuit(provider).state


# ---------------------------------------------------------------------------
# Provider Registry
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """Central registry that holds live provider instances and routes calls."""

    def __init__(self) -> None:
        self._providers: dict[str, ConversationProvider] = {}
        self._circuit_breaker = CircuitBreaker()
        self._routing = RoutingPolicy()

    def register(self, provider: ConversationProvider) -> None:
        self._providers[provider.provider_name] = provider
        logger.info("Registered provider: %s (%s)", provider.provider_name, provider.model_name)

    def get(self, provider_name: str) -> ConversationProvider:
        if provider_name not in self._providers:
            raise ProviderUnavailableError(provider_name, "not registered")
        return self._providers[provider_name]

    def get_available_providers(self, task_type: str = "chat_simple") -> list[ConversationProvider]:
        """Return providers in priority order, skipping unavailable ones."""
        chain = self._routing.get_provider_chain(task_type)
        result = []
        for name in chain:
            if name in self._providers and self._circuit_breaker.is_available(name):
                result.append(self._providers[name])
        return result

    async def call_with_fallback(
        self,
        task_type: str,
        call_fn: Callable[[ConversationProvider], Any],
    ) -> tuple[Any, str, bool]:
        """Call the first available provider, falling back on failure.

        Returns: (result, provider_name_used, fallback_used)
        """
        providers = self.get_available_providers(task_type)
        if not providers:
            raise ProviderUnavailableError("all", "no providers available")

        providers[0].provider_name
        fallback_used = False

        for i, provider in enumerate(providers):
            name = provider.provider_name
            try:
                result = await call_fn(provider)
                self._circuit_breaker.record_success(name)
                if i > 0:
                    fallback_used = True
                logger.debug(
                    "Provider %s succeeded for task %s (fallback=%s)",
                    name, task_type, fallback_used,
                )
                return result, name, fallback_used
            except CircuitBreakerOpenError:
                logger.info("Circuit open for %s, trying next", name)
                continue
            except Exception as exc:
                self._circuit_breaker.record_failure(name)
                logger.warning("Provider %s failed for task %s: %s", name, task_type, exc)
                if i == len(providers) - 1:
                    raise  # All providers failed

        raise ProviderUnavailableError("all", "all providers in chain failed")

    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker


# ---------------------------------------------------------------------------
# Module-level singleton (populated during app startup)
# ---------------------------------------------------------------------------

_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def init_registry_from_settings() -> ProviderRegistry:
    """Initialize the registry from application settings.

    Called during FastAPI startup lifespan.
    """
    from app.core.config import get_settings

    settings = get_settings()
    registry = get_registry()

    # Register Claude if key is configured
    if settings.anthropic_api_key:
        from app.ai.providers.claude import ClaudeConversationProvider
        registry.register(
            ClaudeConversationProvider(
                api_key=settings.anthropic_api_key,
                model=None,  # use default
            )
        )
        logger.info("Claude provider registered")
    else:
        logger.warning("ANTHROPIC_API_KEY not set — Claude provider not registered")

    # Register OpenAI if key is configured
    if settings.openai_api_key:
        from app.ai.providers.openai_provider import OpenAIConversationProvider
        registry.register(
            OpenAIConversationProvider(
                api_key=settings.openai_api_key,
                model=None,  # use default
            )
        )
        logger.info("OpenAI provider registered")
    else:
        logger.warning("OPENAI_API_KEY not set — OpenAI provider not registered")

    # Register 9Router providers if API key is configured
    # 9Router is preferred: Claude and GPT are both available through it,
    # and it handles billing, rate-limiting, and routing centrally.
    if settings.nine_router_api_key:
        from app.ai.providers.nine_router import NineRouterProvider

        # Primary: Claude via 9Router
        registry.register(
            NineRouterProvider(
                base_url=settings.nine_router_base_url,
                api_key=settings.nine_router_api_key,
                model=settings.nine_router_primary_model,
                provider_name="nine_router_claude",
            )
        )
        # Fallback: GPT via 9Router
        registry.register(
            NineRouterProvider(
                base_url=settings.nine_router_base_url,
                api_key=settings.nine_router_api_key,
                model=settings.nine_router_fallback_model,
                provider_name="nine_router_gpt",
            )
        )
        logger.info(
            "9Router providers registered (primary=%s, fallback=%s)",
            settings.nine_router_primary_model,
            settings.nine_router_fallback_model,
        )
    else:
        logger.warning(
            "MCP_NINE_ROUTER_API_KEY not set — 9Router providers not registered; "
            "falling back to direct Claude/OpenAI"
        )

    return registry
