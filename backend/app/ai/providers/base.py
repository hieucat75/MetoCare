"""Meto AI — Abstract provider interfaces.

Business logic ONLY interacts with these interfaces — never with concrete
provider classes directly. This enables swapping Claude for OpenAI (or any
other provider) without touching any business logic.

Follows 20_PROVIDER_ABSTRACTION.md.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Shared data structures
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict  # JSON Schema


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResponse:
    content: str
    tool_calls: list[ToolCall] | None
    input_tokens: int
    output_tokens: int
    model_used: str
    finish_reason: str  # "stop" | "tool_use" | "max_tokens" | "error"
    latency_ms: int
    provider: str


@dataclass
class ChatStreamChunk:
    delta: str  # Text chunk
    is_tool_call: bool = False
    tool_call_delta: dict | None = None
    is_final: bool = False
    total_tokens: int | None = None  # Only in final chunk


@dataclass
class ProviderHealthStatus:
    provider: str
    is_alive: bool
    last_latency_ms: int | None = None
    avg_latency_ms: float | None = None
    error: str | None = None
    last_checked_at: float = field(default_factory=time.monotonic)


@dataclass
class EmbeddingVector:
    vector: list[float]
    dimensions: int
    model_used: str
    provider: str
    input_tokens: int


@dataclass
class ModerationResult:
    flagged: bool
    reason: str | None
    categories: dict[str, bool]
    confidence: float
    provider: str


@dataclass
class MedicalScopeResult:
    has_violation: bool
    violation_types: list[str]  # ["diagnosis", "prescription", "dose_change"]
    violating_text: str | None


@dataclass
class CostEstimate:
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    model: str
    provider: str


# ---------------------------------------------------------------------------
# Abstract provider interfaces
# ---------------------------------------------------------------------------

class ConversationProvider(ABC):
    """Core interface for conversational AI.

    Every LLM provider must implement this interface. Business logic only
    interacts with ConversationProvider — never with the concrete class.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """e.g., 'claude', 'openai', 'gemini'"""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """e.g., 'claude-sonnet-4-5', 'gpt-4o'"""

    @property
    @abstractmethod
    def max_context_tokens(self) -> int:
        """Maximum context window in tokens."""

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Whether the provider supports streaming."""

    @property
    @abstractmethod
    def supports_tool_use(self) -> bool:
        """Whether the provider supports tool/function calls."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False,
    ) -> ChatResponse:
        """Non-streaming chat completion."""

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """Streaming chat completion — yields chunks."""
        # Must be implemented as an async generator
        raise NotImplementedError
        yield  # type: ignore[misc]

    @abstractmethod
    async def cancel(self, request_id: str) -> bool:
        """Cancel an in-progress request."""

    @abstractmethod
    async def estimate_tokens(self, text: str) -> int:
        """Estimate token count for given text."""

    @abstractmethod
    def health_check(self) -> ProviderHealthStatus:
        """Return current health status."""


class ModerationProvider(ABC):
    """Provider for content safety moderation."""

    @abstractmethod
    async def check_content(
        self,
        content: str,
        context: str | None = None,
    ) -> ModerationResult:
        """Check content for safety violations."""

    @abstractmethod
    async def check_medical_scope(
        self,
        content: str,
        forbidden_patterns: list[str],
    ) -> MedicalScopeResult:
        """Check specifically for medical scope violations."""


class EmbeddingProvider(ABC):
    """Provider for text embeddings."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Embedding vector dimensions."""

    @property
    @abstractmethod
    def max_input_tokens(self) -> int:
        """Max tokens per embedding call."""

    @abstractmethod
    async def embed(
        self,
        text: str,
        model: str | None = None,
    ) -> EmbeddingVector:
        """Generate embedding for a single text."""

    @abstractmethod
    async def embed_batch(
        self,
        texts: list[str],
        model: str | None = None,
        batch_size: int = 100,
    ) -> list[EmbeddingVector]:
        """Generate embeddings for multiple texts."""


class CostTrackingProvider(ABC):
    """Token counting and cost estimation."""

    @abstractmethod
    async def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str,
        provider: str,
    ) -> CostEstimate:
        """Estimate cost for a given token usage."""

    @abstractmethod
    async def record_usage(
        self,
        user_id: str,
        session_id: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        request_type: str,
    ) -> None:
        """Record actual token/cost usage."""


class ProviderHealth(ABC):
    """Liveness and latency monitoring."""

    @abstractmethod
    async def check_liveness(self, provider_name: str) -> ProviderHealthStatus:
        """Check if a provider is alive."""

    @abstractmethod
    async def get_avg_latency(self, provider_name: str) -> float:
        """Get average latency for a provider (milliseconds)."""
