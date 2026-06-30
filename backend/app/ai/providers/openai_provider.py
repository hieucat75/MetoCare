"""Meto AI — OpenAI conversation provider (fallback).

Implements the same ConversationProvider interface as Claude, enabling
transparent fallback without business logic changes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator

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

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 1.0
_REQUEST_TIMEOUT = 30.0


class OpenAIConversationProvider(ConversationProvider):
    """OpenAI GPT as fallback for conversation.

    Same interface as ClaudeConversationProvider. Business logic uses
    ConversationProvider; the underlying model is transparent.
    """

    _provider_name = "openai"
    _model_name = "gpt-4o"
    _max_context_tokens = 128_000
    _supports_streaming = True
    _supports_tool_use = True

    def __init__(self, api_key: str, model: str | None = None) -> None:
        try:
            import openai
            self._openai = openai
            self._client = openai.AsyncOpenAI(
                api_key=api_key,
                timeout=_REQUEST_TIMEOUT,
            )
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "openai package is required. Add 'openai>=1.0.0' to requirements.txt"
            ) from exc

        self._model = model or self._model_name
        self._last_latency_ms: int | None = None
        self._is_healthy: bool = True
        self._last_health_check: float = 0.0

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

    def _to_openai_messages(self, messages: list[ChatMessage], system_prompt: str) -> list[dict]:
        result: list[dict] = [{"role": "system", "content": system_prompt}]
        for m in messages:
            if m.role == "system":
                continue  # system already prepended
            result.append({"role": m.role, "content": m.content})
        return result

    def _to_openai_tools(self, tools: list[ToolSchema]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _extract_tool_calls(self, response: object) -> list[ToolCall] | None:
        import json
        choice = getattr(response, "choices", [{}])[0] if getattr(response, "choices", []) else None
        if choice is None:
            return None
        msg = getattr(choice, "message", None)
        raw_calls = getattr(msg, "tool_calls", None) if msg else None
        if not raw_calls:
            return None
        result = []
        for tc in raw_calls:
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}
            result.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return result if result else None

    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False,
    ) -> ChatResponse:
        openai_messages = self._to_openai_messages(messages, system_prompt)

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            start = time.monotonic()
            try:
                kwargs: dict = {
                    "model": self._model,
                    "messages": openai_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools:
                    kwargs["tools"] = self._to_openai_tools(tools)

                response = await asyncio.wait_for(
                    self._client.chat.completions.create(**kwargs),
                    timeout=_REQUEST_TIMEOUT,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                self._last_latency_ms = latency_ms
                self._is_healthy = True

                choice = response.choices[0]
                content = choice.message.content or ""
                finish_reason = choice.finish_reason or "stop"
                usage = response.usage

                return ChatResponse(
                    content=content,
                    tool_calls=self._extract_tool_calls(response),
                    input_tokens=usage.prompt_tokens if usage else 0,
                    output_tokens=usage.completion_tokens if usage else 0,
                    model_used=self._model,
                    finish_reason=finish_reason,
                    latency_ms=latency_ms,
                    provider="openai",
                )

            except TimeoutError as exc:
                last_exc = exc
                logger.warning("OpenAI timeout on attempt %d/%d", attempt + 1, _MAX_RETRIES + 1)
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    self._is_healthy = False
                    raise ProviderTimeoutError("openai", _REQUEST_TIMEOUT) from exc

            except Exception as exc:
                last_exc = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                logger.warning(
                    "OpenAI API error on attempt %d/%d: %s",
                    attempt + 1, _MAX_RETRIES + 1, exc,
                )
                if status_code in (401, 403):
                    self._is_healthy = False
                    raise ProviderUnavailableError("openai", str(exc)) from exc
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    self._is_healthy = False
                    raise ProviderResponseError("openai", status_code, str(exc)) from exc

        raise ProviderUnavailableError("openai") from last_exc

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        openai_messages = self._to_openai_messages(messages, system_prompt)

        kwargs: dict = {
            "model": self._model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = self._to_openai_tools(tools)

        try:
            async with await self._client.chat.completions.create(**kwargs) as stream:
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield ChatStreamChunk(delta=delta.content)
                    if chunk.choices and chunk.choices[0].finish_reason:
                        yield ChatStreamChunk(delta="", is_final=True)
                        break
            self._is_healthy = True
        except TimeoutError as exc:
            self._is_healthy = False
            raise ProviderTimeoutError("openai", _REQUEST_TIMEOUT) from exc
        except Exception as exc:
            self._is_healthy = False
            raise ProviderResponseError("openai", detail=str(exc)) from exc

    async def cancel(self, request_id: str) -> bool:
        logger.debug("OpenAI cancel requested for %s (no-op)", request_id)
        return False

    async def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def health_check(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            provider="openai",
            is_alive=self._is_healthy,
            last_latency_ms=self._last_latency_ms,
            last_checked_at=self._last_health_check,
        )
