"""Post-deploy PHI crypto smoke — proves encrypted columns are actually readable.

Why this exists
---------------
Boot-time validation (`config.validate_required_env_vars`) proves every entry in
MCP_ENCRYPTION_KEYS is a WELL-FORMED Fernet key. It cannot prove it is the RIGHT
key, and nothing else in the deploy pipeline touches an encrypted column:
`/health` is `SELECT 1`, and the smoke suite is unauthenticated and asserts 401s.

Reproduced against a real database: with a wrong-but-well-formed key, boot
validation PASSES, the health check PASSES, and an authenticated encrypted read
raises UndecryptablePHIError. The deploy is reported healthy while medication
reminders (Notification.title/body — NOT NULL, on_decrypt_failure="raise") and
the medication timeline (MedicationStatement.raw_drug_name — same) are broken for
every patient. A mis-rotated key is the realistic way to get there, and it is
completely silent.

Why a command and not an endpoint
---------------------------------
An HTTP endpoint that decrypts on demand is a crypto oracle: it turns "can you
reach this URL" into "can you learn whether a key works", and it then has to be
defended forever. This runs as a one-shot job with the same identity and secrets
the app already has, returns no PHI, and exits non-zero on failure.

Safety properties
-----------------
- SYNTHETIC sentinels only: every value written is `CRYPTO-SMOKE-<uuid4>`. No
  patient data is invented, so a leaked log line discloses nothing.
- Never prints a decrypted value, a key, or any part of one. Failures are an
  entity name and a reason code.
- Sentinels are rolled back, so a run leaves nothing behind even on failure.
- Environment-gated: refuses production unless explicitly allowed, so it cannot
  become a routine writer against real patient data.
- Legacy verification is READ-ONLY and bounded. It decrypts a small sample of
  PRE-EXISTING rows, because the round-trip alone would pass with any
  self-consistent key — including a freshly generated wrong one.

Exit codes: 0 pass, 1 fail, 2 misconfiguration.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

SENTINEL_PREFIX = "CRYPTO-SMOKE"

# Environments this may write sentinels in without an explicit flag.
NON_PRODUCTION_ENVS = frozenset({"staging", "dev", "development", "local", "test"})
LEGACY_SAMPLE = 5

# (entity, table, column) — read-only legacy checks. These are the columns whose
# failure takes down a hot path: reminders and the medication timeline.
LEGACY_TARGETS = (
    ("meto_message.content", "meto_messages", "content"),
    ("extraction_candidate.fields_json", "extraction_candidates", "fields_json"),
    ("medication_statement.raw_drug_name", "medication_statements", "raw_drug_name"),
    ("notification.body", "notifications", "body"),
)


def legacy_targets() -> tuple[tuple[str, str, str], ...]:
    """The four hot paths first, then EVERY other encrypted column.

    The hot paths stay hardcoded and first because they are the ones a
    mis-rotation takes down for every patient, and they must be checked even if
    model introspection ever fails. The rest are enumerated off the ORM metadata
    rather than listed, so a PHI column added next quarter is scanned without
    anyone remembering to add it here — which is exactly the maintenance a
    hand-written list does not survive.
    """
    from app.core.phi_keyscan import encrypted_columns

    seen = {(table, column) for _entity, table, column in LEGACY_TARGETS}
    rest = tuple(
        (col.entity, col.table, col.column)
        for col in encrypted_columns()
        if (col.table, col.column) not in seen
    )
    return LEGACY_TARGETS + rest


def _sentinel() -> str:
    """A synthetic payload. Deliberately not PHI-shaped: a leaked line is inert."""
    return f"{SENTINEL_PREFIX}-{uuid.uuid4()}"


def _emit(record: dict) -> None:
    """One PHI-free JSON line. Never carries a value, a key or a patient id."""
    print(json.dumps(record, sort_keys=True))


class SmokeFailure(RuntimeError):
    def __init__(self, entity: str, reason: str):
        self.entity = entity
        self.reason = reason
        super().__init__(f"{entity}: {reason}")


def check_roundtrip(session: Session, entity: str, model, field: str, **extra) -> None:
    """Write a sentinel through the ORM, read it back, compare, verify ciphertext.

    Reads after `expire_all()` so the value genuinely comes off the database and
    back through the decrypting TypeDecorator, rather than out of the session's
    identity map — otherwise this would pass with no working key at all, which is
    exactly the false green it exists to prevent.
    """
    from app.core.crypto import is_fernet_token

    value = _sentinel()
    row_id = f"cs-{uuid.uuid4().hex[:16]}"
    session.add(model(id=row_id, **{field: value}, **extra))
    session.flush()
    session.expire_all()

    try:
        fetched = session.get(model, row_id)
    except Exception as exc:  # UndecryptablePHIError, InvalidToken, ...
        raise SmokeFailure(entity, type(exc).__name__) from exc
    if fetched is None:
        raise SmokeFailure(entity, "row_disappeared_after_write")

    got = getattr(fetched, field, None)
    if got is None:
        # on_decrypt_failure="none" degrades to None rather than raising.
        raise SmokeFailure(entity, "decrypted_to_none")
    if got != value:
        # Neither side is logged: a mismatch means the ciphertext decrypted to
        # something ELSE, and that something else may be real PHI.
        raise SmokeFailure(entity, "roundtrip_mismatch")

    raw = session.execute(
        sa.text(f"SELECT {field} FROM {model.__tablename__} WHERE id = :i"),  # noqa: S608
        {"i": row_id},
    ).scalar()
    if raw is None:
        raise SmokeFailure(entity, "no_ciphertext_at_rest")
    stored = raw if isinstance(raw, str) else json.dumps(raw)
    if not is_fernet_token(stored):
        # A column quietly storing plaintext round-trips perfectly and is
        # completely unencrypted.
        raise SmokeFailure(entity, "plaintext_where_ciphertext_required")

    session.delete(fetched)
    session.flush()


def _source_cipher():
    """A cipher over the repository's committed default key, for diagnosis only.

    Not a secret and not a runtime key: it is never added to
    `MCP_ENCRYPTION_KEYS`, so nothing in the application can read PHI with it.
    It exists so this command can answer the question that actually matters
    during an incident — "is this row encrypted with the key from the repo, or
    is it corrupt?" — which `try_decrypt() is None` cannot distinguish, and
    which decides whether the response is a re-encryption or a restore.
    """
    from app.core.crypto import repo_default_key
    from cryptography.fernet import Fernet, MultiFernet

    try:
        return MultiFernet([Fernet(repo_default_key().encode())])
    except (ValueError, TypeError):
        # The default is no longer a valid Fernet key. Diagnosis degrades to
        # "unreadable"; the verdict does not change.
        return None


def check_legacy(session: Session, entity: str, table: str, column: str) -> dict[str, int]:
    """Classify a bounded sample of PRE-EXISTING rows — the mis-rotation detector.

    The round-trip proves the key is self-consistent; it would pass with ANY
    valid key. Only reading rows written by an EARLIER deploy proves the key
    matches what is already at rest. Read-only, capped, values never printed.

    Returns COUNTS, and does not raise on a bad row.
    -----------------------------------------------
    It used to raise on the first bad row, which is why the 2026-08-06 incident
    reported::

        {"entity":"meto_message.content","reason":"legacy_row_undecryptable",…}
        …
        {"entities_checked":2,"failures":4,"legacy_rows_total":0}

    Every sampled row in four columns was unreadable, and the row counter read
    ZERO — because it only ever incremented on success and the raise jumped past
    it. "legacy_rows_total: 0" is a sentence an on-call reads as "no stored rows
    were affected", which was the exact opposite of the truth, in the incident's
    own evidence.

    Classifying every row instead means the affected count RISES with the
    damage, and each row lands in a bucket naming which key it needs: a
    wrong-key row and a corrupt row demand different responses, and neither of
    them is "plaintext".
    """
    from app.core.crypto import active_cipher
    from app.core.phi_keyscan import add_counts, empty_counts, resolve

    rows = session.execute(
        sa.text(  # noqa: S608 - literals, not user input
            f"SELECT {column} FROM {table} "
            # ORDER BY id: without it the sampled rows are implementation-defined,
            # so a rotation that DROPS an old-but-still-referenced key could be
            # missed simply because the sample happened to avoid older rows.
            f"WHERE {column} IS NOT NULL AND id NOT LIKE 'cs-%' ORDER BY id LIMIT :n"
        ),
        {"n": LEGACY_SAMPLE},
    ).scalars().all()

    target = active_cipher()
    source = _source_cipher()
    counts = empty_counts()
    for raw in rows:
        stored = raw if isinstance(raw, str) else json.dumps(raw)
        res = resolve(stored, target=target, source=source)
        counts = add_counts(counts, {res.classification: 1})
    return counts


def run(allow_production: bool = False) -> int:
    # ALLOW-list, not a deny-list. Checking `env in ("prod","production")` fails
    # OPEN: an unset, empty or differently-spelled MCP_ENV would let this write
    # sentinels (including INSERTs into users/meto_conversations) against
    # whatever database it is pointed at. The realistic path to that is the
    # incident-response run the deploy's own remediation text instructs an
    # engineer to perform, from a shell where MCP_ENV may be anything.
    env = (os.environ.get("MCP_ENV") or "").lower()
    if env not in NON_PRODUCTION_ENVS and not allow_production:
        _emit({"check": "crypto_smoke", "result": "skipped",
               "reason": "non_allowlisted_env_requires_explicit_flag", "env": env})
        return 2
    if not (os.environ.get("MCP_ENCRYPTION_KEYS") or "").strip():
        _emit({"check": "crypto_smoke", "result": "fail",
               "reason": "missing_key", "env": env})
        return 1

    from app.core.config import get_settings
    from app.models.meto import MetoMessage
    from app.models.notification import Notification

    settings = get_settings()
    build_sha = getattr(settings, "build_sha", "") or "unknown"
    engine = sa.create_engine(settings.database_url, poolclass=sa.pool.NullPool)

    from app.core.phi_keyscan import FAILING_CLASSES, add_counts, empty_counts

    failures: list[SmokeFailure] = []
    checked: list[str] = []
    legacy_rows_seen = 0
    legacy_detail: dict[str, dict[str, int]] = {}
    legacy_totals = empty_counts()

    with Session(engine) as session:
        try:
            # These columns are NOT NULL FKs, so the sentinel needs parents. They
            # are created inside the same rolled-back transaction and are as
            # synthetic as the payloads.
            owner_id = f"cs-{uuid.uuid4().hex[:16]}"
            convo_id = f"cs-{uuid.uuid4().hex[:16]}"
            session.execute(
                sa.text(
                    "INSERT INTO users (id,email,password_hash,role,is_active,"
                    "mfa_enabled,created_at,updated_at) VALUES "
                    "(:i,:e,'!','PATIENT',false,false,now(),now())"
                ),
                {"i": owner_id, "e": f"{owner_id}@crypto-smoke.invalid"},
            )
            session.execute(
                sa.text(
                    "INSERT INTO meto_conversations (id,user_id,status,"
                    "last_active_at,created_at,updated_at) VALUES "
                    "(:i,:u,'active',now(),now(),now())"
                ),
                {"i": convo_id, "u": owner_id},
            )
            session.flush()

            # Each round-trip exercises a DIFFERENT TypeDecorator
            # (EncryptedString vs EncryptedJSON) and a different failure policy
            # ("raise" vs "none"), so one passing does not imply the others do.
            for entity, model, field, extra in (
                ("notification.title", Notification, "title",
                 {"user_id": owner_id, "type": "crypto_smoke", "body": _sentinel()}),
                ("meto_message.content", MetoMessage, "content",
                 {"conversation_id": convo_id, "role": "user"}),
            ):
                try:
                    check_roundtrip(session, entity, model, field, **extra)
                    checked.append(entity)
                except SmokeFailure as exc:
                    failures.append(exc)
                except Exception as exc:
                    # A schema/FK problem is not a crypto verdict; report it as
                    # unavailable rather than claiming the key is broken.
                    failures.append(
                        SmokeFailure(entity, f"unavailable:{type(exc).__name__}")
                    )

            for entity, table, column in legacy_targets():
                # A SAVEPOINT per column. Without one, a single missing table
                # aborts the transaction and EVERY later column then fails with
                # InFailedSqlTransaction — one absent table would be reported as
                # four broken ones, in the middle of an incident.
                try:
                    with session.begin_nested():
                        counts = check_legacy(session, entity, table, column)
                except Exception as exc:
                    failures.append(
                        SmokeFailure(entity, f"unavailable:{type(exc).__name__}")
                    )
                    continue

                scanned = sum(counts.values())
                legacy_rows_seen += scanned
                legacy_totals = add_counts(legacy_totals, counts)
                legacy_detail[entity] = counts
                checked.append(f"legacy:{entity}:{scanned}")
                # One failure per class present, each naming the class and the
                # count. The reason code IS the remediation: a source-key row is
                # re-encrypted, an unreadable row is restored, and a plaintext
                # row was never encrypted at all.
                for name in FAILING_CLASSES:
                    if counts[name]:
                        failures.append(SmokeFailure(entity, f"{name}={counts[name]}"))
        finally:
            # Never leave a sentinel behind, even on an unexpected error.
            session.rollback()

    # The legacy read is the ONLY check that can distinguish the right key from
    # a merely well-formed one — the round-trip passes with any self-consistent
    # key. If it inspected ZERO rows (empty tables, all-NULL columns, a freshly
    # reseeded staging database) it silently degraded to a no-op and the run
    # would report pass having proven nothing about the deployed key.
    if not failures and legacy_rows_seen == 0:
        failures.append(
            SmokeFailure("legacy", "no_legacy_rows_to_verify")
        )

    for f in failures:
        _emit({"check": "crypto_smoke", "result": "fail", "entity": f.entity,
               "reason": f.reason, "env": env, "build_sha": build_sha})
    _emit({
        "check": "crypto_smoke",
        "result": "fail" if failures else "pass",
        "entities_checked": len(checked),
        # Per-entity bucket counts, so an operator can tell "verified 5 real
        # rows" from "verified 0 because the table was empty" — and, since
        # 2026-08-06, "5 rows readable" from "5 rows encrypted with the key from
        # the repository". The aggregate alone expressed neither.
        "legacy_rows_by_class": legacy_detail,
        # Flattened totals under the same four names, so a grep for
        # `ciphertext_source_key_rows` finds the blast radius without parsing
        # the nested object.
        **legacy_totals,
        "legacy_rows_scanned": legacy_rows_seen,
        # Retained under its original name for the dashboards and the earlier
        # evidence files that quote it — but it is now the number of rows
        # SCANNED, which rises with the damage instead of collapsing to zero.
        "legacy_rows_total": legacy_rows_seen,
        "failures": len(failures),
        "env": env,
        "build_sha": build_sha,
    })
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-deploy PHI crypto smoke.")
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="permit running against a production database (writes sentinels)",
    )
    args = parser.parse_args()
    return run(allow_production=args.allow_production)


if __name__ == "__main__":
    sys.exit(main())
