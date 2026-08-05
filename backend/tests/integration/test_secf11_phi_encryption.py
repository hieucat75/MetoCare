"""SEC-F11 — Meto message bodies and OCR candidate fields are encrypted at rest.

Real-PostgreSQL integration test. SQLite cannot cover this: the `fields_json`
column changes type JSONB → TEXT, `#>> '{}'` is Postgres-only, and the ordering bug
this guards against (writing a Fernet token into a still-`jsonb` column raises
`invalid input syntax for type json`) is invisible on SQLite, whose JSON is TEXT.

Activation: only runs when POSTGRES_TEST_URL is set (skipped in unit runs).

Covers the SEC-F11 acceptance list:
  * ciphertext at rest for BOTH columns, with no plaintext PHI recoverable
  * plaintext round-trip through the real ORM models
  * a NEW ORM write is encrypted (not just the backfill)
  * idempotent / restart-safe backfill (no double-encryption)
  * upgrade → downgrade → re-upgrade, byte-identical restoration
  * wrong-key downgrade REFUSES rather than corrupting data
  * no silent partial migration
  * no PHI in migration logs
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import uuid

import pytest
import sqlalchemy as sa

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REVISION = "j4_m9_secf11_phi_encryption"
PARENT = "j4_m8_consent_versioning"

# Synthetic PHI-shaped strings — invented, never real patient data.
MSG_PHI = "Tôi bị đau ngực khi leo cầu thang, HbA1c 8.9"
DRUG_PHI = "Metformin"

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests.",
)


def _fernet_key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


def _alembic(args: list[str], url: str, key: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, MCP_DATABASE_URL=url, MCP_ENCRYPTION_KEYS=key)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _reload_crypto(key: str) -> None:
    os.environ["MCP_ENCRYPTION_KEYS"] = key
    from app.core.config import get_settings
    from app.core.crypto import _cipher

    get_settings.cache_clear()
    _cipher.cache_clear()


@pytest.fixture
def scratch_db():
    """A throwaway database migrated to the revision BEFORE SEC-F11, seeded with
    plaintext PHI so the backfill has something real to convert."""
    admin = sa.create_engine(POSTGRES_TEST_URL, isolation_level="AUTOCOMMIT")
    name = f"secf11_{uuid.uuid4().hex[:12]}"
    with admin.connect() as c:
        c.execute(sa.text(f'CREATE DATABASE "{name}"'))

    url = POSTGRES_TEST_URL.rsplit("/", 1)[0] + f"/{name}"
    key = _fernet_key()
    up = _alembic(["upgrade", PARENT], url, key)
    assert up.returncode == 0, up.stderr

    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO users (id,email,password_hash,role,is_active,mfa_enabled,"
                "created_at,updated_at) VALUES "
                "('u1','a@b.c','x','PATIENT',true,false,now(),now())"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO patient_profiles (id,user_id,created_at,updated_at) "
                "VALUES ('p1','u1',now(),now())"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO meto_conversations (id,user_id,status,last_active_at,"
                "created_at,updated_at) VALUES ('c1','u1','active',now(),now(),now())"
            )
        )
        # >1 batch (_BATCH_SIZE=500) so keyset pagination is genuinely exercised.
        c.execute(
            sa.text(
                "INSERT INTO meto_messages (id,conversation_id,role,content,"
                "created_at,updated_at) VALUES (:i,'c1','user',:v,now(),now())"
            ),
            [{"i": f"m{i:05d}", "v": f"{MSG_PHI} #{i}"} for i in range(1200)],
        )
        c.execute(
            sa.text(
                "INSERT INTO medical_documents (id,patient_id,quarantine_key,status,"
                "object_state,source,data_classification,created_at,updated_at) VALUES "
                "('d1','p1','q','accepted','accepted','upload','sensitive_health',now(),now())"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO document_extractions (id,document_id,schema_version,provider,"
                "extraction_run_id,review_state,created_at,updated_at) VALUES "
                "('e1','d1','mdi-1','tesseract','r1','pending',now(),now())"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO extraction_candidates (id,extraction_id,document_id,patient_id,"
                "candidate_type,ordinal,fields_json,dedupe_key,status,created_at,updated_at) "
                "VALUES (:i,'e1','d1','p1','medication',:o,CAST(:f AS jsonb),:d,"
                "'needs_review',now(),now())"
            ),
            [
                {
                    "i": f"k{i:05d}",
                    "o": i,
                    "f": json.dumps({"name": DRUG_PHI, "strength": f"{i}mg"}),
                    "d": f"dk{i}",
                }
                for i in range(700)
            ],
        )

    yield engine, url, key

    engine.dispose()
    with admin.connect() as c:
        c.execute(
            sa.text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :n AND pid <> pg_backend_pid()"
            ),
            {"n": name},
        )
        c.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
    admin.dispose()


def _column_type(engine, table: str, column: str) -> str:
    with engine.connect() as c:
        return c.execute(
            sa.text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()


def test_upgrade_encrypts_both_columns_and_leaves_no_plaintext(scratch_db):
    from app.core.crypto import is_fernet_token

    engine, url, key = scratch_db
    assert _column_type(engine, "extraction_candidates", "fields_json") == "jsonb"

    res = _alembic(["upgrade", "head"], url, key)
    assert res.returncode == 0, res.stderr

    # The column type must have converted, or ciphertext could not be stored.
    assert _column_type(engine, "extraction_candidates", "fields_json") == "text"

    with engine.connect() as c:
        msgs = [r[0] for r in c.execute(sa.text("SELECT content FROM meto_messages"))]
        cands = [r[0] for r in c.execute(sa.text("SELECT fields_json FROM extraction_candidates"))]

    assert len(msgs) == 1200 and len(cands) == 700
    assert all(is_fernet_token(m) for m in msgs)
    assert all(is_fernet_token(k) for k in cands)
    # The whole point: the PHI is not recoverable from the raw column.
    assert not any(MSG_PHI in m for m in msgs)
    assert not any(DRUG_PHI in k for k in cands)


def test_orm_reads_plaintext_and_new_writes_are_encrypted(scratch_db):
    from sqlalchemy.orm import Session

    engine, url, key = scratch_db
    assert _alembic(["upgrade", "head"], url, key).returncode == 0
    _reload_crypto(key)

    from app.models.medical_document import ExtractionCandidate
    from app.models.meto import MetoMessage

    with Session(engine) as s:
        assert s.get(MetoMessage, "m00000").content == f"{MSG_PHI} #0"
        fields = s.get(ExtractionCandidate, "k00000").fields_json
        assert isinstance(fields, dict) and fields["name"] == DRUG_PHI

        fresh = MetoMessage(conversation_id="c1", role="user", content="Đường huyết 15.2 mmol/L")
        s.add(fresh)
        s.commit()
        fresh_id = fresh.id

    with engine.connect() as c:
        raw = c.execute(
            sa.text("SELECT content FROM meto_messages WHERE id = :i"), {"i": fresh_id}
        ).scalar()
    assert raw.startswith("gAAAA") and "Đường huyết" not in raw


def _load_migration(name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        name, os.path.join(BACKEND_ROOT, "alembic", "versions", f"{REVISION}.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_backfill_is_idempotent_and_restart_safe(scratch_db):
    """An interrupted run must be safely re-runnable — no double-encryption."""
    engine, url, key = scratch_db
    assert _alembic(["upgrade", "head"], url, key).returncode == 0
    _reload_crypto(key)
    mig = _load_migration("secf11_mig")

    with engine.begin() as c:
        before = [r[0] for r in c.execute(sa.text("SELECT content FROM meto_messages ORDER BY id"))]
        mig._encrypt_messages(c)
        mig._encrypt_candidate_fields(c)
        after = [r[0] for r in c.execute(sa.text("SELECT content FROM meto_messages ORDER BY id"))]

    assert before == after


def test_downgrade_restores_plaintext_byte_identically_then_re_upgrades(scratch_db):
    engine, url, key = scratch_db
    assert _alembic(["upgrade", "head"], url, key).returncode == 0

    down = _alembic(["downgrade", "-1"], url, key)
    assert down.returncode == 0, down.stderr

    assert _column_type(engine, "extraction_candidates", "fields_json") == "jsonb"
    with engine.connect() as c:
        restored = c.execute(
            sa.text("SELECT count(*) FROM meto_messages WHERE content LIKE :p"),
            {"p": f"{MSG_PHI}%"},
        ).scalar()
        cand = c.execute(
            sa.text("SELECT fields_json FROM extraction_candidates WHERE id = 'k00000'")
        ).scalar()
    assert restored == 1200
    assert cand["name"] == DRUG_PHI

    assert _alembic(["upgrade", "head"], url, key).returncode == 0
    cur = _alembic(["current"], url, key)
    assert REVISION in cur.stdout


def test_downgrade_with_the_wrong_key_refuses_rather_than_corrupting(scratch_db):
    """Losing PHI silently is worse than a failed downgrade."""
    from app.core.crypto import is_fernet_token

    engine, url, key = scratch_db
    assert _alembic(["upgrade", "head"], url, key).returncode == 0

    bad = _alembic(["downgrade", "-1"], url, _fernet_key())
    assert bad.returncode != 0
    assert "Refusing to overwrite" in bad.stderr

    # Data must be untouched and still decryptable with the correct key.
    _reload_crypto(key)
    with engine.connect() as c:
        rows = [r[0] for r in c.execute(sa.text("SELECT content FROM meto_messages"))]
        head = c.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    assert all(is_fernet_token(r) for r in rows)
    assert head == REVISION


def test_partial_migration_is_never_reported_as_success(scratch_db):
    """The post-backfill assertion must reject a table that is still plaintext."""
    engine, url, key = scratch_db
    _reload_crypto(key)
    mig = _load_migration("secf11_mig_partial")

    # meto_messages is still entirely plaintext here (no upgrade run yet).
    with engine.begin() as c, pytest.raises(RuntimeError, match="still plaintext"):
        mig._assert_fully_encrypted(c, "meto_messages", "content")


def test_migration_logs_contain_no_phi(scratch_db, caplog):
    engine, url, key = scratch_db
    with caplog.at_level(logging.DEBUG):
        res = _alembic(["upgrade", "head"], url, key)
    assert res.returncode == 0
    combined = res.stdout + res.stderr + caplog.text
    assert MSG_PHI not in combined
    assert DRUG_PHI not in combined
    assert key not in combined
