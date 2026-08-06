"""P1-5 — the PHI surfaces SEC-F11 left readable are encrypted at rest.

Real-PostgreSQL integration test. SQLite cannot cover it: two columns change type
JSONB → TEXT, `#>> '{}'` is Postgres-only, `notifications.title` widens from
VARCHAR(256) (ciphertext does not fit), and the ordering bug this guards against
— writing a Fernet token into a still-`jsonb` column raises `invalid input syntax
for type json` — is invisible on SQLite, whose JSON is TEXT underneath.

Activation: only runs when POSTGRES_TEST_URL is set.

All PHI-shaped strings below are invented. No real patient data appears here.

Covers:
  * ciphertext at rest for every one of the nine columns
  * no plaintext PHI recoverable by a raw SQL reader
  * values round-trip unchanged
  * a NEW ORM write is encrypted, not just the backfill
  * idempotent backfill (re-running does not double-encrypt)
  * upgrade → downgrade → re-upgrade restores values exactly
  * a wrong-key downgrade REFUSES rather than destroying data
  * no PHI in migration output
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid

import pytest
import sqlalchemy as sa

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REVISION = "j4_m10_p15_residual_phi"
PARENT = "j4_m9_secf11_phi_encryption"

# Synthetic PHI-shaped strings — invented, never real patient data.
DRUG_PHI = "Metformin 500mg"
PRESCRIBER_PHI = "BS. Nguyen Van A"
NOTIF_PHI = "Den gio uong Metformin 500mg"
NOTIF_TITLE = "Den gio uong thuoc"
CORRECTION_PHI = {"test_name": "HDL Cholesterol", "value": 1.2}

# Every (table, column) the migration encrypts.
ENCRYPTED_COLUMNS = (
    ("medication_statements", "raw_drug_name"),
    ("medication_statements", "normalized_name"),
    ("medication_statements", "raw_dose"),
    ("medication_statements", "raw_frequency"),
    ("medication_statements", "raw_prescriber"),
    ("notifications", "title"),
    ("notifications", "body"),
    ("extraction_candidates", "corrections_json"),
    ("medication_statements", "payload_snapshot"),
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not POSTGRES_TEST_URL,
        reason="POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests.",
    ),
]


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


def _seed(engine) -> None:
    """Plaintext rows on the PARENT revision, so the backfill has real work."""
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
        # >1 batch (_BATCH_SIZE=500) so keyset pagination is genuinely exercised.
        c.execute(
            sa.text(
                "INSERT INTO notifications (id,user_id,type,title,body,is_read,created_at)"
                " VALUES (:i,'u1','medication_reminder',:t,:b,false,now())"
            ),
            [
                {"i": f"n{i:05d}", "t": NOTIF_TITLE, "b": f"{NOTIF_PHI} #{i}"}
                for i in range(600)
            ],
        )
        c.execute(
            sa.text(
                "INSERT INTO medication_statements (id,patient_id,source_type,"
                "assertion_type,raw_drug_name,normalized_name,raw_dose,raw_frequency,"
                "raw_prescriber,payload_snapshot,statement_status,created_at) "
                "VALUES (:i,'p1','ocr','reported',:d,:n,'500mg','2 lan/ngay',:pr,"
                "CAST(:s AS jsonb),'active',now())"
            ),
            [
                {
                    "i": f"s{i:05d}",
                    "d": f"{DRUG_PHI} #{i}",
                    "n": "metformin",
                    "pr": PRESCRIBER_PHI,
                    "s": json.dumps({"drug": DRUG_PHI, "idx": i}),
                }
                for i in range(600)
            ],
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
                "INSERT INTO extraction_candidates (id,extraction_id,document_id,"
                "patient_id,candidate_type,ordinal,fields_json,corrections_json,"
                "dedupe_key,status,created_at,updated_at) VALUES "
                "(:i,'e1','d1','p1','lab_result',:o,:f,CAST(:cr AS jsonb),:d,"
                "'needs_review',now(),now())"
            ),
            [
                {
                    "i": f"k{i:05d}",
                    "o": i,
                    # fields_json is already TEXT at PARENT; its content is not
                    # what this test is about.
                    "f": json.dumps({"x": i}),
                    "cr": json.dumps(CORRECTION_PHI),
                    "d": f"dk{i}",
                }
                for i in range(600)
            ],
        )


@pytest.fixture
def scratch_db():
    """Throwaway database at the revision BEFORE P1-5, seeded with plaintext."""
    admin = sa.create_engine(POSTGRES_TEST_URL, isolation_level="AUTOCOMMIT")
    name = f"p15_{uuid.uuid4().hex[:12]}"
    with admin.connect() as c:
        c.execute(sa.text(f'CREATE DATABASE "{name}"'))

    url = POSTGRES_TEST_URL.rsplit("/", 1)[0] + f"/{name}"
    key = _fernet_key()
    up = _alembic(["upgrade", PARENT], url, key)
    assert up.returncode == 0, up.stderr

    engine = sa.create_engine(url)
    _seed(engine)
    try:
        yield url, key, engine
    finally:
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


def _raw(engine, table: str, column: str) -> list[str]:
    with engine.connect() as c:
        return [
            r[0]
            for r in c.execute(
                sa.text(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL")  # noqa: S608
            )
        ]


# ── 1. Ciphertext at rest, for every column ─────────────────────────────────


def test_every_column_is_ciphertext_at_rest(scratch_db):
    url, key, engine = scratch_db
    r = _alembic(["upgrade", REVISION], url, key)
    assert r.returncode == 0, r.stderr
    _reload_crypto(key)

    from app.core.crypto import is_fernet_token

    for table, column in ENCRYPTED_COLUMNS:
        values = _raw(engine, table, column)
        assert values, f"{table}.{column} had no rows — the test proves nothing"
        bad = [v for v in values if not is_fernet_token(v)]
        assert not bad, f"{table}.{column}: {len(bad)} row(s) still plaintext"


@pytest.mark.parametrize(
    "needle", [DRUG_PHI, PRESCRIBER_PHI, NOTIF_PHI, "HDL Cholesterol"]
)
def test_no_plaintext_phi_is_recoverable_by_a_raw_reader(scratch_db, needle):
    """The actual threat model: someone with a database dump or a read replica,
    without the application's keys."""
    url, key, engine = scratch_db
    assert _alembic(["upgrade", REVISION], url, key).returncode == 0

    for table, column in ENCRYPTED_COLUMNS:
        with engine.connect() as c:
            hits = c.execute(
                sa.text(
                    f"SELECT count(*) FROM {table} WHERE {column} LIKE :p"  # noqa: S608
                ),
                {"p": f"%{needle}%"},
            ).scalar()
        assert hits == 0, f"{needle!r} readable in {table}.{column}"


# ── 2. Values survive the round trip ────────────────────────────────────────


def test_values_round_trip(scratch_db):
    url, key, engine = scratch_db
    assert _alembic(["upgrade", REVISION], url, key).returncode == 0
    _reload_crypto(key)

    from app.core.crypto import try_decrypt

    with engine.connect() as c:
        body = c.execute(
            sa.text("SELECT body FROM notifications WHERE id = 'n00000'")
        ).scalar()
        drug = c.execute(
            sa.text("SELECT raw_drug_name FROM medication_statements WHERE id = 's00000'")
        ).scalar()
        corr = c.execute(
            sa.text("SELECT corrections_json FROM extraction_candidates WHERE id='k00000'")
        ).scalar()

    assert try_decrypt(body) == f"{NOTIF_PHI} #0"
    assert try_decrypt(drug) == f"{DRUG_PHI} #0"
    assert json.loads(try_decrypt(corr)) == CORRECTION_PHI


def test_a_new_write_through_the_orm_is_encrypted(scratch_db):
    """Not just the backfill: the TypeDecorators must cover ongoing writes, or
    the table refills with plaintext the day after the migration."""
    url, key, engine = scratch_db
    assert _alembic(["upgrade", REVISION], url, key).returncode == 0
    _reload_crypto(key)

    from app.core.crypto import is_fernet_token
    from app.models.notification import Notification
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        s.add(
            Notification(
                id="new1", user_id="u1", type="medication_reminder",
                title=NOTIF_TITLE, body="Den gio uong Atorvastatin 20mg",
            )
        )
        s.commit()

    with engine.connect() as c:
        stored = c.execute(
            sa.text("SELECT body FROM notifications WHERE id = 'new1'")
        ).scalar()
    assert is_fernet_token(stored), "a new ORM write landed in plaintext"
    assert "Atorvastatin" not in stored


# ── 3. Restart-safety and reversibility ─────────────────────────────────────


def test_backfill_is_idempotent(scratch_db):
    """A migration interrupted and re-run must not double-encrypt — the second
    pass would produce a token that decrypts to a token."""
    url, key, engine = scratch_db
    assert _alembic(["upgrade", REVISION], url, key).returncode == 0
    _reload_crypto(key)

    from app.core.crypto import try_decrypt

    before = _raw(engine, "notifications", "body")
    assert _alembic(["downgrade", PARENT], url, key).returncode == 0
    assert _alembic(["upgrade", REVISION], url, key).returncode == 0
    after = _raw(engine, "notifications", "body")

    assert len(before) == len(after)
    assert all(try_decrypt(v) is not None for v in after)
    assert all(NOTIF_PHI in try_decrypt(v) for v in after)


def test_upgrade_downgrade_upgrade_preserves_values(scratch_db):
    url, key, engine = scratch_db
    assert _alembic(["upgrade", REVISION], url, key).returncode == 0
    down = _alembic(["downgrade", PARENT], url, key)
    assert down.returncode == 0, down.stderr

    with engine.connect() as c:
        # Back to readable plaintext, and JSON columns are JSON again.
        assert (
            c.execute(sa.text("SELECT body FROM notifications WHERE id='n00000'")).scalar()
            == f"{NOTIF_PHI} #0"
        )
        assert (
            c.execute(
                sa.text(
                    "SELECT corrections_json->>'test_name' FROM extraction_candidates "
                    "WHERE id='k00000'"
                )
            ).scalar()
            == "HDL Cholesterol"
        )

    assert _alembic(["upgrade", REVISION], url, key).returncode == 0
    _reload_crypto(key)
    from app.core.crypto import try_decrypt

    with engine.connect() as c:
        again = c.execute(
            sa.text("SELECT body FROM notifications WHERE id='n00000'")
        ).scalar()
    assert try_decrypt(again) == f"{NOTIF_PHI} #0"


def test_downgrade_with_the_wrong_key_refuses_rather_than_destroying_data(scratch_db):
    """The dangerous operator error: rolling back with a rotated-away key. The
    migration must refuse, not overwrite ciphertext it cannot read."""
    url, key, engine = scratch_db
    assert _alembic(["upgrade", REVISION], url, key).returncode == 0

    wrong = _fernet_key()
    result = _alembic(["downgrade", PARENT], url, wrong)
    assert result.returncode != 0, "downgrade with the wrong key succeeded"

    _reload_crypto(key)
    from app.core.crypto import is_fernet_token, try_decrypt

    values = _raw(engine, "notifications", "body")
    assert values, "rows disappeared"
    assert all(is_fernet_token(v) for v in values), "data was overwritten"
    assert try_decrypt(values[0]) is not None, "data is no longer readable"


def test_migration_output_contains_no_phi(scratch_db):
    """A migration that logs the rows it rewrites defeats the encryption."""
    url, key, _engine = scratch_db
    r = _alembic(["upgrade", REVISION], url, key)
    combined = (r.stdout or "") + (r.stderr or "")
    for needle in (DRUG_PHI, PRESCRIBER_PHI, NOTIF_PHI, "HDL Cholesterol"):
        assert needle not in combined, f"{needle!r} leaked into migration output"
