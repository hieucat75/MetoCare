# MetoCare Patient Platform — Credential-Readiness Matrix (DIST-RC)

**Date:** 2026-08-03 · **Branch:** `feat/patient-platform-journey2`

Every remaining gap to full Distribution Release is an **external credential /
authorization the owner must supply** — none is an engineering blocker. Each row
states what the credential gates, what already works without it, and what
flips on the moment it arrives.

| # | Credential / authorization | Gates (blocked until supplied) | Works NOW without it | Unblocks on receipt |
|---|---|---|---|---|
| 1 | **Apple signing identity** (Apple Developer Program, distribution cert + provisioning profile) | iOS TestFlight / App Store distribution builds | Full app runs on iOS **simulator**; EAS iOS-simulator artifact builds; all JS/logic identical to Android | `eas build -p ios` release + TestFlight submit |
| 2 | **Google Play signing** (Play Console app signing key + service account) | Play Store / internal-track distribution | Android **emulator + dev-client** builds, installs, and boots (verified on-device — see `evidence/native-j2j5/`); debug APK builds | `eas build -p android` release + Play internal track |
| 3 | **APNs / FCM push keys** (APNs auth key; FCM sender/service-account) | Real remote push notifications | In-app + deterministic notification transports (always-on, §1.1); reminder/adherence loop fully works in-app | Register the push transport capability; device-token flow enables remote push |
| 4 | **Azure Document Intelligence key** + **PHI-to-cloud processing authorization** | Cloud OCR (higher-accuracy extraction) AND any PHI leaving the device/region | Local/mock OCR pipeline (Tesseract path); the full staged OCR → candidate → confirm flow works on local/mock; `document_scan_mode` posture explicit | Set the Azure DI key + flip the cloud-OCR flag **only after** owner authorizes PHI-to-cloud |
| 5 | **Real payment gateway** (e.g. VNPay merchant creds) | Real money movement for consultations | Approved **mock-payment** consultation flow (browse→book→pay→consult→review) works end-to-end | Swap the mock payment adapter for the real gateway adapter |
| 6 | **Staging/prod auth secrets** (real `MCP_SECRET_KEY`, `MCP_ENCRYPTION_KEYS`) + secure auth config | Booting staging/production at all (fail-loud guards) | dev/test run on committed dev defaults | Inject real secrets via the deploy secret store; set `MCP_MFA_ENFORCEMENT_ENABLED=true` + strong password policy (§C guard enforces this) |

## Standing safety rule
**Cloud PHI processing (row 4) stays DISABLED until the owner both authorizes it
and supplies credentials.** The code path is flag-gated and fail-closed; no PHI
leaves local/mock processing by default.

## Capability independence (per owner directive)
- Apple signing does **not** block Android/dev verification. ✔ (Android verified on-device)
- Google signing does **not** block emulator/dev build. ✔
- APNs/FCM does **not** block in-app/deterministic notifications. ✔
- Azure DI does **not** block local/mock OCR. ✔
- Real payment creds do **not** block the approved mock-payment flow. ✔

## Engineering readiness (no credential required) — DONE this program
- A: metrics verified-source guard · B: per-category consent (fail-closed,
  versioned, revocable, audited, mobile controls) · C: MFA + password policy
  restored with env-scoped fail-loud · D: Android native-runtime defect found +
  fixed on-device · G: account export + deletion (data-subject rights).
