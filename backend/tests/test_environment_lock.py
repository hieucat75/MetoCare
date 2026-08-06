"""Synthetic-only mode: the containment that stops staging collecting real people.

The 2026-08-06 encryption incident was a crypto bug. What made it a *privacy*
incident was that 90 real users had self-registered on staging, because open
registration on a public ingress was never gated. Fixing the crypto does not fix
that; this does.

Two failure directions, and they are not symmetric:

* letting a real identity through a locked environment re-creates the incident;
* locking production out would deny every patient access to their own care.

So the lock defaults OFF and fails CLOSED — an identifier it cannot classify is
not synthetic, and an environment that has not explicitly opted in is not locked.

All addresses here are invented.
"""

from __future__ import annotations

import pytest
from app.core import environment_lock as lock
from app.core.config import Settings


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setattr(lock, "get_settings", lambda: Settings(synthetic_only_mode=True))
    return lock


@pytest.fixture
def unlocked(monkeypatch):
    monkeypatch.setattr(lock, "get_settings", lambda: Settings(synthetic_only_mode=False))
    return lock


# ── 1. Default posture ──────────────────────────────────────────────────────


def test_the_lock_is_off_by_default():
    """Production must be unaffected by construction. A lock that had to be
    explicitly disabled in production is one deploy away from locking out every
    patient."""
    assert Settings().synthetic_only_mode is False


def test_an_unlocked_environment_permits_everything(unlocked):
    for ident in ("nguyen.van.a@gmail.com", "0912345678", "", None):
        assert unlocked.permits(ident) is True
    assert unlocked.outbound_transports_permitted() is True
    assert unlocked.banner() == ""


# ── 2. Who gets in while locked ─────────────────────────────────────────────


@pytest.mark.parametrize("ident", [
    "demo.patient@example.com", "pilot.doctor@example.com",
    "qa.tester@example.com", "verify.smoke@example.com",
    "someone@metocare.test", "cs-abc@crypto-smoke.invalid",
    "ws4f3-deadbeef@example.com",
])
def test_synthetic_identities_are_admitted(locked, ident):
    assert locked.permits(ident), f"{ident} should be admitted"


@pytest.mark.parametrize("ident", [
    "nguyen.van.a@gmail.com", "patient@benhvien.vn",
    "real.person@outlook.com", "someone@metocare.me",
    "0912345678", "+84912345678",
])
def test_real_identities_are_refused(locked, ident):
    """THE containment property. Each of these is the shape of an identifier
    that turned up on staging for real."""
    assert not locked.permits(ident), f"{ident} must be refused"


@pytest.mark.parametrize("ident", ["", None, "   ", "not-an-identifier"])
def test_unclassifiable_identifiers_fail_closed(locked, ident):
    """The cost of a false 'synthetic' is admitting a real person into an
    environment that has already leaked once."""
    assert not locked.permits(ident)


def test_the_matcher_is_anchored_so_it_cannot_be_spoofed(locked):
    """Unanchored, `example\\.com` matches `example.com.attacker.net` and a bare
    `demo` matches `demonstration.nguyen@gmail.com`. Here that mistake grants
    ACCESS, not merely a wrong label."""
    for spoof in ("attacker@example.com.evil.net", "demonstration.nguyen@gmail.com",
                  "pilots@gmail.com", "notqa.person@gmail.com",
                  # These four are why the local-part patterns were removed: each
                  # starts with a seed prefix and ends at a REAL mailbox.
                  "demo.attacker@gmail.com", "qa.metocare.internal@gmail.com",
                  "pilot.someone@outlook.com", "verify.me@gmail.com"):
        assert not locked.permits(spoof), f"{spoof} slipped through"
    # Every marker must be anchored to the DOMAIN — the part of an address the
    # sender does not get to choose.
    for pattern in lock.SYNTHETIC_PATTERNS:
        assert pattern.endswith("$") and pattern.startswith("@"), (
            f"{pattern!r} is not domain-anchored; a local-part marker can be spoofed"
        )


# ── 3. The operator escape hatch, bounded ───────────────────────────────────


def test_the_extra_allowlist_admits_exact_identifiers_and_domain_suffixes(monkeypatch):
    """Phone numbers have no reserved range, so staging QA needs a way in."""
    monkeypatch.setattr(lock, "get_settings", lambda: Settings(
        synthetic_only_mode=True,
        synthetic_extra_allowlist="0987000111,@qa.metocare.internal",
    ))
    assert lock.permits("0987000111")
    assert lock.permits("anyone@qa.metocare.internal")
    assert not lock.permits("0987000112"), "near-miss must not be admitted"
    assert not lock.permits("qa.metocare.internal@gmail.com"), "suffix must anchor"


# ── 4. Nothing reaches a real person ────────────────────────────────────────


def test_outbound_transports_are_suppressed_while_locked(locked):
    """Push and email are inert today only because no credentials are
    configured. 'Inert by accident' stops being true the moment someone adds
    them, and this environment must not be able to notify a real person about
    data that should never have been here."""
    assert locked.outbound_transports_permitted() is False


def test_the_transport_returns_before_reaching_push_or_email():
    import inspect

    from app.services import notification_transport as nt

    src = inspect.getsource(nt.deliver)
    guard = src.index("outbound_transports_permitted")
    assert guard < src.index("_push_configured(settings)")
    assert guard < src.index("_email_configured(settings)")
    # In-app and deterministic must still work: they never leave the system,
    # and reminders are the feature under test in staging.
    assert src.index('delivered.append("in_app")') < guard


# ── 5. The banner says so out loud ──────────────────────────────────────────


def test_a_locked_environment_has_a_banner_naming_the_risk(locked):
    text = locked.banner()
    assert text
    assert "giả lập" in text or "synthetic" in text.lower()
    assert "thật" in text or "real" in text.lower()


def test_the_banner_is_overridable(monkeypatch):
    monkeypatch.setattr(lock, "get_settings", lambda: Settings(
        synthetic_only_mode=True, environment_banner="CUSTOM"))
    assert lock.banner() == "CUSTOM"


# ── 6. The refusal is not an enumeration oracle ─────────────────────────────


def test_the_refusal_message_reveals_nothing_about_the_account():
    """A locked environment must not become a way to discover which of the
    accounts caught up in the incident exist."""
    msg = lock.LOCKED_MESSAGE.lower()
    for leak in ("not found", "does not exist", "unknown user", "no such"):
        assert leak not in msg


def test_login_refuses_before_any_credential_check():
    """Identical response whether or not the account exists, and no password
    comparison for a locked-out identity."""
    import inspect

    from app.api.v1.routes import auth

    src = inspect.getsource(auth.login)
    gate = src.index("env_lock.permits(lkey)")
    assert gate < src.index("lockout.is_locked("), "gate runs after the lockout check"
    assert "authenticate" not in src[:gate], "a credential check precedes the gate"


def test_register_refuses_before_creating_anything():
    import inspect

    from app.api.v1.routes import auth

    src = inspect.getsource(auth.register)
    gate = src.index("env_lock.permits(")
    assert gate < src.index("auth.register("), "an account is created before the gate"


# ── 7. One definition of synthetic, shared with the forensic report ─────────


def test_the_lock_and_the_provenance_report_agree_on_what_synthetic_means():
    """Two definitions would mean the tool that measures the incident and the
    lock that prevents the next one could disagree about the same account."""
    from scripts import provenance_report as pr

    assert set(pr.SYNTHETIC_PATTERNS) <= set(lock.SYNTHETIC_PATTERNS)
