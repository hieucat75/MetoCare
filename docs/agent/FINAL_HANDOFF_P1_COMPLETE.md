# FINAL HANDOFF — P1 COMPLETE (#1–#8 + CI)

> Tác giả: Claude Code · Ngày: 2026-06-13 · Nhánh: `main` (Sprint 0 tag `v0.1.0-sprint0-foundation`)
> **Toàn bộ P1 hoàn tất.** DỪNG đợi user review. **P2 để dành cho fresh session.**

---

## 1. Tổng quan

P1 hoàn tất 8 mốc + CI trên `main`, mỗi mốc ≥1 commit, test xanh sau từng commit.
Tổng so với `v0.1.0-sprint0-foundation`: **53 files changed, +3402 / -104**.
Test: **96 passed, 1 skipped** (skip = TimescaleDB integration, cần Postgres). 5 migration Alembic. 15 test file.

## 2. Toàn bộ P1 (#1–#8)

| Mốc | Nội dung | Commit |
|-----|----------|--------|
| #1 | Alembic + Postgres/TimescaleDB (hypertable + CAGG, dialect-guard) | `396ae12` |
| #2 | JWT + Argon2 + RBAC (thay `X-User-Id`) | `9cee651` |
| #3 | Field-level PHI encryption (Fernet/MultiFernet) | `2a4e420` |
| #4 | Structured logging (no-PHI) + metrics + audit retention | `33d4a1a` |
| #5 | Refresh tokens + MFA/TOTP | `a5be99b` |
| #6 | Rate limiting + account lockout | `a15c9bb` |
| #7 | Ép MFA enrollment cho doctor/admin | `6cd289f` |
| #8 | Refresh token reuse detection (token families) | `d9d8cab` |
| CI | GitHub Actions (ruff + alembic + pytest, matrix 3.13/3.14) | `84e2e6b` |

## 3. Ba mốc của phiên này (chi tiết)

### P1 #6 — Rate limiting + lockout
- `app/core/ratelimit.py`: `RateLimiter` abstract + `InMemoryRateLimiter` (token bucket) + factory theo `MCP_RATELIMIT_BACKEND` (redis = placeholder, raise `NotImplementedError` — pluggable, chưa cần Redis thật).
- `enforce_rate_limit` áp cho `/auth/login`, `/auth/register`, `/auth/refresh`, `/auth/mfa/verify` → 429 khi vượt.
- `LockoutManager`: khóa account sau N login fail (default 5), cooldown 15 phút; **reset khi login thành công** (gồm MFA) hoặc **admin unlock** (`POST /admin/unlock-account`, role+MFA gated, audit `admin_action`).
- Config-driven (capacity/window/max-failures/cooldown); `.env.example` cập nhật.
- Test: token-bucket + lockout unit, 429, lockout→reset→admin-unlock, endpoint ngoài auth không bị limit.

### P1 #7 — Ép MFA enrollment
- `MFA_REQUIRED_ROLES` (doctor/clinic_admin/internal_admin/medical_reviewer/super_admin) trong `models.user`.
- Access token mang claim `mfa_enrollment_required` (true nếu role thuộc nhóm trên & chưa bật MFA).
- `MfaEnrollmentMiddleware`: chặn **mọi** endpoint (403 `mfa_enrollment_required`) trừ allowlist (`/auth/mfa/*`, `/auth/me`, `/auth/logout`, `/auth/login`, `/auth/register`, `/auth/refresh`, `/health`, `/metrics`, docs) cho tới khi enroll. Observability middleware bọc ngoài để vẫn log 403.
- Test: doctor mới → bị chặn → enroll+verify → re-login → bỏ chặn; patient **không** bị ép.

### P1 #8 — Refresh token reuse detection
- `RefreshToken` thêm `family_id` + `generation`: 1 login = 1 family; mỗi rotation tăng generation.
- Dùng lại token đã rotate (đã revoke) → **revoke toàn bộ family** (tín hiệu compromise) + 401.
- Audit `refresh_token_reuse_detected`, `severity=high`, `outcome=deny` (cột `severity` mới ở AuditLog).
- Test: rotation chain OK, reuse → cả family chết, audit high-severity ghi đúng.

## 4. Kết quả kiểm thử (thật)

```
pytest:                 96 passed, 1 skipped, 1 warning (third-party starlette/httpx)
ruff check:             All checks passed!  (app, tests, alembic/env.py)
compileall:             OK
alembic up/down chain:  5 migrations, clean & reversible on SQLite
CI yaml:                 valid (matrix py3.13/3.14)
```
Skip: `test_postgres_hypertable_ingest_and_trend` (đặt `MCP_TEST_POSTGRES_URL`).

## 5. Trạng thái bảo mật P1 (tổng kết)

| Lớp | Trạng thái |
|-----|-----------|
| Mật khẩu | Argon2id |
| Token | JWT HS256 access (15') + refresh revocable (rotation + reuse-detection + family revoke) |
| MFA | TOTP + backup codes (Argon2, single-use); ép enroll cho doctor/admin; gate endpoint nhạy cảm |
| RBAC | `require_roles` deny-by-default + `require_mfa` |
| Brute-force | rate limit (token bucket) + account lockout + admin unlock |
| PHI at rest | Fernet field-level encryption (MultiFernet rotation) |
| Audit | append-only + severity + retention theo category + reuse-detection log |
| Logging | JSON no-PHI (whitelist field) + request_id correlation |
| Secrets | toàn bộ qua env; dev default là placeholder + cảnh báo prod |

## 6. Hạn chế còn lại / Risk

- **TimescaleDB chưa chạy DB thật** (Docker không có trong môi trường) — migration #2 guard + verify tĩnh; cần `MCP_TEST_POSTGRES_URL`.
- **CI chưa chạy thật** (chưa push GitHub) — yaml đã validate.
- **Rate limit/lockout in-memory** → không chia sẻ giữa nhiều instance; cần Redis backend (interface đã sẵn) khi scale ngang.
- **Refresh token cleanup job** (xóa revoked/expired) chưa có.
- **Email chưa mã hóa** (cần cho login lookup); blind-index chưa có.
- MFA secret hiển thị 1 lần khi enroll (đúng thiết kế); chưa có recovery flow ngoài backup codes.

## 7. Recommended P2 Prioritization

> P2 là big chunk — **nên làm ở fresh session** để giữ chất lượng. Thứ tự đề xuất:

1. **P2 #1 — LLM Gateway + RAG**: provider abstraction + rate/cost guard + safety-prompt injection; RAG retrieval skeleton (pgvector) chỉ guideline đã duyệt. **Không gọi LLM thật** (mock provider mặc định). Mọi response vẫn qua guardrail input/output đã có.
2. **P2 #2 — OCR worker**: background queue (Redis/RQ hoặc tương đương), mock OCR provider, pipeline lab document thật (upload→queue→OCR→LabResult→interpret) thay cho mock đồng bộ hiện tại.
3. **P2 #3 — Next.js portal**: auth flow (login/MFA/refresh) + Doctor/Patient health timeline UI; consume API v1.
4. **P2 #4 — Flutter mobile**: auth + health tracking screens (metric entry, trend, metabolic score).

Trước/song song P2: đẩy GitHub để CI chạy; xác minh TimescaleDB trên Docker; thêm Redis (rate limit + queue); refresh-token cleanup job; rate limiting cho login brute-force phân tán.

## 8. Checklist tuân thủ (phiên này)

| Ràng buộc | Trạng thái |
|-----------|-----------|
| Test cũ (84) vẫn xanh sau mỗi commit | ✅ (nay 96; test rotation cũ điều chỉnh theo hành vi reuse-detection mới) |
| Không thêm dependency nặng (Redis chỉ interface) | ✅ (chỉ pyotp đã có; ratelimit thuần stdlib) |
| Không hardcode config | ✅ (env-driven; `.env.example` cập nhật) |
| Update `.env.example` | ✅ (ratelimit + lockout) |
| Mỗi mốc 1 commit | ✅ |
| Không bắt đầu P2 | ✅ |

---

- **MERGE_ALLOWED: YES** (đã ở `main`; mỗi mốc committed, 96 test xanh).
- **REASON:** P1 #6–#8 hoàn tất an toàn, không phá test cũ (test rotation điều chỉnh hợp lý theo reuse-detection), không phá backward-compat (SQLite vẫn chạy zero-config), tuân thủ đủ ràng buộc (no hardcode, Redis chỉ interface, no heavy dep). TimescaleDB & CI cần hạ tầng thật (thiếu Docker/GitHub remote) — đã guard + validate, không chặn merge.
- **NEXT_ACTION:** User review P1 hoàn chỉnh (#1–#8 + CI). Khi sẵn sàng cho P2, **mở fresh session** và bắt đầu **P2 #1 (LLM Gateway + RAG)** theo prioritization mục 7.
