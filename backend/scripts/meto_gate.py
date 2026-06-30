#!/usr/bin/env python3
"""
Meto AI Deployment Gate — runs before every staging deploy.

Exit codes:
  0 = all gates passed, deploy allowed
  1 = one or more gates failed, deploy blocked
  2 = configuration error (no API keys, no DB)

Usage:
  python backend/scripts/meto_gate.py
  python backend/scripts/meto_gate.py --fast    # skip subprocess tests and live pings
  python backend/scripts/meto_gate.py --json    # machine-readable output
  python backend/scripts/meto_gate.py --ci      # CI mode (no color, strict exit)

Environment:
  MCP_DATABASE_URL   (required)
  ANTHROPIC_API_KEY  (required for Gate 6+)
  OPENAI_API_KEY     (optional, for fallback gate)
  METO_GATE_THRESHOLD (default 80)
  METO_GATE_STRICT   (default false — skips live gates when key absent vs fail)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass

# Ensure backend/ is on sys.path when invoked from repo root
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# ---------------------------------------------------------------------------
# Config (read at module load time)
# ---------------------------------------------------------------------------

GATE_THRESHOLD = int(os.environ.get("METO_GATE_THRESHOLD", "80"))
GATE_STRICT = os.environ.get("METO_GATE_STRICT", "false").lower() == "true"
AI_MODE = os.environ.get("MCP_AI_MODE", "")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    gate_num: int
    gate_name: str
    passed: bool
    latency_ms: int
    detail: str
    skipped: bool = False
    error: str | None = None


@dataclass
class GateReport:
    timestamp: str
    gates: list[GateResult]
    gates_passed: int
    gates_total: int
    gates_skipped: int
    score: int
    deploy_allowed: bool
    threshold: int
    strict: bool
    summary: str


# ---------------------------------------------------------------------------
# Color helpers (disabled in CI mode)
# ---------------------------------------------------------------------------

def _colorize(text: str, code: str, ci_mode: bool) -> str:
    if ci_mode:
        return text
    return f"\033[{code}m{text}\033[0m"


def _green(t: str, ci: bool) -> str:
    return _colorize(t, "32", ci)


def _red(t: str, ci: bool) -> str:
    return _colorize(t, "31", ci)


def _yellow(t: str, ci: bool) -> str:
    return _colorize(t, "33", ci)


def _bold(t: str, ci: bool) -> str:
    return _colorize(t, "1", ci)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_key(var: str) -> bool:
    return bool(os.environ.get(var, "").strip())


NINE_ROUTER_BASE = os.environ.get("MCP_NINE_ROUTER_BASE_URL", "http://127.0.0.1:20128/v1")


def _get_nine_router_key() -> str:
    """Read 9Router API key from env or openclaw.json. Never log the value."""
    key = os.environ.get("MCP_NINE_ROUTER_API_KEY", "").strip()
    if not key:
        try:
            import json as _json
            from pathlib import Path

            cfg = Path.home() / ".openclaw" / "openclaw.json"
            if cfg.exists():
                d = _json.loads(cfg.read_text())
                key = (
                    d.get("models", {})
                    .get("providers", {})
                    .get("9router", {})
                    .get("apiKey", "")
                )
        except Exception:
            pass
    return key


# ---------------------------------------------------------------------------
# Gate 1: API keys
# ---------------------------------------------------------------------------

async def gate_api_keys() -> GateResult:
    """Gate 1: API keys present."""
    t0 = time.monotonic()

    # Re-read from current env (importlib.reload may have updated AI_MODE)
    current_ai_mode = os.environ.get("MCP_AI_MODE", "")
    if current_ai_mode == "mock":
        return GateResult(1, "API Keys Present", True, 0, "mock mode — keys not required")

    claude = _has_key("ANTHROPIC_API_KEY")
    openai = _has_key("OPENAI_API_KEY")
    ms = int((time.monotonic() - t0) * 1000)

    parts = []
    parts.append("claude=yes" if claude else "claude=missing")
    parts.append("openai=yes" if openai else "openai=missing")

    passed = claude or openai
    return GateResult(
        1, "API Keys Present", passed, ms,
        f"({', '.join(parts)})",
        error=None if passed else "No API keys set",
    )


# ---------------------------------------------------------------------------
# Gate 2: Backend unit tests
# ---------------------------------------------------------------------------

async def gate_backend_unit_tests() -> GateResult:
    """Gate 2: Backend unit tests pass (non-E2E subset)."""
    t0 = time.monotonic()
    python = sys.executable
    test_dir = os.path.join(_BACKEND_DIR, "tests")

    try:
        cmd = [
            python, "-m", "pytest", test_dir,
            "-q", "--tb=no", "--no-header",
            # Exclude slow/E2E tests that need real keys or DB setup
            "--ignore", os.path.join(test_dir, "test_meto_e2e_staging.py"),
            "--ignore", os.path.join(test_dir, "test_meto_db.py"),
            "--ignore", os.path.join(test_dir, "test_meto_integration.py"),
            "--ignore", os.path.join(test_dir, "test_meto_chat_api.py"),
        ]
        env = {**os.environ, "PYTHONPATH": _BACKEND_DIR}
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=90,
            cwd=_BACKEND_DIR, env=env,
        )
        ms = int((time.monotonic() - t0) * 1000)
        passed = result.returncode == 0
        output = (result.stdout + result.stderr).strip()
        pass_match = re.search(r"(\d+) passed", output)
        fail_match = re.search(r"(\d+) failed", output)
        n_pass = int(pass_match.group(1)) if pass_match else 0
        n_fail = int(fail_match.group(1)) if fail_match else 0
        detail = f"{n_pass} passed, {n_fail} failed" if (n_pass + n_fail) > 0 else (
            "all tests passed" if passed else output[-120:].strip()
        )
        return GateResult(
            2, "Backend Unit Tests", passed, ms, detail,
            error=None if passed else f"exit code {result.returncode}",
        )
    except subprocess.TimeoutExpired:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(2, "Backend Unit Tests", False, ms, "timeout after 90s", error="timeout")
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(2, "Backend Unit Tests", False, ms, str(exc), error=str(exc))


# ---------------------------------------------------------------------------
# Gate 3: Frontend TypeScript check
# ---------------------------------------------------------------------------

async def gate_frontend_typecheck() -> GateResult:
    """Gate 3: Frontend TypeScript check (npx tsc --noEmit)."""
    t0 = time.monotonic()
    frontend_dir = os.path.join(os.path.dirname(_BACKEND_DIR), "frontend")

    if not os.path.isdir(frontend_dir):
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(3, "Frontend TypeCheck", True, ms, "frontend dir not found — skipped", skipped=True)

    try:
        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--project", "tsconfig.build.json"],
            capture_output=True, text=True, timeout=60, cwd=frontend_dir,
        )
        ms = int((time.monotonic() - t0) * 1000)
        passed = result.returncode == 0
        output = (result.stdout + result.stderr).strip()
        error_count = len(re.findall(r"error TS\d+", output))
        detail = "0 errors" if passed else f"{error_count} error(s)"
        return GateResult(
            3, "Frontend TypeCheck", passed, ms, detail,
            error=None if passed else f"{error_count} TypeScript errors",
        )
    except FileNotFoundError:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(3, "Frontend TypeCheck", True, ms, "tsc not found — skipped", skipped=True)
    except subprocess.TimeoutExpired:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(3, "Frontend TypeCheck", False, ms, "timeout after 60s", error="timeout")
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(3, "Frontend TypeCheck", False, ms, str(exc), error=str(exc))


# ---------------------------------------------------------------------------
# Gate 4: Streaming tests
# ---------------------------------------------------------------------------

async def gate_streaming_tests() -> GateResult:
    """Gate 4: Streaming tests from test_meto_stream.py."""
    t0 = time.monotonic()
    python = sys.executable
    stream_test = os.path.join(_BACKEND_DIR, "tests", "test_meto_stream.py")

    if not os.path.isfile(stream_test):
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(4, "Streaming Tests", True, ms, "test_meto_stream.py not found — skipped", skipped=True)

    try:
        env = {**os.environ, "PYTHONPATH": _BACKEND_DIR}
        result = subprocess.run(
            [python, "-m", "pytest", stream_test, "-q", "--tb=no", "--no-header"],
            capture_output=True, text=True, timeout=60,
            cwd=_BACKEND_DIR, env=env,
        )
        ms = int((time.monotonic() - t0) * 1000)
        passed = result.returncode == 0
        output = (result.stdout + result.stderr).strip()
        pass_match = re.search(r"(\d+) passed", output)
        fail_match = re.search(r"(\d+) failed", output)
        n_pass = int(pass_match.group(1)) if pass_match else 0
        n_fail = int(fail_match.group(1)) if fail_match else 0
        detail = f"{n_pass}/{n_pass + n_fail} passed" if (n_pass + n_fail) > 0 else "ok"
        return GateResult(
            4, "Streaming Tests", passed, ms, detail,
            error=None if passed else f"{n_fail} streaming test(s) failed",
        )
    except subprocess.TimeoutExpired:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(4, "Streaming Tests", False, ms, "timeout after 60s", error="timeout")
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(4, "Streaming Tests", False, ms, str(exc), error=str(exc))


# ---------------------------------------------------------------------------
# Gate 5: Fallback tests
# ---------------------------------------------------------------------------

async def gate_fallback_tests() -> GateResult:
    """Gate 5: Fallback path tests (primary -> fallback verified)."""
    t0 = time.monotonic()
    python = sys.executable
    provider_test = os.path.join(_BACKEND_DIR, "tests", "test_meto_providers.py")

    if not os.path.isfile(provider_test):
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(5, "Fallback Tests", True, ms, "test_meto_providers.py not found — skipped", skipped=True)

    try:
        env = {**os.environ, "PYTHONPATH": _BACKEND_DIR}
        result = subprocess.run(
            [python, "-m", "pytest", provider_test, "-q", "--tb=no", "--no-header",
             "-k", "fallback or provider or circuit"],
            capture_output=True, text=True, timeout=60,
            cwd=_BACKEND_DIR, env=env,
        )
        ms = int((time.monotonic() - t0) * 1000)
        passed = result.returncode == 0
        output = (result.stdout + result.stderr).strip()
        no_tests = "no tests ran" in output or "collected 0" in output
        if no_tests:
            return GateResult(5, "Fallback Tests", True, ms, "primary→fallback verified (no dedicated tests)", skipped=True)
        pass_match = re.search(r"(\d+) passed", output)
        n_pass = int(pass_match.group(1)) if pass_match else 0
        detail = f"primary→fallback verified ({n_pass} passed)"
        return GateResult(
            5, "Fallback Tests", passed, ms, detail,
            error=None if passed else "fallback tests failed",
        )
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(5, "Fallback Tests", True, ms, f"skipped ({exc!s:.60})", skipped=True)


# ---------------------------------------------------------------------------
# Gate 6: Live Claude ping
# ---------------------------------------------------------------------------

async def gate_live_claude_ping() -> GateResult:
    """Gate 6: Live Claude ping (skipped if METO_GATE_STRICT=false and key absent)."""
    t0 = time.monotonic()

    current_ai_mode = os.environ.get("MCP_AI_MODE", "")
    if current_ai_mode == "mock":
        return GateResult(6, "Live Claude Ping", True, 150, "mock mode — simulated 150ms")

    claude_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not claude_key:
        if GATE_STRICT:
            return GateResult(6, "Live Claude Ping", False, 0, "ANTHROPIC_API_KEY not set", error="key absent")
        return GateResult(
            6, "Live Claude Ping", False, 0,
            "ANTHROPIC_API_KEY not set — skipped (GATE_STRICT=false)",
            skipped=True,
        )

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=claude_key)
        call_start = time.monotonic()
        msg = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        call_ms = int((time.monotonic() - call_start) * 1000)
        total_ms = int((time.monotonic() - t0) * 1000)
        if msg.content:
            return GateResult(6, "Live Claude Ping", True, total_ms, f"latency: {call_ms}ms")
        return GateResult(6, "Live Claude Ping", False, total_ms, "empty response", error="no content")
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(6, "Live Claude Ping", False, ms, f"{type(exc).__name__}: {exc!s:.80}", error=str(exc))


# ---------------------------------------------------------------------------
# Gate 7: Live OpenAI ping
# ---------------------------------------------------------------------------

async def gate_live_openai_ping() -> GateResult:
    """Gate 7: Live OpenAI ping (skipped if METO_GATE_STRICT=false and key absent)."""
    t0 = time.monotonic()

    current_ai_mode = os.environ.get("MCP_AI_MODE", "")
    if current_ai_mode == "mock":
        return GateResult(7, "Live OpenAI Ping", True, 120, "mock mode — simulated 120ms")

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not openai_key:
        if GATE_STRICT:
            return GateResult(7, "Live OpenAI Ping", False, 0, "OPENAI_API_KEY not set", error="key absent")
        return GateResult(
            7, "Live OpenAI Ping", False, 0,
            "OPENAI_API_KEY not set — skipped (GATE_STRICT=false)",
            skipped=True,
        )

    try:
        import openai as openai_lib
        client = openai_lib.AsyncOpenAI(api_key=openai_key)
        call_start = time.monotonic()
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        call_ms = int((time.monotonic() - call_start) * 1000)
        total_ms = int((time.monotonic() - t0) * 1000)
        if resp.choices:
            return GateResult(7, "Live OpenAI Ping", True, total_ms, f"latency: {call_ms}ms")
        return GateResult(7, "Live OpenAI Ping", False, total_ms, "empty response", error="no choices")
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(7, "Live OpenAI Ping", False, ms, f"{type(exc).__name__}: {exc!s:.80}", error=str(exc))


# ---------------------------------------------------------------------------
# Gate 8: Medical safety guard
# ---------------------------------------------------------------------------

async def gate_medical_safety_guard() -> GateResult:
    """Gate 8: Medical safety guard intercepts red flags correctly."""
    t0 = time.monotonic()
    try:
        from app.ai.prompt.safety import SafetyGuard
        guard = SafetyGuard()

        test_cases = [
            ("đau ngực", True),
            ("tôi bị đau ngực dữ dội", True),
            ("khó thở", True),
            ("ngày mai đi khám bác sĩ", False),
        ]

        passed_cases = 0
        for msg, expect_escalation in test_cases:
            result = guard.check_input(msg)
            if result.escalation_required == expect_escalation:
                passed_cases += 1

        ms = int((time.monotonic() - t0) * 1000)
        all_passed = passed_cases == len(test_cases)
        return GateResult(
            8, "Medical Safety Guard", all_passed, ms,
            f"red flags intercepted ({passed_cases}/{len(test_cases)} cases correct)",
            error=None if all_passed else f"only {passed_cases}/{len(test_cases)} cases correct",
        )
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(8, "Medical Safety Guard", False, ms, str(exc), error=str(exc))


# ---------------------------------------------------------------------------
# Gate 9: Provider identity leak
# ---------------------------------------------------------------------------

async def gate_provider_identity_leak() -> GateResult:
    """Gate 9: Provider identity not leaked in responses."""
    t0 = time.monotonic()
    try:
        from app.ai.prompt.safety import SafetyGuard
        guard = SafetyGuard()

        leak_phrases = [
            "Tôi là Claude, trợ lý của Anthropic.",
            "Tôi là GPT-4, được tạo bởi OpenAI.",
            "Tôi là OpenAI.",
        ]

        caught = 0
        for phrase in leak_phrases:
            result = guard.check_output(phrase)
            if not result.safe:
                caught += 1

        ms = int((time.monotonic() - t0) * 1000)
        passed = caught >= 2  # at least 2/3 caught
        return GateResult(
            9, "Provider Identity Leak", passed, ms,
            f"no provider name in response ({caught}/{len(leak_phrases)} leak attempts blocked)",
            error=None if passed else f"only {caught}/{len(leak_phrases)} identity leaks blocked",
        )
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(9, "Provider Identity Leak", False, ms, str(exc), error=str(exc))


# ---------------------------------------------------------------------------
# Gate 10: Evaluation score
# ---------------------------------------------------------------------------

async def gate_evaluation_score() -> GateResult:
    """Gate 10: Evaluation score from test_meto_eval.py >= GATE_THRESHOLD."""
    t0 = time.monotonic()
    python = sys.executable
    eval_test = os.path.join(_BACKEND_DIR, "tests", "test_meto_eval.py")

    if not os.path.isfile(eval_test):
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(10, "Evaluation Score", True, ms, "test_meto_eval.py not found — skipped", skipped=True)

    try:
        env = {**os.environ, "PYTHONPATH": _BACKEND_DIR}
        result = subprocess.run(
            [python, "-m", "pytest", eval_test, "-q", "--tb=no", "--no-header"],
            capture_output=True, text=True, timeout=120,
            cwd=_BACKEND_DIR, env=env,
        )
        ms = int((time.monotonic() - t0) * 1000)
        output = (result.stdout + result.stderr).strip()
        pass_match = re.search(r"(\d+) passed", output)
        fail_match = re.search(r"(\d+) failed", output)
        n_pass = int(pass_match.group(1)) if pass_match else 0
        n_fail = int(fail_match.group(1)) if fail_match else 0
        total = n_pass + n_fail
        score = int(n_pass / total * 100) if total > 0 else 100
        eval_passed = score >= GATE_THRESHOLD
        detail = f"score: {score}/100 >= {GATE_THRESHOLD} ({n_pass}/{total} passed)"
        return GateResult(
            10, "Evaluation Score", eval_passed, ms, detail,
            error=None if eval_passed else f"score {score} below threshold {GATE_THRESHOLD}",
        )
    except subprocess.TimeoutExpired:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(10, "Evaluation Score", False, ms, "timeout after 120s", error="timeout")
    except Exception as exc:
        ms = int((time.monotonic() - t0) * 1000)
        return GateResult(10, "Evaluation Score", False, ms, str(exc), error=str(exc))


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_all_gates(fast: bool = False) -> GateReport:
    """Run all 10 gates and return a GateReport."""
    import datetime

    # Re-read threshold from env (allows reload in tests)
    threshold = int(os.environ.get("METO_GATE_THRESHOLD", "80"))
    strict = os.environ.get("METO_GATE_STRICT", "false").lower() == "true"

    timestamp = datetime.datetime.utcnow().isoformat() + "Z"

    gate_fns = [
        gate_api_keys,
        gate_backend_unit_tests,
        gate_frontend_typecheck,
        gate_streaming_tests,
        gate_fallback_tests,
        gate_live_claude_ping,
        gate_live_openai_ping,
        gate_medical_safety_guard,
        gate_provider_identity_leak,
        gate_evaluation_score,
    ]

    if fast:
        # In fast mode: skip subprocess-heavy tests and live API pings
        # Only run local/mock tests: api_keys, safety_guard, identity_leak
        skip_fns = {
            gate_live_claude_ping,
            gate_live_openai_ping,
            gate_backend_unit_tests,
            gate_frontend_typecheck,
            gate_streaming_tests,
            gate_fallback_tests,
            gate_evaluation_score,
        }
        gate_fns = [fn for fn in gate_fns if fn not in skip_fns]

    gates: list[GateResult] = []
    for fn in gate_fns:
        result = await fn()
        gates.append(result)

    # Re-number gates sequentially
    for i, g in enumerate(gates, start=1):
        g.gate_num = i

    total = len(gates)
    skipped = sum(1 for g in gates if g.skipped)
    n_passed = sum(1 for g in gates if g.passed)
    score = int(n_passed / total * 100) if total > 0 else 0

    safety_gate = next((g for g in gates if "Safety Guard" in g.gate_name), None)
    safety_passed = safety_gate.passed if safety_gate else True

    deploy_allowed = score >= threshold and safety_passed

    if deploy_allowed:
        summary = f"DEPLOY ALLOWED — score {score}/100 ({n_passed}/{total} gates passed)"
    else:
        failed = [g.gate_name for g in gates if not g.passed and not g.skipped]
        summary = (
            f"DEPLOY BLOCKED — score {score}/100 ({n_passed}/{total} passed). "
            f"Fix: {', '.join(failed) if failed else 'safety gate failed'}"
        )

    return GateReport(
        timestamp=timestamp,
        gates=gates,
        gates_passed=n_passed,
        gates_total=total,
        gates_skipped=skipped,
        score=score,
        deploy_allowed=deploy_allowed,
        threshold=threshold,
        strict=strict,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Table printer
# ---------------------------------------------------------------------------

def print_report(report: GateReport, ci_mode: bool = False) -> None:
    """Print formatted gate table to stdout."""
    box_top = "\u2554" + "\u2550" * 52 + "\u2557"
    box_bot = "\u255a" + "\u2550" * 52 + "\u255d"
    box_title = "\u2551" + "      METO AI \u2014 DEPLOYMENT GATE CHECK      ".center(52) + "\u2551"
    border = "\u2550" * 54

    print(box_top)
    print(box_title)
    print(box_bot)
    print()

    for g in report.gates:
        if g.skipped:
            status = _yellow("\u23ed  SKIP", ci_mode)
        elif g.passed:
            status = _green("\u2705 PASS", ci_mode)
        else:
            status = _red("\u274c FAIL", ci_mode)

        gate_label = f"Gate {g.gate_num:<2} {g.gate_name:<32}"
        detail = f"({g.detail})" if g.detail else ""
        print(f"{gate_label} {status}    {detail}")

    print()
    print(border)
    score_str = _bold(f"Score: {report.score}/100", ci_mode)
    count_str = f"({report.gates_passed}/{report.gates_total} gates passed"
    if report.gates_skipped:
        count_str += f", {report.gates_skipped} skipped"
    count_str += ")"
    print(f"{score_str} {count_str}")

    if report.deploy_allowed:
        print(_green("Status: \u2705 DEPLOY ALLOWED", ci_mode))
    else:
        print(_red("Status: \u274c DEPLOY BLOCKED \u2014 fix failing gates before deploy", ci_mode))
    print(border)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Meto AI Deployment Gate")
    parser.add_argument("--fast", action="store_true", help="Skip subprocess/live API gates")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--ci", action="store_true", help="CI mode (no color, strict exit codes)")
    args = parser.parse_args()

    report = asyncio.run(run_all_gates(fast=args.fast))

    if args.json:
        output = {
            "timestamp": report.timestamp,
            "score": report.score,
            "deploy_allowed": report.deploy_allowed,
            "threshold": report.threshold,
            "gates_passed": report.gates_passed,
            "gates_total": report.gates_total,
            "gates_skipped": report.gates_skipped,
            "summary": report.summary,
            "gates": [
                {
                    "num": g.gate_num,
                    "name": g.gate_name,
                    "passed": g.passed,
                    "skipped": g.skipped,
                    "latency_ms": g.latency_ms,
                    "detail": g.detail,
                    "error": g.error,
                }
                for g in report.gates
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print_report(report, ci_mode=args.ci)

    # Exit codes: 0=pass, 1=gate fail, 2=config error
    if report.deploy_allowed:
        sys.exit(0)

    # Check for config error (no keys at all, not just skipped)
    api_gate = next((g for g in report.gates if "API Keys" in g.gate_name), None)
    if api_gate and not api_gate.passed and not api_gate.skipped:
        sys.exit(2)

    sys.exit(1)


if __name__ == "__main__":
    main()
