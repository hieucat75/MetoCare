# FINAL HANDOFF — P1 COMPLETE (#1–#5 + CI)

> Tác giả: Claude Code · Ngày: 2026-06-12 · Nhánh: `main` (Sprint 0 tag `v0.1.0-sprint0-foundation`)
> Tổng hợp toàn bộ P1. **DỪNG đợi user review.**

---

## 1. Tổng quan

Hoàn tất **5 phase P1 + CI** trên `main`, mỗi phase ≥1 commit, test xanh sau từng commit.
Tổng so với `v0.1.0-sprint0-foundation`: **46 files changed, +2675 / -104**.
Test: **84 passed, 1 skipped** (skip = TimescaleDB integration, cần Postgres). 4 migration Alembic.

## 2. Commits (P1)

| Commit | Nội dung |
|--------|----------|
| `396ae12` | **P1#1** Alembic + Postgres/TimescaleDB (hypertable + CAGG, dialect-guard) |
| `9cee651` | **P1#2** JWT + Argon2 + RBAC (thay `X-User-Id`) |
| `2a4e420` | **P1#3** Field-level PHI encryption (Fernet/MultiFernet) |
| `a963399` | docs handoff P1 (#1–#3) |
| `33d4a1a` | **P1#4** Structured logging + metrics + audit retention |
| `a5be99b` | **P1#5** Refresh tokens + MFA/TOTP |
| `84e2e6b` | **CI** GitHub Actions (ruff + alembic + pytest, matrix 3.13/3.14) |

## 3. P1 #4 — Audit retention + Observability

- **Structured logging** (`app/core/logging.py`): JSON, **no-PHI** — chỉ metadata an toàn + `request_id`/`user_id` (UUID, không PHI). Whitelist field chống rò rỉ PHI qua log ad-hoc.
- **Middleware** (`ObservabilityMiddleware`): sinh/propagate `X-Request-ID`, access log, metrics; `current_user` ghi `request.state.user_id` để correlate.
- **Metrics** (`app/core/metrics.py`, no dependency): `http_requests_total`, `http_request_duration_seconds` (histogram), `http_server_errors_total`. Endpoint `/metrics` (Prometheus text), gate bằng `MCP_METRICS_ENABLED`.
- **Audit retention** (`audit_retention.purge_expired`): TTL theo category (auth 365 / data_access 730 / admin 1095 ngày), job purge idempotent. AuditLog vẫn append-only khi vận hành; purge là lifecycle policy.
- **Test:** request-id echo/generate, metrics counters, **JSON access log no-PHI assertion**, retention purge theo category.

## 4. P1 #5 — Refresh token + MFA

- **Refresh token:** JWT riêng (`type=refresh`, TTL 7 ngày), **persist + revocable** qua bảng `refresh_tokens` (jti, expires_at, revoked_at, mfa). **Rotation on use** (token cũ bị revoke; reuse → 401). Endpoint `/auth/refresh`, `/auth/logout`.
- **MFA TOTP** (`pyotp`): enroll (secret + otpauth URI + 10 backup codes), verify, enable. **TOTP secret mã hóa at rest** (EncryptedString); **backup codes Argon2-hashed, single-use**.
- **Login:** nếu `mfa_enabled` → bắt buộc TOTP hoặc backup code; access token mang claim `mfa`.
- **MFA gate:** `require_mfa` dependency; `/admin/audit-logs` yêu cầu role admin **và** session MFA-verified.
- **Test:** refresh rotation/reuse/logout, TOTP login, backup-code login (single-use), MFA gate admin (mfa=false→403, mfa=true→200).

## 5. CI

- `.github/workflows/ci.yml`: trigger push `main` + PR; matrix **Python 3.13 + 3.14**; steps: `ruff check` → `alembic upgrade head` + `downgrade base` (SQLite) → `pytest`. Pip cache theo `requirements-dev.txt`. CI badge (đường dẫn tương đối) trong README.
- *Lưu ý:* workflow chưa chạy thực tế ở đây (chưa có GitHub remote/push). Sẽ active khi repo push lên GitHub.

## 6. Kết quả kiểm thử (thật)

```
pytest:                 84 passed, 1 skipped, 1 warning (third-party starlette/httpx)
ruff check:             All checks passed!  (app, tests, alembic/env.py)
compileall:             OK
alembic up/down chain:  4 migrations, clean & reversible on SQLite
CI yaml:                 valid (matrix 3.13/3.14)
```
14 test files. Skip: `test_postgres_hypertable_ingest_and_trend` (đặt `MCP_TEST_POSTGRES_URL`).

## 7. Quyết định kỹ thuật mới (P1 #4–#5)

1. **Metrics tự cài, không thêm dependency nặng** (prometheus_client không cần cho foundation).
2. **No-PHI logging bằng whitelist field** — an toàn hơn blacklist; PHI không thể lọt qua log ad-hoc.
3. **Refresh rotation + DB blacklist** (không chỉ stateless JWT) để revoke được — đánh đổi 1 query/refresh lấy khả năng thu hồi.
4. **MFA claim trong access token** (`mfa: bool`) → gate endpoint nhạy cảm theo "đã xác thực 2 lớp", tách khỏi "đã enroll".
5. **Backup codes Argon2** (không sha256) vì entropy mỗi code vừa phải; verify duyệt ≤10 code.
6. Migration dùng kiểu DB nền (`sa.Text()`) cho cột encrypted → migration tự chứa, không phụ thuộc app code.

## 8. Hạn chế còn lại / Risk

- **TimescaleDB chưa chạy trên DB thật** (Docker daemon không có trong môi trường này). Migration #2 guard + verify tĩnh; cần `MCP_TEST_POSTGRES_URL` trên máy có Docker để xác nhận hypertable/CAGG.
- **CI chưa chạy thật** (chưa push GitHub) — yaml đã validate.
- **MFA bắt buộc khi login** chỉ kích hoạt khi `mfa_enabled=true`; **chưa ép** doctor/admin phải enroll (mới ép ở tầng truy cập endpoint nhạy cảm qua `require_mfa`). Nếu muốn cứng hơn: chặn login doctor/admin chưa enroll, hoặc bắt enroll lần đầu.
- **Rate limiting** cho login/MFA brute-force: chưa (Redis-based, để sau).
- **Email chưa mã hóa** (cần cho login lookup); **blind index** chưa có.
- **Refresh token cleanup**: revoked/expired rows chưa có job purge riêng (audit có).

## 9. Việc tiếp theo (đề xuất — CHỜ USER REVIEW)

- **Rate limiting** (Redis) cho auth/MFA + lockout.
- **Ép MFA enrollment** cho doctor/admin (chặn hoặc onboarding bắt buộc).
- **Refresh token retention/cleanup job** + reuse-detection (revoke cả family nếu phát hiện reuse).
- **Xác minh TimescaleDB thật** (`docker compose up postgres` + `MCP_TEST_POSTGRES_URL`).
- **Đẩy lên GitHub** để CI chạy; thêm branch protection.
- P2: LLM Gateway + RAG, OCR worker, booking flow, Next.js/Flutter.

## 10. Checklist tuân thủ

| Ràng buộc | Trạng thái |
|-----------|-----------|
| 71 test cũ vẫn xanh sau mỗi commit | ✅ (nay 84 pass; behaviors giữ nguyên) |
| Không đụng `~$ ....docx` | ✅ (gitignored) |
| Mock TOTP/refresh trong test, không external | ✅ (pyotp local, không gọi mạng) |
| Refresh/MFA secret qua env, không hardcode | ✅ (secret_key/refresh_ttl qua env; secret TOTP mã hóa DB) |
| Cập nhật `.env.example` mỗi khi thêm config | ✅ (observability + retention; auth dùng config sẵn) |
| Mỗi phase 1 commit, test xanh | ✅ |

---

- **MERGE_ALLOWED: YES** (đã ở `main`; mỗi phase committed, test xanh).
- **REASON:** P1 #4, #5 + CI hoàn tất an toàn, không phá test cũ (84 pass), không phá backward-compat (SQLite vẫn chạy zero-config), tuân thủ đủ ràng buộc bảo mật/secret/no-PHI. Chỉ TimescaleDB + CI cần xác minh trên hạ tầng thật (môi trường này thiếu Docker/GitHub remote) — đã guard + validate, không chặn merge.
- **NEXT_ACTION:** User review 3 mốc (P1#4, P1#5, CI). Nếu OK → chọn hướng tiếp: **rate limiting + ép MFA enrollment**, hoặc **xác minh TimescaleDB/đẩy CI lên GitHub**, hoặc bắt đầu **P2** (LLM Gateway/OCR/booking/frontend).
