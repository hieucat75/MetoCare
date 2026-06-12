# CLAUDE CODE EXECUTION PLAN — Metabolic Care Platform (Sprint 0 Foundation)

> Tác giả: Claude Code · Ngày: 2026-06-12 · Nguồn: discovery + 10 tài liệu `docs/*.md`.
> Nguyên tắc: build chạy được, test được, an toàn y tế, an toàn dữ liệu. Không over-engineer. Không microservices. Không API/PHI thật.

---

## 1. Target Outcome

Một **FastAPI modular monolith foundation** chạy được và test được, hiện thực hóa các tầng
**an toàn cốt lõi** (AI guardrail, triage red-flag, lab interpreter, consent/audit) đúng theo
`AI_Safety_Guardrail.md`, `Technical_Architecture.md`, `Data_Model_Overview.md`, sẵn sàng cho
team vào sprint phát triển tính năng.

## 2. Assumptions

- Repo bắt đầu trống code → dựng foundation mới (không có backward-compat cũ để giữ).
- Stack Python/FastAPI theo doctrine (đã chốt trong tài liệu).
- Dev/test không có Postgres/Redis/MinIO/LLM/OCR thật → dùng **SQLite + mock mode** mặc định, config-driven để chuyển prod.
- Logic an toàn y tế (guardrail/triage/lab/score) viết **pure-Python stdlib** để test độc lập, không phụ thuộc framework/DB.

## 3. Constraints (ràng buộc bắt buộc)

- AI **không** chẩn đoán khẳng định, **không** kê đơn, **không** đổi liều; red flag → escalate.
- Dữ liệu sức khỏe = nhạy cảm → consent + audit + RBAC + encryption strategy.
- Không hardcode secret; không commit `.env`; không PHI/PII thật trong test/fixture.
- Không gọi LLM/OCR provider thật trong dev/test.
- Modular monolith; service-interface giữa module; Consent/Audit cross-cutting.

## 4. Workstreams

| Workstream | Lần chạy này (P0) | Sau (P1/P2) |
|------------|-------------------|-------------|
| **Documentation** | Discovery, Execution Plan, Self-review | OpenAPI contract đầy đủ, ADRs |
| **Backend** | App factory, config, DB session, module skeleton | Toàn bộ 15 module, RBAC middleware |
| **Database** | SQLAlchemy models entity lõi (SQLite dev) | Alembic migration, Postgres + TimescaleDB hypertable |
| **AI Safety** | Policies + guardrail input/output validator | LLM Gateway, RAG, human-in-the-loop queue |
| **OCR/Lab Interpreter** | Mock OCR + parse + normalize + classify + explain | Provider thật qua worker, verify flow |
| **Health Tracking** | create/list/trend metric, profile, timeline | Continuous aggregate, anomaly → triage |
| **Doctor/Clinic** | Models + skeleton listing | Booking, availability, consult note, care plan |
| **Frontend/Web** | (không trong lần này) | Next.js portals |
| **Mobile** | (không trong lần này) | Flutter app |
| **DevOps** | `.gitignore`, `.env.example`, docker-compose skeleton | CI/CD, secret manager, staging |
| **Testing** | pytest domain + API smoke | eval set AI, load test, e2e |
| **Security** | Consent + Audit baseline, no-secret config | Field-level encryption, MFA, pen-test |

## 5. Task Breakdown theo Phase

- **Phase 0 — Repo baseline & safety** ✅: `git init`, branch, `.gitignore`, `.env.example`, venv + deps.
- **Phase 1 — Documentation alignment** ✅: `PROJECT_DISCOVERY_REPORT.md`, `CLAUDE_CODE_EXECUTION_PLAN.md`.
- **Phase 2 — Backend foundation**: `app/core/config.py`, `app/core/database.py`, `app/main.py`, `app/api/v1/router.py`, `/health` + `/api/v1` skeleton.
- **Phase 3 — Data model & migrations**: `app/models/*` (SQLAlchemy) cho entity lõi; `create_all` cho SQLite dev; Alembic để Phase sau.
- **Phase 4 — Health tracking MVP APIs**: service + routes create/list/trend metric, patient profile, timeline; normal-range/status logic.
- **Phase 5 — Lab result interpreter foundation**: `domain/lab_interpreter.py` (normalize biomarker, reference range, classify normal/high/low/critical, patient + doctor explanation) + route upload(mock OCR)/interpret.
- **Phase 6 — AI guardrail & triage rule foundation**: `domain/policies.py`, `domain/guardrails.py` (input+output validator), `domain/triage.py` (red-flag engine + 4-level classifier + escalation), `domain/metabolic_score.py`; route ai/chat (guardrailed) + triage/assess.
- **Phase 7 — Doctor/clinic skeleton**: models Doctor/Clinic/Appointment + read-only routes skeleton.
- **Phase 8 — Test & review**: pytest cho guardrail/triage/lab/score/consent-audit/API; ruff; `SELF_REVIEW_REPORT.md`; fix loop.

## 6. P0 / P1 / P2 Prioritization

- **P0 (lần chạy này):** guardrail engine, triage red-flag, lab classify, metabolic score, consent/audit baseline, health metric API, config no-secret, tests cho các phần này. → *an toàn y tế + dữ liệu trước.*
- **P1 (sprint kế):** Alembic + Postgres/TimescaleDB, RBAC middleware đầy đủ, LLM Gateway thật, OCR worker, booking flow, CI.
- **P2:** Next.js portals, Flutter, RAG, payment, teleconsult, FHIR-lite.

## 7. Files Expected to Change / Create

```
.gitignore, .env.example, docker-compose.yml, README.md
backend/pyproject.toml, backend/requirements.txt
backend/app/__init__.py, main.py
backend/app/core/{config,database,security}.py
backend/app/domain/{policies,guardrails,triage,lab_interpreter,metabolic_score}.py
backend/app/models/{base,user,patient,clinical,ai,care,governance}.py
backend/app/schemas/{common,health,lab,ai}.py
backend/app/services/{audit,consent,health_metrics,lab}.py
backend/app/api/deps.py, api/v1/router.py, api/v1/routes/{system,health,lab,triage,ai,consent}.py
backend/tests/{conftest,test_guardrails,test_triage,test_lab_interpreter,test_metabolic_score,test_consent_audit,test_health_metrics_api,test_lab_api}.py
docs/agent/{PROJECT_DISCOVERY_REPORT,CLAUDE_CODE_EXECUTION_PLAN,SELF_REVIEW_REPORT}.md
```

## 8. Test Strategy

- **Domain (pure python):** unit test trực tiếp — guardrail prohibited actions, triage red-flag set (false negative = 0), lab classification ranh giới, metabolic score, escalation routing.
- **API:** FastAPI `TestClient` trên SQLite in-memory/file tạm; smoke + happy path + guardrail enforced ở tầng API.
- **Consent/Audit:** truy cập sinh audit; consent gate từ chối khi thiếu consent.
- **Không** PHI thật: fixtures dùng dữ liệu giả rõ ràng (Nguyễn Văn Test...).
- Quality gates: `ruff check`, `pytest`, `python -m compileall`.

## 9. Rollback Strategy

- Toàn bộ trên branch `foundation/sprint0-healthcare-platform`; main không bị đụng.
- Mỗi phase là commit logic; rollback = `git revert`/`git reset` commit tương ứng.
- Foundation mới, không sửa code cũ → rủi ro phá backward-compat = 0.
- SQLite dev DB nằm trong `data/` (gitignored) → xóa file là reset sạch.

## 10. Acceptance Criteria (lần chạy này)

- [ ] App import được; `GET /health` trả 200.
- [ ] Guardrail chặn 100% output chứa chẩn đoán khẳng định/kê đơn/đổi liều trong test set.
- [ ] Triage red-flag test set: false negative = 0 (mọi red flag → EMERGENCY/escalate).
- [ ] Lab interpreter classify đúng normal/high/low/critical + sinh giải thích bệnh nhân (ngôn ngữ khả năng, có disclaimer).
- [ ] Mọi truy cập dữ liệu bệnh nhân (qua service) sinh AuditLog; consent gate test được.
- [ ] `pytest` xanh; `ruff check` sạch; `compileall` không lỗi.
- [ ] Không secret hardcode; `.env` không bị track; không PHI thật.
