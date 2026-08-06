"""The 2026-08-06 incident's metric bug: damage that counted itself as zero.

The post-deploy crypto smoke caught the wrong-key migration correctly, and then
reported it like this::

    {"entity":"meto_message.content","reason":"legacy_row_undecryptable","result":"fail"}
    {"entity":"extraction_candidate.fields_json","reason":"legacy_row_undecryptable",…}
    {"entity":"medication_statement.raw_drug_name","reason":"legacy_row_undecryptable",…}
    {"entity":"notification.body","reason":"legacy_row_undecryptable","result":"fail"}
    {"entities_checked":2,"failures":4,"legacy_rows_total":0}

Four columns of PHI were unreadable and the row counter said ZERO, because it
only incremented on success and the first bad row raised straight past it. The
number an on-call reads as blast radius went DOWN as the blast radius went up.

Two things are pinned here:

1. `resolve()` puts every value in exactly one named bucket, and tells a
   wrong-key row apart from a corrupt one and from plaintext. Those three need
   different responses — re-encrypt, restore, backfill — and
   `try_decrypt() is None` collapses all three into "None".
2. `check_legacy()` COUNTS instead of raising, so N wrong-key rows report as N.

All PHI-shaped strings here are invented.
"""

from __future__ import annotations

import inspect

import pytest
from app.core import phi_keyscan as ks
from cryptography.fernet import Fernet, MultiFernet

# Synthetic, invented — never real patient data.
PHI = "Nguyen Van A — Metformin 500mg, uong sau an"


@pytest.fixture
def target() -> MultiFernet:
    return MultiFernet([Fernet(Fernet.generate_key())])


@pytest.fixture
def source() -> MultiFernet:
    return MultiFernet([Fernet(Fernet.generate_key())])


def _enc(cipher: MultiFernet, value: str) -> str:
    return cipher.encrypt(value.encode()).decode()


# ── 1. One value, one bucket ────────────────────────────────────────────────


def test_a_row_the_deployed_key_can_read_is_healthy(target, source):
    res = ks.resolve(_enc(target, PHI), target=target, source=source)
    assert res.classification == ks.CLASS_TARGET
    assert res.plaintext == PHI
    assert res.is_healthy
    assert not res.needs_rewrite


def test_a_row_encrypted_with_the_source_key_is_named_as_such(target, source):
    """THE incident row: valid ciphertext, wrong key. It is neither plaintext
    nor corrupt, and calling it either sends the response down the wrong path."""
    res = ks.resolve(_enc(source, PHI), target=target, source=source)
    assert res.classification == ks.CLASS_SOURCE
    assert res.used_source
    assert res.plaintext == PHI  # recoverable — this is why re-encryption works
    assert res.needs_rewrite
    assert not res.is_healthy


def test_a_row_neither_key_can_read_is_unreadable_and_yields_no_plaintext(target, source):
    """A restore case. It must not be handed to a re-encryption job: there is
    nothing to write back, and overwriting it destroys the evidence."""
    stranger = MultiFernet([Fernet(Fernet.generate_key())])
    res = ks.resolve(_enc(stranger, PHI), target=target, source=source)
    assert res.classification == ks.CLASS_UNREADABLE
    assert res.plaintext is None
    assert not res.needs_rewrite


def test_a_legacy_plaintext_row_is_not_called_undecryptable(target, source):
    res = ks.resolve(PHI, target=target, source=source)
    assert res.classification == ks.CLASS_PLAINTEXT
    assert res.layers == 0
    assert res.needs_rewrite  # the column requires ciphertext


def test_a_row_the_migration_re_encrypted_on_top_of_app_ciphertext_resolves(target, source):
    """`source(target(phi))` — what the migration did to a column the app had
    already encrypted. Both layers must be peeled, or it looks like corruption."""
    doubled = _enc(source, _enc(target, PHI))
    res = ks.resolve(doubled, target=target, source=source)
    assert res.classification == ks.CLASS_SOURCE
    assert res.layers == 2
    assert res.plaintext == PHI
    assert res.needs_rewrite


def test_an_over_wrapped_row_is_unreadable_rather_than_returning_ciphertext(target):
    """Past the depth limit, `plaintext` must stay None. Returning the token
    would make a re-encryption job wrap it again and cement it forever."""
    value = PHI
    for _ in range(ks._MAX_DECRYPT_DEPTH + 2):
        value = _enc(target, value)
    res = ks.resolve(value, target=target, source=None)
    assert res.classification == ks.CLASS_UNREADABLE
    assert res.plaintext is None


def test_a_healthy_row_never_needs_the_source_key(target):
    """Absent a source cipher, correct rows must still classify — the smoke runs
    this way in every normal deploy."""
    assert ks.resolve(_enc(target, PHI), target=target).classification == ks.CLASS_TARGET


# ── 2. Counting cannot lose rows ────────────────────────────────────────────


def test_every_class_is_reported_even_at_zero():
    """An absent key reads as "not measured". The failure being fixed here is a
    missing number that got read as a safe one."""
    counts = ks.empty_counts()
    assert set(counts) == set(ks.CLASSES)
    assert all(v == 0 for v in counts.values())


def test_counts_sum_to_the_number_of_rows_examined(target, source):
    values = (
        [_enc(target, PHI)] * 3
        + [_enc(source, PHI)] * 7
        + [PHI] * 2
        + [_enc(MultiFernet([Fernet(Fernet.generate_key())]), PHI)]
    )
    counts = ks.counted([ks.resolve(v, target=target, source=source) for v in values])
    assert counts[ks.CLASS_TARGET] == 3
    assert counts[ks.CLASS_SOURCE] == 7
    assert counts[ks.CLASS_PLAINTEXT] == 2
    assert counts[ks.CLASS_UNREADABLE] == 1
    assert sum(counts.values()) == len(values)


def test_add_counts_does_not_mutate_its_arguments():
    left = ks.empty_counts()
    ks.add_counts(left, {ks.CLASS_SOURCE: 5})
    assert left[ks.CLASS_SOURCE] == 0


# ── 3. The regression itself ────────────────────────────────────────────────


class _StubResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _StubSession:
    """Just enough Session for `check_legacy`'s single SELECT."""

    def __init__(self, values):
        self._values = values

    def execute(self, _sql, _params=None):
        return _StubResult(self._values)


@pytest.fixture
def stub_ciphers(monkeypatch, target, source):
    from scripts import crypto_smoke

    monkeypatch.setattr(crypto_smoke, "_source_cipher", lambda: source)
    monkeypatch.setattr("app.core.crypto.active_cipher", lambda: target)
    return crypto_smoke


def test_wrong_key_rows_are_never_reported_as_zero_legacy_impact(
    stub_ciphers, target, source
):
    """The exact misreport from the incident.

    Before: the scan raised on row 1, `legacy_rows_total` stayed 0, and the
    summary read "legacy_rows_total: 0" beside four failures. After: five
    wrong-key rows are five wrong-key rows.
    """
    rows = [_enc(source, PHI) for _ in range(5)]
    counts = stub_ciphers.check_legacy(
        _StubSession(rows), "meto_message.content", "meto_messages", "content"
    )

    assert counts[ks.CLASS_SOURCE] == 5, "the blast radius must not report as zero"
    assert counts[ks.CLASS_TARGET] == 0
    assert sum(counts.values()) == len(rows)


def test_a_mixed_column_reports_each_class_separately(stub_ciphers, target, source):
    """Partial damage is the realistic mid-remediation state, and "some rows are
    fine" must not round to either "all fine" or "all broken"."""
    rows = [_enc(target, PHI), _enc(source, PHI), PHI]
    counts = stub_ciphers.check_legacy(
        _StubSession(rows), "notification.body", "notifications", "body"
    )
    assert counts[ks.CLASS_TARGET] == 1
    assert counts[ks.CLASS_SOURCE] == 1
    assert counts[ks.CLASS_PLAINTEXT] == 1
    assert counts[ks.CLASS_UNREADABLE] == 0


def test_check_legacy_does_not_raise_on_a_bad_row(stub_ciphers, source):
    """Raising is what discarded the count. A bad row is DATA, not an error."""
    counts = stub_ciphers.check_legacy(
        _StubSession([_enc(source, PHI)]), "e", "notifications", "body"
    )
    assert counts[ks.CLASS_SOURCE] == 1


def _run_source() -> str:
    from scripts import crypto_smoke

    return inspect.getsource(crypto_smoke.run)


def test_the_smoke_reports_a_scanned_count_that_rises_with_damage():
    """`legacy_rows_total` is kept for the dashboards and evidence files that
    quote it, but it is now rows SCANNED. Under the old code it fell to 0
    exactly when every row was broken."""
    src = _run_source()
    assert '"legacy_rows_total": legacy_rows_seen' in src
    assert '"legacy_rows_scanned": legacy_rows_seen' in src
    assert "**legacy_totals" in src, "the four class totals are not flattened out"


def test_the_failure_reason_names_the_class_and_the_count():
    """"legacy_row_undecryptable" said neither how many nor which key. The
    reason code has to carry the remediation."""
    assert 'f"{name}={counts[name]}"' in _run_source()


def test_one_missing_table_is_not_reported_as_four_broken_columns():
    """A failed statement aborts the Postgres transaction, so without a
    savepoint every LATER column fails with InFailedSqlTransaction — during an
    incident, one absent table would read as total loss."""
    assert "session.begin_nested()" in _run_source()


# ── 4. Column discovery ─────────────────────────────────────────────────────


def test_every_encrypted_column_is_discovered_from_the_orm():
    """A hand-maintained list is how a PHI column added next quarter escapes the
    scan. These are the incident's own columns."""
    entities = {c.entity for c in ks.encrypted_columns()}
    assert {
        "meto_messages.content",
        "extraction_candidates.fields_json",
        "medication_statements.raw_drug_name",
        "notifications.body",
        "notifications.title",
    } <= entities
    assert len(entities) >= 30


def test_discovered_columns_are_all_keyset_pageable():
    """The re-encryption job pages on `id`. A column without one would be
    silently skipped, so discovery must not return any."""
    assert all(c.pk == "id" for c in ks.encrypted_columns())


def test_the_smoke_scans_every_encrypted_column_not_just_the_hot_paths():
    from scripts import crypto_smoke

    scanned = {t for _e, t, _c in crypto_smoke.legacy_targets()}
    assert {"meto_messages", "notifications", "medication_statements"} <= scanned
    assert "patient_profiles" in scanned, "profile PHI was never checked"
    assert len(crypto_smoke.legacy_targets()) >= len(ks.encrypted_columns())
