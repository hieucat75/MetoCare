# FINAL HANDOFF — P2 FOUNDATION (LLM Gateway + RAG + OCR)

> Tác giả: Claude Code · Ngày: 2026-06-13 · Branch: `foundation/p2-llm-gateway-rag-ocr` (từ `main`)
> Tiếp nối Sprint 0 (`v0.1.0`) + P1 (`v0.2.0`). 3 phase P2 hoàn tất, mỗi phase 1 commit, test xanh sau từng commit.

---

## 1. Tổng quan

| Phase | Nội dung | Commit |
|-------|----------|--------|
| P2 #1 | LLM Gateway (provider abstraction + guardrail + cost guard + cache) | `254774b` |
| P2 #2 | RAG Retrieval skeleton (embedding + vector store + KB + pipeline) | `bd19ecc` |
| P2 #3 | OCR worker foundation (asyncio queue + state machine + pipeline) | `c0ac2d6` |

**Kết quả test (thật):**
```
pytest:        128 passed, 1 skipped, 1 warning (third-party starlette/httpx)
               (96 P1 cũ giữ xanh + 32 mới: 13 LLM + 9 RAG + 10 OCR)
ruff check:    All checks passed! (app, tests, alembic)
compileall:    OK
alembic:       6 migrations, up/down reversible, single head a1b2c3d4e5f6
```
Skip: `test_postgres_hypertable_ingest_and_trend` (cần `MCP_TEST_POSTGRES_URL`).

## 2. Branch & Files changed

Branch: `foundation/p2-llm-gateway-rag-ocr`.

**Mới:**
- `backend/app/llm/` — `__init__.py`, `base.py`, `errors.py`, `factory.py`, `cache.py`, `cost.py`, `gateway.py`, `providers/{__init__,mock,openai,anthropic}.py`
- `backend/app/rag/` — `__init__.py`, `errors.py`, `embedding.py`, `vector_store.py`, `knowledge_base.py`, `retrieval.py`
- `backend/app/services/` — `ocr.py`, `notifications.py`, `lab_pipeline.py`
- `backend/data/rag_seed/` — `metabolic_disorders.md`, `biomarkers.md`, `lifestyle.md`
- `backend/alembic/versions/a1b2c3d4e5f6_lab_document_pipeline_status.py`
- `backend/tests/` — `test_llm_gateway.py`, `test_rag.py`, `test_lab_pipeline.py`

**Sửa:**
- `backend/app/core/config.py` — settings LLM / RAG / OCR
- `backend/app/domain/policies.py` — `SYSTEM_SAFETY_PROMPT_VI`, `INSTRUCTION_INJECTION_PATTERNS`
- `backend/app/domain/guardrails.py` — `is_injection`
- `backend/app/services/ai_assistant.py` — chạy qua LLM Gateway + `with_rag=True`
- `backend/app/api/v1/routes/ai.py` — user_id cost-subject + 429 mapping
- `backend/app/api/v1/routes/lab.py` — `/process` (202), `GET /lab-documents/{id}`
- `backend/app/schemas/{ai,lab}.py` — field mới
- `backend/app/models/clinical.py` — `LabDocument.status`
- `backend/app/main.py` — start/stop OCR worker trong lifespan
- `backend/tests/conftest.py` — reset gateway/retriever/worker/notifications, tắt worker test
- `.env.example` — config LLM/RAG/OCR
- `docs/agent/SELF_REVIEW_REPORT.md` — section P2

## 3. Đã implement (chi tiết)

### P2 #1 — LLM Gateway
- `LLMProvider.complete(messages, system, max_tokens, temperature) -> LLMResponse`.
- Adapters: `MockLLMProvider` (default, deterministic VI), `OpenAIProvider`/`AnthropicProvider` skeleton (`LLMConfigError`, **không** gọi mạng). Factory theo `MCP_LLM_PROVIDER`.
- Gateway = choke point duy nhất: **cost/rate guard** (per-user sliding 60s, RPM+TPM → `LLMRateLimitError` → HTTP 429) → **cache** (LRU+TTL, key gồm user) → provider → **output guardrail** (BLOCK → safe message) → disclaimer → token accounting + metrics.
- `ai_assistant`: input red-flag escalate + medication redirect (không gọi model) giữ nguyên; generation qua gateway.

### P2 #2 — RAG Retrieval
- `EmbeddingProvider`: `MockEmbedding` (hash bag-of-words deterministic) + `OpenAIEmbedding` skeleton.
- `VectorStore`: `InMemoryVectorStore` (cosine, không faiss) + `PgVectorStore`/`QdrantStore` skeleton.
- `KnowledgeBase`: load `data/rag_seed/*.md`, chunk theo `##`, **vet injection khi ingest**.
- `Retriever`: embed → top-k → rerank (0.7 cosine + 0.3 lexical) → injection-vet lần 2 → context window "ĐÃ DUYỆT".
- Gateway `with_rag=True` prepend context vào system prompt.

### P2 #3 — OCR worker
- `OCRProvider`: `MockOCRProvider` (fixture map; key "fail"/"corrupt" → lỗi) + `Tesseract`/`Cloud` skeleton.
- State machine `LabDocStatus` + `_transition` validate; pipeline `process_document` (OCR → interpret → LabResult → audit → notify), lỗi → terminal failed + audit warning, không crash worker.
- Queue: `OCRWorkerManager` (asyncio.Event + buffer + in-flight set), worker trong lifespan, `run_in_executor`. Idempotent enqueue. Migration thêm cột `status`.

## 4. What couldn't verify (giới hạn môi trường)

- **Provider thật (OpenAI/Anthropic/Tesseract/Cloud OCR/pgvector/Qdrant)**: chỉ skeleton, chưa wire SDK/credentials → không thể chạy thật trong môi trường này (đúng thiết kế: dev/test không gọi external).
- **TimescaleDB**: vẫn skip (không có Postgres/Docker).
- **CI thật**: chưa push remote.
- **Concurrency của worker dưới tải cao**: chỉ test 1 document qua async loop; chưa load-test nhiều job song song / nhiều instance.

## 5. Key decisions

1. **Guardrail đặt trong Gateway** (không ở adapter) → không code path nào emit response chưa validate.
2. **`/ai/chat` giữ không bắt buộc auth** để 96 test cũ xanh; cost-subject = token sub nếu có, else client IP.
3. **Skeleton raise lỗi rõ ràng** thay vì degrade thầm → dev/test không bao giờ chạm provider thật.
4. **Sync `interpret_document` giữ song song** async pipeline (backward-compat) — async là canonical mới.
5. **Queue thuần asyncio**, idempotency qua in-flight set + document status; không thêm Celery/Redis/faiss.
6. **Worker tắt trong test**, pipeline chạy tất định; async worker test riêng qua `asyncio.run`.

## 6. Security / AI safety notes

- Mọi LLM response qua `guardrails.check_output`; BLOCK → safe message + disclaimer.
- Safety system prompt (`SYSTEM_SAFETY_PROMPT_VI`) tiêm mọi call.
- RAG context qua `is_injection` 2 lớp (ingest + retrieve) → chống prompt-injection/corpus poisoning.
- Cost/rate guard per-user chống lạm dụng/cost blow-up (429).
- OCR failure → audit `severity=warning, outcome=failure`; pipeline audit đầy đủ (enqueue/extract/interpret).
- Không secret hardcode; mọi provider mock default; không PHI thật (seed + fixture giả).

## 7. Remaining risks

- Cost guard / cache / queue **in-memory** → không chia sẻ giữa nhiều instance (cần Redis/distributed khi scale ngang — interface đã pluggable).
- Mock embedding bag-of-words → ranking thô; chỉ đủ cho foundation, cần embedding thật cho chất lượng retrieval.
- Notification mới là placeholder in-memory (chưa push/email/SMS thật).
- RAG corpus nhỏ, cần medical board duyệt + versioning trước khi dùng thật.
- Injection patterns theo regex → cần mở rộng eval set.

## 8. Recommended next (roadmap còn lại)

1. **Wire provider thật** (Anthropic/OpenAI LLM + embedding; pgvector/Qdrant; Tesseract/Cloud OCR) sau eval hồi quy guardrail.
2. **Distributed backend**: Redis cho cost guard + cache + queue (thay in-memory) khi scale ngang.
3. **Notification system thật** (push/email/SMS) thay placeholder.
4. **Doctor handoff + Appointment + booking** (model đã có, chưa route).
5. **Next.js portal** (auth/MFA/refresh + Doctor/Patient timeline) consume API v1.
6. **Flutter mobile** (auth + health tracking + metabolic score).
7. Đẩy GitHub cho CI chạy; xác minh TimescaleDB trên Docker; refresh-token cleanup job.

## 9. Compliance checklist (phiên này)

| Ràng buộc | Trạng thái |
|-----------|-----------|
| 96 test P1 cũ vẫn xanh | ✅ (nay 128) |
| Mỗi phase 1 commit, test xanh sau từng commit | ✅ |
| Không dependency nặng (Celery/Redis/faiss) | ✅ (asyncio + in-memory + interface) |
| Provider thật chỉ skeleton, không gọi thật | ✅ |
| Mock mode default mọi nơi | ✅ |
| Mọi LLM response qua guardrail | ✅ |
| Update `.env.example` + `config.py` | ✅ |
| Migration up/down reversible, single head | ✅ (`a1b2c3d4e5f6`) |
| Không secret hardcode / không PHI thật | ✅ |
| Không đụng `~$ ....docx` | ✅ |

---

- **MERGE_ALLOWED: YES**
- **REASON:** 3 phase P2 foundation hoàn tất an toàn — 128 test xanh (96 cũ giữ nguyên + 32 mới), ruff sạch, compileall OK, alembic up/down reversible single head. Tuân thủ đủ bất biến: mọi LLM response qua guardrail, mock/skeleton không gọi external, không dependency nặng, không secret/PHI thật, backward-compat. Provider thật + TimescaleDB + CI cần hạ tầng ngoài môi trường (đã skeleton/guard/validate), không chặn merge.
- **NEXT_ACTION:** User review P2 foundation. Khi sẵn sàng: wire provider thật (sau eval guardrail) + distributed backend (Redis) hoặc bắt đầu frontend (Next.js portal / Flutter) — xem §8.
