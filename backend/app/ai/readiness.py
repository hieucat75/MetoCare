"""
Meto AI readiness check — verifies providers are configured before enabling.

Used by:
- Startup health check
- Feature flag gate
- Deploy validation script
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


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

    if claude_ready and openai_ready:
        mode = "full"
    elif claude_ready:
        mode = "fallback_only"  # only primary, no fallback
    elif openai_ready:
        mode = "fallback_only"  # only fallback
    else:
        mode = "unavailable"

    return {
        "claude": claude_ready,
        "openai": openai_ready,
        "any_ready": claude_ready or openai_ready,
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
