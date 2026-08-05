"""SEC-F11: encrypt Meto message bodies and OCR candidate fields at rest.

Two free-text PHI surfaces were plaintext while everything comparable was already
encrypted:

* ``meto_messages.content`` — patient-typed symptoms and AI answers quoting their
  labs/medications. Pure data migration; an encrypted column is still TEXT.
* ``extraction_candidates.fields_json`` — extracted drug names, strengths, doses
  and diagnosis text, while the OCR page text it was derived from
  (``document_pages.ocr_raw``) was already encrypted. This one also changes type:
  JSON/JSONB → TEXT holding ciphertext. Verified safe because nothing filters,
  indexes or joins on that column by value; reads deserialize the whole dict in
  Python.

DESIGN NOTES
------------
Restart-safe and idempotent in BOTH directions. ``upgrade`` skips values that are
already ciphertext; ``downgrade`` skips values that are already plaintext. An
interrupted run can simply be re-run.

Batching is by KEYSET (``WHERE id > :last ORDER BY id``), not LIMIT/OFFSET. OFFSET
paging over a table you are simultaneously rewriting is the classic way to skip
rows; keyset paging cannot skip, and does not degrade on large tables.

Each batch is written with a single ``executemany`` rather than a round trip per row.

NO SILENT PARTIAL MIGRATION: after each rewrite the table is re-scanned, and if any
row is still plaintext the migration raises. A half-encrypted table must fail the
deploy, not be reported as success.

NO PHI IN LOGS: nothing here logs a value, a key, or a row id — only counts.

DOWNGRADE: reverses to plaintext. If a value is ciphertext that cannot be decrypted
with any configured key, downgrade RAISES rather than writing a corrupted or empty
value — silently losing PHI is worse than a failed downgrade. Recovery: re-run with
the correct ``MCP_ENCRYPTION_KEYS``.

Revision ID: j4_m9_secf11_phi_encryption
Revises: j4_m8_consent_versioning
Create Date: 2026-08-05
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j4_m9_secf11_phi_encryption"
down_revision: str | None = "j4_m8_consent_versioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Rows fetched (and rewritten) per round trip. Small enough to bound memory on a
# large table, large enough that the executemany amortises the round trip.
_BATCH_SIZE = 500


def _iter_batches(conn, table: str, column: str):
    """Yield ``[(id, value), …]`` batches using KEYSET pagination.

    ``WHERE id > :last`` is stable while the same rows are being rewritten —
    LIMIT/OFFSET is not, because rewriting rows can shift what a given OFFSET
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
    """Normalize a driver value to text.

    ``fields_json`` is JSONB before this migration, so the driver hands back a
    dict; after the type change it is TEXT and comes back as ``str``.
    """
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


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
            f"SEC-F11: {remaining} row(s) in {table}.{column} are still plaintext after "
            "the backfill. Refusing to report a partial migration as complete — "
            "re-run the migration."
        )


# ── meto_messages.content ────────────────────────────────────────────────────
def _encrypt_messages(conn) -> None:
    from app.core.crypto import encrypt, try_decrypt

    for batch in _iter_batches(conn, "meto_messages", "content"):
        updates = [
            {"id": row_id, "value": encrypt(content)}
            for row_id, content in batch
            # Already ciphertext → skip, so a re-run is a no-op.
            if content is not None and try_decrypt(content) is None
        ]
        _write(conn, "meto_messages", "content", updates)


def _decrypt_messages(conn) -> None:
    from app.core.crypto import is_fernet_token, try_decrypt

    for batch in _iter_batches(conn, "meto_messages", "content"):
        updates = []
        for row_id, content in batch:
            if content is None:
                continue
            plaintext = try_decrypt(content)
            if plaintext is not None:
                updates.append({"id": row_id, "value": plaintext})
            elif is_fernet_token(content):
                raise RuntimeError(
                    "SEC-F11 downgrade: meto_messages.content holds ciphertext that "
                    "cannot be decrypted with the configured MCP_ENCRYPTION_KEYS. "
                    "Refusing to overwrite it — that would destroy patient data. "
                    "Re-run the downgrade with the correct key(s)."
                )
            # else: already plaintext → skip (idempotent).
        _write(conn, "meto_messages", "content", updates)


# ── extraction_candidates.fields_json ────────────────────────────────────────
def _encrypt_candidate_fields(conn) -> None:
    from app.core.crypto import encrypt, try_decrypt

    for batch in _iter_batches(conn, "extraction_candidates", "fields_json"):
        updates = []
        for row_id, raw in batch:
            if raw is None:
                continue
            if isinstance(raw, str) and try_decrypt(raw) is not None:
                continue  # already ciphertext
            updates.append({"id": row_id, "value": encrypt(_as_text(raw))})
        _write(conn, "extraction_candidates", "fields_json", updates)


def _decrypt_candidate_fields(conn) -> None:
    from app.core.crypto import is_fernet_token, try_decrypt

    for batch in _iter_batches(conn, "extraction_candidates", "fields_json"):
        updates = []
        for row_id, raw in batch:
            if raw is None or not isinstance(raw, str):
                continue  # already a JSON value
            plaintext = try_decrypt(raw)
            if plaintext is not None:
                updates.append({"id": row_id, "value": plaintext})
            elif is_fernet_token(raw):
                raise RuntimeError(
                    "SEC-F11 downgrade: extraction_candidates.fields_json holds "
                    "ciphertext that cannot be decrypted with the configured "
                    "MCP_ENCRYPTION_KEYS. Refusing to overwrite it — that would "
                    "destroy extracted clinical data. Re-run with the correct key(s)."
                )
        _write(conn, "extraction_candidates", "fields_json", updates)


def upgrade() -> None:
    conn = op.get_bind()

    _encrypt_messages(conn)
    _assert_fully_encrypted(conn, "meto_messages", "content")

    # Convert JSONB → TEXT *first*, then encrypt. The other order fails: a Fernet
    # token is a bare string, and writing one into a still-`jsonb` column raises
    # `invalid input syntax for type json` (verified on Postgres). `#>> '{}'`
    # renders the JSON document to its text form, which is exactly what the
    # ciphertext must wrap. SQLite goes through batch_alter_table — its JSON is
    # TEXT underneath already.
    if conn.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "ALTER TABLE extraction_candidates "
                "ALTER COLUMN fields_json TYPE TEXT USING fields_json #>> '{}'"
            )
        )
    else:
        with op.batch_alter_table("extraction_candidates", schema=None) as batch:
            batch.alter_column("fields_json", type_=sa.Text(), existing_nullable=False)
    _encrypt_candidate_fields(conn)
    _assert_fully_encrypted(conn, "extraction_candidates", "fields_json")


def downgrade() -> None:
    conn = op.get_bind()

    _decrypt_messages(conn)
    _decrypt_candidate_fields(conn)

    if conn.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "ALTER TABLE extraction_candidates "
                "ALTER COLUMN fields_json TYPE JSONB USING fields_json::jsonb"
            )
        )
    else:
        with op.batch_alter_table("extraction_candidates", schema=None) as batch:
            batch.alter_column("fields_json", type_=sa.JSON(), existing_nullable=False)
