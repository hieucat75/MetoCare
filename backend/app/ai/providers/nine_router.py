"""Meto AI — 9Router provider.

Routes all LLM calls through the local 9Router OpenAI-compatible endpoint.
This is the PREFERRED provider for staging/production — all billing,
rate-limiting, and model routing is managed by 9Router.

Primary model:  cc/claude-sonnet-4-6 (Claude Sonnet via 9Router)
Fallback model: cx/gpt-5.4-mini      (GPT via 9Router)

Interface: ConversationProvider (same as ClaudeConversationProvider)
No model name or provider name is ever exposed to the patient UI.
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
_PING_TIMEOUT = 8.0


class NineRouterProvider(ConversationProvider):
    """Routes LLM calls through 9Router's OpenAI-compatible local proxy.

    9Router manages model selection, billing, rate-limiting, and fallback
    between Claude and GPT. Business logic uses ConversationProvider;
    the underlying model is transparent to the patient UI.
    """

    _max_context_tokens = 200_000
    _supports_streaming = True
    _supports_tool_use = True

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "cc/claude-sonnet-4-6",
        provider_name: str = "nine_router",
    ) -> None:
        try:
            import openai

            self._openai = openai
            self._client = openai.AsyncOpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=_REQUEST_TIMEOUT,
            )
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "openai package is required. Add 'openai>=1.0.0' to requirements.txt"
            ) from exc

        self._model = model
        self._provider_name_val = provider_name
        self._base_url = base_url
        self._last_latency_ms: int | None = None
        self._is_healthy: bool = True
        self._last_health_check: float = 0.0

    # ------------------------------------------------------------------
    # ConversationProvider interface
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return self._provider_name_val

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

    # ------------------------------------------------------------------
    # Message / tool conversion helpers
    # ------------------------------------------------------------------

    def _to_openai_messages(
        self, messages: list[ChatMessage], system_prompt: str
    ) -> list[dict]:
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
        import json as _json

        choices = getattr(response, "choices", [])
        if not choices:
            return None
        msg = getattr(choices[0], "message", None)
        raw_calls = getattr(msg, "tool_calls", None) if msg else None
        if not raw_calls:
            return None
        result = []
        for tc in raw_calls:
            try:
                args = _json.loads(tc.function.arguments)
            except Exception:
                args = {}
            result.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return result if result else None

    def _map_exception(self, exc: Exception, context: str) -> Exception:
        """Map openai SDK exceptions to Meto provider exceptions."""
        exc_type = type(exc).__name__

        # Authentication / authorization errors
        if exc_type in ("AuthenticationError",) or getattr(
            getattr(exc, "response", None), "status_code", None
        ) in (401, 403):
            return ProviderUnavailableError(self._provider_name_val, f"auth error: {exc}")

        # Rate limit errors
        if exc_type in ("RateLimitError",) or getattr(
            getattr(exc, "response", None), "status_code", None
        ) == 429:
            return ProviderUnavailableError(
                self._provider_name_val, f"rate limited: {exc}"
            )

        # Timeout
        if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
            return ProviderTimeoutError(self._provider_name_val, _REQUEST_TIMEOUT)

        # Generic API error
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        return ProviderResponseError(self._provider_name_val, status_code, str(exc))

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

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
                    provider=self._provider_name_val,
                )

            except TimeoutError as exc:
                last_exc = exc
                logger.warning(
                    "9Router timeout on attempt %d/%d (model=%s)",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    self._model,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2**attempt))
                else:
                    self._is_healthy = False
                    raise ProviderTimeoutError(
                        self._provider_name_val, _REQUEST_TIMEOUT
                    ) from exc

            except Exception as exc:
                last_exc = exc
                status_code = getattr(
                    getattr(exc, "response", None), "status_code", None
                )
                logger.warning(
                    "9Router API error on attempt %d/%d (model=%s): %s",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    self._model,
                    exc,
                )
                # Auth errors → immediately surface, no retry
                if status_code in (401, 403) or type(exc).__name__ == "AuthenticationError":
                    self._is_healthy = False
                    raise ProviderUnavailableError(
                        self._provider_name_val, str(exc)
                    ) from exc
                # Rate limit → immediately surface
                if status_code == 429 or type(exc).__name__ == "RateLimitError":
                    self._is_healthy = False
                    raise ProviderUnavailableError(
                        self._provider_name_val, f"rate limited: {exc}"
                    ) from exc

                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2**attempt))
                else:
                    self._is_healthy = False
                    raise ProviderResponseError(
                        self._provider_name_val, status_code, str(exc)
                    ) from exc

        raise ProviderUnavailableError(
            self._provider_name_val, "all retry attempts failed"
        ) from last_exc

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
            raise ProviderTimeoutError(self._provider_name_val, _REQUEST_TIMEOUT) from exc
        except Exception as exc:
            self._is_healthy = False
            raise ProviderResponseError(
                self._provider_name_val, detail=str(exc)
            ) from exc

    async def ping(self) -> bool:
        """Lightweight connectivity check — used by Gate CLI and health endpoints."""
        try:
            import openai

            sync_client = openai.OpenAI(
                base_url=self._base_url,
                api_key=self._client.api_key,
                timeout=_PING_TIMEOUT,
            )
            resp = sync_client.chat.completions.create(
                model=self._model,
                max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            self._is_healthy = bool(resp.choices)
            return self._is_healthy
        except Exception as exc:
            logger.warning(
                "9Router ping failed (model=%s): %s", self._model, exc
            )
            self._is_healthy = False
            return False

    async def cancel(self, request_id: str) -> bool:
        logger.debug(
            "9Router cancel requested for %s (no-op — 9Router manages cancellation)",
            request_id,
        )
        return False

    async def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def health_check(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            provider=self._provider_name_val,
            is_alive=self._is_healthy,
            last_latency_ms=self._last_latency_ms,
            last_checked_at=self._last_health_check,
        )
