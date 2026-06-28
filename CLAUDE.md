# MetoCare — Claude Code project guide

Metabolic care platform. **Backend:** FastAPI + SQLAlchemy/Alembic (`backend/`, Python).
**Frontend:** Next.js 14 + Tailwind + Radix (`frontend/`, TypeScript/React).
Deploy: Azure Container Apps (active). DigitalOcean = LEGACY (deprecated 2026-06-28). See `docs/LEGACY_DIGITALOCEAN.md`.

## ECC operator layer (installed globally)

This machine has the **ECC** plugin (`ecc@ecc`, v2.0.0) enabled at **user scope**, so it
applies to every project including this one. It adds ~363 skills, 67 specialized agents,
reusable hooks, and an MCP convention layer on top of Claude Code.

- **Skills / agents / commands**: invoke via the normal Skill tool and `/`-commands —
  e.g. `python-review`, `fastapi-review`, `react-review`, `security-review`, `tdd-workflow`,
  `code-review`. Agents like `security-reviewer`, `fastapi-reviewer`, `react-reviewer`,
  `database-reviewer` are available to the `Agent` tool.
- **Find the right tool**: `npx ecc consult "<what you want>" --target claude`
  (run from `~/.claude/plugins/cache/ecc/ecc/2.0.0` or any project).
- **Rules** (standards/checklists, not auto-loaded into context): installed at
  `~/.claude/rules/ecc/{common,python,typescript,react}/`. These match MetoCare's stack;
  consult them for coding-style / testing / security conventions.

### ECC hooks change default behavior — know these

ECC registers blocking `PreToolUse` hooks that run in every session:

- **gateguard-fact-force** — blocks the *first* Edit/Write/MultiEdit to each file until
  you've investigated importers / data schemas / the user instruction. Expect a one-time
  gate per file, then edits proceed.
- **config-protection** — blocks edits to linter/formatter config files (steers you to
  fix code, not weaken configs).
- **Bash pre-dispatcher** — tmux dev-server / git-push review / quality gates, and blocks
  `git --no-verify` (don't bypass pre-commit/pre-push hooks).

Tune via ECC env vars / `configure-ecc` skill if a gate is unwanted. Opt-in hooks
(e.g. governance capture) require `ECC_GOVERNANCE_CAPTURE=1` and stay off by default.

## Project guardrails (pre-existing — keep)

- Do **not** touch DigitalOcean VPS (legacy — server still running, do not modify without PTH approval). Do not touch Azure infra workflow/config or the Postgres
  firewall as part of unrelated work.
- Do not seed admin accounts.
- CI policy: production-affecting commits use `[skip ci]` where appropriate (see git history).
