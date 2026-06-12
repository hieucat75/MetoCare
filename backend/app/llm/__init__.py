"""LLM Gateway (P2 #1).

Provider abstraction + guardrail enforcement + cost/rate guard + response cache.
No real LLM is called in the default mock mode; the OpenAI/Anthropic adapters are
config-gated skeletons that never make a network call in dev/test.
"""

from __future__ import annotations

from .base import LLMMessage, LLMProvider, LLMResponse, estimate_tokens
from .errors import LLMConfigError, LLMRateLimitError
from .factory import get_provider, reset_provider
from .gateway import LLMGateway, get_gateway, reset_gateway

__all__ = [
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    "estimate_tokens",
    "LLMConfigError",
    "LLMRateLimitError",
    "get_provider",
    "reset_provider",
    "LLMGateway",
    "get_gateway",
    "reset_gateway",
]
