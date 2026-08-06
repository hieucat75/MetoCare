"""One-off STAGING remediation: move PHI off the repository's default key.

Why this exists
---------------
On 2026-08-06 the staging Alembic Container Apps Job was created with only
`MCP_DATABASE_URL` and `MCP_ENV`. `Settings.encryption_keys` has a default
committed to this repository, so `_cipher()` fell back to it, and the SEC-F11 /
j4_m10 data migrations — which convert previously-plaintext PHI columns to
ciphertext, and ran for the first time in that deploy — encrypted all of
staging's PHI with a public key. The application then started with the real Key
Vault key and could not read a single one of those rows.

Fixing the pipeline (PR #137) stops it recurring. It does not repair the rows.
This does: decrypt with the wrong key, re-encrypt with the right one, verify.

Why it is not `alembic upgrade`
-------------------------------
A migration runs unattended on every deploy, in every environment, with the
ambient key. This needs the opposite of all four: one environment, one
supervised run, an explicit confirmation, and TWO keysets at once. Shipping it
as a migration would put a routine that decrypts PHI with a repository-committed
key onto the production deploy path — a worse defect than the one it repairs.

Guardrails
----------
- **Staging only.** An allow-list of exactly `{"staging"}`, so an unset,
  empty or misspelled `MCP_ENV` refuses rather than running against whatever
  database it happens to be pointed at. Production is refused by name as well,
  with its own message, because that is the mistake worth naming out loud.
- **Explicit confirmation.** `STAGING_REENCRYPT_CONFIRM` must equal
  `REENCRYPT-STAGING-PHI`. Not a boolean: a value someone has to have read the
  runbook to know.
- **Neither key is ever printed.** No key, no fragment, no length, no
  ciphertext, no plaintext. Rows are referenced by `sha256(table|id)[:16]`.
  Both keys arrive by secret reference; neither appears in `--args`.
- **The source key is never registered at runtime.** It is built into a private
  `MultiFernet` here and passed explicitly. It is never written to
  `MCP_ENCRYPTION_KEYS`, so no ORM read path can reach it, and the job refuses
  to start if someone has added it there — a decrypt-only "secondary" is still a
  key whose ciphertext anyone holding this repository can read.
- **`_cipher()`'s refusal is relied on, not bypassed.** The target keyset comes
  from `crypto.active_cipher()`, so if someone runs this with the default key as
  the *target* it raises before touching a row.

Algorithm
---------
Six modes, run in this order::

    dry-run → snapshot → verify-snapshot → apply → final-scan
                                        ↘ restore-snapshot (the undo)

`dry-run` measures. `snapshot` copies every ciphertext value this job would
touch into a sibling table, still encrypted and never decrypted, because Azure
refuses on-demand backups on the Burstable server staging runs on
(`CustomerOnDemandBackupCannotBePerformedOnBurstableServer`) and PITR restores
to a whole new server. `verify-snapshot` proves that copy is complete BEFORE
anything writes. `apply` repairs. `final-scan` proves the result.
`restore-snapshot` is the undo, and it is covered by tests rather than
described in a runbook — an undo nobody has executed is a hope.

`dry-run` and `final-scan` are read-only and differ only in verdict: `dry-run`
always exits 0 (it is a measurement, and a non-zero exit on "there is work to
do" trains people to ignore it), `final-scan` exits non-zero unless every
scanned row is healthy under the target key.

`apply` walks each column by keyset pagination — `WHERE id > :cursor ORDER BY id
LIMIT :n` — never LIMIT/OFFSET, which re-walks a table whose ordering is
shifting under the very UPDATEs being issued. Each row is:

    resolved → rewritten → read back → re-resolved → committed

with the update conditioned on the ciphertext it was read with, so a row that
changed underneath the job is detected instead of clobbered. A row already
healthy under the target key is skipped, which makes the whole thing idempotent
and restart-safe: interrupt it anywhere and re-run, and it resumes by finding
what is still wrong rather than by remembering where it stopped.

An unreadable row is never rewritten. There is no plaintext to write, and a job
that "repaired" it would be destroying the evidence a restore needs.

Exit codes: 0 pass, 1 fail, 2 misconfiguration/refusal.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass

import sqlalchemy as sa
from app.core import crypto
from app.core.phi_keyscan import (
    CLASS_UNREADABLE,
    FAILING_CLASSES,
    EncryptedColumn,
    add_counts,
    empty_counts,
    encrypted_columns,
    resolve,
)
from cryptography.fernet import Fernet, MultiFernet
from sqlalchemy.orm import Session

#: The only environment this may run in. An allow-list, not a deny-list: a
#: deny-list fails OPEN for an env value nobody anticipated.
ALLOWED_ENVS = frozenset({"staging"})
PRODUCTION_ENVS = frozenset({"prod", "production"})

CONFIRM_ENV = "STAGING_REENCRYPT_CONFIRM"
CONFIRM_VALUE = "REENCRYPT-STAGING-PHI"
SOURCE_KEYS_ENV = "REENCRYPT_SOURCE_KEYS"

DEFAULT_BATCH = 500
#: Cap on individually reported failure rows. The counts are always complete;
#: this bounds the log, not the verdict.
MAX_REPORTED_ROWS = 25

#: Prefix for the pre-remediation ciphertext snapshot tables.
#:
#: Staging Postgres is a Burstable server, and Azure refuses customer on-demand
#: backups on those outright:
#:
#:     (CustomerOnDemandBackupCannotBePerformedOnBurstableServer)
#:
#: PITR remains — and covers catastrophic loss — but it restores to a NEW server
#: and rolls the whole database back, which is a sledgehammer for "put four
#: columns back the way they were". So before writing anything, every ciphertext
#: value this job would touch is copied, still encrypted, into a sibling table.
#: The copy is byte-for-byte, never decrypted, and `restore-snapshot` puts it
#: back exactly. A remediation whose undo has not been executed is not an undo.
#:
#: A prefixed table rather than a schema: SQLite has no schemas, and the tests
#: that prove the restore path works have to run somewhere.
SNAPSHOT_PREFIX = "phi_reencrypt_backup__"

MODES = (
    "dry-run",          # measure, write nothing
    "snapshot",         # copy every ciphertext value aside, still encrypted
    "verify-snapshot",  # prove the copy is complete before anything writes
    "apply",            # decrypt with source, re-encrypt with target, verify
    "final-scan",       # prove the table
    "restore-snapshot",  # put the original ciphertext back, byte for byte
)


class Refusal(RuntimeError):
    """A guardrail said no. Exit 2 — misconfiguration, not a data verdict."""


def _emit(record: dict) -> None:
    """One PHI-free JSON line. Never carries a value, a key or a key length."""
    print(json.dumps(record, sort_keys=True))


def row_ref(table: str, row_id: str) -> str:
    """A stable, PHI-free handle for one row.

    Row ids are opaque UUIDs, but they are still identifiers that join to a
    patient, and this output is pasted into incident evidence. A digest is just
    as useful for "is it the same row as last run" and discloses nothing.
    """
    return hashlib.sha256(f"{table}|{row_id}".encode()).hexdigest()[:16]


# ── Guardrails ───────────────────────────────────────────────────────────────


def _require_staging(env: str) -> None:
    if env in PRODUCTION_ENVS:
        raise Refusal(
            "refusing to run against production. This job decrypts PHI with a "
            "key committed to the repository; it exists only to repair the "
            "2026-08-06 staging incident."
        )
    if env not in ALLOWED_ENVS:
        raise Refusal(
            f"MCP_ENV={env!r} is not in the allow-list {sorted(ALLOWED_ENVS)}. "
            "Refusing rather than guessing which database this is."
        )


def _require_confirmation() -> None:
    if (os.environ.get(CONFIRM_ENV) or "").strip() != CONFIRM_VALUE:
        raise Refusal(
            f"{CONFIRM_ENV} must be set to the exact value documented in the "
            "remediation runbook. This job rewrites every encrypted PHI column."
        )


def _source_cipher() -> MultiFernet:
    """Build the wrong-key cipher, in private, from its own variable.

    Deliberately NOT `Settings`: the source key must not be reachable by any
    ORM read path, so it never goes near `MCP_ENCRYPTION_KEYS`.
    """
    raw = (os.environ.get(SOURCE_KEYS_ENV) or "").strip()
    if not raw:
        raise Refusal(
            f"{SOURCE_KEYS_ENV} is not set. Supply the key the rows were WRONGLY "
            "encrypted with, by secret reference."
        )
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError) as exc:
        # `exc` is cryptography's fixed "Fernet key must be 32 url-safe
        # base64-encoded bytes." — it never quotes the key it rejected.
        raise Refusal(f"{SOURCE_KEYS_ENV} is malformed: {exc}") from exc


def _refuse_source_registered_as_runtime_key() -> None:
    """The source key must not also be a live decrypt key.

    Registering it as a MultiFernet secondary would "fix" every read instantly
    and permanently — while leaving the PHI encrypted under a key published in
    this repository, and removing the only signal that anything was wrong.
    """
    runtime = (os.environ.get("MCP_ENCRYPTION_KEYS") or "").strip()
    source = (os.environ.get(SOURCE_KEYS_ENV) or "").strip()
    if not runtime or not source:
        return
    runtime_keys = {k.strip() for k in runtime.split(",") if k.strip()}
    for key in (k.strip() for k in source.split(",") if k.strip()):
        if key in runtime_keys:
            raise Refusal(
                "the source key is also present in MCP_ENCRYPTION_KEYS. A "
                "decrypt-only secondary is still a key that can read this PHI; "
                "remove it from the runtime keyset before remediating."
            )


# ── Scanning and repair ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ColumnResult:
    """What one column looked like when the job walked it.

    `counts` is always the state as FOUND, in every mode. Apply reports what it
    changed separately, and the proof that the change worked is `final-scan`
    re-reading the column — not this job describing its own success.

    `rows` is a bounded list of PHI-free row references for the non-healthy
    rows; it is diagnostic. `unavailable` is different in kind — the column
    could not be scanned at all — and it is the only one of the two that on its
    own makes a run fail.
    """

    entity: str
    scanned: int
    counts: dict[str, int]
    rewritten: int
    verified: int
    rows: tuple[str, ...]
    unavailable: str | None
    checksum: str

    @property
    def failing(self) -> int:
        return sum(self.counts.get(name, 0) for name in FAILING_CLASSES)


def _quoted(session: Session, name: str) -> str:
    """Dialect-correct identifier quoting.

    Table and column names come from SQLAlchemy metadata, not from input, so
    this is belt-and-braces — but these strings are interpolated into SQL and
    the next person to add a `--table` flag should find quoting already here.
    """
    return session.bind.dialect.identifier_preparer.quote(name)


def _page(session: Session, col: EncryptedColumn, cursor: str | None, size: int):
    """One keyset page. NOT offset: the table is being UPDATEd underneath."""
    table, column = _quoted(session, col.table), _quoted(session, col.column)
    where = f"{column} IS NOT NULL"
    params: dict[str, object] = {"n": size}
    if cursor is not None:
        where += " AND id > :cursor"
        params["cursor"] = cursor
    sql = f"SELECT id, {column} FROM {table} WHERE {where} ORDER BY id LIMIT :n"  # noqa: S608
    return session.execute(sa.text(sql), params).all()


def _stored_text(raw: object) -> str:
    """A column value as the text the cipher sees.

    A legacy JSON/JSONB row arrives from the driver already deserialized; the
    encrypted form is always TEXT. Serializing with the same `sort_keys=True`
    that `EncryptedJSON.process_bind_param` uses keeps a converted row
    byte-identical to one the application would have written.
    """
    if isinstance(raw, str):
        return raw
    return json.dumps(raw, ensure_ascii=False, sort_keys=True)


def scan_column(
    session: Session,
    col: EncryptedColumn,
    *,
    target: MultiFernet,
    source: MultiFernet,
    batch: int,
) -> ColumnResult:
    """Read-only classification of every non-NULL value in one column."""
    counts = empty_counts()
    scanned = 0
    flagged: list[str] = []
    digest = hashlib.sha256()
    cursor: str | None = None

    while True:
        rows = _page(session, col, cursor, batch)
        if not rows:
            break
        for row_id, raw in rows:
            stored = _stored_text(raw)
            res = resolve(stored, target=target, source=source)
            counts = add_counts(counts, {res.classification: 1})
            scanned += 1
            # Hashing the CIPHERTEXT, in id order: a checksum an operator can
            # compare before and after a restore without it ever containing PHI.
            digest.update(row_id.encode())
            digest.update(stored.encode())
            if res.classification in FAILING_CLASSES and len(flagged) < MAX_REPORTED_ROWS:
                flagged.append(f"{res.classification}:{row_ref(col.table, row_id)}")
            cursor = row_id
    # Read-only: end the snapshot rather than hold one open across 31 columns.
    session.rollback()
    return ColumnResult(
        entity=col.entity,
        scanned=scanned,
        counts=counts,
        rewritten=0,
        verified=0,
        rows=tuple(flagged),
        unavailable=None,
        checksum=digest.hexdigest()[:32],
    )


def apply_column(
    session: Session,
    col: EncryptedColumn,
    *,
    target: MultiFernet,
    source: MultiFernet,
    batch: int,
) -> ColumnResult:
    """Rewrite every recoverable non-healthy value under the target key.

    Commits per page, so an interrupted run leaves a prefix of the table
    repaired and the rest untouched — both states the next run handles, because
    it decides what to do per row rather than from a saved position.
    """
    counts = empty_counts()
    scanned = rewritten = verified = 0
    flagged: list[str] = []
    stuck = 0
    cursor: str | None = None
    table, column = _quoted(session, col.table), _quoted(session, col.column)

    while True:
        rows = _page(session, col, cursor, batch)
        if not rows:
            break
        for row_id, raw in rows:
            cursor = row_id
            stored = _stored_text(raw)
            res = resolve(stored, target=target, source=source)
            counts = add_counts(counts, {res.classification: 1})
            scanned += 1

            if res.is_healthy:
                continue
            if not res.needs_rewrite:
                # Unreadable. Left exactly as found: there is no plaintext to
                # write back, and overwriting it would destroy what a restore
                # needs. The run fails on it at the end.
                stuck += 1
                if len(flagged) < MAX_REPORTED_ROWS:
                    flagged.append(f"{CLASS_UNREADABLE}:{row_ref(col.table, row_id)}")
                continue

            new = target.encrypt(res.plaintext.encode()).decode()
            # Conditioned on the value we read. If anything wrote to this row in
            # between, rowcount is 0 and we stop rather than overwrite a value
            # we never resolved.
            updated = session.execute(
                sa.text(  # noqa: S608 - identifiers are metadata, values are bound
                    f"UPDATE {table} SET {column} = :new "
                    f"WHERE id = :id AND {column} = :old"
                ),
                {"new": new, "id": row_id, "old": stored},
            ).rowcount
            if updated != 1:
                # Staging writes are frozen for the remediation, so this means
                # the freeze leaked. Counted as stuck, not retried: re-reading
                # and rewriting in a loop is how a job races a live writer.
                stuck += 1
                if len(flagged) < MAX_REPORTED_ROWS:
                    flagged.append(
                        f"row_changed_concurrently:{row_ref(col.table, row_id)}"
                    )
                continue
            rewritten += 1

            # Verify immediately, off the database, through the target key only.
            # A rewrite that is not read back is a rewrite nobody has checked.
            back = session.execute(
                sa.text(f"SELECT {column} FROM {table} WHERE id = :id"),  # noqa: S608
                {"id": row_id},
            ).scalar()
            check = resolve(_stored_text(back), target=target, source=None)
            if not check.is_healthy or check.plaintext != res.plaintext:
                # Neither side is logged: a mismatch means the row decrypted to
                # something else, and that something else is PHI. Abort the whole
                # column rather than continue — a rewrite path that can produce a
                # wrong value must not be allowed to produce a thousand more.
                session.rollback()
                raise RuntimeError(
                    f"a rewritten row did not read back correctly "
                    f"({row_ref(col.table, row_id)}); the page was rolled back "
                    "and nothing further was written to this column"
                )
            verified += 1
        session.commit()

    return ColumnResult(
        entity=col.entity,
        scanned=scanned,
        # The state as FOUND. What it is now is `final-scan`'s job to say.
        counts=counts,
        rewritten=rewritten,
        verified=verified,
        rows=tuple(flagged),
        unavailable=(f"rows_not_remediated:{stuck}" if stuck else None),
        checksum="",
    )


# ── Ciphertext snapshot: the undo, executed rather than described ────────────


def snapshot_name(col: EncryptedColumn) -> str:
    """Deterministic, so every mode finds the same table without a manifest."""
    return f"{SNAPSHOT_PREFIX}{col.table}__{col.column}"


def _table_exists(session: Session, name: str) -> bool:
    return sa.inspect(session.bind).has_table(name)


def _checksum(session: Session, table: str, column: str) -> tuple[int, str]:
    """(row count, digest of id+ciphertext in id order). Never decrypts."""
    t, c = _quoted(session, table), _quoted(session, column)
    rows = session.execute(
        sa.text(f"SELECT id, {c} FROM {t} WHERE {c} IS NOT NULL ORDER BY id")  # noqa: S608
    ).all()
    digest = hashlib.sha256()
    for row_id, raw in rows:
        digest.update(row_id.encode())
        digest.update(_stored_text(raw).encode())
    return len(rows), digest.hexdigest()[:32]


def snapshot_column(session: Session, col: EncryptedColumn) -> ColumnResult:
    """Copy every non-NULL ciphertext value into a sibling table, as-is.

    Refuses to overwrite an existing snapshot. A second run part-way through a
    remediation would otherwise capture the half-repaired state and quietly
    replace the only copy of the original — destroying the undo at the exact
    moment it is most likely to be needed.
    """
    name = snapshot_name(col)
    if _table_exists(session, name):
        return ColumnResult(
            entity=col.entity, scanned=0, counts=empty_counts(), rewritten=0,
            verified=0, rows=(), unavailable="snapshot_already_exists", checksum="",
        )
    src, column, dst = _quoted(session, col.table), _quoted(session, col.column), _quoted(
        session, name
    )
    session.execute(
        sa.text(  # noqa: S608 - identifiers come from ORM metadata
            f"CREATE TABLE {dst} AS "
            f"SELECT id, {column} FROM {src} WHERE {column} IS NOT NULL"
        )
    )
    session.commit()
    count, digest = _checksum(session, name, col.column)
    return ColumnResult(
        entity=col.entity, scanned=count, counts=empty_counts(), rewritten=count,
        verified=0, rows=(), unavailable=None, checksum=digest,
    )


def verify_snapshot_column(session: Session, col: EncryptedColumn) -> ColumnResult:
    """Prove the snapshot is a complete, faithful copy — before anything writes.

    A snapshot nobody counted is a belief, not a backup.
    """
    name = snapshot_name(col)
    if not _table_exists(session, name):
        return ColumnResult(
            entity=col.entity, scanned=0, counts=empty_counts(), rewritten=0,
            verified=0, rows=(), unavailable="snapshot_missing", checksum="",
        )
    live_count, live_digest = _checksum(session, col.table, col.column)
    snap_count, snap_digest = _checksum(session, name, col.column)
    mismatch = None
    if snap_count != live_count:
        mismatch = f"row_count_mismatch:live={live_count}:snapshot={snap_count}"
    elif snap_digest != live_digest:
        mismatch = "ciphertext_digest_mismatch"
    return ColumnResult(
        entity=col.entity, scanned=snap_count, counts=empty_counts(), rewritten=0,
        verified=snap_count if mismatch is None else 0, rows=(),
        unavailable=mismatch, checksum=snap_digest,
    )


def restore_snapshot_column(session: Session, col: EncryptedColumn) -> ColumnResult:
    """Put the original ciphertext back, byte for byte.

    Row-by-row rather than `UPDATE … FROM`: the same statement then works on
    both Postgres and SQLite, so the restore path this incident depends on is
    exercised by the test suite instead of being read and hoped about.
    """
    name = snapshot_name(col)
    if not _table_exists(session, name):
        return ColumnResult(
            entity=col.entity, scanned=0, counts=empty_counts(), rewritten=0,
            verified=0, rows=(), unavailable="snapshot_missing", checksum="",
        )
    live, column, snap = _quoted(session, col.table), _quoted(session, col.column), _quoted(
        session, name
    )
    rows = session.execute(
        sa.text(f"SELECT id, {column} FROM {snap} ORDER BY id")  # noqa: S608
    ).all()
    restored = 0
    missing = 0
    for row_id, original in rows:
        updated = session.execute(
            sa.text(f"UPDATE {live} SET {column} = :v WHERE id = :i"),  # noqa: S608
            {"v": original, "i": row_id},
        ).rowcount
        if updated == 1:
            restored += 1
        else:
            # The row was deleted after the snapshot. Reported, not recreated:
            # resurrecting a deleted patient record is not a restore.
            missing += 1
    session.commit()
    _, digest = _checksum(session, col.table, col.column)
    return ColumnResult(
        entity=col.entity, scanned=len(rows), counts=empty_counts(), rewritten=restored,
        verified=restored, rows=(),
        unavailable=(f"rows_absent_from_live_table:{missing}" if missing else None),
        checksum=digest,
    )


# ── Entry point ──────────────────────────────────────────────────────────────


def run(mode: str) -> int:
    if mode not in MODES:
        _emit({"job": "reencrypt_phi", "result": "refused",
               "reason": f"unknown_mode:{mode}"})
        return 2

    env = (os.environ.get("MCP_ENV") or "").lower()
    try:
        _require_staging(env)
        _require_confirmation()
        _refuse_source_registered_as_runtime_key()
        source = _source_cipher()
        # Raises EncryptionConfigError if the TARGET is the committed default —
        # re-encrypting onto a public key would look like success and be worse
        # than doing nothing.
        target = crypto.active_cipher()
    except (Refusal, crypto.EncryptionConfigError) as exc:
        _emit({"job": "reencrypt_phi", "mode": mode, "env": env,
               "result": "refused", "reason": str(exc)})
        return 2

    columns = encrypted_columns()
    settings = crypto.get_settings()
    engine = sa.create_engine(settings.database_url, poolclass=sa.pool.NullPool)

    results: list[ColumnResult] = []
    totals = empty_counts()
    with Session(engine) as session:
        for col in columns:
            try:
                if mode == "apply":
                    result = apply_column(
                        session, col, target=target, source=source, batch=DEFAULT_BATCH
                    )
                elif mode == "snapshot":
                    result = snapshot_column(session, col)
                elif mode == "verify-snapshot":
                    result = verify_snapshot_column(session, col)
                elif mode == "restore-snapshot":
                    result = restore_snapshot_column(session, col)
                else:
                    result = scan_column(
                        session, col, target=target, source=source, batch=DEFAULT_BATCH
                    )
            except Exception as exc:  # noqa: BLE001 - reported, never swallowed
                # A failed statement poisons the transaction for every later
                # column, so the session is reset before continuing. The column
                # is reported unavailable, which fails the run in every mode:
                # "we could not look" must never read like "there was nothing".
                session.rollback()
                result = ColumnResult(
                    entity=col.entity, scanned=0, counts=empty_counts(), rewritten=0,
                    verified=0, rows=(), unavailable=type(exc).__name__, checksum="",
                )
            results.append(result)
            totals = add_counts(totals, result.counts)
            _emit({
                "job": "reencrypt_phi", "mode": mode, "entity": result.entity,
                "scanned": result.scanned, **result.counts,
                "rewritten": result.rewritten, "verified": result.verified,
                "unavailable": result.unavailable,
                "ciphertext_sha256_16": result.checksum,
                "rows": list(result.rows),
            })

    found_unhealthy = sum(totals.get(name, 0) for name in FAILING_CLASSES)
    unavailable = [r.entity for r in results if r.unavailable]
    rewritten = sum(r.rewritten for r in results)
    summary = {
        "job": "reencrypt_phi",
        "mode": mode,
        "env": env,
        "build_sha": getattr(settings, "build_sha", "") or "unknown",
        "columns_scanned": len(results),
        "rows_scanned": sum(r.scanned for r in results),
        **totals,
        "rows_rewritten": rewritten,
        "rows_verified": sum(r.verified for r in results),
        "rows_needing_remediation": found_unhealthy,
        "entities_unavailable": unavailable,
    }

    if mode == "dry-run":
        # A measurement, not a gate. Finding work to do is the expected outcome
        # and must exit 0 — a dry run that exits non-zero on its own findings is
        # one an operator learns to invoke with `|| true`. Only a column it
        # could not read is a failure.
        _emit({**summary, "result": "measured" if not unavailable else "fail"})
        return 1 if unavailable else 0

    if mode in ("snapshot", "verify-snapshot", "restore-snapshot"):
        # These do not classify rows, so `rows_needing_remediation` is
        # meaningless here and the verdict rests entirely on completeness.
        # `snapshot_already_exists` is a failure on purpose: silently reusing an
        # older snapshot would let a half-repaired state pass as backed up.
        ok = not unavailable
        _emit({**summary, "result": "pass" if ok else "fail"})
        return 0 if ok else 1

    if mode == "apply":
        # Apply is judged on what it did, not on the state it found: it walked a
        # broken table, so `found_unhealthy` is SUPPOSED to be large. It passes
        # when every non-healthy row it found was rewritten and verified, and no
        # column was left partially done. `final-scan` is what proves the table.
        ok = not unavailable and rewritten == found_unhealthy
        _emit({**summary, "result": "pass" if ok else "fail",
               "rows_left_unremediated": found_unhealthy - rewritten})
        return 0 if ok else 1

    # final-scan: the only mode whose verdict is about the table's state.
    ok = found_unhealthy == 0 and not unavailable
    _emit({**summary, "result": "pass" if ok else "fail"})
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0] if argv else "dry-run"
    return run(mode)


if __name__ == "__main__":
    sys.exit(main())
