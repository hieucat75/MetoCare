"""P1-5: encrypt the PHI surfaces SEC-F11 left in plaintext.

SEC-F11 encrypted `meto_messages.content` and `extraction_candidates.fields_json`.
Three readable surfaces holding the same class of data remained, and each is
worse than it first looks:

  - `extraction_candidates.corrections_json` — the patient's CORRECTIONS to the
    extracted fields. Same clinical values as `fields_json`, usually *more*
    accurate because a human fixed them. Encrypting the machine's guess and
    leaving the confirmed truth readable is the wrong way round.

  - `medication_statements.raw_*` and `payload_snapshot` — verbatim OCR strings
    off a prescription: drug name, dose, frequency, prescriber. A drug name is
    PHI in the strongest sense; an antiretroviral, an antipsychotic or an
    oncology agent discloses the condition more directly than most diagnosis
    fields do. `payload_snapshot` is a superset of the rest, so encrypting the
    columns and not the snapshot would leave the same data readable.

  - `notifications.title` / `body` — medication reminders put the drug name in
    the body BY DESIGN ("Đến giờ uống Metformin"), so this table accumulates a
    plaintext, timestamped medication history for every patient. `title` is
    encrypted too: the reminder path uses a fixed template, but POST
    /notifications accepts an arbitrary admin-supplied title, so "titles contain
    no patient data" is a convention, not an invariant.

None of these columns is filtered, ordered or grouped by value anywhere (checked
before writing this), so Fernet's non-determinism costs nothing.

`on_decrypt_failure` per column follows EncryptedString's documented rule rather
than a blanket choice: NOT NULL columns (`raw_drug_name`, `notifications.title`,
`notifications.body`) use "raise", because a silent None would violate the column
and crash response serialization; the optional overlays use "none", so one
unreadable row degrades a field instead of making a whole record unopenable.

Ordering matters and is not cosmetic: the JSONB → TEXT conversions must happen
BEFORE the values are encrypted. A Fernet token is a bare string, and writing one
into a still-`jsonb` column raises `invalid input syntax for type json` — the
same trap SEC-F11 hit. `notifications.title` must also widen from VARCHAR(256),
since ciphertext is longer than its plaintext.

Revision ID: j4_m10_p15_residual_phi
Revises: j4_m9_secf11_phi_encryption
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "j4_m10_p15_residual_phi"
down_revision = "j4_m9_secf11_phi_encryption"
branch_labels = None
depends_on = None

_BATCH_SIZE = 500
_LOCK_TIMEOUT = "5s"

_TEXT_COLUMNS = (
    ("medication_statements", "raw_drug_name"),
    ("medication_statements", "normalized_name"),
    ("medication_statements", "raw_dose"),
    ("medication_statements", "raw_frequency"),
    ("medication_statements", "raw_prescriber"),
    ("notifications", "title"),
    ("notifications", "body"),
)
_JSON_COLUMNS = (
    ("extraction_candidates", "corrections_json"),
    ("medication_statements", "payload_snapshot"),
)


def _iter_batches(conn, table: str, column: str):
    """Yield ``[(id, value), …]`` using KEYSET pagination.

    ``WHERE id > :last`` stays stable while the same rows are being rewritten;
    LIMIT/OFFSET does not, because rewriting rows can shift what a given OFFSET
    points at and silently skip data.
    """
    last = ""
    while True:
        batch = conn.execute(
            sa.text(
                f"SELECT id, {column} FROM {table} "  # noqa: S608 - literals, not user input
                "WHERE id > :last ORDER BY id LIMIT :limit"
            ),
            {"last": last, "limit": _BATCH_SIZE},
        ).fetchall()
        if not batch:
            return
        yield batch
        last = batch[-1][0]


def _write(conn, table: str, column: str, updates: list[dict]) -> None:
    if not updates:
        return
    conn.execute(
        sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id"),  # noqa: S608
        updates,
    )


def _as_text(value) -> str:
    """Normalize a driver value to text (JSONB comes back as dict/list)."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _preflight_locks(conn, table: str) -> None:
    """Name what would block a rewrite, before attempting to take the lock."""
    if conn.dialect.name != "postgresql":
        return
    try:
        rows = conn.execute(
            sa.text(
                """
                SELECT a.pid, a.state,
                       COALESCE(EXTRACT(EPOCH FROM (now() - a.xact_start)), 0)::int
                  FROM pg_locks l
                  JOIN pg_stat_activity a ON a.pid = l.pid
                 WHERE l.relation = to_regclass(:t) AND a.pid <> pg_backend_pid()
                """
            ),
            {"t": table},
        ).fetchall()
    except Exception as exc:  # pragma: no cover - diagnostics must never break DDL
        print(f"[p15] lock preflight unavailable ({exc}); continuing")
        return
    if rows:
        detail = ", ".join(f"pid={r[0]} state={r[1]} xact_age={r[2]}s" for r in rows)
        print(
            f"[p15] WARNING: {len(rows)} session(s) hold locks on {table}: {detail}. "
            f"The rewrite aborts after {_LOCK_TIMEOUT} rather than queueing behind them."
        )


def _guard_lock_waits(conn) -> None:
    """Bound the lock WAIT; leave the rewrite unbounded once the lock is held.

    An ACCESS EXCLUSIVE waiter sits at the head of the lock queue, so every later
    query on the table queues behind it — one idle-in-transaction session would
    otherwise take the table offline for as long as it stays open.
    """
    if conn.dialect.name != "postgresql":
        return
    conn.execute(sa.text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'"))
    conn.execute(sa.text("SET LOCAL statement_timeout = 0"))


def _assert_fully_encrypted(conn, table: str, column: str) -> None:
    """Fail loudly if any row is still plaintext — never report a partial run green."""
    from app.core.crypto import is_fernet_token

    remaining = 0
    for batch in _iter_batches(conn, table, column):
        remaining += sum(
            1 for _id, v in batch if v is not None and not is_fernet_token(_as_text(v))
        )
    if remaining:
        raise RuntimeError(
            f"P1-5: {remaining} row(s) in {table}.{column} are still plaintext after "
            "the backfill. Refusing to report a partial migration as complete — "
            "re-run the migration."
        )


def _encrypt(conn, table: str, column: str) -> None:
    from app.core.crypto import encrypt, is_fernet_token

    for batch in _iter_batches(conn, table, column):
        updates = [
            {"id": _id, "value": encrypt(_as_text(v))}
            for _id, v in batch
            if v is not None and not is_fernet_token(_as_text(v))
        ]
        _write(conn, table, column, updates)


def _decrypt(conn, table: str, column: str, *, as_json: bool) -> None:
    from app.core.crypto import is_fernet_token, try_decrypt

    for batch in _iter_batches(conn, table, column):
        updates = []
        for _id, v in batch:
            if v is None or not is_fernet_token(_as_text(v)):
                continue
            plain = try_decrypt(_as_text(v))
            if plain is None:
                raise RuntimeError(
                    f"P1-5 downgrade: {table}.{column} row {_id} cannot be decrypted "
                    "with the configured MCP_ENCRYPTION_KEYS. Refusing to overwrite it "
                    "— that would destroy clinical data. Re-run with the correct key(s)."
                )
            if as_json:
                # Validate before writing back into a JSON column, so a bad value
                # fails here rather than as a constraint error mid-rewrite.
                json.loads(plain)
            updates.append({"id": _id, "value": plain})
        _write(conn, table, column, updates)


def _alter_json(conn, table: str, column: str, *, to_text: bool) -> None:
    if conn.dialect.name == "postgresql":
        _preflight_locks(conn, table)
        _guard_lock_waits(conn)
        using = f"{column} #>> '{{}}'" if to_text else f"{column}::jsonb"
        target = "TEXT" if to_text else "JSONB"
        op.execute(
            sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {target} USING {using}"
            )
        )
    else:
        with op.batch_alter_table(table, schema=None) as batch:
            batch.alter_column(
                column,
                type_=sa.Text() if to_text else sa.JSON(),
                existing_nullable=True,
            )


def _assert_titles_fit_varchar256(conn) -> None:
    """Refuse the downgrade with an ACTIONABLE error rather than a raw DataError.

    `ALTER COLUMN title TYPE VARCHAR(256)` does not truncate — Postgres raises
    `StringDataRightTruncation` — so a single notification longer than 256 chars
    blocks the rollback path entirely. The transaction rolls back cleanly, so
    there is no corruption, but an operator mid-incident gets a bare SQL error and
    no indication of which rows are at fault.

    `NotificationCreate.title` is now bounded at 256, so no NEW row can trip this;
    this covers rows written while the bound did not exist. Same fail-loud,
    say-what-to-do-about-it shape as the wrong-key guard in `_decrypt`.
    """
    if conn.dialect.name != "postgresql":
        return
    over = conn.execute(
        sa.text(
            "SELECT id, length(title) AS n FROM notifications "
            "WHERE length(title) > 256 ORDER BY n DESC LIMIT 5"
        )
    ).fetchall()
    if over:
        ids = ", ".join(f"{r[0]} ({r[1]} chars)" for r in over)
        raise RuntimeError(
            "P1-5 downgrade: notifications.title cannot be narrowed back to "
            f"VARCHAR(256) — {len(over)}+ row(s) exceed it, e.g. {ids}. Postgres "
            "raises rather than truncating, so this would fail mid-ALTER. Shorten "
            "or delete those rows, then re-run the downgrade."
        )


def _alter_title(conn, *, to_text: bool) -> None:
    if not to_text:
        _assert_titles_fit_varchar256(conn)
    if conn.dialect.name == "postgresql":
        _preflight_locks(conn, "notifications")
        _guard_lock_waits(conn)
        target = "TEXT" if to_text else "VARCHAR(256)"
        op.execute(
            sa.text(f"ALTER TABLE notifications ALTER COLUMN title TYPE {target}")
        )
    else:
        with op.batch_alter_table("notifications", schema=None) as batch:
            batch.alter_column(
                "title",
                type_=sa.Text() if to_text else sa.String(256),
                existing_nullable=False,
            )


def upgrade() -> None:
    conn = op.get_bind()

    # 1. JSON → TEXT first. Encrypting first would try to store a bare Fernet
    #    token in a jsonb column: `invalid input syntax for type json`.
    for table, column in _JSON_COLUMNS:
        _alter_json(conn, table, column, to_text=True)

    # 2. Widen notifications.title — ciphertext does not fit VARCHAR(256).
    _alter_title(conn, to_text=True)

    # 3. Backfill, then prove it.
    for table, column in _TEXT_COLUMNS + _JSON_COLUMNS:
        _encrypt(conn, table, column)
        _assert_fully_encrypted(conn, table, column)


def downgrade() -> None:
    conn = op.get_bind()

    for table, column in _TEXT_COLUMNS:
        _decrypt(conn, table, column, as_json=False)
    for table, column in _JSON_COLUMNS:
        _decrypt(conn, table, column, as_json=True)

    # Plaintext must be back before the JSON type is restored, or the cast fails.
    for table, column in _JSON_COLUMNS:
        _alter_json(conn, table, column, to_text=False)

    _alter_title(conn, to_text=False)
