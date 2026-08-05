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
LEGACY_SAMPLE = 5

# (entity, table, column) — read-only legacy checks. These are the columns whose
# failure takes down a hot path: reminders and the medication timeline.
LEGACY_TARGETS = (
    ("meto_message.content", "meto_messages", "content"),
    ("extraction_candidate.fields_json", "extraction_candidates", "fields_json"),
    ("medication_statement.raw_drug_name", "medication_statements", "raw_drug_name"),
    ("notification.body", "notifications", "body"),
)


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


def check_legacy(session: Session, entity: str, table: str, column: str) -> int:
    """Decrypt a bounded sample of PRE-EXISTING rows — the mis-rotation detector.

    The round-trip proves the key is self-consistent; it would pass with ANY
    valid key. Only reading rows written by an EARLIER deploy proves the key
    matches what is already at rest. Read-only, capped, values never printed.
    """
    from app.core.crypto import is_fernet_token, try_decrypt

    rows = session.execute(
        sa.text(  # noqa: S608 - literals, not user input
            f"SELECT {column} FROM {table} "
            f"WHERE {column} IS NOT NULL AND id NOT LIKE 'cs-%' LIMIT :n"
        ),
        {"n": LEGACY_SAMPLE},
    ).scalars().all()

    checked = 0
    for raw in rows:
        stored = raw if isinstance(raw, str) else json.dumps(raw)
        if not is_fernet_token(stored):
            raise SmokeFailure(entity, "legacy_row_is_plaintext")
        if try_decrypt(stored) is None:
            raise SmokeFailure(entity, "legacy_row_undecryptable")
        checked += 1
    return checked


def run(allow_production: bool = False) -> int:
    env = (os.environ.get("MCP_ENV") or "").lower()
    if env in ("prod", "production") and not allow_production:
        _emit({"check": "crypto_smoke", "result": "skipped",
               "reason": "production_requires_explicit_flag", "env": env})
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

    failures: list[SmokeFailure] = []
    checked: list[str] = []

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

            for entity, table, column in LEGACY_TARGETS:
                try:
                    n = check_legacy(session, entity, table, column)
                    checked.append(f"legacy:{entity}:{n}")
                except SmokeFailure as exc:
                    failures.append(exc)
                except Exception as exc:
                    failures.append(
                        SmokeFailure(entity, f"unavailable:{type(exc).__name__}")
                    )
        finally:
            # Never leave a sentinel behind, even on an unexpected error.
            session.rollback()

    for f in failures:
        _emit({"check": "crypto_smoke", "result": "fail", "entity": f.entity,
               "reason": f.reason, "env": env, "build_sha": build_sha})
    _emit({
        "check": "crypto_smoke",
        "result": "fail" if failures else "pass",
        "entities_checked": len(checked),
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
