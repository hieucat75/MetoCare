"""Read-only PHI population preflight.

Answers one question, and only in the affirmative direction: **is this database
provably empty of PHI?** Exit 0 means yes. Every other outcome — rows present, a
count that failed, a database it could not reach — exits non-zero.

Why it exists separately from `crypto_smoke`
--------------------------------------------
The crypto smoke needs the PHI master key, because it decrypts. This does not: it
counts rows. Keeping the two apart means the step that decides "the database is
empty" can run in a Container Apps Job that never receives
`MCP_ENCRYPTION_KEYS`, so the decision costs nothing in key exposure. After
2026-08-06 — an incident whose root cause was a job holding the wrong key — a
preflight that needs no key is worth more than one function fewer.

Why the exit code carries the verdict
-------------------------------------
A Container Apps Job execution reports `Succeeded` or `Failed`, not stdout. A
caller that must branch on the answer can only read the exit status, so the
answer IS the exit status, and it fails closed: `Failed` covers "rows exist",
"the count errored" and "the job never ran", all of which must deny the
empty-database permission equally.

Emits one PHI-free JSON line. No column value is ever read.
"""

from __future__ import annotations

import json
import sys

import sqlalchemy as sa
from sqlalchemy.orm import Session

EXIT_EMPTY = 0
EXIT_NOT_EMPTY = 1
EXIT_UNAVAILABLE = 2


def census_tables() -> tuple[str, ...]:
    """Identity tables plus every table holding an encrypted column."""
    from scripts.crypto_smoke import CENSUS_IDENTITY_TABLES, legacy_targets

    return tuple(
        dict.fromkeys(CENSUS_IDENTITY_TABLES + tuple(t for _e, t, _c in legacy_targets()))
    )


def main() -> int:
    from app.core.config import get_settings

    from scripts.crypto_smoke import census

    try:
        settings = get_settings()
        engine = sa.create_engine(settings.database_url, poolclass=sa.pool.NullPool)
    except Exception as exc:  # noqa: BLE001 - report, never leak a URL
        print(json.dumps({"check": "phi_population", "result": "unavailable",
                          "reason": type(exc).__name__}, sort_keys=True))
        return EXIT_UNAVAILABLE

    try:
        with Session(engine) as session:
            result = census(session, census_tables())
            # Read-only by construction, but the census opens SAVEPOINTs; end the
            # transaction explicitly rather than relying on the context manager.
            session.rollback()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"check": "phi_population", "result": "unavailable",
                          "reason": type(exc).__name__}, sort_keys=True))
        return EXIT_UNAVAILABLE
    finally:
        engine.dispose()

    verdict = "empty" if result.proves_empty else "not_empty"
    print(json.dumps({
        "check": "phi_population",
        "result": verdict,
        "tables_present_empty": len(result.present_empty),
        # Absent because a migration has not run yet is a KNOWN state and does
        # not by itself deny emptiness — the tables cannot hold rows.
        "tables_absent": len(result.absent),
        "tables_non_empty": dict(result.non_empty),
        # A failed count is never folded into "zero": it lands here, and its
        # presence alone makes `proves_empty` false.
        "query_failures": dict(result.errors),
    }, sort_keys=True))

    return EXIT_EMPTY if result.proves_empty else EXIT_NOT_EMPTY


if __name__ == "__main__":
    sys.exit(main())
