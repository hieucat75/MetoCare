"""P1-7 — three-state proof: correct key passes, wrong key FAILS, restored passes.

Needs a real database: the mis-rotation detector reads rows written by an EARLIER
deploy, which is the whole point. A round-trip alone would pass with any
self-consistent key, including a freshly generated wrong one — so a same-process
test could not tell a correct key from a wrong one.

All PHI-shaped strings are invented. No real patient data appears here.
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


def _smoke(url: str, key: str, **extra_env: str) -> subprocess.CompletedProcess:
    env = dict(
        os.environ,
        MCP_DATABASE_URL=url,
        MCP_ENCRYPTION_KEYS=key,
        MCP_ENV="staging",
        **extra_env,
    )
    return subprocess.run(
        [sys.executable, "-m", "scripts.crypto_smoke"],
        cwd=BACKEND_ROOT, env=env, capture_output=True, text=True,
    )


def _summary(run: subprocess.CompletedProcess) -> dict:
    """The LAST JSON line — the aggregate verdict.

    The per-entity failure lines come first and carry the same keys, so picking
    the first match would assert against one column while claiming to describe
    the run.
    """
    lines = [line for line in run.stdout.strip().splitlines() if line.startswith("{")]
    assert lines, f"the smoke emitted no JSON:\n{run.stdout}\n{run.stderr}"
    return json.loads(lines[-1])


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
    assert "ciphertext_unreadable_rows" in r.stdout


def test_a_wrong_key_is_never_reported_as_zero_legacy_impact(deployed_db):
    """The 2026-08-06 misreport, against a real database.

    The old scan raised on the first bad row, so the counter it only incremented
    on success stayed at zero and the summary read::

        {"entities_checked":2,"failures":4,"legacy_rows_total":0}

    beside four unreadable columns. The number an on-call reads as blast radius
    fell to zero exactly when every row was broken. Both rows the fixture wrote
    must now be COUNTED.
    """
    url, _key = deployed_db
    summary = _summary(_smoke(url, _fernet_key()))

    assert summary["result"] == "fail"
    assert summary["legacy_rows_total"] > 0, (
        "the affected-row count collapsed to zero while rows were unreadable"
    )
    assert summary["ciphertext_unreadable_rows"] >= 2, summary
    assert summary["ciphertext_target_key_rows"] == 0
    # Unreadable is not plaintext, and not a wrong-but-known key. Each sends the
    # responder somewhere different.
    assert summary["plaintext_legacy_rows"] == 0


def test_the_repository_default_key_is_named_rather_than_called_corrupt(deployed_db):
    """The incident's actual state: rows encrypted with the key committed to
    this repository. "undecryptable" would send the responder to a restore; the
    correct response is re-encryption, and only naming the key tells them
    apart."""
    url, key = deployed_db
    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
    try:
        from app.core.crypto import repo_default_key
        from cryptography.fernet import Fernet

        default = Fernet(repo_default_key().encode())
        with engine.begin() as c:
            c.execute(
                sa.text("UPDATE notifications SET body = :b WHERE id NOT LIKE 'cs-%'"),
                {"b": default.encrypt(LEGACY_BODY.encode()).decode()},
            )
    finally:
        engine.dispose()

    summary = _summary(_smoke(url, key))
    assert summary["result"] == "fail"
    assert summary["ciphertext_source_key_rows"] >= 1, summary
    assert summary["legacy_rows_by_class"]["notifications.body"][
        "ciphertext_source_key_rows"
    ] >= 1


def test_a_passing_run_proves_it_actually_read_something(deployed_db):
    """A pass with every counter at zero means the scan verified nothing — which
    is why `no_legacy_rows_to_verify` is itself a failure."""
    url, key = deployed_db
    summary = _summary(_smoke(url, key))
    assert summary["result"] == "pass"
    assert summary["ciphertext_target_key_rows"] > 0, summary
    assert summary["ciphertext_source_key_rows"] == 0
    assert summary["ciphertext_unreadable_rows"] == 0


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
        for table in (
            "notifications", "meto_messages", "users", "meto_conversations",
            # The extended round-trips scaffold these too. A leaked patient
            # profile or document row in production would be exactly the
            # "synthetic business record" this design promised not to create.
            "patient_profiles", "medication_statements", "medical_documents",
            "document_extractions", "extraction_candidates",
        ):
            left = c.execute(
                sa.text(f"SELECT count(*) FROM {table} WHERE id LIKE 'cs-%'")  # noqa: S608
            ).scalar()
            assert left == 0, f"{table} kept {left} sentinel row(s)"
    engine.dispose()


# ── Empty-database verdict (MCP_CRYPTO_SMOKE_ALLOW_EMPTY) ────────────────────
#
# The four cases of the decision table, against a database migrated to head and
# holding nothing — the state production was measured in before its first deploy.


@pytest.fixture
def empty_db():
    """Migrated to head, zero rows. No user, no profile, no PHI of any kind."""
    admin = sa.create_engine(POSTGRES_TEST_URL, isolation_level="AUTOCOMMIT")
    name = f"csmoke_empty_{uuid.uuid4().hex[:12]}"
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
    try:
        yield url, key
    finally:
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


def test_empty_database_without_the_flag_still_fails(empty_db):
    """Case B — the default. Unchanged behaviour, and the reason code is the
    same one every existing runbook and dashboard already greps for."""
    url, key = empty_db
    r = _smoke(url, key)

    assert r.returncode == 1, "an unverified empty database reported healthy"
    summary = _summary(r)
    assert summary["result"] == "fail"
    assert summary["allow_empty_enabled"] is False
    assert "no_legacy_rows_to_verify" in r.stdout


def test_empty_database_with_the_flag_returns_its_own_verdict(empty_db):
    """Case C — passes, but never as the ordinary `pass`.

    An operator reading `pass` must be able to assume real stored rows were
    decrypted. On an empty database none were, so the verdict says so in its own
    name rather than leaving it to be inferred from a zero.
    """
    url, key = empty_db
    r = _smoke(url, key, MCP_CRYPTO_SMOKE_ALLOW_EMPTY="1")

    assert r.returncode == 0, r.stdout + r.stderr
    summary = _summary(r)
    assert summary["result"] == "pass_empty_database"
    assert summary["mode"] == "empty_database"
    assert summary["failures"] == 0
    assert summary["legacy_rows_total"] == 0
    # The crypto path was still exercised — that is what makes this a verdict
    # rather than a skip.
    assert summary["synthetic_roundtrip_entities"], "nothing was round-tripped"
    assert '"result": "pass"' not in r.stdout, "emitted the ordinary pass as well"


def test_the_empty_verdict_still_covers_every_required_entity(empty_db):
    """The round-trip set the owner named: both notification columns, the Meto
    message, a medication raw field, and the extraction candidate JSON."""
    url, key = empty_db
    summary = _summary(_smoke(url, key, MCP_CRYPTO_SMOKE_ALLOW_EMPTY="1"))

    assert set(summary["synthetic_roundtrip_entities"]) >= {
        "notification.title",
        "notification.body",
        "meto_message.content",
        "medication_statement.raw_drug_name",
        "extraction_candidate.fields_json",
    }


def test_empty_plus_flag_still_fails_on_a_malformed_key(empty_db):
    """The flag waives the legacy-row requirement, nothing else. A key that
    cannot complete a round-trip fails whatever the population is."""
    url, _key = empty_db
    r = _smoke(url, "not-a-valid-fernet-key", MCP_CRYPTO_SMOKE_ALLOW_EMPTY="1")

    assert r.returncode != 0, "a malformed key passed under the empty-database flag"
    assert '"result": "pass_empty_database"' not in r.stdout


def test_an_empty_database_cannot_detect_a_wrong_but_well_formed_key(empty_db):
    """The limitation the verdict exists to NAME, pinned so nobody later reads
    `pass_empty_database` as the same assurance as `pass`.

    A wrong-but-well-formed key round-trips perfectly: it encrypts and decrypts
    its own sentinels. The only thing that can catch it is reading a row an
    EARLIER deploy wrote, and an empty database has none. So this passes — and
    it must pass under a verdict that says so in its own name, never under a
    bare `pass`.
    """
    url, _key = empty_db
    r = _smoke(url, _fernet_key(), MCP_CRYPTO_SMOKE_ALLOW_EMPTY="1")

    summary = _summary(r)
    assert summary["result"] == "pass_empty_database"
    assert summary["mode"] == "empty_database"
    # The distinction that makes the verdict honest.
    assert summary["legacy_rows_total"] == 0
    assert '"result": "pass"' not in r.stdout


def test_empty_plus_flag_still_fails_on_a_missing_key(empty_db):
    url, _key = empty_db
    r = _smoke(url, "", MCP_CRYPTO_SMOKE_ALLOW_EMPTY="1")

    assert r.returncode == 1
    assert "missing_key" in r.stdout
    assert "pass_empty_database" not in r.stdout


def test_a_populated_database_ignores_the_flag(deployed_db):
    """Case A — the flag is not consulted when rows exist, so it can never turn a
    populated database into an unverified one."""
    url, key = deployed_db
    summary = _summary(_smoke(url, key, MCP_CRYPTO_SMOKE_ALLOW_EMPTY="1"))

    assert summary["result"] == "pass"
    assert summary["mode"] == "legacy_population"
    assert summary["legacy_rows_total"] > 0


def test_a_populated_database_with_a_wrong_key_fails_even_with_the_flag(deployed_db):
    """The dangerous combination: someone sets the flag believing it is harmless,
    on a database that DOES hold rows, under a mis-rotated key."""
    url, _key = deployed_db
    r = _smoke(url, _fernet_key(), MCP_CRYPTO_SMOKE_ALLOW_EMPTY="1")

    assert r.returncode == 1, "the flag suppressed a real mis-rotation"
    assert '"result": "fail"' in r.stdout
    assert "ciphertext_unreadable_rows" in r.stdout


def test_rows_present_but_unsampled_are_never_called_empty(empty_db):
    """Case D — the census disagrees with the sample.

    A user row with no PHI values leaves every encrypted column empty, so the
    sample sees zero. That is a database with accounts, not an empty one, and it
    must not receive the empty-database verdict.
    """
    url, key = empty_db
    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
    uid = str(uuid.uuid4())
    with engine.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO users (id,email,password_hash,role,is_active,mfa_enabled,"
                "created_at,updated_at) VALUES (:i,:e,'!','PATIENT',true,false,now(),now())"
            ),
            {"i": uid, "e": f"{uid}@t.invalid"},
        )
    engine.dispose()

    r = _smoke(url, key, MCP_CRYPTO_SMOKE_ALLOW_EMPTY="1")

    assert r.returncode == 1, "a database with accounts was called empty"
    assert "sampled_zero_but_census_found_rows" in r.stdout
    assert "pass_empty_database" not in r.stdout
