# PROJECT DISCOVERY REPORT — Metabolic Care Platform (MCP)

> Tác giả: Claude Code (Principal Engineer / Solution Architect / Tech Lead / QA Lead)
> Ngày: 2026-06-12
> Phạm vi: Repository discovery trước khi thay đổi code (Phần 1 của nhiệm vụ Sprint 0).

---

## 1. Repo Summary

MCP là nền tảng chăm sóc sức khỏe chuyển hóa (tiền tiểu đường, rối loạn chuyển hóa, béo bụng,
mỡ máu). Tại thời điểm discovery, repository **chỉ chứa tài liệu thiết kế**, chưa có dòng code nào.

| Hạng mục | Trạng thái khi discovery |
|----------|--------------------------|
| Git repository | ❌ Chưa init (đã `git init` trong Phase 0 của lần chạy này) |
| Source code (backend/frontend/mobile) | ❌ Không có |
| Database schema / migration | ❌ Không có |
| Docker / docker-compose | ❌ Không có |
| Tests | ❌ Không có |
| CI/CD | ❌ Không có |
| Auth / security code | ❌ Không có (chỉ có docs) |
| AI module code | ❌ Không có (chỉ có docs) |
| Tài liệu thiết kế (`docs/*.md`) | ✅ Đầy đủ 10 tài liệu nền tảng |
| Đề án `.docx` | ✅ Có (`đề án kiến trúc tổng thể MCP.docx`, đang mở trong Word — có file lock `~$`) |

**Kết luận:** đây là **repo mới ở giai đoạn pre-Sprint 0** — tài liệu kiến trúc rất hoàn chỉnh,
nhưng nền kỹ thuật (repo, code, test, CI) chưa tồn tại. Nhiệm vụ lần này là dựng **foundation**.

## 2. Current Tech Stack

### 2.1 Đã chốt trên tài liệu (chưa hiện thực hóa)
- **Backend:** FastAPI modular monolith (15 module nghiệp vụ + 2 cross-cutting Consent/Audit), API-first, `/api/v1`.
- **Data:** PostgreSQL (core) + TimescaleDB hypertable (`health_metric`) + Redis + S3/MinIO + pgvector (RAG).
- **Mobile:** Flutter. **Web/Portals:** Next.js (Doctor / Clinic / Internal Admin).
- **AI:** LLM Gateway (không gọi LLM trực tiếp) + Medical RAG (chỉ guideline đã duyệt) + Guardrail rule engine 2 đầu input/output + Triage lai (rule trước, LLM sau, classifier 4 mức, escalation).
- **AuthN/Z:** JWT access + refresh, MFA cho doctor/admin, Argon2/bcrypt, RBAC + consent context.

### 2.2 Toolchain thực tế trên máy (đo được)
| Tool | Phiên bản | Ghi chú |
|------|-----------|---------|
| Python | 3.14.5 | bleeding-edge; đã xác nhận FastAPI/SQLAlchemy/pydantic có wheel chạy được |
| Node | 22.22.3 / npm 10.9.8 | sẵn cho web/mobile sau |
| Docker | 29.4.2 | sẵn cho compose |
| git | 2.50.1 | OK |
| pytest / ruff | (đã cài vào `.venv` trong lần chạy này) | trước đó chưa có |

## 3. Existing Modules (tài liệu)

10 tài liệu nền tảng trong `docs/` (tất cả đều tồn tại — **không có file missing**):

| Tài liệu | Vai trò |
|----------|---------|
| `Architecture_Doctrine.md` | Luật gốc kiến trúc — doctrine thắng khi xung đột |
| `Technical_Architecture.md` | Kiến trúc kỹ thuật chi tiết (module, data layer, AI layer, RBAC, deploy) |
| `Data_Model_Overview.md` | 21 core entity + classification + consent/audit + FHIR-lite |
| `AI_Safety_Guardrail.md` | Ranh giới AI (allowed/prohibited/escalation/red-flag/policies) — **spec trực tiếp cho code** |
| `Security_Compliance_Framework.md` | Threat model, consent, RBAC, encryption, audit, retention |
| `BRD.md` | Yêu cầu nghiệp vụ |
| `Product_Module_Map.md` | Bản đồ module + ưu tiên P0/P1/P2 |
| `MVP_Scope_and_Roadmap.md` | MVP 16 tuần + roadmap 12 tháng |
| `DevEnv_Hardening_Plan.md` | Môi trường dev an toàn (no real PHI) |
| `Sprint0_Execution_Blueprint.md` | Kế hoạch Sprint 0 |

## 4. Missing Modules (cần dựng)

Toàn bộ **lớp hiện thực** còn thiếu. Theo ưu tiên Sprint 0 / MVP P0:

- Backend skeleton FastAPI (modular monolith) + config + DB session.
- Data model (SQLAlchemy models) cho các entity lõi.
- **AI Safety guardrail engine** (input + output) — P0 ưu tiên cao nhất về an toàn.
- **Triage rule engine** (red flag cứng, false negative = 0).
- **Lab Interpreter** skeleton + mock OCR mode.
- **Health Tracking** APIs (create/list/trend metric, patient profile, timeline).
- **Metabolic Score** calculator.
- **Consent + Audit** baseline (model + service).
- Test framework + test cho logic an toàn quan trọng.
- `.env.example`, `.gitignore`, `docker-compose.yml` (đã làm trong lần chạy này; compose ở mức skeleton).
- CI (đề xuất, chưa bắt buộc trong lần chạy này).

## 5. Key Risks

| Rủi ro | Mức | Ghi chú |
|--------|-----|---------|
| **False negative red flag** (bỏ sót dấu hiệu nguy hiểm) | 🔴 Cao | Theo doctrine: rule engine cứng, độc lập LLM, test set false negative = 0 |
| **AI vượt ranh giới** (chẩn đoán/kê đơn/đổi liều) | 🔴 Cao | Guardrail output validator chặn theo pattern + test |
| **Rò rỉ dữ liệu sức khỏe nhạy cảm** | 🔴 Cao | Consent gate + audit + field-level encryption (thiết kế) |
| Python 3.14 quá mới, thiếu wheel | 🟡 TB | Đã verify stack core cài + import OK |
| OCR sai làm bẩn LabResult | 🟡 TB | `ocr_confidence` + verify trước khi kết luận; mock mode ở dev |
| Over-engineering / microservices sớm | 🟡 TB | Doctrine cấm; giữ modular monolith |

## 6. Immediate Blockers

- **Không có blocker chặn hoàn toàn.** Repo cho phép ghi file; toolchain đầy đủ; stack cài được.
- Ràng buộc cần tôn trọng (không phải blocker): không API key thật, không PHI thật, không gọi
  LLM/OCR provider thật trong dev/test → giải quyết bằng **mock mode mặc định**.
- Postgres/TimescaleDB chưa chạy local → dev/test dùng **SQLite mặc định** (config-driven),
  schema thiết kế tương thích để chuyển Postgres sau.

## 7. Recommended Execution Plan (tóm tắt)

Chi tiết tại `CLAUDE_CODE_EXECUTION_PLAN.md`. Tóm tắt theo phase (chỉ thực thi P0 an toàn, kiểm chứng được bằng test):

1. **Phase 0 — Baseline & safety:** git init, `.gitignore`, `.env.example`, venv + deps. ✅
2. **Phase 1 — Documentation alignment:** discovery report + execution plan. ✅
3. **Phase 2 — Backend foundation:** FastAPI app factory, config (pydantic-settings, env-driven), DB session.
4. **Phase 3 — Data model:** SQLAlchemy models cho entity lõi (User, PatientProfile, HealthMetric, LabDocument, LabResult, SymptomLog, Medication, RiskScore, AIConversation, Appointment, Doctor, Clinic, Consent, AuditLog).
5. **Phase 4 — Health Tracking MVP APIs:** create/list/trend metric, patient profile, timeline.
6. **Phase 5 — Lab Interpreter foundation:** upload (mock OCR) → parse → normalize → classify → patient/doctor explanation.
7. **Phase 6 — AI guardrail + triage rule foundation:** policies, guardrail input/output validator, triage red-flag engine + 4-level classifier + escalation.
8. **Phase 7 — Doctor/Clinic skeleton:** models + read-only listing skeleton.
9. **Phase 8 — Test & review:** pytest cho domain an toàn + API; ruff; self-review report.

**Nguyên tắc thực thi:** ưu tiên build chạy được + test được + an toàn y tế + an toàn dữ liệu;
không over-engineer; không microservices; không API/PHI thật; mock mode mặc định.
