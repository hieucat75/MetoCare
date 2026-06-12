"""Provider factory — selects an adapter from MCP_LLM_PROVIDER.

Singleton per process; `reset_provider()` clears it for tests / config changes.
"""

from __future__ import annotations

from app.core.config import get_settings

from .base import LLMProvider
from .errors import LLMConfigError
from .providers import AnthropicProvider, MockLLMProvider, OpenAIProvider

_provider: LLMProvider | None = None


def _build(name: str, model: str) -> LLMProvider:
    if name == "mock":
        return MockLLMProvider(model=model)
    if name == "openai":
        return OpenAIProvider(model=model)
    if name == "anthropic":
        return AnthropicProvider(model=model)
    raise LLMConfigError(f"Unknown MCP_LLM_PROVIDER: {name!r}")


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        _provider = _build(settings.llm_provider, settings.llm_model)
    return _provider


def reset_provider() -> None:
    """Test helper: drop the cached provider so a new config takes effect."""
    global _provider
    _provider = None
