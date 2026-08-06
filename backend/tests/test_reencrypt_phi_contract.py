"""The staging re-encryption job is itself dangerous. These are its brakes.

It holds two keysets at once, decrypts PHI with a key committed to this
repository, and rewrites every encrypted column in the database. The incident it
repairs was caused by a job running with the wrong key and nobody noticing, so
the failure mode to design against is not "it does not work" — it is "it works
somewhere it should never have run".

Every guardrail is pinned here, plus the end-to-end repair against a real
table: classify → rewrite → verify → idempotent re-run.

All PHI-shaped strings are invented.
"""

from __future__ import annotations

import inspect
import json

import pytest
import sqlalchemy as sa
from app.core import crypto
from app.core import phi_keyscan as ks
from cryptography.fernet import Fernet, MultiFernet
from scripts import reencrypt_phi as job
from sqlalchemy.orm import Session

# Synthetic, invented — never real patient data.
PHI = (
    "Tran Thi B — Metformin 500mg",
    "Nguyen Van C — Insulin 10UI",
    "Le D — di ung Penicillin",
)


@pytest.fixture
def target_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def source_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def staged(monkeypatch, target_key, source_key):
    """A correctly configured staging invocation. Each test breaks one bit."""
    monkeypatch.setenv("MCP_ENV", "staging")
    monkeypatch.setenv("MCP_ENCRYPTION_KEYS", target_key)
    monkeypatch.setenv(job.SOURCE_KEYS_ENV, source_key)
    monkeypatch.setenv(job.CONFIRM_ENV, job.CONFIRM_VALUE)
    crypto.get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    crypto.get_settings.cache_clear()
    crypto._cipher.cache_clear()


def _last_record(capsys) -> dict:
    lines = [line for line in capsys.readouterr().out.strip().splitlines() if line]
    return json.loads(lines[-1])


# ── 1. Where it may run ─────────────────────────────────────────────────────


@pytest.mark.parametrize("env", ["prod", "production"])
def test_it_refuses_production_by_name(staged, monkeypatch, capsys, env):
    """The single most important line in the file."""
    monkeypatch.setenv("MCP_ENV", env)
    crypto.get_settings.cache_clear()
    assert job.run("dry-run") == 2
    record = _last_record(capsys)
    assert record["result"] == "refused"
    assert "production" in record["reason"]


@pytest.mark.parametrize("env", ["", "stagingg", "qa", "dev", "test"])
def test_the_environment_gate_is_an_allow_list(staged, monkeypatch, capsys, env):
    """A deny-list fails OPEN: an unset or misspelled MCP_ENV would let this
    rewrite whatever database it is pointed at. Even `dev` and `test` are
    refused — this is not a routine tool."""
    monkeypatch.setenv("MCP_ENV", env)
    crypto.get_settings.cache_clear()
    assert job.run("dry-run") == 2
    assert _last_record(capsys)["result"] == "refused"


def test_staging_with_everything_set_is_not_refused(staged, monkeypatch, capsys):
    """The guardrails must not be so tight the remediation cannot happen — an
    unusable brake gets removed rather than respected."""
    monkeypatch.setenv("MCP_DATABASE_URL", "sqlite://")
    crypto.get_settings.cache_clear()
    job.run("dry-run")
    assert _last_record(capsys)["result"] != "refused"


# ── 2. Confirmation ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value", ["", "1", "true", "yes", "REENCRYPT", "reencrypt-staging-phi"]
)
def test_it_requires_the_exact_confirmation_value(staged, monkeypatch, capsys, value):
    """Not a boolean: a value you only know from having read the runbook."""
    monkeypatch.setenv(job.CONFIRM_ENV, value)
    assert job.run("apply") == 2
    assert job.CONFIRM_ENV in _last_record(capsys)["reason"]


def test_a_missing_confirmation_refuses(staged, monkeypatch, capsys):
    monkeypatch.delenv(job.CONFIRM_ENV, raising=False)
    assert job.run("apply") == 2
    assert _last_record(capsys)["result"] == "refused"


# ── 3. Key handling ─────────────────────────────────────────────────────────


def test_a_missing_source_key_refuses_rather_than_running_with_one_key(
    staged, monkeypatch, capsys
):
    monkeypatch.delenv(job.SOURCE_KEYS_ENV, raising=False)
    assert job.run("dry-run") == 2
    assert job.SOURCE_KEYS_ENV in _last_record(capsys)["reason"]


def test_a_malformed_source_key_fails_loud_and_does_not_echo_the_key(
    staged, monkeypatch, capsys
):
    monkeypatch.setenv(job.SOURCE_KEYS_ENV, "obviously-not-a-fernet-key")
    assert job.run("dry-run") == 2
    reason = _last_record(capsys)["reason"]
    assert "malformed" in reason
    assert "obviously-not-a-fernet-key" not in reason


def test_it_refuses_when_the_source_key_is_also_a_runtime_key(
    staged, monkeypatch, capsys, target_key, source_key
):
    """The tempting non-fix: add the wrong key to MCP_ENCRYPTION_KEYS as a
    decrypt-only secondary. Every read starts working immediately — and the PHI
    stays encrypted under a key published in this repository, with the only
    signal that anything is wrong now silenced."""
    monkeypatch.setenv("MCP_ENCRYPTION_KEYS", f"{target_key},{source_key}")
    crypto.get_settings.cache_clear()
    crypto._cipher.cache_clear()
    assert job.run("dry-run") == 2
    assert "runtime keyset" in _last_record(capsys)["reason"]


def test_it_refuses_to_re_encrypt_onto_the_repository_default(
    staged, monkeypatch, capsys
):
    """Re-encrypting onto the committed key would report success and leave the
    PHI exactly as exposed. `_cipher()`'s refusal is relied on, not bypassed."""
    monkeypatch.setenv("MCP_ENCRYPTION_KEYS", crypto.repo_default_key())
    crypto.get_settings.cache_clear()
    crypto._cipher.cache_clear()
    assert job.run("apply") == 2
    assert _last_record(capsys)["result"] == "refused"


def test_the_target_cipher_comes_from_the_application_not_the_environment():
    """Rebuilding a cipher from MCP_ENCRYPTION_KEYS would also rebuild the
    chance of routing around the committed-default guard."""
    src = inspect.getsource(job.run)
    assert "crypto.active_cipher()" in src
    assert "MultiFernet" not in src


def test_no_key_material_can_reach_the_output():
    src = inspect.getsource(job)
    for banned in ("print(raw", "print(key", '"key":', "key_prefix", "key_length"):
        assert banned not in src
    # The one place a key is read, it goes straight into a cipher.
    assert 'os.environ.get(SOURCE_KEYS_ENV) or ""' in src


def test_row_references_are_hashed_not_raw_ids():
    """This output is pasted into incident evidence, and a row id is an
    identifier that joins to a patient."""
    assert "hashlib.sha256" in inspect.getsource(job.row_ref)
    assert "row_ref(" in inspect.getsource(job.apply_column)


# ── 4. Pagination and write safety ──────────────────────────────────────────


def _code_only(obj) -> str:
    """Source with comments and docstring prose removed.

    The module EXPLAINS why it does not use OFFSET, by naming it. A substring
    check that counted the explanation would fail on its own documentation —
    the same trap `test_the_production_smoke_defines_its_own_variables` calls
    out in the crypto-smoke suite.
    """
    lines = []
    in_doc = False
    for line in inspect.getsource(obj).splitlines():
        stripped = line.strip()
        if stripped.startswith(("#", "#:")):
            continue
        if stripped.startswith(('"""', "'''")):
            # A one-line docstring opens and closes on the same line.
            if len(stripped) > 3 and stripped.endswith(('"""', "'''")):
                continue
            in_doc = not in_doc
            continue
        if in_doc:
            continue
        lines.append(line)
    return "\n".join(lines)


def test_pagination_is_keyset_not_offset():
    """OFFSET re-walks a table whose ordering is shifting under the very UPDATEs
    being issued, so rows get skipped — silently, and only under load."""
    src = _code_only(job._page)
    assert "id > :cursor" in src and "ORDER BY id" in src
    assert "OFFSET" not in src.upper()


def test_no_offset_anywhere_in_the_module():
    assert "OFFSET" not in _code_only(job).upper()


def test_the_update_is_conditioned_on_the_value_that_was_read():
    """Otherwise a row written between the read and the write is clobbered with
    a re-encryption of a value that no longer exists."""
    src = inspect.getsource(job.apply_column)
    assert "AND {column} = :old" in src
    assert "updated != 1" in src


def test_every_rewrite_is_read_back_and_verified():
    src = inspect.getsource(job.apply_column)
    assert "SELECT {column} FROM {table} WHERE id = :id" in src
    assert "check.is_healthy" in src
    assert "verified += 1" in src


def test_a_verify_failure_rolls_back_and_stops():
    """A rewrite path that can produce one wrong value must not be allowed to
    produce a thousand more."""
    body = inspect.getsource(job.apply_column).split("if not check.is_healthy")[1]
    assert "session.rollback()" in body
    assert "raise" in body


def test_an_unreadable_row_is_never_rewritten():
    """There is no plaintext to write back, and overwriting it destroys what a
    restore needs."""
    src = inspect.getsource(job.apply_column)
    assert "if not res.needs_rewrite" in src
    assert src.index("if not res.needs_rewrite") < src.index("target.encrypt")


# ── 5. Modes ────────────────────────────────────────────────────────────────


def test_the_default_mode_does_not_write():
    """A missing argument must not start rewriting a database."""
    import run_reencrypt_phi

    assert '"dry-run"' in inspect.getsource(run_reencrypt_phi.main)


def test_the_entrypoint_takes_no_dash_prefixed_arguments():
    """`az containerapp job --args` drops the whole list at the first `-` token
    and the job is then never created — a failure indistinguishable in the log
    from the job itself failing."""
    import run_reencrypt_phi

    code = "\n".join(
        line
        for line in inspect.getsource(run_reencrypt_phi).splitlines()
        if not line.strip().startswith(("#", '"""', "--args", "`"))
    )
    for banned in ("add_argument", "ArgumentParser"):
        assert banned not in code


def test_an_unknown_mode_refuses(staged, capsys):
    assert job.run("delete-everything") == 2
    assert "unknown_mode" in _last_record(capsys)["reason"]


def test_dry_run_makes_no_writes():
    src = inspect.getsource(job.scan_column)
    for write in ("UPDATE ", "INSERT ", "DELETE ", "commit("):
        assert write not in src


# ── 6. End to end, against a real table ─────────────────────────────────────


COLUMN = ks.EncryptedColumn(
    table="notifications", column="body", pk="id",
    kind="EncryptedString", on_decrypt_failure="raise", nullable=False,
)


def _table(rows: list[tuple[str, str | None]]):
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    with engine.begin() as conn:
        conn.execute(
            sa.text("CREATE TABLE notifications (id TEXT PRIMARY KEY, body TEXT)")
        )
        for row_id, body in rows:
            conn.execute(
                sa.text("INSERT INTO notifications VALUES (:i, :b)"),
                {"i": row_id, "b": body},
            )
    return engine


@pytest.fixture
def wrong_key_table(target_key, source_key):
    """A table in the state the migration left staging in: rows under the source
    key, plus one healthy, one plaintext, one unreadable, one NULL."""
    target = MultiFernet([Fernet(target_key.encode())])
    source = MultiFernet([Fernet(source_key.encode())])
    stranger = MultiFernet([Fernet(Fernet.generate_key())])
    engine = _table([
        ("r1", source.encrypt(PHI[0].encode()).decode()),
        ("r2", source.encrypt(PHI[1].encode()).decode()),
        ("r3", target.encrypt(PHI[2].encode()).decode()),
        ("r4", "legacy plaintext note"),
        ("r5", stranger.encrypt(b"lost").decode()),
        ("r6", None),
    ])
    return engine, target, source


def test_a_dry_run_counts_the_damage_without_touching_it(wrong_key_table):
    engine, target, source = wrong_key_table
    with Session(engine) as session:
        result = job.scan_column(session, COLUMN, target=target, source=source, batch=2)

    assert result.scanned == 5  # the NULL row is not scanned
    assert result.counts[ks.CLASS_SOURCE] == 2
    assert result.counts[ks.CLASS_TARGET] == 1
    assert result.counts[ks.CLASS_PLAINTEXT] == 1
    assert result.counts[ks.CLASS_UNREADABLE] == 1
    assert result.rewritten == 0
    assert result.checksum, "no PHI-free checksum was produced for the evidence"

    with engine.begin() as conn:
        still = conn.execute(
            sa.text("SELECT body FROM notifications WHERE id='r1'")
        ).scalar()
    assert source.decrypt(still.encode()).decode() == PHI[0]


def test_apply_repairs_the_wrong_key_rows_and_leaves_the_unreadable_one(wrong_key_table):
    engine, target, source = wrong_key_table
    with Session(engine) as session:
        result = job.apply_column(session, COLUMN, target=target, source=source, batch=2)

    assert result.rewritten == 3  # 2 source-key + 1 plaintext
    assert result.verified == 3
    assert result.unavailable == "rows_not_remediated:1"  # the unreadable row

    with engine.begin() as conn:
        for row_id, expected in (("r1", PHI[0]), ("r2", PHI[1]), ("r3", PHI[2])):
            stored = conn.execute(
                sa.text("SELECT body FROM notifications WHERE id=:i"), {"i": row_id}
            ).scalar()
            assert target.decrypt(stored.encode()).decode() == expected
        lost = conn.execute(
            sa.text("SELECT body FROM notifications WHERE id='r5'")
        ).scalar()
    assert ks.resolve(lost, target=target, source=source).classification == (
        ks.CLASS_UNREADABLE
    ), "an unreadable row was modified"


def test_apply_is_idempotent(wrong_key_table):
    """Restart-safety in practice: it resumes by finding what is still wrong,
    not by remembering where it stopped."""
    engine, target, source = wrong_key_table
    with Session(engine) as session:
        job.apply_column(session, COLUMN, target=target, source=source, batch=2)
    with Session(engine) as session:
        second = job.apply_column(session, COLUMN, target=target, source=source, batch=2)

    assert second.rewritten == 0, "a healthy row was rewritten again"
    assert second.counts[ks.CLASS_TARGET] == 4


def test_apply_normalises_a_double_encrypted_row(target_key, source_key):
    """`source(target(phi))` — what the migration did to a column the app had
    already encrypted. It must come out singly wrapped under the target key."""
    target = MultiFernet([Fernet(target_key.encode())])
    source = MultiFernet([Fernet(source_key.encode())])
    doubled = source.encrypt(target.encrypt(PHI[0].encode())).decode()
    engine = _table([("r1", doubled)])

    with Session(engine) as session:
        result = job.apply_column(session, COLUMN, target=target, source=source, batch=10)
    assert result.rewritten == 1

    with engine.begin() as conn:
        stored = conn.execute(sa.text("SELECT body FROM notifications")).scalar()
    res = ks.resolve(stored, target=target, source=None)
    assert res.is_healthy and res.layers == 1
    assert res.plaintext == PHI[0]


# ── 7. The undo, executed ───────────────────────────────────────────────────
#
# Staging Postgres is Burstable, and Azure refuses customer on-demand backups on
# those outright — verified against the live server:
#
#     (CustomerOnDemandBackupCannotBePerformedOnBurstableServer)
#
# PITR covers catastrophic loss but restores to a NEW server. The surgical undo
# is the ciphertext snapshot, and it only counts as a backup if the restore has
# actually been run. These run it.


def test_the_snapshot_copies_every_ciphertext_value_without_decrypting(wrong_key_table):
    engine, target, source = wrong_key_table
    with Session(engine) as session:
        result = job.snapshot_column(session, COLUMN)

    assert result.scanned == 5  # every non-NULL row
    assert result.checksum, "no checksum recorded for the evidence"
    with engine.begin() as conn:
        copied = conn.execute(
            sa.text(f"SELECT id, body FROM {job.snapshot_name(COLUMN)} ORDER BY id")
        ).all()
        live = conn.execute(
            sa.text("SELECT id, body FROM notifications WHERE body IS NOT NULL ORDER BY id")
        ).all()
    assert copied == live, "the snapshot is not byte-identical to the live column"


def test_a_second_snapshot_refuses_rather_than_overwriting_the_first(wrong_key_table):
    """Re-running part-way through a remediation would capture the HALF-REPAIRED
    state and replace the only copy of the original — destroying the undo at the
    exact moment it is most likely to be needed."""
    engine, _target, _source = wrong_key_table
    with Session(engine) as session:
        job.snapshot_column(session, COLUMN)
        second = job.snapshot_column(session, COLUMN)
    assert second.unavailable == "snapshot_already_exists"
    assert second.rewritten == 0


def test_verify_snapshot_passes_before_apply_and_fails_after(wrong_key_table):
    """It compares the snapshot against the LIVE column, so it is only
    meaningful before the rewrite — which is exactly when it must be run."""
    engine, target, source = wrong_key_table
    with Session(engine) as session:
        job.snapshot_column(session, COLUMN)
        before = job.verify_snapshot_column(session, COLUMN)
    assert before.unavailable is None
    assert before.verified == 5

    with Session(engine) as session:
        job.apply_column(session, COLUMN, target=target, source=source, batch=10)
        after = job.verify_snapshot_column(session, COLUMN)
    assert after.unavailable == "ciphertext_digest_mismatch"


def test_verify_snapshot_fails_loud_when_there_is_no_snapshot(wrong_key_table):
    """"No backup" must never read as "backup fine"."""
    engine, _t, _s = wrong_key_table
    with Session(engine) as session:
        assert job.verify_snapshot_column(session, COLUMN).unavailable == "snapshot_missing"


def test_the_restore_puts_the_original_ciphertext_back_byte_for_byte(wrong_key_table):
    """The whole remediation is only safe because this works. Asserted, not
    assumed."""
    engine, target, source = wrong_key_table
    with engine.begin() as conn:
        original = conn.execute(
            sa.text("SELECT id, body FROM notifications ORDER BY id")
        ).all()

    with Session(engine) as session:
        job.snapshot_column(session, COLUMN)
        job.apply_column(session, COLUMN, target=target, source=source, batch=2)

    with engine.begin() as conn:
        changed = conn.execute(
            sa.text("SELECT id, body FROM notifications ORDER BY id")
        ).all()
    assert changed != original, "apply did not actually change anything to restore"

    with Session(engine) as session:
        restored = job.restore_snapshot_column(session, COLUMN)
    assert restored.rewritten == 5

    with engine.begin() as conn:
        back = conn.execute(sa.text("SELECT id, body FROM notifications ORDER BY id")).all()
    assert back == original, "the restore did not reproduce the original ciphertext"
    # And the restored rows read under the SOURCE key again — i.e. genuinely the
    # pre-remediation state, not a re-encryption dressed up as one.
    assert source.decrypt(dict(back)["r1"].encode()).decode() == PHI[0]


def test_the_restore_does_not_resurrect_a_row_deleted_after_the_snapshot(wrong_key_table):
    """Putting a deleted patient record back is not a restore."""
    engine, _t, _s = wrong_key_table
    with Session(engine) as session:
        job.snapshot_column(session, COLUMN)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM notifications WHERE id='r2'"))
    with Session(engine) as session:
        result = job.restore_snapshot_column(session, COLUMN)
    assert result.rewritten == 4
    assert result.unavailable == "rows_absent_from_live_table:1"
    with engine.begin() as conn:
        assert conn.execute(
            sa.text("SELECT count(*) FROM notifications WHERE id='r2'")
        ).scalar() == 0


def test_snapshot_tables_are_not_themselves_scanned_as_phi_columns():
    """They hold ciphertext keyed by id and would otherwise be walked, doubling
    the work and reporting the backup's rows as damage."""
    from app.core import phi_keyscan as keyscan

    assert not any(
        c.table.startswith(job.SNAPSHOT_PREFIX) for c in keyscan.encrypted_columns()
    )


def test_every_mode_is_reachable_and_unknown_ones_are_not():
    """`dry-run` and `final-scan` deliberately share the read-only scan path and
    differ only in verdict, so they reach it through the `else` branch. The
    three that WRITE must each be dispatched by name — a write mode that fell
    through to the default would silently do something other than its name."""
    assert set(job.MODES) == {
        "dry-run", "snapshot", "verify-snapshot", "apply", "final-scan",
        "restore-snapshot",
    }
    dispatch = inspect.getsource(job.run)
    for mode in ("apply", "snapshot", "verify-snapshot", "restore-snapshot"):
        assert f'mode == "{mode}"' in dispatch, f"{mode} is never dispatched by name"
    # And both read-only modes must reach a verdict branch of their own.
    assert 'mode == "dry-run"' in dispatch
    assert "final-scan" in dispatch


def test_pagination_covers_every_row_when_the_batch_is_smaller_than_the_table(
    target_key, source_key
):
    """The bug OFFSET would produce: rows silently skipped as the table shifts
    under the UPDATEs."""
    target = MultiFernet([Fernet(target_key.encode())])
    source = MultiFernet([Fernet(source_key.encode())])
    engine = _table([
        (f"r{i:03d}", source.encrypt(f"note {i}".encode()).decode()) for i in range(37)
    ])

    with Session(engine) as session:
        result = job.apply_column(session, COLUMN, target=target, source=source, batch=5)
    assert result.scanned == 37
    assert result.rewritten == 37

    with Session(engine) as session:
        after = job.scan_column(session, COLUMN, target=target, source=source, batch=5)
    assert after.counts[ks.CLASS_TARGET] == 37
    assert after.counts[ks.CLASS_SOURCE] == 0
