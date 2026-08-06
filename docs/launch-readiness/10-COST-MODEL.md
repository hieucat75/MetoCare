# 10 — Cost & Capacity Model (WS11)

**Date:** 2026-08-03 · **Status:** planning estimates (list prices, not billed actuals). Azure Container Apps (Southeast Asia / Singapore), consumption tier. Figures are order-of-magnitude for capacity planning, not a quote. Revisit against real Azure Cost Management once metering exists.

## Per-user monthly usage assumptions (pilot profile)

| Driver | Assumption / user / month | Basis |
|---|---|---|
| Documents uploaded | 4 | onboarding burst + occasional |
| OCR pages processed | 6 | multi-page labs |
| AI (Meto) messages | 20 | modest engagement |
| Document blob storage | 10 MB cumulative → ~120 MB/yr | photos/PDFs |
| Push/in-app notifications | 30 | reminders + adherence |
| API requests | ~1,500 | app usage |

**Cost driver ranking:** AI messages ≫ cloud-OCR (if ever enabled) > compute > storage > notifications. Local/mock OCR is $0 marginal (runs in-container); cloud OCR is the single largest *latent* cost and stays OFF until authorized.

## Cost model by scale (USD/month, estimates)

Assumes: ACA min-1 replica always-on (1 vCPU / 2 GiB) scaling on load; Postgres Flexible Server Burstable; Blob hot tier ($0.018/GB); Azure Monitor (~$2.3/GB ingest beyond 5 GB free); AI via OpenRouter (Sonnet-class ~$3/M in, ~$15/M out; ~1.5k in + 0.5k out per message ≈ **$0.012/message**); FCM/APNs push free; cloud OCR OFF (=$0).

| Component | 100 users | 500 users | 1,000 users | 10,000 users |
|---|---|---|---|---|
| ACA compute (backend) | ~$35 (min replica) | ~$70 | ~$130 | ~$900 (autoscale) |
| PostgreSQL | ~$15 (B1ms) | ~$60 (B2s) | ~$120 (B2ms/GP-small) | ~$450 (GP 4vCPU + HA) |
| Blob storage + ops | ~$1 | ~$5 | ~$10 | ~$120 |
| Bandwidth (egress) | ~$2 | ~$8 | ~$16 | ~$150 |
| AI / Meto (`AI_ASSISTANT` on) | ~$24 (100×20×$0.012) | ~$120 | ~$240 | ~$2,400 |
| Notifications (FCM/APNs) | $0 | $0 | $0 | $0 |
| Monitoring / logs | ~$0 (free tier) | ~$10 | ~$25 | ~$200 |
| Mobile distribution | Apple $99/yr + Play $25 once (amortized ~$10/mo) | ~$10 | ~$10 | ~$10 |
| **Subtotal (AI ON)** | **~$97/mo** | **~$293/mo** | **~$561/mo** | **~$4,430/mo** |
| **Subtotal (AI OFF)** | ~$73 | ~$173 | ~$321 | ~$2,030 |
| **Cost / user / month** | ~$0.97 | ~$0.59 | ~$0.56 | ~$0.44 |

**Cloud OCR (IF authorized):** Azure Document Intelligence read ≈ $1.50/1,000 pages → at 6 pages/user: 100u ≈ $0.90, 1ku ≈ $9, 10ku ≈ $90/mo. Small vs AI, but it is the PHI-to-cloud path — cost is not the gate, authorization is.

## Cost ceiling & abuse scenarios

| Abuse | Uncontrolled cost impact | Existing / needed control |
|---|---|---|
| Upload flood | Blob + OCR compute | upload rate-limit (verified present on documents + lab-OCR; WS2 to confirm scope) + upload-session expiry |
| AI message flood | AI $ (largest lever) | **needs** per-user/day AI message cap + token ceiling (recommend before `AI_ASSISTANT` wide-on) |
| Large-file / decompression bomb | storage + OCR CPU | content size + page/decompression limits (WS2 to confirm) |
| Notification spam loops | negligible ($0 push) | schedule idempotency (`ON CONFLICT DO NOTHING`) |

## Recommendations
1. **Add a per-user AI rate/token cap** before enabling Meto beyond the controlled pilot — it is the dominant and most abuse-sensitive cost.
2. Keep cloud OCR OFF; local/mock path is $0 marginal and privacy-preserving.
3. Set an Azure **budget alert** at 1.5× the projected subtotal for the active scale.
4. Retention policy (WS3) directly bounds storage/log cost — define document + log TTLs.
5. Pilot recommended ceiling: **50 users** → est. **< $80/mo** (AI on), trivially within budget; the limit is operational (support/monitoring), not cost.
