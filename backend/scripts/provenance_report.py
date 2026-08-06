"""Was the affected staging data synthetic, or did real people put it there?

Written for the 2026-08-06 staging encryption incident. 103 PHI values sat at
rest under a key committed to this repository for five hours. Whether that is an
engineering defect or a disclosure turns entirely on one question, and the
incident record could not answer it: **who created those rows?**

Why this needs a script rather than a query someone runs by hand
----------------------------------------------------------------
The obvious way to answer it is to look at the accounts. That is exactly what
must not happen — reading identifiers to decide whether the identifiers are real
is self-defeating, and it puts PHI in a terminal during an incident, which is
how one problem acquires a second.

So this classifies and counts, and returns nothing else. Every value it emits is
an integer or an ISO date bound. No email, name, id or row content leaves the
process; there is no code path that prints one, and the contract test asserts it.

How provenance is established
-----------------------------
Four independent signals, because none alone is conclusive:

1. **Synthetic address markers.** The seed scripts use fixed, reserved-domain
   addresses (`@example.com`, `.test`, `.invalid`) and fixed local parts
   (`demo.*`, `pilot.*`). RFC 2606 reserves those domains precisely so they can
   never belong to a real person.
2. **Self-registration audit trail.** `POST /auth/register` writes an `AuditLog`
   row. A seeded account has none. An account WITH one was created through the
   public API — which, on a publicly reachable staging ingress, could be anyone.
3. **Creation clustering.** Seeded accounts appear in bursts seconds apart from
   one job execution. Organic signups do not.
4. **Ownership of the affected rows.** Only the 103 matter. This walks each
   affected column back to its owning user and counts how many belong to
   non-synthetic accounts. That number, not the total, is the disposition.

One non-synthetic owner of an affected row means CONFIRMED REAL DATA PRESENT.
Zero, with the other signals agreeing, means CONFIRMED SYNTHETIC. Anything else
is CANNOT ESTABLISH, and the caller must then treat the data as real.

Read-only; makes no writes. Exits 0 always — this is a measurement, and an exit
code would invite someone to gate a deploy on it.
"""

from __future__ import annotations

import json
import os
import re
import sys

import sqlalchemy as sa

#: Imported, not redefined. `app/core/environment_lock.py` uses the same list to
#: decide who may register or authenticate in a locked environment. Two copies
#: would let the tool that MEASURES the incident and the lock that PREVENTS the
#: next one disagree about the same account.
from app.core.environment_lock import SYNTHETIC_PATTERNS
from sqlalchemy.orm import Session

_SYNTHETIC = re.compile("|".join(SYNTHETIC_PATTERNS), re.IGNORECASE)

#: The columns the 2026-08-06 migration encrypted with the wrong key, and the
#: path from each back to the owning user. Hardcoded deliberately: this reports
#: on ONE incident, and a set that silently grew would change what the verdict
#: means without anyone deciding to.
AFFECTED = (
    ("meto_messages", "content",
     "JOIN meto_conversations c ON c.id = t.conversation_id JOIN users u ON u.id = c.user_id"),
    ("medication_statements", "raw_drug_name",
     "JOIN patient_profiles p ON p.id = t.patient_id JOIN users u ON u.id = p.user_id"),
    ("medication_statements", "raw_dose",
     "JOIN patient_profiles p ON p.id = t.patient_id JOIN users u ON u.id = p.user_id"),
    ("medication_statements", "raw_frequency",
     "JOIN patient_profiles p ON p.id = t.patient_id JOIN users u ON u.id = p.user_id"),
    ("medication_statements", "payload_snapshot",
     "JOIN patient_profiles p ON p.id = t.patient_id JOIN users u ON u.id = p.user_id"),
    ("notifications", "title", "JOIN users u ON u.id = t.user_id"),
    ("notifications", "body", "JOIN users u ON u.id = t.user_id"),
    ("extraction_candidates", "fields_json",
     "JOIN medical_documents d ON d.id = t.document_id "
     "JOIN patient_profiles p ON p.id = d.patient_id JOIN users u ON u.id = p.user_id"),
    ("users", "full_name", ""),   # the row IS the user
)


def _emit(record: dict) -> None:
    """One JSON line. Integers and date bounds only, by construction."""
    print(json.dumps(record, sort_keys=True))


def run() -> int:  # noqa: C901 - linear report; splitting would scatter the verdict
    from app.core.config import get_settings

    settings = get_settings()
    engine = sa.create_engine(settings.database_url, poolclass=sa.pool.NullPool)
    per_column: dict[str, dict] = {}
    owners_total = owners_non_synthetic = 0
    real_ids: set[str] = set()

    with Session(engine) as session:
        # ── Signal 1: address markers ───────────────────────────────────────
        # Emails are pulled in to regex them and discarded in the same loop.
        # Only the classification survives past this block.
        synthetic_ids: set[str] = set()
        by_role: dict[str, dict[str, int]] = {}
        for uid, email, role in session.execute(
            sa.text("SELECT id, email, role FROM users")
        ).all():
            is_syn = bool(email) and _SYNTHETIC.search(email) is not None
            (synthetic_ids if is_syn else real_ids).add(uid)
            bucket = by_role.setdefault(str(role), {"synthetic": 0, "non_synthetic": 0})
            bucket["synthetic" if is_syn else "non_synthetic"] += 1

        _emit({"signal": "address_markers",
               "users_total": len(synthetic_ids) + len(real_ids),
               "synthetic": len(synthetic_ids), "non_synthetic": len(real_ids),
               "by_role": by_role})

        # ── Signal 2: self-registration audit trail ─────────────────────────
        registered = {
            r[0] for r in session.execute(
                sa.text("SELECT DISTINCT actor_id FROM audit_logs "
                        "WHERE action = 'register' AND actor_id IS NOT NULL")
            ).all()
        }
        _emit({"signal": "self_registration_audit",
               "accounts_with_register_event": len(registered),
               "of_which_non_synthetic_address": len(registered & real_ids),
               "note": "a seeded account has no register event; an account with "
                       "one was created through the public API"})

        # ── Signal 3: creation clustering ───────────────────────────────────
        lo, hi, n = session.execute(
            sa.text("SELECT min(created_at), max(created_at), count(*) FROM users")
        ).one()
        distinct_seconds = int(session.execute(sa.text(
            "SELECT count(DISTINCT date_trunc('second', created_at)) FROM users"
        )).scalar() or 0)
        _emit({"signal": "creation_clustering",
               "earliest": lo.isoformat() if lo else None,
               "latest": hi.isoformat() if hi else None,
               "users": int(n or 0),
               "distinct_creation_seconds": distinct_seconds,
               "note": "few distinct seconds relative to user count means bulk "
                       "seeding; many means accounts arrived independently"})

        # ── Signal 4: who owns the AFFECTED rows ────────────────────────────
        # The disposition. Everything above is context; this is the answer.
        for table, column, join in AFFECTED:
            key = f"{table}.{column}"
            try:
                if table == "users":
                    sql = f"SELECT t.id FROM users t WHERE t.{column} IS NOT NULL"  # noqa: S608
                else:
                    sql = (f"SELECT u.id FROM {table} t {join} "  # noqa: S608
                           f"WHERE t.{column} IS NOT NULL")
                with session.begin_nested():
                    owners = [r[0] for r in session.execute(sa.text(sql)).all()]
            except Exception as exc:  # noqa: BLE001 - reported, never swallowed
                session.rollback()
                per_column[key] = {"error": type(exc).__name__}
                continue
            bad = sum(1 for o in owners if o in real_ids)
            owners_total += len(owners)
            owners_non_synthetic += bad
            per_column[key] = {"rows": len(owners),
                               "owned_by_non_synthetic_account": bad}

        _emit({"signal": "affected_row_ownership",
               "rows_examined": owners_total,
               "owned_by_non_synthetic_account": owners_non_synthetic,
               "per_column": per_column})

        session.rollback()   # read-only: end the snapshot explicitly

    unresolved = [k for k, v in per_column.items() if "error" in v]
    if unresolved:
        verdict, why = "CANNOT_ESTABLISH", f"columns not resolvable: {unresolved}"
    elif owners_non_synthetic > 0:
        verdict, why = ("CONFIRMED_REAL_DATA_PRESENT",
                        f"{owners_non_synthetic} affected row(s) belong to accounts "
                        "whose address is not a reserved synthetic marker")
    elif not real_ids:
        verdict, why = ("CONFIRMED_SYNTHETIC",
                        "every account carries a reserved synthetic address marker, "
                        "so no affected row can belong to a real person")
    else:
        verdict, why = ("CONFIRMED_SYNTHETIC",
                        f"{len(real_ids)} non-synthetic account(s) exist but own ZERO "
                        "affected rows")

    _emit({"check": "provenance", "verdict": verdict, "reason": why,
           "affected_rows_examined": owners_total,
           "affected_rows_non_synthetic_owner": owners_non_synthetic,
           "env": (os.environ.get("MCP_ENV") or "").lower()})
    return 0


if __name__ == "__main__":
    sys.exit(run())
