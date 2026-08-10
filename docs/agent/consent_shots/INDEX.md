# Consultation Sharing Consent — screenshot evidence

Full record, including how each sharing state was verified:
[`docs/patient-platform-program/evidence/2026-08-07-consultation-sharing-consent-evidence.md`](../../patient-platform-program/evidence/2026-08-07-consultation-sharing-consent-evidence.md)

All frames are synthetic staging accounts on a database holding no real patient
data. No metadata chunks are embedded in the PNGs.

## Current — staging build `6c6a3df8` (PR #140)

| file | surface | state |
|---|---|---|
| `01-active-patient.png` | patient, web | `ACTIVE` |
| `02-revoke-confirmation.png` | patient, web | revoke confirmation |
| `03-revoked-patient.png` | patient, web | `REVOKED` |
| `04-reshare-dialog.png` | patient, web | re-share consent dialog |
| `05-revoked-doctor.png` | doctor, web | `REVOKED` |
| `06-active-doctor-partial-grant.png` | doctor, web | `ACTIVE`, partial grant |

## Retained from PR #139 (mobile viewport)

| file | status |
|---|---|
| `1-booking-consent-modal.png` | current — modal unchanged by PR #140 |
| `2-active-sharing.png` | **SUPERSEDED** → `01-active-patient.png` |
| `3-revoke-dialog.png` | **SUPERSEDED** → `02-revoke-confirmation.png` |
| `4-revoked-state.png` | **SUPERSEDED** → `03-revoked-patient.png` |
| `5-reshare-consent.png` | current — re-share dialog unchanged by PR #140 |

`NEVER_GRANTED` was verified live before the first grant but not captured; no
frame for it is reconstructed. `NEEDS_RECONSENT` is unreachable from any
application write path and is covered by backend, web and mobile tests only —
see the evidence record for why it was not forced live.
