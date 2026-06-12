"""OpenAI provider skeleton.

Intentionally does NOT perform a network call. It exists to (a) fix the adapter
shape and config wiring, and (b) fail loudly via LLMConfigError if selected in an
environment without the `openai` SDK / API key. Real wiring is deferred; dev/test
must never reach a live provider.
"""

from __future__ import annotations

from app.core.config import get_settings

from ..base import LLMMessage, LLMProvider, LLMResponse
from ..errors import LLMConfigError


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        settings = get_settings()
        self._model = model
        self._api_key = settings.llm_api_key
        self._base_url = settings.llm_gateway_url or "https://api.openai.com/v1"

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> LLMResponse:
        # Skeleton: never calls the network. Implementing this requires the
        # `openai` SDK and a verified key; until then selecting this provider
        # must fail explicitly rather than silently degrade.
        raise LLMConfigError(
            "OpenAIProvider is a skeleton and makes no real call. "
            "Set MCP_LLM_PROVIDER=mock for dev/test."
        )
