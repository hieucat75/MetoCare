"""LLM provider interface + transport types.

`LLMProvider.complete` is the single method every adapter implements. The gateway
(not the provider) owns guardrail enforcement, caching, and cost accounting, so
adapters stay thin and side-effect free.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LLMMessage:
    """A single chat turn. `role` is one of: system | user | assistant."""

    role: str
    content: str


@dataclass
class LLMResponse:
    """Result of a completion.

    `text` is the model output. After the gateway runs the output guardrail,
    `text` is guaranteed safe (and `blocked`/`safety_flags` reflect any
    substitution). Token counts feed the cost guard.
    """

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False
    blocked: bool = False
    finish_reason: str = "stop"
    safety_flags: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def estimate_tokens(text: str) -> int:
    """Cheap, deterministic token estimate (~4 chars/token).

    Used by the mock provider and the cost guard so accounting is reproducible
    without a real tokenizer dependency. Real adapters should prefer the
    provider-reported usage when available.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


class LLMProvider(ABC):
    """Abstract completion provider. Implementations MUST NOT apply guardrails or
    caching themselves — that is the gateway's responsibility."""

    name: str = "base"

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Generate a completion for `messages` (optionally prefixed by `system`)."""
