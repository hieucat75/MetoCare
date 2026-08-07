"""The explicit sharing state of one consultation.

Why this exists
---------------
Before this module the only thing a doctor surface could observe was a generic
403 from the PHI endpoints, and the UI inferred "the patient revoked" from it.
That inference is wrong for a consultation booked before consent was recorded at
all: nothing was ever granted, so nothing was ever withdrawn. Telling a doctor
"bệnh nhân đã thu hồi" in that case is a false statement about a patient's
action, and it points the doctor at the wrong remedy.

A 403 is an *authorisation outcome*. It cannot carry why. This module names the
state instead, so every surface reads the same four-way distinction from one
place rather than each re-deriving it from an error code:

``ACTIVE``           a grant exists and authorises access right now.
``REVOKED``          a grant existed and the patient withdrew it.
``NEVER_GRANTED``    no grant has ever existed for this consultation.
``NEEDS_RECONSENT``  a grant exists and was not withdrawn, but no longer
                     authorises access — the consent semantics moved under it
                     (``CONSENT_VERSION`` bumped) or it carries no category.
                     Distinct from REVOKED on purpose: the patient did not do
                     anything, so saying they withdrew would be the same false
                     statement in a different disguise.

"Unavailable/error" is deliberately NOT a member. It is a transport outcome, not
a consent fact, and the client owns it — folding it in here would let a network
blip render as a statement about what the patient decided.

Nothing here is PHI: a state token, identifiers and version stamps only.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from app.models.consultation import ConsultationStatus


class SharingState(StrEnum):
    """Why a consultation's health data is, or is not, readable by its doctor."""

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    NEVER_GRANTED = "NEVER_GRANTED"
    NEEDS_RECONSENT = "NEEDS_RECONSENT"


#: Statuses in which a patient may still grant or re-grant sharing.
#:
#: The terminal statuses are excluded because the care relationship itself has
#: ended: ``consultation_access.revoke_on_end`` has already closed every grant,
#: so consenting would record a decision that reopens nothing. Offering the
#: action there would promise the patient something the system cannot deliver.
SHAREABLE_STATUSES: frozenset[str] = frozenset(
    {
        ConsultationStatus.REQUESTED,
        ConsultationStatus.CONFIRMED,
        ConsultationStatus.PAID,
        ConsultationStatus.IN_PROGRESS,
    }
)


def resolve(
    record,
    *,
    now: dt.datetime,
    current_consent_version: str,
) -> SharingState:
    """Classify *record* (a ``ConsultationDataConsent`` or ``None``).

    Order matters and is chosen so that no state can be reported as a patient
    action the patient did not take:

    1. absence first — no row can never mean "withdrawn";
    2. an explicit ``revoked_at`` next — that IS the patient's action;
    3. then the active check, which owns every remaining fail-closed reason.

    Fail-closed: anything that is not provably active is reported as a
    not-readable state, never as ACTIVE.
    """
    if record is None:
        return SharingState.NEVER_GRANTED
    if record.revoked_at is not None:
        return SharingState.REVOKED
    if record.is_active_at(now, current_consent_version=current_consent_version):
        return SharingState.ACTIVE
    # Not absent, not withdrawn, still not usable — the terms moved, or the row
    # carries no category. Either way the patient must consent again.
    return SharingState.NEEDS_RECONSENT


def may_share(consultation_status: str) -> bool:
    """True when the lifecycle still permits granting or re-granting sharing."""
    return consultation_status in SHAREABLE_STATUSES
