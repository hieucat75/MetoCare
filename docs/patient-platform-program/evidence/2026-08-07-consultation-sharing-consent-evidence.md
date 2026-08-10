# Consultation Sharing Consent — evidence closeout

Feature: consultation-specific doctor data-sharing consent (patient-facing
sharing management + explicit four-way sharing state).
Evidence captured 2026-08-07 on staging. Closed out 2026-08-10.
Docs-only record — no code, config, infrastructure or deployment change.

## What shipped

| item | value |
|---|---|
| PR #139 — consultation-specific doctor data-sharing consent | merge `ec442cbe171d818e6fcae9b8c54ddd9fa5f7d582` |
| PR #140 — explicit consent state (never say "đã thu hồi" when nothing was granted) | merge `6c6a3df838eddd53e972c1d52b204af23b404a64` |
| Staging build under test | `6c6a3df8` |
| Alembic head | `mkt_c1_consult_consent` (single head; no later revision declares it as `down_revision`) |
| CI + Staging Auto-Deploy, head `6c6a3df8` | success — [run 31168857481](https://github.com/hieucat75/MetoCare/actions/runs/31168857481) |

The staging build SHA is not asserted from the outside: every screenshot below
carries the environment banner, and the banner renders `6c6a3df8`. The frames
are self-identifying as to which build produced them.

## Sharing states and how each was verified

`app/domain/consultation_sharing_state.py` names four states. A 403 is an
authorisation outcome and cannot carry *why*, so the state is reported
explicitly and every surface reads the same distinction from one place.

| state | meaning | verification |
|---|---|---|
| `ACTIVE` | a grant exists and authorises access now | **live on staging** — patient and doctor surfaces, incl. a partial grant |
| `REVOKED` | a grant existed and the patient withdrew it | **live on staging** — patient and doctor surfaces |
| `NEVER_GRANTED` | no grant has ever existed for this consultation | **live on staging**, observed before the first grant was recorded |
| `NEEDS_RECONSENT` | a grant exists, was not withdrawn, and no longer authorises access | **automated tests only** — backend, web and mobile. See below. |

### NEVER_GRANTED

Verified live in the ordinary flow, on the consultation as it existed *before*
the patient's first grant — the same window a consultation booked prior to this
feature sits in permanently. No screenshot of that pre-grant window was captured
at the time, and none is reconstructed here: the state was observed, the frame
was not, and inventing one would make this record say something it cannot
support. Its behaviour is additionally covered by automated tests in
`backend/tests/test_consultation_sharing_state.py`,
`frontend/src/__tests__/ConsultationSharingCard.test.tsx`,
`frontend/src/__tests__/DoctorSummaryWithheldCategories.test.tsx` and
`mobile/__tests__/consultationSharingCardLegacy.test.tsx`.

### NEEDS_RECONSENT — why it was not forced live

> No valid application write path can create a stale consent version. Creating
> the fixture would require direct database mutation or additional test-only
> access. Neither is warranted solely for staging evidence.

This is a property of the design, not a gap in the testing. Every write path
stamps the current constant (`consent_policy.CONSENT_VERSION`) rather than
accepting one from the caller, and both client-facing write routes reject a
submitted version that is not current with `409 Conflict` — booking
(`backend/app/api/v1/routes/consultations.py:182`) and re-share
(`backend/app/api/v1/routes/consultations.py:529`). A row whose
`consent_version` trails the constant is therefore unreachable from the
application: it can only arise from the constant being bumped under an existing
row — a future deploy — or from writing to the table directly.

The backend test makes the same point in the only way available: it reaches
past the API and sets `row.consent_version = "0.9"` on the ORM object
(`test_stale_consent_version_is_needs_reconsent_not_revoked`). That is precisely
the direct database mutation this record declines to perform against staging.

Covered by automated tests on all three surfaces:

| surface | test |
|---|---|
| backend | `test_consultation_sharing_state.py::test_stale_consent_version_is_needs_reconsent_not_revoked` — asserts `state == NEEDS_RECONSENT` **and** `consent.revoked_at is None` |
| web — patient | `ConsultationSharingCard.test.tsx` › "a needs-reconsent state is not reported as a withdrawal" — asserts "Cần xác nhận lại", asserts "Đã thu hồi" absent |
| web — doctor | `DoctorSummaryWithheldCategories.test.tsx` › "a needs-reconsent state is not blamed on the patient" — asserts the notice says the terms changed and says it is not a patient withdrawal |
| mobile | `consultationSharingCardLegacy.test.tsx` › "a needs-reconsent state is not reported as a withdrawal" |

The claim these tests defend is the one that matters clinically and legally:
a version bump is our action, so no surface may render it as the patient's.

## Screenshots

All frames are synthetic staging accounts on a database that holds no real
patient data, under the standing banner "MÔI TRƯỜNG THỬ NGHIỆM (staging) — dữ
liệu ở đây không phải dữ liệu thật".

### Current — build `6c6a3df8` (PR #140 UI)

| file | surface | state shown |
|---|---|---|
| `01-active-patient.png` | patient, web | `ACTIVE` — "Đang chia sẻ" with the categories currently shared |
| `02-revoke-confirmation.png` | patient, web | revoke confirmation — states the doctor loses access immediately, that the consultation continues and is not refunded, and that re-sharing is possible |
| `03-revoked-patient.png` | patient, web | `REVOKED` — "Đã thu hồi", categories shown in the past tense ("đã từng chia sẻ") |
| `04-reshare-dialog.png` | patient, web | re-share consent dialog, categories enumerated before consent |
| `05-revoked-doctor.png` | doctor, web | `REVOKED` — "Chưa có quyền xem hồ sơ", attributed to the patient's withdrawal, with a route that does not require the data |
| `06-active-doctor-partial-grant.png` | doctor, web | `ACTIVE` with a partial grant — warns that unshared items do **not** mean absent data |

`06` carries the safety-critical line: a doctor reading a partially shared
record must not read silence as "no such data".

### Retained from PR #139 — historical

Kept as the record of what the earlier build showed. PR #140 rewrote
`ConsultationSharingCard` (state-driven status lines replacing a status-inferred
"Đang chia sẻ / Đã thu hồi" pair), so the frames of that card no longer depict
current behaviour.

| file | status |
|---|---|
| `1-booking-consent-modal.png` | current — `DataSharingConsentModal` was not changed by PR #140 |
| `2-active-sharing.png` | **SUPERSEDED** by `01-active-patient.png` — card rewritten in PR #140 |
| `3-revoke-dialog.png` | **SUPERSEDED** by `02-revoke-confirmation.png` — card rewritten in PR #140 |
| `4-revoked-state.png` | **SUPERSEDED** by `03-revoked-patient.png` — card rewritten in PR #140 |
| `5-reshare-consent.png` | current — the re-share dialog component was not changed by PR #140; `04-reshare-dialog.png` is the desktop-web equivalent |

The PR #139 frames are mobile-viewport captures; the new frames are desktop web.
They are complementary, not duplicates, except where marked SUPERSEDED.

## Data hygiene

- PNG chunk scan of all six new files: `IHDR` and image data only. No `tEXt`,
  `iTXt`, `zTXt` or `eXIf` chunks — no capture tool, path, account or timestamp
  metadata is embedded.
- No credential, token, secret, session identifier or account handle appears in
  this document.
- Consultation reference codes and display names are visible in the frames.
  They are synthetic staging values on a database with no real patient data;
  they are deliberately not transcribed into this document.

## Scope of this record

Closed: PR #139 and #140 are merged, staging is running `6c6a3df8` with Alembic
head `mkt_c1_consult_consent`, and three of the four sharing states are verified
live with the fourth verified by automated test on backend, web and mobile.

Not covered here, and not claimed: production deployment. Nothing in this
closeout deploys, and no consent behaviour was changed to produce it.
