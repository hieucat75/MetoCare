"""
Meto AI — Deep Readiness Check

Layers:
  1. API key present
  2. 9Router reachable (if configured)
  3. Provider ping (lightweight test call)
  4. Conversation endpoint self-test
  5. Streaming self-test
  6. Latency under threshold

Used by:
  - /meto/health endpoint
  - CI deployment gate script
  - GitHub Actions gate step
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    gate: str           # gate name
    passed: bool
    latency_ms: int
    detail: str         # human-readable
    error: str | None = None


@dataclass
class ReadinessReport:
    timestamp: str
    mode: str           # "full" | "fallback_only" | "mock" | "unavailable"
    gates: list[GateResult] = field(default_factory=list)
    all_passed: bool = False
    score: int = 0          # 0-100, gates_passed / total_gates * 100
    deploy_allowed: bool = False  # score >= 80 AND safety gate passed
    summary: str = ""       # one-line human readable


# ---------------------------------------------------------------------------
# Legacy simple check (kept for backwards compatibility)
# ---------------------------------------------------------------------------

def check_provider_readiness() -> dict:
    """Return readiness status for each AI provider.

    Returns dict with:
      - claude: bool (ANTHROPIC_API_KEY present and non-empty)
      - openai: bool (OPENAI_API_KEY present and non-empty)
      - any_ready: bool (at least one provider ready)
      - mode: "full" | "fallback_only" | "mock" | "unavailable"
    """
    ai_mode = os.environ.get("MCP_AI_MODE", "")
    if ai_mode == "mock":
        return {"claude": False, "openai": False, "any_ready": True, "mode": "mock"}

    claude_ready = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    openai_ready = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    nine_router_ready = bool(os.environ.get("MCP_NINE_ROUTER_API_KEY", "").strip())
    openrouter_ready = bool(os.environ.get("MCP_OPENROUTER_API_KEY", "").strip())
    deepseek_ready = bool(os.environ.get("MCP_DEEPSEEK_API_KEY", "").strip())

    any_ready = claude_ready or openai_ready or nine_router_ready or openrouter_ready or deepseek_ready

    if (claude_ready or nine_router_ready or openrouter_ready) and (openai_ready or deepseek_ready):
        mode = "full"
    elif any_ready:
        mode = "fallback_only"
    else:
        mode = "unavailable"

    return {
        "claude": claude_ready,
        "openai": openai_ready,
        "nine_router": nine_router_ready,
        "openrouter": openrouter_ready,
        "deepseek": deepseek_ready,
        "any_ready": any_ready,
        "mode": mode,
    }


def assert_provider_ready() -> None:
    """Raise RuntimeError if no provider is configured."""
    status = check_provider_readiness()
    if not status["any_ready"]:
        raise RuntimeError(
            "Meto AI: no provider configured. "
            "Set ANTHROPIC_API_KEY or OPENAI_API_KEY."
        )
    logger.info("Meto provider readiness: %s", status)


# ---------------------------------------------------------------------------
# Deep readiness checker
# ---------------------------------------------------------------------------

class MetoReadinessChecker:
    """Multi-layer readiness check for Meto AI."""

    PROVIDER_IDENTITY_PHRASES = [
        "i am claude",
        "i'm claude",
        "made by anthropic",
        "from anthropic",
        "i am gpt",
        "i'm gpt",
        "i am openai",
        "made by openai",
        "tôi là claude",
        "tôi là gpt",
        "tôi là openai",
        "tôi là anthropic",
    ]

    async def check_all(self, fast: bool = False) -> ReadinessReport:
        """Run all readiness layers. fast=True skips provider ping."""
        import datetime

        timestamp = datetime.datetime.utcnow().isoformat() + "Z"

        # Determine mode
        ai_mode = os.environ.get("MCP_AI_MODE", "")
        basic = check_provider_readiness()
        mode = basic["mode"] if ai_mode != "mock" else "mock"

        gates: list[GateResult] = []

        # Gate 1: API keys
        gates.append(await self.check_keys())

        if not fast:
            # Gate 2: Provider ping (skipped in fast mode)
            gates.append(await self.check_provider_ping())

        # Gate 3: Streaming
        gates.append(await self.check_streaming())

        # Gate 4: Latency
        gates.append(await self.check_latency())

        # Gate 5: Safety guard
        gates.append(await self.check_safety_guard())

        # Gate 6: Provider identity leak check
        gates.append(await self.check_provider_identity())

        total = len(gates)
        passed = sum(1 for g in gates if g.passed)
        score = int(passed / total * 100) if total > 0 else 0

        safety_gate = next((g for g in gates if g.gate == "safety_guard"), None)
        safety_passed = safety_gate.passed if safety_gate else False

        deploy_allowed = score >= 80 and safety_passed
        all_passed = passed == total

        if deploy_allowed:
            summary = f"✅ Ready — {passed}/{total} gates passed (score {score}/100)"
        else:
            failed_gates = [g.gate for g in gates if not g.passed]
            summary = (
                f"❌ Not ready — {passed}/{total} gates passed (score {score}/100). "
                f"Failed: {', '.join(failed_gates)}"
            )

        return ReadinessReport(
            timestamp=timestamp,
            mode=mode,
            gates=gates,
            all_passed=all_passed,
            score=score,
            deploy_allowed=deploy_allowed,
            summary=summary,
        )

    async def check_keys(self) -> GateResult:
        """Gate 1: API keys present."""
        t0 = time.monotonic()

        ai_mode = os.environ.get("MCP_AI_MODE", "")
        if ai_mode == "mock":
            return GateResult(
                gate="api_keys",
                passed=True,
                latency_ms=int((time.monotonic() - t0) * 1000),
                detail="mock mode — key check bypassed",
            )

        claude_key = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
        openai_key = bool(os.environ.get("OPENAI_API_KEY", "").strip())
        nine_router_key = bool(os.environ.get("MCP_NINE_ROUTER_API_KEY", "").strip())
        openrouter_key = bool(os.environ.get("MCP_OPENROUTER_API_KEY", "").strip())
        deepseek_key = bool(os.environ.get("MCP_DEEPSEEK_API_KEY", "").strip())

        latency_ms = int((time.monotonic() - t0) * 1000)

        any_key = claude_key or openai_key or nine_router_key or openrouter_key or deepseek_key

        if any_key:
            parts = []
            if claude_key:
                parts.append("claude=yes")
            if openai_key:
                parts.append("openai=yes")
            if nine_router_key:
                parts.append("9router=yes")
            if openrouter_key:
                parts.append("openrouter=yes")
            if deepseek_key:
                parts.append("deepseek=yes")
            return GateResult(
                gate="api_keys",
                passed=True,
                latency_ms=latency_ms,
                detail=f"({', '.join(parts)})",
            )
        else:
            return GateResult(
                gate="api_keys",
                passed=False,
                latency_ms=latency_ms,
                detail="no API keys configured",
                error="No provider API keys found (ANTHROPIC_API_KEY, OPENAI_API_KEY, MCP_NINE_ROUTER_API_KEY, MCP_OPENROUTER_API_KEY, MCP_DEEPSEEK_API_KEY all absent)",
            )

    async def check_provider_ping(self) -> GateResult:
        """Gate 2: lightweight ping to each configured provider."""
        t0 = time.monotonic()

        ai_mode = os.environ.get("MCP_AI_MODE", "")
        if ai_mode == "mock":
            return GateResult(
                gate="provider_ping",
                passed=True,
                latency_ms=int((time.monotonic() - t0) * 1000),
                detail="mock mode — ping simulated",
            )

        claude_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        results = []
        errors = []

        if claude_key:
            try:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=claude_key)
                ping_start = time.monotonic()
                msg = await client.messages.create(
                    model="claude-haiku-4-5",
                    max_tokens=5,
                    messages=[{"role": "user", "content": "ping"}],
                )
                ping_ms = int((time.monotonic() - ping_start) * 1000)
                if msg.content:
                    results.append(f"claude={ping_ms}ms")
                else:
                    errors.append("claude=empty_response")
            except Exception as exc:
                errors.append(f"claude={type(exc).__name__}: {exc!s:.80}")

        if openai_key:
            try:
                import openai as openai_lib
                client = openai_lib.AsyncOpenAI(api_key=openai_key)
                ping_start = time.monotonic()
                resp = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=5,
                    messages=[{"role": "user", "content": "ping"}],
                )
                ping_ms = int((time.monotonic() - ping_start) * 1000)
                if resp.choices:
                    results.append(f"openai={ping_ms}ms")
                else:
                    errors.append("openai=empty_response")
            except Exception as exc:
                errors.append(f"openai={type(exc).__name__}: {exc!s:.80}")

        latency_ms = int((time.monotonic() - t0) * 1000)

        if not claude_key and not openai_key:
            return GateResult(
                gate="provider_ping",
                passed=False,
                latency_ms=latency_ms,
                detail="no keys configured",
                error="ANTHROPIC_API_KEY and OPENAI_API_KEY both absent",
            )

        if errors and not results:
            return GateResult(
                gate="provider_ping",
                passed=False,
                latency_ms=latency_ms,
                detail="; ".join(errors),
                error="; ".join(errors),
            )

        detail_parts = results + errors
        return GateResult(
            gate="provider_ping",
            passed=bool(results),
            latency_ms=latency_ms,
            detail=", ".join(detail_parts),
            error="; ".join(errors) if errors else None,
        )

    async def check_streaming(self) -> GateResult:
        """Gate 3: verify streaming works — receive at least 1 chunk."""
        t0 = time.monotonic()

        ai_mode = os.environ.get("MCP_AI_MODE", "")
        if ai_mode == "mock":
            return GateResult(
                gate="streaming",
                passed=True,
                latency_ms=int((time.monotonic() - t0) * 1000),
                detail="mock mode — streaming simulated (3 chunks)",
            )

        claude_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        nine_router_key = os.environ.get("MCP_NINE_ROUTER_API_KEY", "").strip()
        openrouter_key = os.environ.get("MCP_OPENROUTER_API_KEY", "").strip()
        deepseek_key = os.environ.get("MCP_DEEPSEEK_API_KEY", "").strip()
        deepseek_base_url = os.environ.get("MCP_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        deepseek_model = os.environ.get("MCP_DEEPSEEK_MODEL", "deepseek-chat")
        openrouter_base_url = os.environ.get("MCP_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        openrouter_model = os.environ.get("MCP_OPENROUTER_PRIMARY_MODEL", "openai/gpt-4o-mini")
        nine_router_base_url = os.environ.get("MCP_NINE_ROUTER_BASE_URL", "http://127.0.0.1:20128/v1")
        nine_router_model = os.environ.get("MCP_NINE_ROUTER_PRIMARY_MODEL", "cc/claude-sonnet-4-6")

        if not any([claude_key, openai_key, nine_router_key, openrouter_key, deepseek_key]):
            return GateResult(
                gate="streaming",
                passed=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                detail="no keys — streaming not testable",
                error="no API keys configured",
            )

        # Try Claude streaming first
        if claude_key:
            try:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=claude_key)
                chunk_count = 0
                async with client.messages.stream(
                    model="claude-haiku-4-5",
                    max_tokens=20,
                    messages=[{"role": "user", "content": "Say hello"}],
                ) as stream:
                    async for _ in stream.text_stream:
                        chunk_count += 1
                        if chunk_count >= 1:
                            break

                latency_ms = int((time.monotonic() - t0) * 1000)
                if chunk_count >= 1:
                    return GateResult(
                        gate="streaming",
                        passed=True,
                        latency_ms=latency_ms,
                        detail=f"claude streaming ok ({chunk_count}+ chunks)",
                    )
                else:
                    return GateResult(
                        gate="streaming",
                        passed=False,
                        latency_ms=latency_ms,
                        detail="claude streaming returned 0 chunks",
                        error="0 chunks received",
                    )
            except Exception as exc:
                logger.warning("Claude streaming check failed: %s", exc)
                if not openai_key:
                    return GateResult(
                        gate="streaming",
                        passed=False,
                        latency_ms=int((time.monotonic() - t0) * 1000),
                        detail=f"claude streaming failed: {exc!s:.80}",
                        error=str(exc),
                    )

        # Try OpenAI streaming fallback
        if openai_key:
            try:
                import openai as openai_lib
                client = openai_lib.AsyncOpenAI(api_key=openai_key)
                chunk_count = 0
                async for _ in await client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=20,
                    messages=[{"role": "user", "content": "Say hello"}],
                    stream=True,
                ):
                    if _.choices and _.choices[0].delta.content:
                        chunk_count += 1
                        if chunk_count >= 1:
                            break

                latency_ms = int((time.monotonic() - t0) * 1000)
                passed = chunk_count >= 1
                return GateResult(
                    gate="streaming",
                    passed=passed,
                    latency_ms=latency_ms,
                    detail=f"openai streaming {'ok' if passed else 'failed'} ({chunk_count} chunks)",
                    error=None if passed else "0 chunks received",
                )
            except Exception as exc:
                return GateResult(
                    gate="streaming",
                    passed=False,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    detail=f"openai streaming failed: {exc!s:.80}",
                    error=str(exc),
                )

        # Try OpenAI-compatible providers: 9Router, OpenRouter, DeepSeek
        for key, base_url, model, label in [
            (nine_router_key, nine_router_base_url, nine_router_model, "9router"),
            (openrouter_key, openrouter_base_url, openrouter_model, "openrouter"),
            (deepseek_key, deepseek_base_url, deepseek_model, "deepseek"),
        ]:
            if not key:
                continue
            try:
                import openai as openai_lib
                client = openai_lib.AsyncOpenAI(base_url=base_url, api_key=key)
                chunk_count = 0
                stream = await client.chat.completions.create(
                    model=model,
                    max_tokens=20,
                    messages=[{"role": "user", "content": "Say hello"}],
                    stream=True,
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        chunk_count += 1
                        if chunk_count >= 1:
                            break

                latency_ms = int((time.monotonic() - t0) * 1000)
                passed = chunk_count >= 1
                return GateResult(
                    gate="streaming",
                    passed=passed,
                    latency_ms=latency_ms,
                    detail=f"{label} streaming {'ok' if passed else 'failed'} ({chunk_count} chunks)",
                    error=None if passed else "0 chunks received",
                )
            except Exception as exc:
                logger.warning("%s streaming check failed: %s", label, exc)
                continue

        return GateResult(
            gate="streaming",
            passed=False,
            latency_ms=int((time.monotonic() - t0) * 1000),
            detail="no streaming provider available",
            error="no API keys",
        )

    async def check_latency(self, threshold_ms: int = 8000) -> GateResult:
        """Gate 4: full round-trip latency under threshold."""
        t0 = time.monotonic()

        ai_mode = os.environ.get("MCP_AI_MODE", "")
        if ai_mode == "mock":
            simulated_ms = 150
            return GateResult(
                gate="latency",
                passed=True,
                latency_ms=simulated_ms,
                detail=f"mock mode — simulated {simulated_ms}ms (threshold {threshold_ms}ms)",
            )

        claude_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        nine_router_key = os.environ.get("MCP_NINE_ROUTER_API_KEY", "").strip()
        openrouter_key = os.environ.get("MCP_OPENROUTER_API_KEY", "").strip()
        deepseek_key = os.environ.get("MCP_DEEPSEEK_API_KEY", "").strip()
        deepseek_base_url = os.environ.get("MCP_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        deepseek_model = os.environ.get("MCP_DEEPSEEK_MODEL", "deepseek-chat")
        openrouter_base_url = os.environ.get("MCP_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        openrouter_model = os.environ.get("MCP_OPENROUTER_PRIMARY_MODEL", "openai/gpt-4o-mini")
        nine_router_base_url = os.environ.get("MCP_NINE_ROUTER_BASE_URL", "http://127.0.0.1:20128/v1")
        nine_router_model = os.environ.get("MCP_NINE_ROUTER_PRIMARY_MODEL", "cc/claude-sonnet-4-6")

        if not any([claude_key, openai_key, nine_router_key, openrouter_key, deepseek_key]):
            return GateResult(
                gate="latency",
                passed=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                detail="no keys — latency not testable",
                error="no API keys configured",
            )

        # Try Claude
        if claude_key:
            try:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=claude_key)
                call_start = time.monotonic()
                await client.messages.create(
                    model="claude-haiku-4-5",
                    max_tokens=30,
                    messages=[{"role": "user", "content": "Reply in one sentence: what is 2+2?"}],
                )
                call_ms = int((time.monotonic() - call_start) * 1000)
                total_ms = int((time.monotonic() - t0) * 1000)
                passed = call_ms < threshold_ms
                exceeded = f"latency {call_ms}ms exceeds threshold {threshold_ms}ms"
                return GateResult(
                    gate="latency",
                    passed=passed,
                    latency_ms=total_ms,
                    detail=f"claude round-trip {call_ms}ms (threshold {threshold_ms}ms)",
                    error=None if passed else exceeded,
                )
            except Exception as exc:
                if not openai_key:
                    return GateResult(
                        gate="latency",
                        passed=False,
                        latency_ms=int((time.monotonic() - t0) * 1000),
                        detail=f"claude call failed: {exc!s:.80}",
                        error=str(exc),
                    )

        # Try OpenAI fallback
        if openai_key:
            try:
                import openai as openai_lib
                client = openai_lib.AsyncOpenAI(api_key=openai_key)
                call_start = time.monotonic()
                await client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=30,
                    messages=[{"role": "user", "content": "Reply in one sentence: what is 2+2?"}],
                )
                call_ms = int((time.monotonic() - call_start) * 1000)
                total_ms = int((time.monotonic() - t0) * 1000)
                passed = call_ms < threshold_ms
                exceeded = f"latency {call_ms}ms exceeds threshold {threshold_ms}ms"
                return GateResult(
                    gate="latency",
                    passed=passed,
                    latency_ms=total_ms,
                    detail=f"openai round-trip {call_ms}ms (threshold {threshold_ms}ms)",
                    error=None if passed else exceeded,
                )
            except Exception as exc:
                return GateResult(
                    gate="latency",
                    passed=False,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    detail=f"openai call failed: {exc!s:.80}",
                    error=str(exc),
                )

        # Try OpenAI-compatible providers: 9Router, OpenRouter, DeepSeek
        for key, base_url, model, label in [
            (nine_router_key, nine_router_base_url, nine_router_model, "9router"),
            (openrouter_key, openrouter_base_url, openrouter_model, "openrouter"),
            (deepseek_key, deepseek_base_url, deepseek_model, "deepseek"),
        ]:
            if not key:
                continue
            try:
                import openai as openai_lib
                client = openai_lib.AsyncOpenAI(base_url=base_url, api_key=key)
                call_start = time.monotonic()
                await client.chat.completions.create(
                    model=model,
                    max_tokens=30,
                    messages=[{"role": "user", "content": "Reply in one sentence: what is 2+2?"}],
                )
                call_ms = int((time.monotonic() - call_start) * 1000)
                total_ms = int((time.monotonic() - t0) * 1000)
                passed = call_ms < threshold_ms
                exceeded = f"latency {call_ms}ms exceeds threshold {threshold_ms}ms"
                return GateResult(
                    gate="latency",
                    passed=passed,
                    latency_ms=total_ms,
                    detail=f"{label} round-trip {call_ms}ms (threshold {threshold_ms}ms)",
                    error=None if passed else exceeded,
                )
            except Exception as exc:
                logger.warning("%s latency check failed: %s", label, exc)
                continue

        return GateResult(
            gate="latency",
            passed=False,
            latency_ms=int((time.monotonic() - t0) * 1000),
            detail="no provider available",
            error="no API keys",
        )

    async def check_safety_guard(self) -> GateResult:
        """Gate 5: safety guard intercepts red flag without calling AI."""
        t0 = time.monotonic()

        try:
            from app.ai.prompt.safety import SafetyGuard

            guard = SafetyGuard()
            result = guard.check_input("đau ngực")
            latency_ms = int((time.monotonic() - t0) * 1000)

            if result.escalation_required:
                if latency_ms > 100:
                    return GateResult(
                        gate="safety_guard",
                        passed=False,
                        latency_ms=latency_ms,
                        detail=f"safety guard too slow: {latency_ms}ms (threshold 100ms)",
                        error=f"latency {latency_ms}ms exceeds 100ms threshold",
                    )
                return GateResult(
                    gate="safety_guard",
                    passed=True,
                    latency_ms=latency_ms,
                    detail=f"red flags intercepted in {latency_ms}ms (no AI call needed)",
                )
            else:
                return GateResult(
                    gate="safety_guard",
                    passed=False,
                    latency_ms=latency_ms,
                    detail="safety guard failed to detect 'đau ngực' red flag",
                    error="escalation_required=False for known emergency phrase",
                )
        except Exception as exc:
            return GateResult(
                gate="safety_guard",
                passed=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                detail=f"safety guard error: {exc!s:.120}",
                error=str(exc),
            )

    async def check_provider_identity(self) -> GateResult:
        """Gate 6: provider identity not leaked in response."""
        t0 = time.monotonic()

        try:
            from app.ai.prompt.safety import SafetyGuard

            # Test that SafetyGuard's output checker catches identity leaks
            guard = SafetyGuard()

            # Simulate a response that leaks provider name
            leaky_response = "Tôi là Claude, được tạo bởi Anthropic. Tôi có thể giúp bạn."
            check_result = guard.check_output(leaky_response)

            latency_ms = int((time.monotonic() - t0) * 1000)

            # The check_output should flag forbidden patterns like "tôi là claude"
            if not check_result.safe:
                return GateResult(
                    gate="provider_identity",
                    passed=True,
                    latency_ms=latency_ms,
                    detail="provider identity leak detected and blocked by safety guard",
                )
            else:
                # Try manual check with our own identity phrases
                leaky_lower = leaky_response.lower()
                leaked = [p for p in self.PROVIDER_IDENTITY_PHRASES if p in leaky_lower]
                if leaked:
                    # Safety guard didn't catch it — that's the failure
                    return GateResult(
                        gate="provider_identity",
                        passed=False,
                        latency_ms=latency_ms,
                        detail=f"safety guard did NOT catch identity leak: {leaked[0]!r}",
                        error=f"FORBIDDEN_RESPONSE_PATTERNS missing patterns for: {leaked}",
                    )
                else:
                    # No identity leak found in test string — guard works correctly (nothing to block)
                    return GateResult(
                        gate="provider_identity",
                        passed=True,
                        latency_ms=latency_ms,
                        detail="no provider identity patterns found in response (guard not triggered)",
                    )
        except Exception as exc:
            return GateResult(
                gate="provider_identity",
                passed=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                detail=f"provider identity check error: {exc!s:.120}",
                error=str(exc),
            )
