"""Meto AI — Mock provider for staging/testing without real API keys.

Used when MCP_AI_MODE=mock and no real provider keys are configured.
Returns deterministic Vietnamese responses that exercise the full pipeline.
Never exposes provider name or model name to the patient UI.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from app.ai.providers.base import (
    ChatMessage,
    ChatResponse,
    ChatStreamChunk,
    ConversationProvider,
    ProviderHealthStatus,
    ToolSchema,
)


class MockConversationProvider(ConversationProvider):
    """Deterministic mock provider for staging/testing.

    Returns plausible Vietnamese health responses without calling any external API.
    Used only when MCP_AI_MODE=mock and no real provider keys exist.
    """

    _RESPONSES: list[str] = [
        "Xin chào! Tôi là Meto, trợ lý sức khỏe AI của bạn. "
        "Tôi có thể giúp bạn hiểu các chỉ số sức khỏe, thuốc đang dùng, và kết quả xét nghiệm. "
        "Bạn muốn hỏi về điều gì?",
        "Đây là chế độ thử nghiệm. Trong môi trường thực, Meto sẽ phân tích dữ liệu sức khỏe "
        "của bạn và cung cấp thông tin chi tiết hơn. "
        "Hãy tham khảo ý kiến bác sĩ để được tư vấn chuyên môn.",
        "Tôi hiểu câu hỏi của bạn. Để có câu trả lời chính xác nhất, "
        "Meto cần kết nối với hệ thống dữ liệu sức khỏe của bạn. "
        "Vui lòng thử lại hoặc liên hệ với nhóm hỗ trợ.",
    ]
    _call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-1.0"

    @property
    def max_context_tokens(self) -> int:
        return 32_000

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def supports_tool_use(self) -> bool:
        return False

    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False,
    ) -> ChatResponse:
        await asyncio.sleep(0.1)  # Simulate small latency
        response_text = self._pick_response(messages)
        return ChatResponse(
            content=response_text,
            tool_calls=None,
            input_tokens=50,
            output_tokens=len(response_text.split()),
            model_used=self.model_name,
            finish_reason="stop",
            latency_ms=100,
            provider=self.provider_name,
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        response_text = self._pick_response(messages)
        words = response_text.split()
        for i, word in enumerate(words):
            await asyncio.sleep(0.02)
            is_final = i == len(words) - 1
            yield ChatStreamChunk(
                delta=word + (" " if not is_final else ""),
                is_final=is_final,
                total_tokens=len(words) if is_final else None,
            )

    async def cancel(self, request_id: str) -> bool:
        return True

    async def estimate_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def health_check(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            provider=self.provider_name,
            is_alive=True,
            last_latency_ms=100,
            avg_latency_ms=100.0,
        )

    def _pick_response(self, messages: list[ChatMessage]) -> str:
        """Pick a response; cycle through the list for variety."""
        MockConversationProvider._call_count += 1
        idx = (MockConversationProvider._call_count - 1) % len(self._RESPONSES)
        return self._RESPONSES[idx]
