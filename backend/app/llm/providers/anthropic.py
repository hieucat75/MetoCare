"""Anthropic provider skeleton.

Mirror of the OpenAI skeleton: fixes the adapter shape + config wiring but makes
NO network call. Selecting it without real wiring raises LLMConfigError so dev/
test never reach a live provider.
"""

from __future__ import annotations

from app.core.config import get_settings

from ..base import LLMMessage, LLMProvider, LLMResponse
from ..errors import LLMConfigError


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str = "claude-haiku-4-5") -> None:
        settings = get_settings()
        self._model = model
        self._api_key = settings.llm_api_key
        self._base_url = settings.llm_gateway_url or "https://api.anthropic.com"

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> LLMResponse:
        raise LLMConfigError(
            "AnthropicProvider is a skeleton and makes no real call. "
            "Set MCP_LLM_PROVIDER=mock for dev/test."
        )
