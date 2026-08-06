"""The provenance report decides whether an incident is reportable.

That makes two properties load-bearing, and they pull against each other:

* it must be **conclusive enough to act on** — a report that always says
  "cannot establish" is a way of not answering; and
* it must **never emit an identifier** — reading identifiers to decide whether
  identifiers are real is self-defeating, and putting PHI in a terminal during
  an incident turns one problem into two.

Both are pinned here, along with the verdict logic at its boundaries: one
non-synthetic owner flips the answer, and an unresolvable column must not be
silently counted as clean.

All addresses below are invented.
"""

from __future__ import annotations

import inspect
import json
import re

import pytest
from scripts import provenance_report as pr

# ── 1. It cannot leak, by construction ──────────────────────────────────────


def test_the_module_never_prints_an_identifier():
    """Every emitted value must be an integer, a date bound, or a fixed string."""
    src = inspect.getsource(pr)
    for banned in ("print(email", "print(uid", '"email":', '"user_id":',
                   "print(row", "print(owners"):
        assert banned not in src, f"{banned} would put an identifier in the output"
    # The single place addresses are read, they are consumed into a boolean.
    assert "_SYNTHETIC.search(email)" in src


def test_emitted_records_contain_no_string_that_could_be_an_address(capsys):
    pr._emit({"signal": "x", "users_total": 3, "synthetic": 3, "non_synthetic": 0})
    out = capsys.readouterr().out
    assert "@" not in out, "an address reached the output"
    for value in json.loads(out).values():
        assert not (isinstance(value, str) and re.search(r"[^@\s]+@[^@\s]+", value))


def test_it_is_read_only():
    src = inspect.getsource(pr).upper()
    for write in ("UPDATE ", "INSERT ", "DELETE ", "SESSION.COMMIT("):
        assert write not in src, f"{write.strip()} in a read-only report"


def test_it_always_exits_zero():
    """A measurement, not a gate. A non-zero exit invites someone to block a
    deploy on it, and this answer is an input to a human decision."""
    src = inspect.getsource(pr.run)
    assert "return 0" in src
    assert "return 1" not in src


# ── 2. The markers are the ones that cannot belong to a person ──────────────


@pytest.mark.parametrize("email", [
    "demo.patient@example.com", "pilot.doctor@example.com",
    "someone@metocare.test", "cs-abc123@crypto-smoke.invalid",
    "ws4f3-deadbeef@example.com",
])
def test_reserved_and_seeded_addresses_are_classified_synthetic(email):
    """RFC 2606 reserves these domains precisely so they cannot be delivered to,
    so an address using one cannot belong to a person who could be notified."""
    assert pr._SYNTHETIC.search(email), f"{email} should be synthetic"


@pytest.mark.parametrize("email", [
    "nguyen.van.a@gmail.com", "patient@benhvien.vn",
    "someone@metocare.me", "real.person@outlook.com",
    # Deliberately NOT synthetic. `sub.example.org` is arguably reserved too,
    # but the two errors are not symmetric: classifying a real address as
    # synthetic downgrades a reportable disclosure to an engineering defect,
    # while classifying a synthetic one as real only makes the verdict more
    # cautious. The matcher is anchored to the exact reserved domains, and it
    # stays that way.
    "x@sub.example.org",
])
def test_deliverable_addresses_are_not_classified_synthetic(email):
    """The failure that matters: calling a real address synthetic would
    downgrade a reportable disclosure to an engineering defect."""
    assert not pr._SYNTHETIC.search(email), f"{email} must NOT be synthetic"


def test_the_matcher_errs_toward_calling_things_real():
    """Stated as a property, not left implicit in the pattern.

    Every marker is anchored (`$` on the domain, `^` on the local part). An
    unanchored `example\\.com` would match `example.com.attacker.net`; a bare
    `demo` would match `demonstration.nguyen@gmail.com`. Both mistakes point the
    same wrong way — toward "synthetic", toward "not reportable".
    """
    for pattern in pr.SYNTHETIC_PATTERNS:
        assert pattern.startswith("^") or pattern.endswith("$"), (
            f"{pattern!r} is unanchored and can match inside a real address"
        )


def test_the_affected_set_is_the_incidents_columns_and_is_fixed():
    """Hardcoded on purpose: this reports on ONE incident, and a set that
    silently grew would change what the verdict means without a decision."""
    cols = {f"{t}.{c}" for t, c, _ in pr.AFFECTED}
    assert cols == {
        "meto_messages.content",
        "medication_statements.raw_drug_name",
        "medication_statements.raw_dose",
        "medication_statements.raw_frequency",
        "medication_statements.payload_snapshot",
        "notifications.title",
        "notifications.body",
        "extraction_candidates.fields_json",
        "users.full_name",
    }


# ── 3. Verdict boundaries ───────────────────────────────────────────────────
#
# The logic is a small ladder inside `run()`, which needs a live database. These
# assert the ladder's ORDER from its source, which is what makes the boundaries
# safe: "cannot establish" must be checked BEFORE "synthetic", or an
# unresolvable column reads as clean.


def test_unresolvable_columns_outrank_a_clean_verdict():
    src = inspect.getsource(pr.run)
    i_unres = src.index('verdict, why = "CANNOT_ESTABLISH"')
    i_real = src.index('"CONFIRMED_REAL_DATA_PRESENT"')
    i_syn = src.index('"CONFIRMED_SYNTHETIC"')
    assert i_unres < i_real < i_syn, (
        "the ladder must test unresolvable, then real, then synthetic — any other "
        "order lets a column it could not read be reported as clean"
    )


def test_one_non_synthetic_owner_is_enough_to_flip_the_verdict():
    src = inspect.getsource(pr.run)
    assert "owners_non_synthetic > 0" in src, (
        "the threshold must be ONE affected row with a non-synthetic owner; a "
        "percentage or a floor would let real people's data round to zero"
    )


def test_non_synthetic_accounts_owning_no_affected_rows_is_still_synthetic():
    """Staging having real accounts is not the question. Whether real accounts
    own any of the 103 affected rows is."""
    assert "own ZERO" in inspect.getsource(pr.run)


def test_the_entrypoint_takes_no_dash_prefixed_arguments():
    import run_provenance_report

    code = inspect.getsource(run_provenance_report)
    for banned in ("add_argument", "ArgumentParser", "sys.argv"):
        assert banned not in code
