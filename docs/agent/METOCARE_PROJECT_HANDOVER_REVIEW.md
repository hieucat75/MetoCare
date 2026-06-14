# MetoCare — Project Handover Review (Baseline Discovery)

> Tác giả: Claude Code (Lead Engineer / Principal Architect) · Ngày: 2026-06-14
> Step 1–2 của governance workflow. **Mục đích: xác minh trạng thái thật vs spec, quyết định path.**

---

## 0. KẾT LUẬN QUAN TRỌNG (đọc trước)

⚠️ **Spec mô tả baseline lỗi thời.** Spec ghi "branch `foundation/sprint0-healthcare-platform`,
commit `35f29c6`, 56 tests". **Thực tế dự án đã đi xa hơn rất nhiều:**

- Đang ở `main`, HEAD `a51cfc6` (merge), đã push lên GitHub `hieucat75/MetoCare`.
- **P1 #1–#8 + CI ĐÃ HOÀN TẤT và merged.** **P2 #1–#3 (LLM Gateway, RAG, OCR worker) cũng đã merged.**
- **130 tests passed**, 1 skipped (không phải 56).

➡️ **Theo CHECK trong spec: P1 #1 (Alembic + Postgres/TimescaleDB + JWT + RBAC) ĐÃ MERGED.**
**KHÔNG re-implement.** Đề xuất chuyển sang: (a) Controlled Rename → MetoCare (Phần 2, low-risk),
rồi (b) chọn next dev phase. Chờ dispatch/PTH quyết.

## 1. Current State (git)

| Mục | Giá trị thật |
|-----|--------------|
| Branch | `main` |
| HEAD | `a51cfc6` Merge remote-tracking branch 'origin/main' |
| Remote | `origin` → https://github.com/hieucat75/MetoCare.git |
| Tags | `v0.1.0-sprint0-foundation`, `v0.3.0-p2-foundation`, `v0.4.0-demo-ready` |
| Working tree | sạch trừ `.gitignore` (M — thêm ignore `.claude/`, benign) |

**Lịch sử (rút gọn):** Sprint 0 → P1 #1 (`396ae12` DB/Alembic/Timescale) → P1 #2 (`9cee651` JWT/Argon2/RBAC)
→ P1 #3 PHI encryption → #4 observability → #5 refresh+MFA → #6 rate-limit+lockout → #7 force-MFA-enroll
→ #8 reuse-detection → CI → P2 #1 LLM Gateway (`254774b`) → P2 #2 RAG (`bd19ecc`) → P2 #3 OCR worker (`c0ac2d6`)
→ Swagger UI/demo seed → merge GitHub.

## 2. Architecture (hiện tại)

FastAPI modular monolith (`backend/app`), API `/api/v1`. Không microservices.

- **core/**: config (env `MCP_*`), database (SQLite dev / Postgres prod), security (Argon2+JWT),
  crypto (Fernet field-encryption), clock, context, logging (JSON no-PHI), metrics, middleware
  (Observability + MfaEnrollment), ratelimit (token bucket + lockout).
- **domain/** (pure-stdlib safety core): guardrails, triage, lab_interpreter, metabolic_score, policies
  (gồm SYSTEM_SAFETY_PROMPT, injection patterns).
- **models/** (SQLAlchemy 2.0): user, patient, clinical, ai, care, governance, auth_tokens.
- **services/**: audit, audit_retention, consent, health_metrics, lab, lab_pipeline (async OCR worker),
  ocr, auth, mfa, ai_assistant, phi_migration, notifications.
- **llm/** (P2 #1): base, factory, gateway (guardrail choke point), cost, cache, errors.
- **rag/** (P2 #2): embedding, vector_store, knowledge_base, retrieval, errors.
- **api/v1/routes/**: system, auth, health, lab, ai, consent, admin.
- **alembic/**: 6 migrations (initial 14 entities → Timescale hypertable+CAGG → PHI encrypt →
  refresh+MFA → reuse family+severity → lab pipeline status).

## 3. Test / Quality (Step 2 — kết quả THẬT, đo hôm nay)

```
pytest:                 130 passed, 1 skipped, 1 warning (third-party starlette/httpx)  [10.1s]
ruff check:             All checks passed!  (app, tests, alembic/env.py)
compileall:             OK
docker-compose config:  VALID
docker daemon:          DOWN (không chạy được Postgres/TimescaleDB trong môi trường này)
migrations:             6 · test files: 19
```
Skip duy nhất: `test_postgres_hypertable_ingest_and_trend` (cần `MCP_TEST_POSTGRES_URL`).
**Không có test fail. Không sửa gì ở baseline.**

## 4. P1 #1 Scope vs Thực tế (đối chiếu spec)

| P1 #1 yêu cầu | Trạng thái |
|---------------|-----------|
| Alembic + initial migration | ✅ DONE (6 migrations) |
| SQLite dev + Postgres compat | ✅ DONE (env-driven, `create_all` chỉ SQLite, Postgres dùng Alembic) |
| TimescaleDB design (hypertable + CAGG) | ✅ DONE (migration 2, dialect-guarded; chưa verify trên DB thật) |
| JWT util | ✅ DONE (`core/security.py`, PyJWT HS256) |
| Auth dep/middleware, X-User-Id wrap/replace | ✅ DONE (thay bằng Bearer JWT, `api/deps.py`) |
| RBAC role model + role check dep | ✅ DONE (`require_roles`, `require_mfa`) |
| Audit log captures auth actor | ✅ DONE (login/register/refresh/logout audited) |

➡️ **P1 #1 hoàn tất 100% (và vượt: cả P1 #2–#8 + P2 #1–#3).**

## 5. Risks / Limitations (honest)

- **TimescaleDB/Postgres CHƯA verify trên DB thật** (Docker daemon DOWN) — chỉ verify tĩnh + guard dialect.
- **CI chưa rõ đã chạy xanh trên GitHub** chưa (cần kiểm tra Actions trên remote).
- Rate-limit/lockout in-memory (chưa Redis) → không chia sẻ multi-instance.
- Field-encryption đã impl (P1 #3) — vượt scope "docs only" của spec (không vấn đề).
- LLM/OCR đều mock (đúng yêu cầu, không gọi external).
- **Tên sản phẩm chưa đổi sang "MetoCare"** trong README/docs/app title (vẫn "Metabolic Care Platform").

## 6. Merge-ready / P1 safe to start?

- **Merge-ready:** Toàn bộ đã ở `main` và đã push — không có gì pending để merge.
- **P1 #1 safe to start?** → **KHÔNG cần** (đã merged). Re-implement sẽ vi phạm "DO NOT rewrite / DO NOT re-implement".

## 7. Recommended Path (chờ dispatch/PTH)

1. **Step 3 — Controlled Rename → MetoCare** (Phần 2 spec): README title + product definition, docs refs,
   `METOCARE_RENAME_REPORT.md`. **Không** đổi package/module/DB table/imports. Low-risk, đúng yêu cầu "project name MetoCare".
2. **Sau rename → chọn next phase** (thay vì re-implement P1):
   - Hardening tồn đọng: verify TimescaleDB trên Postgres thật, Redis backend (rate-limit), refresh-token cleanup job, email blind-index.
   - Hoặc P2 #4 Next.js portal / P2 #5 Flutter (big chunk — nên fresh session).
   - Hoặc guardrail eval set mở rộng + medical board review (medical safety).

**Không tự ý làm tiếp** — chờ dispatch xác nhận path (rename trước, rồi phase nào).
