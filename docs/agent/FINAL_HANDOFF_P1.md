# FINAL HANDOFF — P1 (Foundation Hardening)

> Tác giả: Claude Code · Ngày: 2026-06-12 · Nhánh: `main` (Sprint 0 đã merge + tag `v0.1.0-sprint0-foundation`)
> Phạm vi: 3 phase P1 (#1 Database, #2 Auth, #3 Encryption). Dừng tại đây để user review trước khi đi tiếp.

---

## 1. Tóm tắt

Sau Sprint 0, đã thực thi **3 phase P1** trên `main`, mỗi phase là 1 commit, test xanh sau từng phase.
Tổng so với `v0.1.0-sprint0-foundation`: **30 files changed, +1506 / -100**. Test: **71 passed, 1 skipped**
(skip = TimescaleDB integration, cần Postgres). 56 test Sprint 0 vẫn xanh (đã thích nghi cơ chế auth mới).

## 2. Ba commit

| # | Commit | Nội dung |
|---|--------|----------|
| P1#1 | `396ae12` feat(db) | Alembic + Postgres/TimescaleDB; 3 migration; hypertable + CAGG (guard dialect) |
| P1#2 | `9cee651` feat(auth) | JWT (PyJWT) + Argon2 + RBAC; thay placeholder `X-User-Id`; auth/admin routes |
| P1#3 | `2a4e420` feat(security) | Field-level PHI encryption (Fernet/MultiFernet); migration #3; re-encrypt job |

## 3. Chi tiết từng phase

### P1 #1 — Database hóa thật
- **Alembic** wired vào app settings + `Base.metadata` (`alembic/env.py`); URL từ `MCP_DATABASE_URL`, không hardcode.
- **3 migration:** (1) 14 entity lõi; (2) TimescaleDB — `health_metrics` → hypertable + continuous aggregate `health_metric_daily` (1-day bucket, phục vụ trend 7/30/90/365 ngày) + compression/retention; (3) encrypt PHI (xem P1#3).
- **Portable:** server_default đổi sang `CURRENT_TIMESTAMP` (chạy cả SQLite lẫn Postgres). Migration #2 **no-op trên SQLite** (guard `dialect.name == 'postgresql'`).
- **Switch SQLite↔Postgres** chỉ bằng env. App auto-create tables **chỉ trên SQLite**; Postgres bắt buộc `alembic upgrade head`.
- **Test:** roundtrip up/down trên SQLite (clean & reversible); hypertable ingest+trend trên Postgres (skip nếu thiếu `MCP_TEST_POSTGRES_URL`).

### P1 #2 — Auth thật (JWT + Argon2 + RBAC)
- **Argon2id** (`argon2-cffi`) thay PBKDF2; **JWT HS256** (`PyJWT`) có `exp`/`iat`/`role`.
- **Endpoints:** `POST /auth/register` (chỉ tạo role patient — chống tự nâng quyền), `POST /auth/login`, `GET /auth/me`.
- **RBAC:** `require_roles(...)` deny-by-default; `GET /admin/audit-logs` chỉ `internal_admin`/`super_admin`.
- **deps:** `HTTPBearer` → `CurrentUser(id, role)`. Routes dữ liệu bệnh nhân giữ consent-gate; principal nay là `user.id` từ JWT.
- **secret_key** dev default ≥32 ký tự (tránh JWT insecure-key warning); cảnh báo nếu chạy prod với default/ngắn.
- **Test:** register/login/me, sai mật khẩu, chặn tự nâng quyền, role gate (patient→admin = 403, admin = 200), token hết hạn = 401.

### P1 #3 — Field-level encryption cho PHI
- **`EncryptedString`** TypeDecorator (Fernet): mã hóa khi ghi / giải mã khi đọc, trong suốt với ORM; ciphertext base64 lưu cột TEXT.
- **MultiFernet** hỗ trợ **key rotation** không downtime (key đầu mã hóa, mọi key giải mã).
- **Trường mã hóa:** `User.full_name`; `PatientProfile`: full_name, dob, phone, address, known_conditions, allergies, family_history, lifestyle_profile; `LabDocument.raw_text`. Trường phi-định-danh (gender/height/weight/waist) giữ plaintext để phục vụ truy vấn/scoring.
- **Key** từ `MCP_ENCRYPTION_KEYS` env (không hardcode prod); dev default là placeholder rõ ràng, cảnh báo nếu prod.
- **Data migration:** `phi_migration.encrypt_existing_phi()` — idempotent, re-encrypt dữ liệu plaintext cũ (đọc raw SQL, bỏ qua nếu đã là ciphertext).
- **Test:** roundtrip, ciphertext-at-rest (đọc raw cột ≠ plaintext), PHI hồ sơ mã hóa, key rotation, data-migration, thiếu key → lỗi.

## 4. Kết quả test (thật)

```
pytest:                 71 passed, 1 skipped, 1 warning (third-party starlette/httpx)
ruff check:             All checks passed!   (app, tests, alembic/env.py; migrations auto-gen excluded)
compileall:             OK
alembic up/down chain:  3 migrations, clean & reversible on SQLite (exit 0)
```
11 test files. Skip duy nhất: `test_postgres_hypertable_ingest_and_trend` (đặt `MCP_TEST_POSTGRES_URL` để chạy).

## 5. Quyết định kỹ thuật quan trọng

1. **Một codebase, hai backend:** SQLite (dev/test, zero-infra) và Postgres/TimescaleDB (prod). TimescaleDB-specific để trong migration guard theo dialect.
2. **CAGG 1-day duy nhất** thay vì 4 view 7/30/90/365 — idiom TimescaleDB (1 aggregate mịn, nhiều cửa sổ query). `trend()` hiện query raw hypertable (chạy cả 2 backend); có thể tối ưu sang CAGG sau.
3. **Hypertable PK** mở rộng thành `(id, measured_at)` ở tầng vật lý (yêu cầu TimescaleDB); ORM vẫn map `id` (UUID) làm khóa logic.
4. **dob lưu encrypted ISO string** thay vì Date (vì mã hóa cần cột TEXT). Cân nhắc lại nếu cần truy vấn theo tuổi.
5. **Email giữ plaintext** (cần cho login lookup); blind-index cho email là việc sau nếu muốn mã hóa.
6. **Argon2/JWT/Fernet** — chuẩn production; token là access-only (refresh token + MFA chưa làm).

## 6. Hạn chế còn lại / Risk

- **TimescaleDB chưa test trên DB thật** trong môi trường này (Docker daemon không chạy). Migration #2 viết theo best practice + guard, verify tĩnh; cần chạy `MCP_TEST_POSTGRES_URL` trên máy có Docker để xác nhận hypertable/CAGG/compression.
- **Refresh token + MFA** chưa có (chỉ access token 15 phút). MFA bắt buộc cho doctor/admin theo doctrine — chưa làm.
- **Email chưa mã hóa**; **blind index** chưa có.
- **Key management** dùng env; production cần secret manager + quy trình rotation thực tế.
- **Downgrade hypertable** không thể un-hypertable in-place (migration #2 downgrade chỉ khôi phục PK; rollback đầy đủ cần restore từ migration #1).

## 7. Việc tiếp theo (đề xuất, CHỜ USER REVIEW)

- **P1 #4 — Audit retention + Observability:** retention/rotation cho audit log; structured JSON logging (no PHI) + `trace_id`; metrics (latency/error/escalation rate); error monitoring.
- **P1 #5 — Refresh token + MFA** cho doctor/admin (doctrine yêu cầu).
- **Xác minh TimescaleDB thật:** chạy `docker compose up postgres` + `MCP_TEST_POSTGRES_URL` để bật integration test.
- **CI:** GitHub Actions chạy `pytest` + `ruff` mỗi PR.
- Cân nhắc P2: LLM Gateway thật + RAG, OCR worker, booking flow, Next.js/Flutter.

## 8. Checklist tuân thủ ràng buộc

| Ràng buộc | Trạng thái |
|-----------|-----------|
| 56 test cũ vẫn xanh | ✅ (thích nghi sang JWT, behaviors giữ nguyên; nay 71 pass) |
| Không đụng `~$ ....docx` | ✅ (gitignored, không chạm) |
| Không hardcode secret | ✅ (mọi key qua env; dev default là placeholder rõ ràng + cảnh báo prod) |
| Mock mode zero-key vẫn chạy | ✅ (AI/OCR mock mặc định; SQLite + dev keys) |
| Postgres tùy chọn, cùng codebase | ✅ (env-driven; SQLite mặc định) |
| Commit từng phase, message rõ | ✅ (3 commit) |
| Fix loop ≤ 3 vòng | ✅ (các lỗi sửa trong 1 vòng/phase) |

---

- **MERGE_ALLOWED: YES** (đã ở `main`; mỗi phase committed, test xanh).
- **REASON:** 3 phase P1 hoàn tất an toàn, không phá test cũ, không phá backward-compat (SQLite vẫn chạy), tuân thủ đủ ràng buộc bảo mật/secret. Chỉ còn TimescaleDB cần xác minh trên DB thật (môi trường này không có Docker) — đã guard + test-skip rõ ràng, không chặn merge.
- **NEXT_ACTION:** User review 3 commit P1. Nếu OK → giao **P1 #4 (audit retention + observability)** và/hoặc **P1 #5 (refresh token + MFA)**. Trên máy có Docker, chạy `docker compose up -d postgres` + đặt `MCP_TEST_POSTGRES_URL` rồi `pytest` để xác nhận hypertable.
