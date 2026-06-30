"""Meto AI — Claude (Anthropic) conversation provider.

Primary provider for all conversational tasks. Implements ConversationProvider
with streaming, retry, and timeout support.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from app.ai.exceptions import (
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.ai.providers.base import (
    ChatMessage,
    ChatResponse,
    ChatStreamChunk,
    ConversationProvider,
    ProviderHealthStatus,
    ToolCall,
    ToolSchema,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Retry configuration
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 1.0  # seconds (exponential backoff)
_REQUEST_TIMEOUT = 30.0  # seconds


class ClaudeConversationProvider(ConversationProvider):
    """Claude via Anthropic SDK.

    Primary provider for all Meto conversational tasks.
    Supports streaming SSE, retry with exponential backoff, and 30s timeout.
    """

    _provider_name = "claude"
    _model_name = "claude-sonnet-4-5"
    _max_context_tokens = 200_000
    _supports_streaming = True
    _supports_tool_use = True

    def __init__(self, api_key: str, model: str | None = None, base_url: str | None = None) -> None:
        try:
            import anthropic
            self._anthropic = anthropic
            kwargs: dict = {"api_key": api_key, "timeout": _REQUEST_TIMEOUT}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = anthropic.AsyncAnthropic(**kwargs)
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "anthropic package is required. Add 'anthropic>=0.112.0' to requirements.txt"
            ) from exc

        self._model = model or self._model_name
        self._last_latency_ms: int | None = None
        self._last_health_check: float = 0.0
        self._is_healthy: bool = True

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def max_context_tokens(self) -> int:
        return self._max_context_tokens

    @property
    def supports_streaming(self) -> bool:
        return self._supports_streaming

    @property
    def supports_tool_use(self) -> bool:
        return self._supports_tool_use

    def _to_anthropic_messages(self, messages: list[ChatMessage]) -> list[dict]:
        result = []
        for m in messages:
            if m.role == "system":
                # system is passed separately in Anthropic API
                continue
            result.append({"role": m.role, "content": m.content})
        return result

    def _to_anthropic_tools(self, tools: list[ToolSchema]) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    def _extract_text(self, response: object) -> str:
        content = getattr(response, "content", [])
        texts = [b.text for b in content if hasattr(b, "text")]
        return "\n".join(texts)

    def _extract_tool_calls(self, response: object) -> list[ToolCall] | None:
        content = getattr(response, "content", [])
        calls = []
        for block in content:
            if getattr(block, "type", None) == "tool_use":
                calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))
        return calls if calls else None

    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False,
    ) -> ChatResponse:
        anthropic_messages = self._to_anthropic_messages(messages)

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            start = time.monotonic()
            try:
                kwargs: dict = {
                    "model": self._model,
                    "system": system_prompt,
                    "messages": anthropic_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools:
                    kwargs["tools"] = self._to_anthropic_tools(tools)

                response = await asyncio.wait_for(
                    self._client.messages.create(**kwargs),
                    timeout=_REQUEST_TIMEOUT,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                self._last_latency_ms = latency_ms
                self._is_healthy = True

                return ChatResponse(
                    content=self._extract_text(response),
                    tool_calls=self._extract_tool_calls(response),
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    model_used=self._model,
                    finish_reason=response.stop_reason or "stop",
                    latency_ms=latency_ms,
                    provider="claude",
                )

            except TimeoutError as exc:
                last_exc = exc
                logger.warning("Claude timeout on attempt %d/%d", attempt + 1, _MAX_RETRIES + 1)
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    self._is_healthy = False
                    raise ProviderTimeoutError("claude", _REQUEST_TIMEOUT) from exc

            except Exception as exc:  # anthropic.APIError, etc.
                last_exc = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                logger.warning(
                    "Claude API error on attempt %d/%d: %s",
                    attempt + 1, _MAX_RETRIES + 1, exc,
                )
                # Don't retry on auth errors
                if status_code in (401, 403):
                    self._is_healthy = False
                    raise ProviderUnavailableError("claude", str(exc)) from exc
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    self._is_healthy = False
                    raise ProviderResponseError("claude", status_code, str(exc)) from exc

        # Should not reach here
        raise ProviderUnavailableError("claude") from last_exc

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        anthropic_messages = self._to_anthropic_messages(messages)

        kwargs: dict = {
            "model": self._model,
            "system": system_prompt,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = self._to_anthropic_tools(tools)

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield ChatStreamChunk(delta=text)

                final = await stream.get_final_message()
                total = final.usage.input_tokens + final.usage.output_tokens
                self._is_healthy = True
                yield ChatStreamChunk(
                    delta="",
                    is_final=True,
                    total_tokens=total,
                )
        except TimeoutError as exc:
            self._is_healthy = False
            raise ProviderTimeoutError("claude", _REQUEST_TIMEOUT) from exc
        except Exception as exc:
            self._is_healthy = False
            raise ProviderResponseError("claude", detail=str(exc)) from exc

    async def cancel(self, request_id: str) -> bool:
        # Anthropic SDK doesn't support explicit cancellation yet
        logger.debug("Claude cancel requested for %s (no-op)", request_id)
        return False

    async def estimate_tokens(self, text: str) -> int:
        # Rough estimate: ~4 chars per token for English/Vietnamese mixed
        return max(1, len(text) // 4)

    def health_check(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            provider="claude",
            is_alive=self._is_healthy,
            last_latency_ms=self._last_latency_ms,
            last_checked_at=self._last_health_check,
        )
