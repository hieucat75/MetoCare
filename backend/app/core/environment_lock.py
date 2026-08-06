"""Synthetic-only mode — the containment switch for a non-production environment.

Why this exists
---------------
The 2026-08-06 staging encryption incident turned out to have affected **real
users' PHI**: 90 accounts had self-registered through a publicly reachable
staging ingress with open registration, and 77 of them had deliverable email
addresses. The data was there because nothing stopped it arriving.

Fixing the encryption does not fix that. As long as real people can register on
staging and upload documents to it, the next staging defect is another privacy
incident. This makes "staging is for synthetic data" enforceable rather than
aspirational.

What it does when enabled
-------------------------
- **Registration** is refused for any identifier that is not recognisably
  synthetic.
- **Login** is refused for the same — which locks out accounts that already
  exist. That is the point: existing real accounts must stop writing new data.
  Their rows are NOT deleted; the incident's evidence-retention plan owns that
  decision, not this switch.
- **Outbound** transports (push, email) are suppressed, so nothing this
  environment does can reach a real person's device or inbox. In-app and
  deterministic records still work, because they never leave the system.

What counts as synthetic
------------------------
The same definition the forensic provenance report uses — one source of truth,
so "which accounts are synthetic" cannot mean two different things in the tool
that measures the incident and the lock that prevents the next one.

RFC 2606 reserves `example.com`, `.test` and `.invalid` precisely so they cannot
be delivered to. An address using one cannot belong to a person who could be
harmed by a disclosure, which is exactly the property wanted here.

Fails **closed**: an identifier that cannot be classified is not synthetic.
"""

from __future__ import annotations

import re

from .config import get_settings

#: One definition, shared with `scripts/provenance_report.py`.
#:
#: DOMAIN-anchored only. An earlier draft also matched local-part prefixes
#: (`^demo\.`, `^qa\.`, …) and its own spoofing test caught the consequence:
#: `qa.metocare.internal@gmail.com` and `demo.attacker@gmail.com` start with
#: those prefixes and would have been ADMITTED — a real address at a real
#: mailbox, in the environment this lock exists to keep real people out of.
#: They were also redundant: every seeded identity in this project already sits
#: on a reserved domain (`demo.patient@example.com`, `cs-…@crypto-smoke.invalid`),
#: so the domain patterns alone cover them. A marker that can appear in the part
#: of an address the attacker chooses is not a marker.
SYNTHETIC_PATTERNS = (
    r"@example\.(com|org|net)$",
    r"@.*\.test$",
    r"@.*\.invalid$",
    r"@.*\.localhost$",
)
_SYNTHETIC = re.compile("|".join(SYNTHETIC_PATTERNS), re.IGNORECASE)


def is_locked() -> bool:
    """True when this environment accepts synthetic identities only."""
    return bool(getattr(get_settings(), "synthetic_only_mode", False))


def _extra_allowlist() -> tuple[str, ...]:
    raw = getattr(get_settings(), "synthetic_extra_allowlist", "") or ""
    return tuple(x.strip().lower() for x in raw.split(",") if x.strip())


def is_synthetic_identifier(identifier: str | None) -> bool:
    """Is this address or phone one that cannot belong to a real person?

    Fails closed. An empty, absent or unparseable identifier is NOT synthetic,
    because the cost of a false "yes" here is admitting a real person into an
    environment that has already leaked once.
    """
    if not identifier:
        return False
    value = identifier.strip().lower()
    if not value:
        return False
    if _SYNTHETIC.search(value):
        return True
    # Operator escape hatch: exact identifiers, or `@domain` suffixes, listed in
    # MCP_SYNTHETIC_EXTRA_ALLOWLIST. Needed because a phone number has no
    # reserved range to match on, and staging QA needs some.
    for allowed in _extra_allowlist():
        if value == allowed or (allowed.startswith("@") and value.endswith(allowed)):
            return True
    return False


def permits(identifier: str | None) -> bool:
    """May this identifier register or authenticate here?

    Unlocked environments permit everything — production must never be affected
    by this module, and a lock that had to be explicitly disabled in production
    would be one deploy away from locking out every patient.
    """
    return True if not is_locked() else is_synthetic_identifier(identifier)


def outbound_transports_permitted() -> bool:
    """False in a locked environment: nothing may reach a real device or inbox."""
    return not is_locked()


def banner() -> str:
    """Environment banner text for the UI. Empty means production."""
    settings = get_settings()
    explicit = (getattr(settings, "environment_banner", "") or "").strip()
    if explicit:
        return explicit
    if is_locked():
        return (
            "MÔI TRƯỜNG THỬ NGHIỆM — chỉ dùng dữ liệu giả lập. "
            "Không nhập thông tin sức khoẻ thật. "
            "(TEST ENVIRONMENT — synthetic data only. Do not enter real health "
            "information.)"
        )
    return ""


#: Refusal text. Names the reason and the remedy, and deliberately does not
#: reveal whether the account exists — a locked environment must not become an
#: account-enumeration oracle for the very accounts caught up in the incident.
LOCKED_MESSAGE = (
    "Môi trường thử nghiệm này chỉ chấp nhận tài khoản giả lập. "
    "Vui lòng liên hệ quản trị viên nếu bạn cần truy cập. "
    "(This test environment accepts synthetic accounts only.)"
)
