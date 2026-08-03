# Native Journey Recordings — Manifest (J A–D)

Four native Android journeys driven by Maestro 2.8.0 against a real API‑34 (arm64)
emulator, each screen‑recorded end‑to‑end. The raw `.mp4` files are kept as local
artifacts (not committed — see `.gitignore`) to avoid ~21 MB of binaries in git;
their SHA‑256 checksums below bind this manifest to the exact recorded files, and
the per‑journey step logs are committed under `logs/`.

- **Device:** AVD `metocare_pilot_api34` — Android 14 (API 34), `arm64-v8a`, `-gpu host`.
- **Build:** debug APK (`me.metocare.patient`), local FastAPI on host `:8001`
  (mock AI, `MCP_QA_FIXTURE_ENABLED=true`, OCR on), `adb reverse tcp:8000→8001`.
- **Credentials:** injected via `${MAESTRO_EMAIL}`/`${MAESTRO_PASSWORD}` env only —
  never hard‑coded, never printed. Synthetic pilot account only.
- **Recorded:** 2026‑08‑03 (UTC).

| Journey | Flow | Video file | SHA‑256 | Size | Steps | Failures |
|---|---|---|---|---|---|---|
| A — Document (QA fixture) | `.maestro/01-documents.yaml` | `videos/01-documents.mp4` | `554f8e9d39a3804c586da0b5e262761803312140854c039696aace68eb5dc6b3` | 4.5M | 25 | 0 |
| B — Medication daily care | `.maestro/02-medication.yaml` | `videos/02-medication.mp4` | `082515385735c76debebfe56f91f41cccf478c8bb82bdcc5d7d8ed049499d8de` | 4.4M | 29 | 0 |
| C — Meto (consent‑aware) | `.maestro/03-meto.yaml` | `videos/03-meto.mp4` | `3da222b4cccc9f2ad317f32c18f1051edc200e2c462c992129306f65d264ecae` | 6.2M | 33 | 0 |
| D — Doctor marketplace | `.maestro/04-marketplace.yaml` | `videos/04-marketplace.mp4` | `43a3d46ea8bbbc21dff805b54a5374b4e42806eae14f65f70cf5bf08495f2868` | 5.7M | 30 | 0 |

## What each journey proves

- **A** — QA document‑fixture entry (dev/staging only) → real upload‑session →
  quarantine → finalize → OCR → candidate review → per‑candidate confirm →
  promotion. Production camera flow untouched; fixture route 404s when
  `qa_fixture_enabled` is off. Each fixture ingest is a distinct accepted doc
  (per‑call nonce), so the flow is re‑runnable.
- **B** — active medication list → detail with linked schedule → reminders screen →
  mark a due dose **taken** → adherence summary updates. Uses the existing
  schedule/occurrence/adherence backend (no parallel medication model). Requires a
  freshly seeded due dose (`_ensure_due_dose`, delete‑then‑recreate at now−10 min).
- **C** — consent‑aware Meto entry (gate when `ai_processing` not granted) → chat →
  reply rendered; escalation + retry covered at hook level in `metoChat.test.ts`.
  Confirmed‑data‑only context enforced server‑side.
- **D** — marketplace browse → doctor detail → book (mock pay + consent) →
  consultation detail. Review form correctly absent for a `REQUESTED` consultation;
  notes 403‑before‑completion is non‑fatal to the detail view.

## Verifying a file against this manifest

```bash
cd docs/patient-platform-program/evidence/native-j2j5/videos
shasum -a 256 -c <<'EOF'
554f8e9d39a3804c586da0b5e262761803312140854c039696aace68eb5dc6b3  01-documents.mp4
082515385735c76debebfe56f91f41cccf478c8bb82bdcc5d7d8ed049499d8de  02-medication.mp4
3da222b4cccc9f2ad317f32c18f1051edc200e2c462c992129306f65d264ecae  03-meto.mp4
43a3d46ea8bbbc21dff805b54a5374b4e42806eae14f65f70cf5bf08495f2868  04-marketplace.mp4
EOF
```
