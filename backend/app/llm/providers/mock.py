"""Deterministic mock LLM provider (default).

Produces safe, Vietnamese, probabilistic-language responses without any network
call. Output is a pure function of the input so tests are reproducible. The reply
intentionally NEVER diagnoses or prescribes; the gateway's output guardrail is
still applied on top as the hard guarantee.
"""

from __future__ import annotations

from ..base import LLMMessage, LLMProvider, LLMResponse, estimate_tokens


class MockLLMProvider(LLMProvider):
    name = "mock"

    def __init__(self, model: str = "mock-vi-1") -> None:
        self._model = model

    def _last_user_text(self, messages: list[LLMMessage]) -> str:
        for msg in reversed(messages):
            if msg.role == "user":
                return msg.content
        return ""

    def _generate(self, user_text: str, system: str | None) -> str:
        """Deterministic canned reply. Keyword-light so it stays safe and generic;
        the gateway still validates this through the output guardrail."""
        text = (user_text or "").lower()
        if any(k in text for k in ("ăn", "bữa", "cơm", "đường", "tinh bột", "phở")):
            body = (
                "Về dinh dưỡng, bạn có thể ưu tiên rau xanh, giảm tinh bột nhanh và đồ ngọt, "
                "và đi bộ nhẹ 15–20 phút sau bữa ăn để hỗ trợ chuyển hóa."
            )
        elif any(k in text for k in ("ngủ", "mệt", "stress", "căng thẳng")):
            body = (
                "Giấc ngủ đủ và đều giúp ổn định chuyển hóa. Bạn có thể thử cố định giờ ngủ, "
                "giảm màn hình trước khi ngủ và vận động nhẹ ban ngày."
            )
        else:
            body = (
                "Dựa trên thông tin bạn chia sẻ, một vài gợi ý lối sống chung: duy trì vận động "
                "nhẹ đều đặn, ăn cân đối, ngủ đủ giấc và theo dõi chỉ số thường xuyên."
            )
        reply = (
            "Cảm ơn bạn đã chia sẻ. "
            + body
            + " Nếu bạn còn băn khoăn, nên trao đổi với bác sĩ để được đánh giá phù hợp."
        )
        return reply

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> LLMResponse:
        user_text = self._last_user_text(messages)
        reply = self._generate(user_text, system)
        prompt_text = (system or "") + " " + " ".join(m.content for m in messages)
        prompt_tokens = estimate_tokens(prompt_text)
        completion_tokens = min(estimate_tokens(reply), max_tokens)
        return LLMResponse(
            text=reply,
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason="stop",
        )
