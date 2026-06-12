# SELF REVIEW REPORT — Sprint 0 Foundation

> Tác giả: Claude Code · Ngày: 2026-06-12 · Branch: `foundation/sprint0-healthcare-platform`
>
> **Cập nhật:** Sprint 0 đã merge vào `main` (tag `v0.1.0-sprint0-foundation`).
> - P1 #1–#3 (Database, Auth, Encryption) → [`FINAL_HANDOFF_P1.md`](FINAL_HANDOFF_P1.md).
> - P1 #4–#5 + CI (Observability/Retention, Refresh+MFA, GitHub Actions) → [`FINAL_HANDOFF_P1_FINAL.md`](FINAL_HANDOFF_P1_FINAL.md).
> - P1 #6–#8 (Rate limit+lockout, Force-MFA-enroll, Refresh reuse-detection) → [`FINAL_HANDOFF_P1_COMPLETE.md`](FINAL_HANDOFF_P1_COMPLETE.md).
> Trạng thái hiện tại: **P1 hoàn tất — 96 test pass, 1 skipped; ruff sạch; 5 migration; CI matrix 3.13/3.14.**
> - **P2 Foundation đang chạy** trên branch `foundation/p2-llm-gateway-rag-ocr` — xem [§P2 cuối file](#p2-foundation-llm-gateway--rag--ocr).

---

## 1. Summary of Changes

Dựng **FastAPI modular monolith foundation** cho MCP từ một repo chỉ-có-tài-liệu:
- Lõi an toàn y tế/AI viết **pure-Python, test độc lập** (`backend/app/domain`): guardrail (input+output),
  triage red-flag, lab interpreter (mock OCR), metabolic score, policies.
- Data model SQLAlchemy 2.x cho 14 entity lõi; consent gate + audit service.
- API `/api/v1`: health tracking, lab upload/interpret, AI chat (guardrailed), triage, metabolic score, consent.
- Config env-driven (không secret), SQLite dev mặc định, mock mode cho AI/OCR.
- Quality gates xanh: 56 test pass, ruff sạch, compileall OK. Docker-compose skeleton hợp lệ.

## 2. Files Changed

71 file staged. Nhóm chính:
- **Domain (an toàn):** `app/domain/{policies,guardrails,triage,lab_interpreter,metabolic_score}.py`
- **Core:** `app/core/{config,database,security,clock}.py`
- **Models:** `app/models/{_mixins,user,patient,clinical,ai,care,governance}.py`
- **Services:** `app/services/{audit,consent,health_metrics,lab,ai_assistant}.py`
- **API:** `app/api/deps.py`, `app/api/v1/router.py`, `app/api/v1/routes/{system,health,lab,ai,consent}.py`
- **Schemas:** `app/schemas/{common,health,lab,ai,consent}.py`
- **Tests:** `tests/{conftest,test_guardrails,test_triage,test_lab_interpreter,test_metabolic_score,test_consent_audit,test_api}.py`
- **Infra/docs:** `.gitignore`, `.env.example`, `docker-compose.yml`, `README.md`, `backend/{pyproject.toml,requirements*.txt}`, `docs/agent/*`

## 3. Architecture Alignment Check

| Doctrine / spec | Tuân thủ |
|-----------------|----------|
| Modular monolith, không microservices | ✅ Một app FastAPI, module theo package |
| API-first `/api/v1` | ✅ |
| Consent + Audit cross-cutting | ✅ Service `consent`/`audit`, mọi truy cập dữ liệu bệnh nhân qua gate + audit |
| AI qua guardrail, không gọi LLM trực tiếp | ✅ `ai_assistant` đi qua input→gen(mock)→output→disclaimer; mock mode mặc định |
| Triage rule TRƯỚC LLM, red flag không phụ thuộc LLM | ✅ `triage.assess` chạy rule cứng trước, `rule_forced=True` |
| HealthMetric time-series | ✅ Model portable; hypertable/continuous-agg để P1 (Alembic + Postgres) |
| Data model bám FHIR | ✅ Entity bám khái niệm; id ổn định |

## 4. Security / Privacy Check

- ✅ **Không hardcode secret** — tất cả qua `Settings` (env `MCP_*`); dev default là placeholder rõ ràng; `warn_if_insecure()` cảnh báo nếu chạy prod với default.
- ✅ **`.env` không bị commit** — `.gitignore` chặn `.env`/`.env.*` (giữ `.env.example`), `*.key/*.pem/secrets/`.
- ✅ **Consent gate** — `require_access` chặn truy cập khi không có consent (test chứng minh: stranger → `ConsentError`/403).
- ✅ **Audit** — mọi create/read/interpret/grant/revoke sinh `AuditLog` (append-only, không lưu nội dung nhạy cảm).
- ✅ **Không log PHI** (chưa thêm logging PHI; audit chỉ metadata).
- ⚠️ **Field-level encryption**: chưa triển khai (thiết kế ở Data_Model §4.3) → P1.
- ⚠️ **Auth**: placeholder header `X-User-Id` → JWT + RBAC + MFA là P1 (đã ghi chú rõ trong code).

## 5. AI Safety Check (AI_Safety_Guardrail.md §4.13)

- ✅ Output validator chặn: chẩn đoán khẳng định, kê đơn, đổi liều, downplay red flag, tiên lượng chắc chắn, nguồn ngoài RAG (6/6 test unsafe → BLOCK).
- ✅ Red flag input → ESCALATE ngay (độc lập LLM).
- ✅ Disclaimer bắt buộc, idempotent (`ensure_disclaimer`).
- ✅ Câu hỏi thuốc/liều → chuyển hướng bác sĩ (safe refusal, không tự trip validator).
- ✅ AI chỉ chạy mock mode — không gọi LLM/OCR thật, không cần API key.

## 6. Medical Safety Check

- ✅ **Triage false-negative = 0** trên test set: mọi red-flag symptom (10 loại) + critical vital → EMERGENCY.
- ✅ Lab interpreter: phân loại normal/low/high/critical theo reference range; **không kết luận bệnh**; giải thích ngôn ngữ khả năng + disclaimer; OCR confidence thấp → cần verify.
- ✅ Metabolic Score gắn nhãn "tham khảo, không phải chẩn đoán".
- ✅ Medication model record-only (AI không sửa liều — enforced ở guardrail).

## 7. Test Results

```
pytest:      56 passed, 1 warning (third-party starlette/httpx deprecation)
ruff check:  All checks passed!
compileall:  OK
docker-compose config: valid (exit 0)
app boot:    GET /health 200; triage red flag -> emergency
```

Coverage có chủ đích vào logic an toàn: guardrail (6 unsafe + 2 safe + input/disclaimer),
triage (10 red flag + vital + borderline + normal), lab (normalize/classify/explain/verify),
score (4 profile), consent/audit (gate + scope + revoke + audit write), API (14 endpoint behaviors).

## 8. Known Limitations

1. **Auth** là placeholder (`X-User-Id`), chưa JWT/RBAC/MFA.
2. **DB**: SQLite dev; chưa có Alembic migration, chưa TimescaleDB hypertable / continuous aggregate.
3. **LLM Gateway + RAG** chưa wire; AI chỉ canned mock response.
4. **OCR thật** chưa tích hợp (mock deterministic).
5. **Field-level encryption**, retention/deletion job, human-in-the-loop queue: chưa.
6. **Doctor/Clinic/Appointment**: chỉ có model, chưa route (booking là P1).
7. `security.py` dùng PBKDF2 + HMAC token (stdlib) — **không** dùng cho prod; cần Argon2/bcrypt + JWT lib.

## 9. Risks Introduced

- Rủi ro thấp: foundation mới, không sửa code cũ → không phá backward-compat.
- Guardrail dựa trên pattern tiếng Việt — có thể có false positive/negative ngoài test set; cần mở rộng eval set + medical board duyệt (đã ghi trong policies là "config do medical board duyệt").
- Datetime chuẩn hóa naive-UTC cho portable SQLite/Postgres (`core/clock.py`) — cần xem lại khi chuyển tz-aware end-to-end ở Postgres (đã ghi chú).

## 10. Recommended Next Fixes (P1)

1. Alembic + PostgreSQL/TimescaleDB hypertable cho `health_metric` + continuous aggregate.
2. JWT auth + refresh + RBAC middleware + MFA cho doctor/admin (thay placeholder).
3. LLM Gateway thật + Medical RAG (chỉ guideline đã duyệt) + output validator regression eval.
4. OCR worker thật (giữ mock cho dev/test).
5. Field-level encryption cho field nhạy cảm; retention/deletion job.
6. Mở rộng red-flag eval set + medical board ký duyệt red flag list/safety prompt.
7. CI (pytest + ruff) chạy trên mỗi PR.

---

### Self-review checklist

| Mục | Kết quả |
|-----|---------|
| Có hardcode secret? | ❌ Không |
| Có commit `.env`? | ❌ Không (gitignored) |
| Có dữ liệu y tế thật? | ❌ Không (fixture giả: "Nguyễn Văn Test") |
| AI có kê đơn/chẩn đoán? | ❌ Không (guardrail chặn + test) |
| Có red flag escalation? | ✅ Có (false-negative=0 test set) |
| Có audit/consent baseline? | ✅ Có |
| Có test cho logic quan trọng? | ✅ 56 test |
| Có phá build? | ❌ Không (build/test xanh) |
| Có migration rủi ro? | ❌ Chưa có migration (create_all dev only) |
| Có update docs? | ✅ discovery + plan + self-review + README |

---

## P2 Foundation — LLM Gateway / RAG / OCR

> Branch `foundation/p2-llm-gateway-rag-ocr` (từ `main`). Mỗi phase 1 commit, test xanh sau từng commit.

### P2 #1 — LLM Gateway (DONE)

**Files mới:** `app/llm/{__init__,base,errors,factory,cache,cost,gateway}.py`, `app/llm/providers/{__init__,mock,openai,anthropic}.py`, `tests/test_llm_gateway.py`.
**Files sửa:** `app/services/ai_assistant.py` (dùng gateway thay mock cứng), `app/api/v1/routes/ai.py` (+user_id cost-subject, 429 mapping), `app/schemas/ai.py` (+model_used/cached), `app/core/config.py` (+LLM/RAG/OCR settings), `app/domain/policies.py` (+SYSTEM_SAFETY_PROMPT_VI), `tests/conftest.py` (reset gateway), `.env.example`.

**Đã làm:**
- `LLMProvider` abstract + `LLMResponse`/`LLMMessage`; adapters `MockLLMProvider` (default, deterministic, tiếng Việt), `OpenAIProvider`/`AnthropicProvider` skeleton (raise `LLMConfigError`, **không** gọi mạng).
- Factory theo `MCP_LLM_PROVIDER`. Gateway = choke point duy nhất: cost-guard → cache → provider → **output guardrail** → disclaimer → token accounting + metrics.
- Mọi response LLM đi qua `guardrails.check_output`; BLOCK → safe message + disclaimer (`blocked=True`).
- Cost/rate guard per-user (sliding 60s, RPM + TPM) → `LLMRateLimitError` → HTTP 429 (Retry-After).
- LRU cache (TTL + max-entries) khóa theo provider+model+system+messages+user → cache hit miễn phí token.
- `ai_assistant.respond` giữ input-guardrail (red flag escalate) + medication redirect (không gọi model), phần generation qua gateway.

**Test (thật):** `tests/test_llm_gateway.py` 13 test — factory switch/unknown, mock determinism, guardrail BLOCK trong gateway, RPM/TPM cap + window slide, 429 E2E, cache hit/miss/TTL/LRU. Tổng suite **109 passed, 1 skipped**; ruff sạch; compileall OK.

**Quyết định / ghi chú an toàn:**
- `/ai/chat` giữ **không bắt buộc auth** (backward-compat 96 test cũ); cost-subject lấy từ token sub nếu có, else client IP.
- Skeleton provider raise lỗi rõ ràng thay vì degrade thầm → dev/test không bao giờ chạm provider thật.
- Guardrail đặt trong gateway (không ở adapter) → không code path nào emit response chưa validate.
