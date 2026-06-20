# MetoCare — Azure Container Apps STAGING — Implementation Plan

> **Plan-only.** Chưa provision resource, chưa sửa app code, chưa commit.
> **HARD CONSTRAINT:** DigitalOcean = PRODUCTION chính, **TUYỆT ĐỐI không đụng**.
> Azure = staging / platform-validation thứ cấp. Không share secret/DB string với DO.

**Chốt từ PTH:** ACA (không App Service) · Region Singapore (`southeastasia`) · REAL staging (Postgres+Timescale, **Alembic only**, không SQLite, không `create_all` runtime) · Budget **≤ $20/mo** · RG `rg-metocare-staging` · ACA default ingress/TLS · LLM/OCR mock-disabled.

Deliverables liên quan:
- `infra/azure-staging-provision.sh` — script provision (template, untracked).
- `infra/azure-staging.yml` — workflow draft (template, untracked, chưa active).

---

## Architecture roles (LOCKED) — cập nhật 2026-06-20: staging LIVE

| Platform | Role | Status |
|---|---|---|
| **DigitalOcean VPS** | **PRIMARY PRODUCTION** | Live — không đụng |
| **Azure Container Apps** | **SECONDARY STAGING** | **LIVE** (`azure-staging.yml`, `workflow_dispatch`) |
| ~~Azure App Service~~ | Deprecated | Archived → `.github/workflows/_archived/main_metocare.yml.archived` |

- ❌ **KHÔNG merge cả 2 approach.** DigitalOcean (Docker Compose + self-managed PostgreSQL/TimescaleDB TSL) và Azure ACA (managed PG Flexible Apache + serverless containers) là 2 stack độc lập, migration behavior khác nhau (TSL full CAGG vs Apache skip CAGG). Giữ tách biệt.
- ❌ **KHÔNG continue / reactivate App Service path.** Azure staging chỉ dùng Container Apps.
- ✅ DigitalOcean = PRIMARY, không bị staging làm phiền (merge main dùng `[skip ci]` hoặc opt-in `[deploy-do]` tag).

> Báo cáo deploy đầy đủ: [`AZURE_ACA_STAGING_REPORT.md`](./AZURE_ACA_STAGING_REPORT.md).

---

## Phần 1 — Azure resource architecture

| # | Resource | Tên | SKU/Tier | Ghi chú |
|---|---|---|---|---|
| RG | Resource Group | `rg-metocare-staging` | — | Region `southeastasia` (Singapore) |
| 1 | Log Analytics | `law-metocare-staging` | PerGB, 5GB free | ACA env bắt buộc cần workspace |
| 2 | Application Insights | `appi-metocare-staging` | workspace-based, **cap 1GB/day** | Lấy `connectionString` cho backend |
| 3 | Key Vault | `kv-metocare-stg` | Standard, RBAC mode | secrets: secret-key, encryption-keys, database-url |
| 4 | PostgreSQL Flexible | `pg-metocare-stg` | **B1ms** Burstable, 32GB, PG16 | TimescaleDB qua `azure.extensions` + `shared_preload_libraries` |
| 5 | Storage (Blob) | `stmetocarestg` | Standard_LRS, Hot | container `lab-docs`, no public access |
| 6 | ACA Environment | `cae-metocare-staging` | Consumption | scale-to-zero capable |
| 7 | Backend app | `ca-metocare-backend` | 0.5 vCPU / 1.0Gi, min0/max2 | system-assigned MI |
| 8 | Frontend app | `ca-metocare-frontend` | 0.25 vCPU / 0.5Gi, min0/max1 | Next.js |
| 9 | Migrate Job | `cj-metocare-migrate` | one-shot ACA Job | cmd `alembic upgrade head` |

**Registry:** dùng **GHCR** (đã có sẵn pipeline GHCR ở workflow cũ) → **$0**, thay vì ACR Basic (+$5/mo, ăn 25% budget). MI/GITHUB_TOKEN pull được. → ACR DEFER.

**Redis:** **DEFER hoàn toàn** — `app/core/ratelimit.py` chọn backend `redis` sẽ `raise` (chưa implement). Staging chạy `MCP_RATELIMIT_BACKEND=memory`. Cấp Redis bây giờ = trả tiền cho thứ chưa dùng.

**Managed Identity wiring:**
- Backend system-assigned MI → role **Key Vault Secrets User** (đọc secret) + **Storage Blob Data Contributor** (lab-docs).
- ACA secret dùng `keyvaultref:...,identityref:system` → env map `secretref:`.
- GHCR pull: registry credential GHCR PAT hoặc public image (staging).

**Auto-stop PG:** B1ms hỗ trợ stop/start; lên lịch stop ngoài giờ qua GitHub Actions cron (`az postgres flexible-server stop/start`) để giảm compute ~60–75%.

---

## Phần 2 — Budget breakdown (mục tiêu ≤ $20/mo, Singapore)

| Service | SKU | Giả định | Ước tính/mo |
|---|---|---|---|
| PostgreSQL B1ms (compute) | Burstable 1vCPU/2GiB | auto-stop → ~160 active h/mo | **~$3** |
| PostgreSQL storage | 32 GB | luôn tính tiền (kể cả stop) | **~$4** |
| PostgreSQL backup | 7-day, ≤100% | trong free backup | ~$0 |
| Container Apps | backend+frontend | scale-to-zero, traffic test thấp → trong free grant (180k vCPU-s + 360k GiB-s) | **~$1–2** |
| Blob Storage | LRS Hot, vài GB | lab docs test | **<$1** |
| Key Vault | Standard | ít operations | **~$0** |
| Application Insights | capped 1GB/day | trong 5GB free | **$0** |
| Log Analytics | PerGB | 5GB free | **$0** |
| ACR | — | **SKIP, dùng GHCR** | **$0** |
| **TỔNG** | | | **~$9–11/mo** |

**Headroom ~$9** dưới cap $20. Cost-saving đã áp dụng: B1ms+auto-stop (halve compute), ACA scale-to-zero, GHCR thay ACR (−$5), App Insights free cap, Blob minimal.
**Sàn không nén được:** PG storage ~$4 (tính cả khi stop). Nếu cần rẻ hơn nữa → fallback Postgres-in-ACA (Phần 8) nhưng mất managed backup.

---

## Phần 3 — CI/CD plan (`infra/azure-staging.yml`)

3 job nối tiếp, thay thế `main_metocare.yml`:
1. **build** — build & push backend + frontend image lên GHCR (tag `sha` + `latest`).
2. **migrate** — `az containerapp job update --image … && job start` chạy **`alembic upgrade head`** (one-shot Job, dùng cùng image backend + secretref `MCP_DATABASE_URL`). Poll tới Succeeded/Failed. **Đây là nơi duy nhất tạo schema** — không còn `create_all` runtime.
3. **deploy** — `az containerapp update --image` tạo revision mới cho backend + frontend; health gate poll `/health`. ACA giữ revision khỏe trước đó nếu revision mới fail (auto-rollback).

**Auth:** GitHub **OIDC → Azure federated credential** (`azure/login@v2` với `AZURE_CLIENT_ID/TENANT_ID/SUBSCRIPTION_ID`). **Không** long-lived secret (bỏ kiểu `GHCR_PAT`/publish-profile cũ). Cần tạo app registration + federated credential (subject = repo `main` / `workflow_dispatch`).

**Approval gate:** staging deploy tự động khi dispatch; production (DO) **ngoài phạm vi** — sẽ thêm GitHub Environment protection rule riêng khi mở rộng, không đụng tới đây.

---

## Phần 4 — Migration path từ App Service hiện tại

- **Parallel run:** giữ App Service `MetoCare` (rg-metocare-dev, Malaysia West, SQLite) **chạy song song** trong lúc validate ACA. Không tắt vội.
- **Data migration:** **fresh start** trên staging — App Service hiện chỉ là SQLite mock/dev, không có dữ liệu thật cần giữ. Schema dựng bằng `alembic upgrade head` trên DB trống. **Không export SQLite → PG.**
- **Workflow:** `main_metocare.yml` → **rename `main_metocare.yml.archived`** (ngừng auto-deploy App Service), kích hoạt `azure-staging.yml` (chuyển từ `infra/` vào `.github/workflows/`).
- **Cleanup App Service:** chỉ sau khi ACA pass toàn bộ acceptance (Phần 7) → xóa App Service + rg-metocare-dev để khỏi phát sinh cost.

---

## Phần 5 — Health / Readiness / Secrets contracts

**Endpoints (đã verify trong code):**
- `GET /health` (root, `app/main.py`) — **liveness**, không chạm DB.
- `GET /api/v1/health` (`routes/system.py`, mounted no-prefix under `/api/v1`) — **readiness**, `SELECT 1`, trả **503** khi DB chết → đúng chuẩn LB. (KHÔNG phải `/api/v1/system/health` — system.router không có prefix riêng.)
- `GET /metrics` — Prometheus (`app/core/metrics.py`), gated bởi `MCP_METRICS_ENABLED`.
- ⚠️ **Không có `/ready`** — không cần thêm code: map ACA readiness probe vào `/api/v1/health`, liveness vào `/health`.

**ENV vars staging (từ `.env.example`):**

| Var | Nguồn | Giá trị |
|---|---|---|
| `MCP_ENV` | plain | `staging` |
| `MCP_DEBUG` | plain | `false` |
| `MCP_DATABASE_URL` | **Key Vault** | `postgresql+psycopg://…@pg-…:5432/metocare_staging?sslmode=require` |
| `MCP_SECRET_KEY` | **Key Vault** | random 48-byte |
| `MCP_ENCRYPTION_KEYS` | **Key Vault** | Fernet key(s) |
| `MCP_STORAGE_MODE` | plain | `s3` (Blob qua MI/S3-compat) |
| `MCP_S3_*` | plain/KV | Blob endpoint/bucket |
| `MCP_AI_MODE` / `MCP_LLM_PROVIDER` | plain | `mock` / `mock` |
| `MCP_OCR_MODE` / `MCP_OCR_WORKER_ENABLED` | plain | `mock` / `false` |
| `MCP_RAG_ENABLED` | plain | `false` |
| `MCP_RATELIMIT_BACKEND` | plain | `memory` |
| `MCP_ENABLE_DOCS` | plain | `false` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | plain | từ App Insights |

**Key Vault refs (ACA syntax):**
```
az containerapp secret set … --secrets \
  mcp-database-url=keyvaultref:https://kv-metocare-stg.vault.azure.net/secrets/mcp-database-url,identityref:system
az containerapp update … --set-env-vars MCP_DATABASE_URL=secretref:mcp-database-url
```

> ⚠️ **Gap cần xác minh ở Phase A:** `MCP_STORAGE_MODE=s3` hiện là **skeleton** trong code (`.env.example` ghi s3/minio = skeleton). Nếu S3 adapter chưa hoàn chỉnh → tạm để `MCP_STORAGE_MODE=local` + ACA volume, hoặc hoàn thiện adapter (code change, cần approve riêng). Blob vẫn provision sẵn.

---

## Phần 6 — Networking + Security

- **Ingress:** ACA external HTTPS auto (cert managed, `*.<region>.azurecontainerapps.io`). Không custom domain.
- **PG access:** dùng **public access + firewall rule** cho phép Azure services / ACA outbound. **Không** Private Endpoint/VNET (tốn NAT GW + delegated subnet, vỡ budget $20). `sslmode=require` bắt buộc.
- **WAF / Front Door:** **DEFER** — không trong budget staging.
- **Isolation:** không có resource/secret nào tham chiếu DigitalOcean. KV + DB string Azure tách biệt hoàn toàn DO prod.

---

## Phần 7 — Acceptance criteria staging

- [ ] `GET /health` → 200.
- [ ] `GET /api/v1/health` → 200 (DB ok); 503 khi PG stopped.
- [ ] `GET /metrics` → text/plain Prometheus format.
- [ ] PG: `CREATE EXTENSION timescaledb` thành công; `create_hypertable` trên `health_metrics` chạy (migration `85416e7…`).
- [ ] `alembic upgrade head` chạy sạch trên DB cold (toàn bộ ~26 revisions).
- [ ] Backend đọc được secret từ Key Vault (start không lỗi config).
- [ ] Frontend serve trên ACA URL.
- [ ] Cost Management cho thấy run-rate ≤ $20/mo.
- [ ] Revision unhealthy → ACA tự giữ revision cũ (auto-rollback verify).

---

## Phần 8 — Risks + mitigations

| Risk | Mức | Mitigation |
|---|---|---|
| **TimescaleDB community trên Azure PG Flexible**: CAGG/compression có thể giới hạn so với migration kỳ vọng | **Cao** | Verify sớm Phase A: enable extension + thử `create_hypertable` + CAGG `health_metric_daily`. Fallback: **Postgres-in-ACA** dùng image `timescale/timescaledb:latest-pg16` (như `docker-compose.internal.yml`) — mất managed backup nhưng full Timescale |
| **B1ms cold start sau auto-stop** (~30–60s) làm chậm test UX | Trung bình | Lịch start trước giờ test; readiness probe 503 → client retry |
| **Budget $20 rất tight** | Trung bình | Sàn là PG storage ~$4; nếu vượt → giảm storage, tắt PG khi không test, hoặc fallback Postgres-in-ACA |
| **`MCP_STORAGE_MODE=s3` skeleton** | Trung bình | Phase A xác minh adapter; tạm `local`+volume nếu chưa xong |
| **OIDC federated credential setup** mới, dễ sai subject | Thấp | Test bằng `workflow_dispatch` trước khi bật `push` |
| **DO prod isolation** | Critical | Không reuse secret/DB string; review script đảm bảo zero DO reference |

---

## Phần 9 — Implementation phases

| Phase | Thời lượng | Việc | Output |
|---|---|---|---|
| **A** | ~1–2h | Chạy `infra/azure-staging-provision.sh` (sau khi review + fill secret). **Verify TimescaleDB ngay** | Resources live, Timescale confirmed |
| **B** | ~1h | Tạo Azure app registration + GitHub OIDC federated credential; move `azure-staging.yml` vào `.github/workflows/`; tạo ACA migrate Job | CI/CD sẵn sàng |
| **C** | ~1h | `workflow_dispatch` first deploy → build → `alembic upgrade head` → deploy → health gate | App live, schema migrated |
| **D** | ~30m | Budget alert (Cost Management $20), PG auto-stop cron, verify acceptance | Monitoring on |

> Mỗi phase cần approve trước khi chạy — đây là plan, chưa execute.

---

## Phần 10 — Deliverables

- ✅ `docs/agent/AZURE_CONTAINER_APPS_STAGING_PLAN.md` (file này, untracked).
- ✅ `infra/azure-staging-provision.sh` (template, untracked).
- ✅ `infra/azure-staging.yml` (workflow draft, untracked, chưa active).
- ✅ Cost estimate inline (Phần 2).
