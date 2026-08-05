"""P1-7 — three-state proof: correct key passes, wrong key FAILS, restored passes.

Needs a real database: the mis-rotation detector reads rows written by an EARLIER
deploy, which is the whole point. A round-trip alone would pass with any
self-consistent key, including a freshly generated wrong one — so a same-process
test could not tell a correct key from a wrong one.

All PHI-shaped strings are invented. No real patient data appears here.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
import sqlalchemy as sa

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Synthetic, invented — never real patient data.
LEGACY_TITLE = "Nhac uong thuoc"
LEGACY_BODY = "Den gio uong Metformin 500mg"

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


def _smoke(url: str, key: str) -> subprocess.CompletedProcess:
    env = dict(
        os.environ,
        MCP_DATABASE_URL=url,
        MCP_ENCRYPTION_KEYS=key,
        MCP_ENV="staging",
    )
    return subprocess.run(
        [sys.executable, "-m", "scripts.crypto_smoke"],
        cwd=BACKEND_ROOT, env=env, capture_output=True, text=True,
    )


@pytest.fixture
def deployed_db():
    """A database migrated to head with PHI written under a KNOWN key — i.e. what
    an earlier deploy leaves behind."""
    admin = sa.create_engine(POSTGRES_TEST_URL, isolation_level="AUTOCOMMIT")
    name = f"csmoke_{uuid.uuid4().hex[:12]}"
    with admin.connect() as c:
        c.execute(sa.text(f'CREATE DATABASE "{name}"'))
    url = POSTGRES_TEST_URL.rsplit("/", 1)[0] + f"/{name}"
    key = _fernet_key()

    up = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=dict(os.environ, MCP_DATABASE_URL=url, MCP_ENCRYPTION_KEYS=key),
        capture_output=True, text=True,
    )
    assert up.returncode == 0, up.stderr

    os.environ["MCP_ENCRYPTION_KEYS"] = key
    from app.core.config import get_settings
    from app.core.crypto import _cipher, encrypt

    get_settings.cache_clear()
    _cipher.cache_clear()

    engine = sa.create_engine(url)
    uid = str(uuid.uuid4())
    with engine.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO users (id,email,password_hash,role,is_active,mfa_enabled,"
                "created_at,updated_at) VALUES (:i,:e,'!','PATIENT',true,false,now(),now())"
            ),
            {"i": uid, "e": f"{uid}@t.invalid"},
        )
        c.execute(
            sa.text(
                "INSERT INTO notifications (id,user_id,type,title,body,is_read,created_at)"
                " VALUES ('legacy1',:u,'medication_reminder',:t,:b,false,now())"
            ),
            {"u": uid, "t": encrypt(LEGACY_TITLE), "b": encrypt(LEGACY_BODY)},
        )
    try:
        yield url, key
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


def test_correct_key_passes(deployed_db):
    url, key = deployed_db
    r = _smoke(url, key)
    assert r.returncode == 0, r.stdout + r.stderr
    assert '"result": "pass"' in r.stdout


def test_a_wrong_but_well_formed_key_fails_the_deploy(deployed_db):
    """The whole point. Boot validation accepts this key and /health passes; the
    smoke must not."""
    url, _key = deployed_db
    wrong = _fernet_key()

    from app.core.config import Settings

    os.environ["MCP_ENCRYPTION_KEYS"] = wrong
    Settings().validate_required_env_vars()  # boot ACCEPTS it — well-formed

    r = _smoke(url, wrong)
    assert r.returncode == 1, "a wrong key produced a healthy verdict"
    assert '"result": "fail"' in r.stdout
    assert "legacy_row_undecryptable" in r.stdout


def test_restoring_the_correct_key_passes_again(deployed_db):
    url, key = deployed_db
    assert _smoke(url, _fernet_key()).returncode == 1
    r = _smoke(url, key)
    assert r.returncode == 0, r.stdout + r.stderr
    assert '"result": "pass"' in r.stdout


def test_a_missing_key_fails(deployed_db):
    url, _key = deployed_db
    r = _smoke(url, "")
    assert r.returncode == 1
    assert "missing_key" in r.stdout


def test_the_smoke_leaks_no_phi_and_no_key(deployed_db):
    """A verification step that logs what it verifies defeats the encryption."""
    url, key = deployed_db
    for k in (key, _fernet_key()):
        out = _smoke(url, k)
        combined = out.stdout + out.stderr
        for needle in (LEGACY_TITLE, LEGACY_BODY, k):
            assert needle not in combined, f"{needle[:12]!r}... leaked into output"


def test_the_smoke_leaves_no_sentinel_rows_behind(deployed_db):
    url, key = deployed_db
    _smoke(url, key)
    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
    with engine.connect() as c:
        for table in ("notifications", "meto_messages", "users", "meto_conversations"):
            left = c.execute(
                sa.text(f"SELECT count(*) FROM {table} WHERE id LIKE 'cs-%'")  # noqa: S608
            ).scalar()
            assert left == 0, f"{table} kept {left} sentinel row(s)"
    engine.dispose()
