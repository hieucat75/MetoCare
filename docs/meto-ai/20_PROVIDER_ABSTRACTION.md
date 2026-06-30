# Meto AI — Provider Abstraction Layer

> **Phiên bản:** 1.0 | **Ngày:** 2026-06-30 | **Trạng thái:** Approved
> **Phase:** 3 — Clinical Intelligence

---

## Tổng quan

Provider Abstraction Layer (PAL) đảm bảo Meto **không phụ thuộc vào bất kỳ AI provider nào**. Thay Claude bằng OpenAI, thêm Gemini, hoặc chạy local model = thay 1 class implement, không sửa business logic.

**Design principle:** Giống như interface trong lập trình hướng đối tượng — business logic chỉ giao tiếp qua interface, không quan tâm implementation cụ thể.

**File backend:**
- `app/ai/providers/` — Provider implementations
- `app/ai/providers/interfaces.py` — All provider interfaces
- `app/ai/providers/registry.py` — Provider & capability registry
- `app/ai/providers/router.py` — Routing policy
- `app/ai/providers/circuit_breaker.py` — Circuit breaker
- `app/ai/providers/health_check.py` — Liveness + latency monitoring
- `app/ai/providers/cost_tracker.py` — Token counting, cost estimation
- `app/ai/providers/feature_flags.py` — Feature-level provider flags

---

## 1. Platform Layer View (Full Stack)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Chat UI / Voice UI                               │
│           (Next.js frontend, Meto Aura mascot, streaming)          │
├─────────────────────────────────────────────────────────────────────┤
│              Agent Orchestration Layer                              │
│  Planner | Reasoner | Tool Selector | Safety Guard                 │
│  (19_AGENT_ORCHESTRATION.md)                                        │
├──────────────┬──────────────┬────────────────────────────────────────┤
│ Context      │ Memory       │ Knowledge                            │
│ Engine       │ Engine       │ Layer                                │
├──────────────┴──────────────┴────────────────────────────────────────┤
│           Clinical Reasoning Layer                                  │
│           (14_CLINICAL_REASONING.md)                                │
├─────────────────────────────────────────────────────────────────────┤
│           Recommendation Engine                                    │
│           (15_RECOMMENDATION_ENGINE.md)                             │
├─────────────────────────────────────────────────────────────────────┤
│    Tool Engine    │  Doctor Handoff │  Multimodal                  │
├─────────────────────────────────────────────────────────────────────┤
│         Conversation Engine (session/state/streaming)               │
├─────────────────────────────────────────────────────────────────────┤
│══════════════════════════════════════════════════════════════════════│
║              PROVIDER ABSTRACTION LAYER  ◀── YOU ARE HERE          ║
║  ConversationProvider  │  ReasoningProvider  │  VisionProvider     ║
║  SpeechProvider  │  EmbeddingProvider  │  RerankingProvider       ║
║  TranslationProvider  │  ModerationProvider  │  EvaluationProvider ║
║  CostTrackingProvider                                               ║
║                                                                     ║
║  ROUTER: rule-based routing → primary → fallback → tertiary        ║
║  CIRCUIT BREAKER: open/half-open/closed per provider               ║
║  HEALTH CHECK: liveness + latency per provider                     ║
║  COST OPTIMIZER: cheapest eligible provider per task               ║
║══════════════════════════════════════════════════════════════════════║
├─────────────────────────────────────────────────────────────────────┤
│  Claude      │  OpenAI     │  Gemini   │  Local/OSS  │  Future     │
│  (primary)   │  (fallback) │(tertiary) │(cost opt.)  │            │
├─────────────────────────────────────────────────────────────────────┤
│    Safety Layer  │  Analytics Layer │ Audit Layer                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Provider Interfaces

### 2.1 ConversationProvider

```python
from abc import ABC, abstractmethod
from typing import AsyncGenerator

class ConversationProvider(ABC):
    """
    Core interface cho conversational AI.
    Mọi LLM provider phải implement interface này.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """e.g., 'claude', 'openai', 'gemini'"""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """e.g., 'claude-sonnet-4-5', 'gpt-4o', 'gemini-2.0-flash'"""
        pass

    @property
    @abstractmethod
    def max_context_tokens(self) -> int:
        """Maximum context window in tokens"""
        pass

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        pass

    @property
    @abstractmethod
    def supports_tool_use(self) -> bool:
        pass

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
        """Non-streaming chat completion"""
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """Streaming chat completion — yields chunks"""
        pass

    @abstractmethod
    async def cancel(self, request_id: str) -> bool:
        """Cancel an in-progress request"""
        pass

    @abstractmethod
    async def estimate_tokens(self, text: str) -> int:
        """Estimate token count for given text"""
        pass

    @abstractmethod
    def health_check(self) -> ProviderHealthStatus:
        """Return current health status of this provider"""
        pass

@dataclass
class ChatMessage:
    role: str                          # "system" | "user" | "assistant" | "tool"
    content: str
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None

@dataclass
class ChatResponse:
    content: str
    tool_calls: list[ToolCall] | None
    input_tokens: int
    output_tokens: int
    model_used: str
    finish_reason: str                 # "stop" | "tool_use" | "max_tokens" | "error"
    latency_ms: int
    provider: str

@dataclass
class ChatStreamChunk:
    delta: str                         # Text chunk
    is_tool_call: bool = False
    tool_call_delta: dict | None = None
    is_final: bool = False
    total_tokens: int | None = None    # Only in final chunk
```

### 2.2 ReasoningProvider

```python
class ReasoningProvider(ABC):
    """
    Provider for structured reasoning and chain-of-thought.
    Separate from ConversationProvider because:
    - May use different models (thinking models)
    - Different token limits
    - Different temperature settings
    - May have extended thinking features
    """

    @property
    @abstractmethod
    def supports_extended_thinking(self) -> bool:
        """Whether provider supports explicit chain-of-thought / thinking tokens"""
        pass

    @abstractmethod
    async def reason(
        self,
        query: str,
        context: str,
        constraints: str,
        max_thinking_tokens: int = 2000,
        output_format: str = "structured_json"
    ) -> ReasoningResult:
        """
        Perform multi-step reasoning.
        Returns reasoning chain + conclusion separately.
        """
        pass

    @abstractmethod
    async def reason_with_chain_of_thought(
        self,
        query: str,
        context: str,
        knowledge: str,
        memory: str,
        previous_steps: list[dict],
        safety_constraints: str,
    ) -> ChainOfThoughtResult:
        pass

    @abstractmethod
    async def self_critique(
        self,
        original_reasoning: str,
        conclusion: str,
        critique_criteria: list[str]
    ) -> CritiqueResult:
        """Provider critiques its own output"""
        pass

@dataclass
class ReasoningResult:
    conclusion: str
    confidence: float                  # 0.0-1.0
    reasoning_summary: str            # Abbreviated chain for audit
    full_chain: str | None            # Full chain (only if extended thinking enabled)
    input_tokens: int
    thinking_tokens: int | None
    output_tokens: int
    provider: str
```

### 2.3 VisionProvider

```python
class VisionProvider(ABC):
    """
    Provider for image understanding, OCR, and visual analysis.
    """

    @property
    @abstractmethod
    def supported_formats(self) -> list[str]:
        """e.g., ['jpg', 'png', 'webp', 'pdf']"""
        pass

    @property
    @abstractmethod
    def max_image_size_mb(self) -> float:
        pass

    @abstractmethod
    async def extract_text(
        self,
        image: bytes | str,            # bytes or URL
        language: str = "vi+en",
        mode: str = "document"         # "document" | "photo" | "handwriting"
    ) -> OCRResult:
        """Extract text from image (OCR)"""
        pass

    @abstractmethod
    async def describe_image(
        self,
        image: bytes | str,
        system_prompt: str,
        max_tokens: int = 500,
    ) -> ImageDescription:
        """Describe visual content of image"""
        pass

    @abstractmethod
    async def classify_image_type(
        self,
        image: bytes | str,
        categories: list[str]
    ) -> ImageClassification:
        """Classify what type of image this is"""
        pass

    @abstractmethod
    async def recognize_food(
        self,
        image: bytes | str,
        language: str = "vi"
    ) -> list[FoodItem]:
        """Recognize food items in image"""
        pass

    @abstractmethod
    async def read_barcode(
        self,
        image: bytes | str,
    ) -> BarcodeData | None:
        """Read barcode/QR from image"""
        pass

    @abstractmethod
    async def extract_insurance_info(
        self,
        image: bytes | str,
    ) -> dict:
        """Extract insurance card fields"""
        pass

    @abstractmethod
    async def extract_id_info_limited(
        self,
        image: bytes | str,
    ) -> dict:
        """Extract only name + birth_year from ID card (privacy-limited)"""
        pass

@dataclass
class OCRResult:
    text: str
    confidence: float
    language_detected: str
    blocks: list[TextBlock]            # Structural blocks (paragraphs, tables)
    provider: str

@dataclass
class ImageDescription:
    text: str
    confidence: float
    provider: str
```

### 2.4 SpeechProvider

```python
class SpeechProvider(ABC):
    """
    Provider for Speech-to-Text (STT) and Text-to-Speech (TTS).
    """

    # STT
    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
        language: str = "vi-VN",
        enable_punctuation: bool = True,
        enable_speaker_diarization: bool = False,
        model: str = "default"
    ) -> TranscriptionResult:
        """Convert speech audio to text"""
        pass

    @abstractmethod
    async def transcribe_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        language: str = "vi-VN",
    ) -> AsyncGenerator[TranscriptionChunk, None]:
        """Real-time streaming transcription"""
        pass

    # TTS
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: str,
        language: str = "vi-VN",
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
        audio_format: str = "mp3"
    ) -> TTSResult:
        """Convert text to speech audio"""
        pass

    @abstractmethod
    async def list_voices(self, language: str = "vi-VN") -> list[VoiceInfo]:
        """List available voices for language"""
        pass

    @abstractmethod
    def supports_streaming_tts(self) -> bool:
        pass

@dataclass
class TranscriptionResult:
    text: str
    confidence: float
    language: str
    words: list[WordTimestamp]         # Per-word timing (for highlighting)
    provider: str

@dataclass
class TTSResult:
    audio_bytes: bytes
    audio_format: str
    duration_seconds: float
    provider: str
```

### 2.5 EmbeddingProvider

```python
class EmbeddingProvider(ABC):
    """
    Provider for text embeddings (for semantic search, memory, RAG).
    """

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Embedding vector dimensions (e.g., 1536 for OpenAI)"""
        pass

    @property
    @abstractmethod
    def max_input_tokens(self) -> int:
        """Max tokens per embedding call"""
        pass

    @abstractmethod
    async def embed(
        self,
        text: str,
        model: str | None = None
    ) -> EmbeddingVector:
        """Generate embedding for single text"""
        pass

    @abstractmethod
    async def embed_batch(
        self,
        texts: list[str],
        model: str | None = None,
        batch_size: int = 100
    ) -> list[EmbeddingVector]:
        """Generate embeddings for multiple texts (batched)"""
        pass

    @abstractmethod
    def cosine_similarity(
        self,
        vec_a: EmbeddingVector,
        vec_b: EmbeddingVector
    ) -> float:
        """Compute cosine similarity between two vectors"""
        pass

@dataclass
class EmbeddingVector:
    vector: list[float]
    dimensions: int
    model_used: str
    provider: str
    input_tokens: int
```

### 2.6 RerankingProvider

```python
class RerankingProvider(ABC):
    """
    Provider for reranking search results by relevance.
    Used in RAG pipeline to improve retrieval quality.
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 5
    ) -> list[RerankResult]:
        """
        Rerank documents by relevance to query.
        Returns top_n results with relevance scores.
        """
        pass

    @abstractmethod
    async def score(
        self,
        query: str,
        document: str
    ) -> float:
        """Score single document against query (0-1)"""
        pass

@dataclass
class RerankResult:
    document_index: int                # Original position in input list
    document: str
    relevance_score: float             # 0-1
    provider: str
```

### 2.7 TranslationProvider

```python
class TranslationProvider(ABC):
    """
    Provider for text translation (VI ↔ EN and others).
    """

    @property
    @abstractmethod
    def supported_language_pairs(self) -> list[tuple[str, str]]:
        """List of (source_lang, target_lang) pairs supported"""
        pass

    @abstractmethod
    async def translate(
        self,
        text: str,
        source_language: str,          # ISO 639-1 or "auto"
        target_language: str,
        domain: str = "medical"        # "medical" | "general" | "consumer"
    ) -> TranslationResult:
        pass

    @abstractmethod
    async def detect_language(
        self,
        text: str
    ) -> LanguageDetectionResult:
        pass

    @abstractmethod
    async def translate_batch(
        self,
        texts: list[str],
        source_language: str,
        target_language: str
    ) -> list[TranslationResult]:
        pass

@dataclass
class TranslationResult:
    translated_text: str
    source_language: str
    target_language: str
    confidence: float
    provider: str
```

### 2.8 ModerationProvider

```python
class ModerationProvider(ABC):
    """
    Provider for content safety moderation.
    Checks user messages AND Meto responses for unsafe content.
    """

    @abstractmethod
    async def check(
        self,
        content: str,
        context: str | None = None
    ) -> ModerationResult:
        """Check content for safety violations"""
        pass

    @abstractmethod
    async def check_batch(
        self,
        contents: list[str]
    ) -> list[ModerationResult]:
        pass

    @abstractmethod
    async def check_medical_scope(
        self,
        content: str,
        forbidden_patterns: list[str]
    ) -> MedicalScopeResult:
        """
        Check specifically for medical scope violations
        (diagnosis, prescription, dose changes).
        This is Meto-specific moderation beyond general safety.
        """
        pass

@dataclass
class ModerationResult:
    flagged: bool
    reason: str | None
    categories: dict[str, bool]        # e.g., {"self_harm": False, "medical_advice": False}
    confidence: float
    provider: str

@dataclass
class MedicalScopeResult:
    has_violation: bool
    violation_types: list[str]         # ["diagnosis", "prescription", "dose_change"]
    violating_text: str | None
```

### 2.9 EvaluationProvider

```python
class EvaluationProvider(ABC):
    """
    Provider for response quality scoring.
    Used to evaluate Meto's output quality (offline/batch, not on every request).
    """

    @abstractmethod
    async def evaluate_response(
        self,
        query: str,
        response: str,
        context: str,
        evaluation_criteria: list[str]
    ) -> EvaluationResult:
        """
        Score a response on multiple criteria.
        Criteria examples: accuracy, safety, empathy, clarity, completeness.
        """
        pass

    @abstractmethod
    async def evaluate_batch(
        self,
        samples: list[EvaluationSample]
    ) -> list[EvaluationResult]:
        """Batch evaluation for offline quality assessment"""
        pass

    @abstractmethod
    async def detect_hallucination(
        self,
        response: str,
        ground_truth_context: str
    ) -> HallucinationResult:
        """Check if response contains claims not grounded in context"""
        pass

@dataclass
class EvaluationResult:
    overall_score: float               # 0-100
    dimension_scores: dict[str, float] # Per-criterion scores
    issues_found: list[str]
    recommendation: str
    provider: str

@dataclass
class HallucinationResult:
    has_hallucination: bool
    hallucination_spans: list[str]     # Text that is hallucinated
    confidence: float
    provider: str
```

### 2.10 CostTrackingProvider

```python
class CostTrackingProvider(ABC):
    """
    Token counting and cost estimation across all providers.
    """

    @abstractmethod
    async def count_tokens(
        self,
        text: str,
        model: str,
        provider: str
    ) -> int:
        pass

    @abstractmethod
    async def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str,
        provider: str
    ) -> CostEstimate:
        pass

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
        request_type: str
    ) -> None:
        pass

    @abstractmethod
    async def get_usage_summary(
        self,
        period: str = "month",
        breakdown_by: str = "provider"
    ) -> UsageSummary:
        pass

@dataclass
class CostEstimate:
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    model: str
    provider: str
```

---

## 3. Provider Implementations

### 3.1 Claude (Anthropic) — Primary

```python
class ClaudeConversationProvider(ConversationProvider):
    """
    Claude via Anthropic API or 9Router (for PTH's setup).
    Primary provider for all conversational and reasoning tasks.
    """

    provider_name = "claude"
    model_name = "claude-sonnet-4-5"
    max_context_tokens = 200000
    supports_streaming = True
    supports_tool_use = True

    def __init__(self, config: ClaudeProviderConfig):
        self.client = anthropic.AsyncAnthropic(api_key=config.api_key)
        self.model = config.model or self.model_name
        self.base_url = config.base_url  # For 9Router

    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False,
    ) -> ChatResponse:
        start_time = time.monotonic()

        anthropic_messages = [self._to_anthropic_message(m) for m in messages]
        anthropic_tools = [self._to_anthropic_tool(t) for t in (tools or [])]

        response = await self.client.messages.create(
            model=self.model,
            system=system_prompt,
            messages=anthropic_messages,
            tools=anthropic_tools if anthropic_tools else anthropic.NOT_GIVEN,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return ChatResponse(
            content=self._extract_text(response),
            tool_calls=self._extract_tool_calls(response),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model_used=self.model,
            finish_reason=response.stop_reason,
            latency_ms=int((time.monotonic() - start_time) * 1000),
            provider="claude"
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        anthropic_messages = [self._to_anthropic_message(m) for m in messages]

        async with self.client.messages.stream(
            model=self.model,
            system=system_prompt,
            messages=anthropic_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ) as stream:
            async for text in stream.text_stream:
                yield ChatStreamChunk(delta=text)

            final = await stream.get_final_message()
            yield ChatStreamChunk(
                delta="",
                is_final=True,
                total_tokens=final.usage.input_tokens + final.usage.output_tokens
            )

    def health_check(self) -> ProviderHealthStatus:
        # Check via models.list or a ping endpoint
        return ProviderHealthStatus(
            provider="claude",
            is_alive=True,  # Updated by background health checker
            last_latency_ms=self._last_latency_ms,
            last_checked_at=self._last_health_check
        )


class ClaudeReasoningProvider(ReasoningProvider):
    """
    Claude with extended thinking for complex reasoning tasks.
    Uses same Claude client but with thinking enabled.
    """

    supports_extended_thinking = True  # Claude 3.7+ supports thinking

    async def reason(
        self,
        query: str,
        context: str,
        constraints: str,
        max_thinking_tokens: int = 2000,
        output_format: str = "structured_json"
    ) -> ReasoningResult:

        response = await self.client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=max_thinking_tokens + 1000,
            thinking={
                "type": "enabled",
                "budget_tokens": max_thinking_tokens
            },
            messages=[{
                "role": "user",
                "content": f"Context:\n{context}\n\nConstraints:\n{constraints}\n\nQuery: {query}"
            }]
        )

        thinking_block = next(
            (b for b in response.content if b.type == "thinking"), None
        )
        text_block = next(
            (b for b in response.content if b.type == "text"), None
        )

        return ReasoningResult(
            conclusion=text_block.text if text_block else "",
            full_chain=thinking_block.thinking if thinking_block else None,
            reasoning_summary=self._summarize_thinking(thinking_block),
            confidence=self._estimate_confidence(text_block),
            input_tokens=response.usage.input_tokens,
            thinking_tokens=response.usage.cache_read_input_tokens or 0,
            output_tokens=response.usage.output_tokens,
            provider="claude"
        )
```

### 3.2 OpenAI — Fallback

```python
class OpenAIConversationProvider(ConversationProvider):
    """
    OpenAI GPT as fallback for conversation and vision.
    """

    provider_name = "openai"
    model_name = "gpt-4o"
    max_context_tokens = 128000
    supports_streaming = True
    supports_tool_use = True

    def __init__(self, config: OpenAIProviderConfig):
        self.client = openai.AsyncOpenAI(api_key=config.api_key)
        self.model = config.model or self.model_name

    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False,
    ) -> ChatResponse:
        openai_messages = [
            {"role": "system", "content": system_prompt},
            *[self._to_openai_message(m) for m in messages]
        ]

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            tools=self._to_openai_tools(tools) if tools else openai.NOT_GIVEN,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return ChatResponse(
            content=response.choices[0].message.content or "",
            tool_calls=self._extract_tool_calls(response),
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            model_used=self.model,
            finish_reason=response.choices[0].finish_reason,
            latency_ms=0,  # Computed externally
            provider="openai"
        )


class OpenAIVisionProvider(VisionProvider):
    """OpenAI GPT-4o with vision for image understanding"""

    supported_formats = ["jpg", "jpeg", "png", "webp", "gif"]
    max_image_size_mb = 20.0

    async def extract_text(self, image, language="vi+en", mode="document") -> OCRResult:
        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": self._to_data_url(image)}
                    },
                    {
                        "type": "text",
                        "text": f"Extract all text from this image. Language: {language}. "
                                f"Return the text exactly as it appears, maintaining structure."
                    }
                ]
            }],
            max_tokens=2000
        )
        return OCRResult(
            text=response.choices[0].message.content,
            confidence=0.85,  # GPT-4o typical OCR confidence
            language_detected=language,
            blocks=[],  # Simplified — no block parsing
            provider="openai"
        )


class OpenAISpeechProvider(SpeechProvider):
    """OpenAI Whisper for STT, OpenAI TTS for TTS"""

    async def transcribe(
        self,
        audio: bytes,
        language: str = "vi",
        **kwargs
    ) -> TranscriptionResult:
        response = await self.client.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.mp3", audio, "audio/mpeg"),
            language=language,
            response_format="verbose_json"
        )
        return TranscriptionResult(
            text=response.text,
            confidence=self._compute_confidence(response.segments),
            language=response.language,
            words=[],
            provider="openai"
        )

    async def synthesize(
        self,
        text: str,
        voice: str = "nova",
        language: str = "vi-VN",
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
        audio_format: str = "mp3"
    ) -> TTSResult:
        response = await self.client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            response_format=audio_format,
            speed=speaking_rate,
        )
        audio_bytes = response.content
        return TTSResult(
            audio_bytes=audio_bytes,
            audio_format=audio_format,
            duration_seconds=len(text) / 15,  # ~15 chars/sec estimate
            provider="openai"
        )


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI text-embedding-3-small for semantic search"""

    dimensions = 1536
    max_input_tokens = 8192

    async def embed(self, text: str, model: str | None = None) -> EmbeddingVector:
        response = await self.client.embeddings.create(
            model=model or "text-embedding-3-small",
            input=text,
            encoding_format="float"
        )
        return EmbeddingVector(
            vector=response.data[0].embedding,
            dimensions=self.dimensions,
            model_used=response.model,
            provider="openai",
            input_tokens=response.usage.prompt_tokens
        )

    async def embed_batch(
        self,
        texts: list[str],
        model: str | None = None,
        batch_size: int = 100
    ) -> list[EmbeddingVector]:
        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            response = await self.client.embeddings.create(
                model=model or "text-embedding-3-small",
                input=batch
            )
            for item in response.data:
                results.append(EmbeddingVector(
                    vector=item.embedding,
                    dimensions=self.dimensions,
                    model_used=response.model,
                    provider="openai",
                    input_tokens=0  # Batch doesn't give per-item token count
                ))
        return results
```

### 3.3 Gemini (Google) — Tertiary

```python
class GeminiConversationProvider(ConversationProvider):
    """Google Gemini as tertiary fallback"""

    provider_name = "gemini"
    model_name = "gemini-2.0-flash"
    max_context_tokens = 1000000      # Gemini has very large context
    supports_streaming = True
    supports_tool_use = True

    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        stream: bool = False,
    ) -> ChatResponse:
        model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system_prompt
        )
        gemini_messages = [self._to_gemini_message(m) for m in messages]

        response = await model.generate_content_async(
            gemini_messages,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        )

        return ChatResponse(
            content=response.text,
            tool_calls=None,
            input_tokens=response.usage_metadata.prompt_token_count,
            output_tokens=response.usage_metadata.candidates_token_count,
            model_used=self.model_name,
            finish_reason="stop",
            latency_ms=0,
            provider="gemini"
        )


class GeminiVisionProvider(VisionProvider):
    """Gemini for vision tasks as fallback"""

    supported_formats = ["jpg", "jpeg", "png", "webp", "pdf"]
    max_image_size_mb = 20.0

    async def extract_text(
        self,
        image: bytes | str,
        language: str = "vi+en",
        mode: str = "document"
    ) -> OCRResult:
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"Extract all text from this image. Language: {language}. Maintain structure."
        response = await model.generate_content_async([
            {"mime_type": "image/jpeg", "data": image},
            prompt
        ])
        return OCRResult(
            text=response.text,
            confidence=0.82,
            language_detected=language,
            blocks=[],
            provider="gemini"
        )
```

### 3.4 Open-Weight Models — Local Fallback

```python
class LocalConversationProvider(ConversationProvider):
    """
    Local open-weight models (Qwen, Llama) for cost optimization.
    Runs via Ollama or vLLM on local/edge infrastructure.
    Used for: simple queries, cost-sensitive paths, data privacy.
    """

    provider_name = "local"
    model_name = "qwen2.5-7b-instruct"   # Default
    max_context_tokens = 32768
    supports_streaming = True
    supports_tool_use = False              # Most local models limited tool use

    def __init__(self, config: LocalProviderConfig):
        self.base_url = config.base_url    # Ollama: "http://localhost:11434"
        self.model = config.model or self.model_name

    async def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        **kwargs
    ) -> ChatResponse:
        # Use OpenAI-compatible API (Ollama supports this)
        client = openai.AsyncOpenAI(
            api_key="ollama",
            base_url=self.base_url + "/v1"
        )
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                *[self._to_openai_format(m) for m in messages]
            ],
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 2000),
        )
        return ChatResponse(
            content=response.choices[0].message.content,
            tool_calls=None,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            model_used=self.model,
            finish_reason="stop",
            latency_ms=0,
            provider="local"
        )
```

---

## 4. Provider Infrastructure

### 4.1 Model Registry

```python
@dataclass
class ModelRegistration:
    model_id: str                      # "claude-sonnet-4-5", "gpt-4o", etc.
    provider: str
    capabilities: list[str]            # ["conversation", "reasoning", "vision", etc.]
    context_window: int
    input_cost_per_1k_tokens: float   # USD
    output_cost_per_1k_tokens: float  # USD
    supports_streaming: bool
    supports_tool_use: bool
    supports_vision: bool
    supports_thinking: bool
    languages_supported: list[str]
    tier: str                          # "primary" | "fallback" | "tertiary" | "local"
    is_active: bool
    added_at: datetime
    deprecated_at: datetime | None

MODEL_REGISTRY = {
    "claude-sonnet-4-5": ModelRegistration(
        model_id="claude-sonnet-4-5",
        provider="claude",
        capabilities=["conversation", "reasoning", "tool_use"],
        context_window=200000,
        input_cost_per_1k_tokens=0.003,
        output_cost_per_1k_tokens=0.015,
        supports_streaming=True,
        supports_tool_use=True,
        supports_vision=False,         # Use claude-3-5-sonnet for vision
        supports_thinking=True,
        languages_supported=["vi", "en", "all"],
        tier="primary",
        is_active=True,
        added_at=datetime(2025, 1, 1)
    ),
    "gpt-4o": ModelRegistration(
        model_id="gpt-4o",
        provider="openai",
        capabilities=["conversation", "vision", "tool_use"],
        context_window=128000,
        input_cost_per_1k_tokens=0.0025,
        output_cost_per_1k_tokens=0.010,
        supports_streaming=True,
        supports_tool_use=True,
        supports_vision=True,
        supports_thinking=False,
        languages_supported=["vi", "en", "all"],
        tier="fallback",
        is_active=True,
        added_at=datetime(2024, 5, 1)
    ),
    "gemini-2.0-flash": ModelRegistration(
        model_id="gemini-2.0-flash",
        provider="gemini",
        capabilities=["conversation", "vision"],
        context_window=1000000,
        input_cost_per_1k_tokens=0.00035,
        output_cost_per_1k_tokens=0.00105,
        supports_streaming=True,
        supports_tool_use=True,
        supports_vision=True,
        supports_thinking=False,
        languages_supported=["vi", "en", "all"],
        tier="tertiary",
        is_active=True,
        added_at=datetime(2025, 2, 1)
    ),
    "qwen2.5-7b-instruct": ModelRegistration(
        model_id="qwen2.5-7b-instruct",
        provider="local",
        capabilities=["conversation"],
        context_window=32768,
        input_cost_per_1k_tokens=0.0,   # Local: no API cost
        output_cost_per_1k_tokens=0.0,
        supports_streaming=True,
        supports_tool_use=False,
        supports_vision=False,
        supports_thinking=False,
        languages_supported=["vi", "en", "zh"],
        tier="local",
        is_active=False,               # Enable when local infra ready
        added_at=datetime(2026, 6, 1)
    ),
}
```

### 4.2 Capability Registry

```python
CAPABILITY_REGISTRY = {
    # Maps feature → provider capabilities
    "conversation_primary": {
        "primary": "claude/claude-sonnet-4-5",
        "fallback": "openai/gpt-4o",
        "tertiary": "gemini/gemini-2.0-flash",
        "local": "local/qwen2.5-7b-instruct",
    },
    "reasoning_extended": {
        "primary": "claude/claude-sonnet-4-5",  # Thinking tokens
        "fallback": "openai/gpt-4o",            # Chain-of-thought without explicit thinking
        "tertiary": None,                        # Gemini not used for reasoning
    },
    "vision_ocr": {
        "primary": "openai/gpt-4o",            # OpenAI better at OCR
        "fallback": "gemini/gemini-2.0-flash",
        "tertiary": None,
    },
    "vision_description": {
        "primary": "openai/gpt-4o",
        "fallback": "gemini/gemini-2.0-flash",
    },
    "speech_stt": {
        "primary": "openai/whisper-1",
        "fallback": None,                       # No secondary STT yet
    },
    "speech_tts": {
        "primary": "openai/tts-1",
        "fallback": None,
    },
    "embedding": {
        "primary": "openai/text-embedding-3-small",
        "fallback": None,
    },
    "reranking": {
        "primary": "cohere/rerank-v3",          # Future
        "fallback": "local/cross-encoder",      # Future
    },
    "translation_vi_en": {
        "primary": "openai/gpt-4o-mini",
        "fallback": "gemini/gemini-2.0-flash",
    },
    "moderation": {
        "primary": "openai/omni-moderation-latest",
        "fallback": "claude/claude-haiku-4",   # Cheaper model for moderation
    },
    "evaluation": {
        "primary": "claude/claude-sonnet-4-5", # Best for nuanced evaluation
        "fallback": "openai/gpt-4o",
    },
    "cost_tracking": {
        "primary": "internal/meto-cost-tracker",  # Internal implementation
    },
}
```

### 4.3 Routing Policy

```python
class RoutingPolicy:
    """
    Rules-based routing: task type → provider.
    Applied before circuit breaker check.
    """

    TASK_TYPE_RULES = {
        # Conversational tasks
        "chat_simple": ["claude", "openai", "gemini", "local"],
        "chat_complex_reasoning": ["claude", "openai", "gemini"],
        "chat_tool_use": ["claude", "openai", "gemini"],

        # Reasoning tasks
        "clinical_reasoning": ["claude", "openai"],   # No local — too important
        "self_critique": ["claude", "openai"],

        # Vision tasks
        "ocr_lab_report": ["openai", "gemini"],       # OpenAI first for OCR
        "image_description": ["openai", "gemini"],
        "food_recognition": ["openai", "gemini"],

        # Speech tasks
        "speech_to_text": ["openai"],                 # Whisper only for now
        "text_to_speech": ["openai"],

        # Embedding tasks
        "knowledge_embedding": ["openai"],
        "memory_embedding": ["openai"],

        # Moderation
        "content_moderation": ["openai", "claude"],
        "medical_scope_check": ["claude"],            # Claude best for nuanced medical

        # Cost optimization
        "simple_translation": ["gemini", "openai"],   # Gemini cheaper
        "simple_classification": ["gemini", "openai", "local"],
    }

    def get_provider_chain(
        self,
        task_type: str,
        user_priority: str = "balanced"  # "quality" | "speed" | "cost" | "balanced"
    ) -> list[str]:

        base_chain = self.TASK_TYPE_RULES.get(task_type, ["claude", "openai", "gemini"])

        if user_priority == "cost":
            # Reorder to prefer cheapest eligible
            return sorted(
                base_chain,
                key=lambda p: MODEL_REGISTRY.get(
                    CAPABILITY_REGISTRY.get(task_type, {}).get("primary", ""), {}
                ).input_cost_per_1k_tokens or 999
            )

        if user_priority == "speed":
            # Reorder to prefer fastest (by last measured latency)
            return sorted(
                base_chain,
                key=lambda p: provider_health_monitor.get_avg_latency(p)
            )

        return base_chain  # Default: quality order
```

### 4.4 Health Check

```python
class ProviderHealthMonitor:
    """
    Background health check per provider.
    Runs every 60 seconds.
    """

    HEALTH_CHECK_INTERVAL_SECONDS = 60
    LATENCY_WINDOW_SIZE = 20           # Rolling window for avg latency

    async def check_provider(self, provider_name: str) -> ProviderHealthStatus:
        provider = provider_registry.get_instance(provider_name)
        start = time.monotonic()

        try:
            # Minimal ping — use cheapest/fastest model
            test_response = await provider.chat(
                messages=[ChatMessage(role="user", content="ping")],
                system_prompt="Reply with 'pong'",
                max_tokens=5
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            await self._record_health(provider_name, True, latency_ms)
            return ProviderHealthStatus(
                provider=provider_name,
                is_alive=True,
                last_latency_ms=latency_ms,
                avg_latency_ms=await self.get_avg_latency(provider_name),
                error=None
            )

        except Exception as e:
            await self._record_health(provider_name, False, None)
            return ProviderHealthStatus(
                provider=provider_name,
                is_alive=False,
                last_latency_ms=None,
                error=str(e)
            )

    async def get_avg_latency(self, provider_name: str) -> float:
        readings = await redis.lrange(f"health:latency:{provider_name}", 0, -1)
        if not readings:
            return 9999.0
        return sum(float(r) for r in readings) / len(readings)
```

### 4.5 Circuit Breaker

```python
class ProviderCircuitBreaker:
    """
    Classic circuit breaker pattern per provider.
    States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing)
    """

    class State(str, Enum):
        CLOSED = "closed"              # Normal operation
        OPEN = "open"                  # Provider failing, reject all calls
        HALF_OPEN = "half_open"        # Testing if provider recovered

    FAILURE_THRESHOLD = 5              # Failures before OPEN
    SUCCESS_THRESHOLD = 2              # Successes in HALF_OPEN before CLOSED
    OPEN_TIMEOUT_SECONDS = 60         # Time in OPEN before trying HALF_OPEN

    async def call(
        self,
        provider_name: str,
        callable_fn: Callable
    ) -> Any:
        state = await self._get_state(provider_name)

        if state == self.State.OPEN:
            # Check if timeout has passed
            open_since = await self._get_open_since(provider_name)
            if (utcnow() - open_since).seconds < self.OPEN_TIMEOUT_SECONDS:
                raise CircuitBreakerOpenError(
                    f"Provider {provider_name} circuit is OPEN"
                )
            # Transition to HALF_OPEN
            await self._set_state(provider_name, self.State.HALF_OPEN)

        try:
            result = await callable_fn()
            await self._record_success(provider_name)
            return result

        except ProviderError as e:
            await self._record_failure(provider_name, e)

            failure_count = await self._get_failure_count(provider_name)
            if failure_count >= self.FAILURE_THRESHOLD:
                await self._set_state(provider_name, self.State.OPEN)
                logger.warning(f"Circuit OPENED for provider: {provider_name}")

            raise

    async def _get_state(self, provider_name: str) -> State:
        raw = await redis.get(f"circuit:{provider_name}:state")
        return self.State(raw) if raw else self.State.CLOSED
```

### 4.6 Cost Optimization

```python
class CostOptimizer:
    """
    Dynamic routing based on cost, while maintaining quality requirements.
    """

    # Quality tiers — minimum model tier required per task
    QUALITY_REQUIREMENTS = {
        "emergency_response": "DO_NOT_OPTIMIZE",  # Always primary provider
        "clinical_reasoning": "DO_NOT_OPTIMIZE",   # Too critical for cost cutting
        "recommendation_engine": "MODERATE",       # Can use fallback
        "simple_explanation": "FLEXIBLE",          # Can use cheapest
        "general_qa": "FLEXIBLE",
        "reminder_creation": "FLEXIBLE",
    }

    def select_provider_for_cost(
        self,
        task_type: str,
        budget_per_request_usd: float = 0.05
    ) -> str:
        quality_tier = self.QUALITY_REQUIREMENTS.get(task_type, "MODERATE")

        if quality_tier == "DO_NOT_OPTIMIZE":
            return "claude"  # Always primary

        # Filter providers by cost
        affordable = []
        for model_id, model in MODEL_REGISTRY.items():
            if not model.is_active:
                continue
            estimated_cost = self._estimate_typical_cost(model_id, task_type)
            if estimated_cost <= budget_per_request_usd:
                affordable.append((model_id, estimated_cost))

        if not affordable:
            return "claude"  # Fallback to primary if nothing fits

        # Sort by cost
        affordable.sort(key=lambda x: x[1])

        # Pick cheapest that meets quality requirement
        if quality_tier == "FLEXIBLE":
            return affordable[0][0]

        # MODERATE: skip local models
        for model_id, _ in affordable:
            if MODEL_REGISTRY[model_id].tier != "local":
                return model_id

        return "claude"  # Safety fallback

    def _estimate_typical_cost(self, model_id: str, task_type: str) -> float:
        model = MODEL_REGISTRY.get(model_id)
        if not model:
            return 999.0

        TYPICAL_TOKENS = {
            "simple_explanation": (500, 300),   # (input, output)
            "clinical_reasoning": (2000, 1000),
            "general_qa": (800, 500),
            "reminder_creation": (300, 100),
        }
        input_t, output_t = TYPICAL_TOKENS.get(task_type, (1000, 500))
        return (input_t * model.input_cost_per_1k_tokens / 1000 +
                output_t * model.output_cost_per_1k_tokens / 1000)
```

### 4.7 Dynamic Routing

```python
class DynamicRouter:
    """
    Combines: policy routing + health + circuit breaker + cost optimization
    Makes final provider selection decision at runtime.
    """

    async def select(
        self,
        task_type: str,
        user_priority: str = "balanced",
        budget_usd: float | None = None
    ) -> str:

        # Get ordered provider chain from policy
        chain = routing_policy.get_provider_chain(task_type, user_priority)

        for provider_name in chain:
            # Check circuit breaker
            state = await circuit_breaker._get_state(provider_name)
            if state == ProviderCircuitBreaker.State.OPEN:
                continue

            # Check health
            health = await health_monitor.get_status(provider_name)
            if not health.is_alive:
                continue

            # Check cost if budget constraint given
            if budget_usd is not None:
                provider_primary_model = CAPABILITY_REGISTRY.get(task_type, {}).get("primary", "")
                model_reg = MODEL_REGISTRY.get(provider_primary_model)
                if model_reg:
                    estimated = cost_optimizer._estimate_typical_cost(
                        provider_primary_model, task_type
                    )
                    if estimated > budget_usd:
                        continue

            return provider_name

        # All providers failed/unavailable
        raise AllProvidersUnavailableError(
            f"No available provider for task: {task_type}"
        )
```

### 4.8 Feature Flags

```python
class ProviderFeatureFlags:
    """
    Enable/disable provider per feature at runtime.
    No deploy needed to switch providers.
    """

    FLAGS_KEY = "meto:provider_flags"

    async def set_flag(
        self,
        feature: str,
        provider: str,
        enabled: bool,
        reason: str
    ):
        await redis.hset(
            self.FLAGS_KEY,
            f"{feature}:{provider}",
            json.dumps({"enabled": enabled, "reason": reason, "set_at": str(utcnow())})
        )
        await audit_log.record({
            "action": "provider_flag_changed",
            "feature": feature,
            "provider": provider,
            "enabled": enabled,
            "reason": reason
        })

    async def is_enabled(self, feature: str, provider: str) -> bool:
        raw = await redis.hget(self.FLAGS_KEY, f"{feature}:{provider}")
        if raw:
            return json.loads(raw)["enabled"]
        return True  # Default: enabled

    # Example usage:
    # await flags.set_flag("conversation", "openai", False, "OpenAI outage 2026-06-30")
    # → Immediately routes all conversation calls away from OpenAI

DEFAULT_FEATURE_FLAGS = {
    # "feature:provider": enabled
    "conversation:claude": True,
    "conversation:openai": True,       # Set to False during OpenAI incidents
    "conversation:gemini": True,
    "conversation:local": False,       # Enable when local infra ready
    "vision:openai": True,
    "vision:gemini": True,
    "speech_stt:openai": True,
    "speech_tts:openai": True,
    "embedding:openai": True,
    "moderation:openai": True,
}
```

---

## 5. Provider Mappings Summary

```
╔══════════════════════════════════════════════════════════════════════╗
║                    PROVIDER CAPABILITY MATRIX                        ║
╠══════════════════╦══════════╦══════════╦══════════╦══════════════════╣
║ Interface        ║ Claude   ║ OpenAI   ║ Gemini   ║ Local (OSS)     ║
╠══════════════════╬══════════╬══════════╬══════════╬══════════════════╣
║ Conversation     ║ PRIMARY  ║ FALLBACK ║ TERTIARY ║ cost_opt (off)  ║
║ Reasoning        ║ PRIMARY  ║ FALLBACK ║    -     ║        -        ║
║ Vision (OCR)     ║    -     ║ PRIMARY  ║ FALLBACK ║        -        ║
║ Vision (Desc.)   ║    -     ║ PRIMARY  ║ FALLBACK ║        -        ║
║ Speech STT       ║    -     ║ PRIMARY  ║    -     ║ future          ║
║ Speech TTS       ║    -     ║ PRIMARY  ║    -     ║ future          ║
║ Embedding        ║    -     ║ PRIMARY  ║    -     ║ future          ║
║ Reranking        ║    -     ║    -     ║    -     ║ Cohere (future) ║
║ Translation      ║    -     ║ FALLBACK ║ PRIMARY  ║        -        ║
║ Moderation       ║ FALLBACK ║ PRIMARY  ║    -     ║        -        ║
║ Evaluation       ║ PRIMARY  ║ FALLBACK ║    -     ║        -        ║
║ Cost Tracking    ║ Internal ║ Internal ║ Internal ║ Internal        ║
╚══════════════════╩══════════╩══════════╩══════════╩══════════════════╝

Note: "-" = Not used for this capability
      Claude does NOT provide vision (use OpenAI/Gemini for images)
```

---

## 6. Design Principle: Swap Provider = Swap One Class

```python
# BEFORE: Business logic (ClinicalReasoningLayer) calls Claude directly
#
# ❌ WRONG (hardcoded)
# class ClinicalReasoningLayer:
#     async def reason(self, context):
#         response = await anthropic.messages.create(
#             model="claude-sonnet-4-5",
#             ...
#         )

# AFTER: Business logic uses interface only
#
# ✅ CORRECT (abstracted)
class ClinicalReasoningLayer:
    def __init__(self, reasoning_provider: ReasoningProvider):
        self.provider = reasoning_provider  # Injected via DI

    async def reason(self, context: AssembledContext) -> ReasoningResult:
        return await self.provider.reason(
            query=context.user_query,
            context=context.to_prompt_block(),
            constraints=REASONING_SAFETY_CONSTRAINTS
        )

# To switch from Claude to OpenAI:
# In DI container, change:
#   ReasoningProvider → ClaudeReasoningProvider(config)
# to:
#   ReasoningProvider → OpenAIReasoningProvider(config)
#
# ClinicalReasoningLayer code: UNCHANGED
# All business logic: UNCHANGED
# Tests: UNCHANGED (mock the interface)

# This applies to ALL 10 interfaces above.
```

---

## 7. Acceptance Criteria

### AC-PAL-001: Interface Compliance
- [ ] All 10 interfaces defined with abstract methods
- [ ] Claude implementation: all abstract methods implemented
- [ ] OpenAI implementation: all abstract methods implemented
- [ ] Gemini implementation: ConversationProvider + VisionProvider implemented
- [ ] Local implementation: ConversationProvider implemented

### AC-PAL-002: Routing
- [ ] Dynamic routing selects provider within 5ms
- [ ] Circuit breaker triggers after 5 consecutive failures
- [ ] Circuit breaker resets after 60 seconds
- [ ] Cost optimization skips providers that exceed budget_per_request

### AC-PAL-003: Health Monitoring
- [ ] Health check runs every 60 seconds per provider
- [ ] Health status queryable via admin API
- [ ] Unhealthy provider automatically removed from rotation

### AC-PAL-004: Feature Flags
- [ ] Feature flag change takes effect within 10 seconds
- [ ] Feature flag changes logged to audit trail
- [ ] Default flags defined for all providers

### AC-PAL-005: Cost Tracking
- [ ] Every LLM call records input/output tokens
- [ ] Cost computed per request
- [ ] Monthly usage summary available
- [ ] DO_NOT_OPTIMIZE tasks never routed by cost

### AC-PAL-006: Provider Swap
- [ ] Business logic classes accept provider via constructor injection
- [ ] No direct provider imports in business logic layers
- [ ] Integration tests pass with mocked providers

---

## 8. Future Provider Additions

```python
# Adding a new provider requires:
# 1. Implement relevant interfaces (1-3 classes max)
# 2. Register in MODEL_REGISTRY
# 3. Register in CAPABILITY_REGISTRY
# 4. Set default feature flags
# 5. Add to DI container
#
# NO changes to:
# - AgentOrchestrationLayer
# - ClinicalReasoningLayer
# - RecommendationEngine
# - DoctorHandoffEngine
# - ConversationEngine
# - ContextEngine
# - Any other business logic

FUTURE_PROVIDERS = [
    "cohere",          # Reranking (soon)
    "azure_openai",    # Enterprise option
    "aws_bedrock",     # AWS option
    "mistral",         # EU privacy option
    "on_device",       # Edge inference (2027+)
]
```

---

*Xem thêm: 19_AGENT_ORCHESTRATION.md (sử dụng PAL qua DI), 18_MULTIMODAL.md (VisionProvider và SpeechProvider), 16_KNOWLEDGE_BASE.md (EmbeddingProvider cho future RAG)*
