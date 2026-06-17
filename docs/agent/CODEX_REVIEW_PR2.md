# Codex Review — PR #2 (P2-HARDENING-1)

> Reviewer: OpenAI Codex CLI v0.137.0 (model gpt-5.5, sandbox read-only)
> Date: 2026-06-14 · Branch: `hardening/p2-hardening-1` vs `main` (merge-base `2bd1bd6`)
> Command: `codex review --base main`
> Raw log: `/tmp/codex_review_pr2.txt` (2967 lines incl. full diff dump). This file = distilled findings.
> ⚠️ Artifact only — intentionally NOT committed to the hardening branch.

---

## Summary (Codex)

> The refresh cleanup can disable refresh-token reuse detection for valid tokens, and the Redis
> implementation can permanently block clients or delete unrelated Redis data.

## Findings (prioritized)

### [P1] Preserve unexpired revoked tokens for reuse detection
`backend/app/services/auth.py:232-233`

When `refresh_token_ttl_minutes` exceeds the seven-day grace period, the cleanup condition deletes
revoked tokens while their JWTs remain valid. Reusing one then appears as an *unknown* token, so
`refresh_session()` cannot detect the theft or revoke the active token family. **Keep revoked rows
until their refresh JWT has expired.**

> Note (Lead Eng): default `refresh_token_ttl_minutes = 10080` (7 days) == grace, so the default
> config is borderline-safe; but a longer TTL silently breaks reuse-detection. Valid P1 — the cleanup
> predicate should be `expires_at < now` only (let reuse-detection own revoked rows until JWT expiry),
> or grace must be ≥ refresh TTL.

### [P2] Set the Redis counter expiry atomically
`backend/app/core/ratelimit.py:124-126`

If the process fails / loses its Redis connection after `INCR` but before `EXPIRE`, the key is left
without a TTL. Once that counter exceeds capacity, the affected client is permanently rate-limited.
Execute increment + conditional expiry atomically (e.g. a Lua script, or `SET NX` + `INCR`).

### [P2] Avoid flushing unrelated Redis data during reset
`backend/app/core/ratelimit.py:129-133`

`reset()` calls `flushdb()`, deleting **every** key in the configured Redis DB (caches, queues, etc.),
not just rate-limit keys. Invoked by the test fixture via `reset_all()`, so running tests against a
shared Redis could destroy unrelated data. Namespace limiter keys and delete only that namespace.

## Verdict

**CHANGES-REQUESTED** — 1 × P1 (correctness/security: reuse-detection bypass), 2 × P2 (Redis robustness).
No secrets/PHI/medical-safety regressions flagged. The P1 overlaps a limitation already noted in
`P2_HARDENING_SELF_REVIEW.md` §6; the Redis P2s are real but only affect the opt-in Redis backend.

## Recommended follow-up (separate patch, await PTH)

1. P1: change refresh cleanup to delete on `expires_at < now` only (don't delete revoked-but-unexpired),
   OR enforce `revoked_grace_days * 86400 >= refresh_token_ttl_minutes * 60`.
2. P2: atomic Redis INCR+EXPIRE (Lua/`SET NX`).
3. P2: namespace Redis keys (`mcp:rl:<key>`) + scan-delete by prefix instead of `flushdb()`.

---

## Resolution log

**Round 1** (commit `17d38d4`): 1×P1 + 2×P2 above.

**Fixes applied** (commit `4883c7f`): FIX 1 (cleanup deletes only `expires_at < now`),
FIX 2 (atomic Lua INCR+EXPIRE + SET NX fallback), FIX 3 (namespaced keys + SCAN/UNLINK, no flushdb).
See `P2_HARDENING_SELF_REVIEW.md` §10.

**Round 2** (`codex review --base main` @ `4883c7f`): P1 + 2×P2 confirmed resolved; 1 new [P2] —
empty/glob `MCP_RATELIMIT_REDIS_PREFIX` could make `reset()` over-match.
**Fixed** (commit `fbaac56`): `RedisRateLimiter` rejects empty/glob-metachar prefix.

**Round 3** (`codex review --base main` @ `fbaac56`): **CLEAN** —
> No actionable correctness issues were identified in the changes relative to main. The new cleanup,
> maintenance, Redis rate-limiter, and blind-index functionality is internally consistent and covered
> by focused tests.

Final: 140 passed, 1 skipped; ruff clean; compileall OK; compose valid; CI green. Docker DOWN →
Postgres/Timescale still NOT verified.
