"""LLM Gateway — the single choke point every LLM response flows through.

Responsibilities (no generation path may bypass these):
1. Per-user cost/rate guard (RPM + TPM)         -> 429 when exceeded
2. Response cache (identical prompt + user)      -> cost reduction
3. Provider completion (mock by default)
4. Output guardrail (Medical Safety Validator)   -> BLOCK -> safe message
5. Mandatory disclaimer + token accounting + metrics

The gateway owns guardrail enforcement so that adapters stay thin and NO code
path can emit an unvalidated LLM response.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.metrics import registry
from app.domain import guardrails, policies
from app.domain.guardrails import GuardrailDecision

from .base import LLMMessage, LLMResponse
from .cache import LRUResponseCache, make_key
from .cost import CostGuard
from .factory import get_provider


class LLMGateway:
    def __init__(self, *, cost_guard: CostGuard, cache: LRUResponseCache | None) -> None:
        self._cost = cost_guard
        self._cache = cache

    @staticmethod
    def _augment_with_rag(system: str, rag_query: str | None, messages: list[LLMMessage]) -> str:
        # Lazy import keeps the LLM package independent of the RAG package.
        from app.rag import get_retriever

        query = rag_query
        if not query:
            for msg in reversed(messages):
                if msg.role == "user":
                    query = msg.content
                    break
        context = get_retriever().build_context(query or "")
        if not context:
            return system
        registry.inc_counter("llm_rag_augmented_total")
        return f"{system}\n\n{context}"

    def complete(
        self,
        *,
        user_id: str,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        with_rag: bool = False,
        rag_query: str | None = None,
        now: float | None = None,
    ) -> LLMResponse:
        settings = get_settings()
        provider = get_provider()
        system = system or policies.SYSTEM_SAFETY_PROMPT_VI
        max_tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens
        temperature = temperature if temperature is not None else settings.llm_temperature

        # 0. Optional RAG augmentation — retrieve approved context and prepend it
        # to the system prompt. Retrieved text is injection-vetted by the retriever.
        if with_rag and settings.rag_enabled:
            system = self._augment_with_rag(system, rag_query, messages)

        # 1. Cost / rate guard (raises LLMRateLimitError -> 429).
        self._cost.check(user_id, now=now)

        # 2. Cache lookup (already-guardrailed responses only).
        key = make_key(
            provider=provider.name,
            model=settings.llm_model,
            system=system,
            messages=messages,
            user_id=user_id,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if self._cache is not None:
            hit = self._cache.get(key, now=now)
            if hit is not None:
                # Count the request for RPM but charge no tokens (cache is free).
                self._cost.record(user_id, 0, now=now)
                registry.inc_counter("llm_cache_hits_total")
                registry.inc_counter("llm_requests_total", {"result": "cache_hit"})
                return hit

        # 3. Provider completion.
        raw = provider.complete(
            messages, system=system, max_tokens=max_tokens, temperature=temperature
        )

        # 4. Output guardrail — last line of defense, runs on EVERY response.
        out = guardrails.check_output(raw.text)
        if out.decision == GuardrailDecision.BLOCK:
            safe = out.safe_message or policies.SAFE_REFUSAL_MEDICATION_VI
            response = LLMResponse(
                text=guardrails.ensure_disclaimer(safe),
                model=raw.model,
                prompt_tokens=raw.prompt_tokens,
                completion_tokens=raw.completion_tokens,
                blocked=True,
                finish_reason="blocked",
                safety_flags=out.safety_flags,
            )
            registry.inc_counter("llm_blocked_total")
            registry.inc_counter("llm_requests_total", {"result": "blocked"})
        else:
            response = LLMResponse(
                text=guardrails.ensure_disclaimer(raw.text),
                model=raw.model,
                prompt_tokens=raw.prompt_tokens,
                completion_tokens=raw.completion_tokens,
                finish_reason=raw.finish_reason,
            )
            registry.inc_counter("llm_requests_total", {"result": "ok"})

        # 5. Token accounting + cache store.
        self._cost.record(user_id, response.total_tokens, now=now)
        if self._cache is not None:
            self._cache.put(key, response, now=now)
        return response


# --------------------------------------------------------------------------- #
# Singleton wiring (per process). reset_gateway() for tests / config changes.
# --------------------------------------------------------------------------- #

_gateway: LLMGateway | None = None


def get_gateway() -> LLMGateway:
    global _gateway
    if _gateway is None:
        settings = get_settings()
        cost = CostGuard(
            max_rpm=settings.llm_max_requests_per_minute,
            max_tpm=settings.llm_max_tokens_per_minute,
        )
        cache = (
            LRUResponseCache(
                max_entries=settings.llm_cache_max_entries,
                ttl_seconds=settings.llm_cache_ttl_seconds,
            )
            if settings.llm_cache_enabled
            else None
        )
        _gateway = LLMGateway(cost_guard=cost, cache=cache)
    return _gateway


def reset_gateway() -> None:
    """Test helper: drop the gateway singleton (also drops cost + cache state)."""
    global _gateway
    _gateway = None
