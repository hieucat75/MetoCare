"""SEC-F11 (unit level) — PHI columns declare encryption and fail loud.

The full behaviour (backfill, ciphertext at rest, downgrade, wrong-key refusal)
is covered against real PostgreSQL in
tests/integration/test_secf11_phi_encryption.py — SQLite cannot model the
JSONB -> TEXT conversion. This file keeps the fast structural assertions.

Original note:

`MetoMessage.content` was a plaintext `Text` column while every other free-text
PHI column in the platform — including the *older* AI conversation model
(`models/ai.py`) and OCR raw text — uses `EncryptedString`. Nothing queries or
indexes `content` by value (reads/writes only), so switching the type is safe.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from app.core.crypto import EncryptedString, is_fernet_token
from app.models.meto import MetoConversation, MetoMessage
from sqlalchemy import text

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATION_REVISION = "j4_m9_secf11_phi_encryption"


def test_content_column_uses_encrypted_string():
    col = MetoMessage.__table__.c.content
    assert isinstance(col.type, EncryptedString)


def test_content_is_ciphertext_at_rest_and_plaintext_through_the_orm(db, patient):
    phi = "Tôi bị đau ngực khi leo cầu thang, HbA1c 8.9"
    conv = MetoConversation(user_id=patient["user_id"], status="active")
    db.add(conv)
    db.flush()
    msg = MetoMessage(conversation_id=conv.id, role="user", content=phi)
    db.add(msg)
    db.commit()

    raw = db.execute(
        text("SELECT content FROM meto_messages WHERE id = :id"), {"id": msg.id}
    ).scalar_one()
    assert phi not in raw
    assert is_fernet_token(raw)

    db.expire_all()
    assert db.get(MetoMessage, msg.id).content == phi

    db.delete(db.get(MetoMessage, msg.id))
    db.delete(db.get(MetoConversation, conv.id))
    db.commit()


def _alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["MCP_DATABASE_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_alembic_has_exactly_one_head():
    out = _alembic(["heads"], "sqlite:///:memory:")
    assert out.returncode == 0, out.stderr
    heads = [ln for ln in out.stdout.strip().splitlines() if ln.strip()]
    assert len(heads) == 1, f"expected a single alembic head, got: {heads}"


def test_migration_upgrades_and_downgrades_cleanly(tmp_path):
    url = f"sqlite:///{tmp_path}/enc.sqlite3"
    up = _alembic(["upgrade", "head"], url)
    assert up.returncode == 0, up.stderr
    current = _alembic(["current"], url)
    assert MIGRATION_REVISION in current.stdout, current.stdout

    down = _alembic(["downgrade", "-1"], url)
    assert down.returncode == 0, down.stderr
    back_up = _alembic(["upgrade", "head"], url)
    assert back_up.returncode == 0, back_up.stderr


def test_content_fails_loud_on_undecryptable_ciphertext():
    """`content` is NOT NULL and the response schema types it as a non-Optional
    str, so a silent None would violate the contract and crash serialization.
    core/crypto.py documents "raise" as REQUIRED for non-nullable columns."""
    assert MetoMessage.__table__.c.content.type.on_decrypt_failure == "raise"


def test_extraction_candidate_fields_json_is_encrypted_and_fails_loud():
    """SEC-F11 also covers the OCR candidate fields — extracted drug names,
    strengths, doses and diagnosis text — which were plaintext JSONB while the
    page text they came from was already encrypted."""
    from app.core.crypto import EncryptedJSON
    from app.models.medical_document import ExtractionCandidate

    col = ExtractionCandidate.__table__.c.fields_json
    assert isinstance(col.type, EncryptedJSON)
    assert col.type.on_decrypt_failure == "raise"
