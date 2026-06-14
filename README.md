# MetoCare

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

> MetoCare is an AI-assisted metabolic health care platform connecting personal health data, lab interpretation, medical safety guardrails, and doctor/clinic workflows.

Nền tảng chăm sóc sức khỏe chuyển hóa (tiền tiểu đường, rối loạn chuyển hóa, béo bụng, mỡ máu).
**AI hỗ trợ + giải thích + phân tầng rủi ro, KHÔNG thay thế bác sĩ.**

> Trạng thái: **Sprint 0 foundation**. Backend FastAPI modular monolith chạy được + test được.
> Tài liệu kiến trúc đầy đủ trong [`docs/`](docs/). Báo cáo của agent trong [`docs/agent/`](docs/agent/).

## Kiến trúc (tóm tắt)

- **Backend:** FastAPI modular monolith (`backend/app`), API `/api/v1`.
- **Data:** PostgreSQL + TimescaleDB + Redis + MinIO/S3 + pgvector (mục tiêu). Dev/test mặc định **SQLite**.
- **AI an toàn:** guardrail rule engine 2 đầu (input/output), triage red-flag (rule trước LLM),
  lab interpreter, metabolic score — toàn bộ là **pure-Python, test độc lập** trong `backend/app/domain`.
- **Bảo mật:** consent gate + audit log + config không hardcode secret. Xem `docs/Security_Compliance_Framework.md`.

## Nguyên tắc an toàn (bắt buộc)

AI **không** chẩn đoán khẳng định · **không** kê đơn · **không** đổi liều · red flag → escalation.
Chi tiết: [`docs/AI_Safety_Guardrail.md`](docs/AI_Safety_Guardrail.md).

## Chạy nhanh (dev)

```bash
# 1. Tạo venv + cài deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt

# 2. Cấu hình env (KHÔNG commit .env)
cp .env.example .env            # mặc định: SQLite + AI/OCR mock mode (không cần key)

# 3. Chạy test + lint
cd backend
pytest
ruff check app tests

# 4. Chạy API
uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
```

Hạ tầng đầy đủ (Postgres/Timescale, Redis, MinIO) qua `docker-compose up -d` khi cần (P1).

## API foundation (đã có)

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/health`, `/api/v1/info` | health-check + chế độ mock |
| POST/GET | `/api/v1/patients/{id}/metrics` | tạo/đọc chỉ số sức khỏe (consent + audit) |
| GET | `/api/v1/patients/{id}/metrics/trend` | xu hướng theo khoảng thời gian |
| POST | `/api/v1/patients/{id}/lab-documents` + `/lab-documents/{id}/interpret` | upload (mock OCR) + giải thích |
| POST | `/api/v1/ai/chat` | trợ lý AI (đi qua guardrail, có disclaimer) |
| POST | `/api/v1/ai/triage` | phân tầng rủi ro (red-flag → emergency) |
| POST | `/api/v1/ai/metabolic-score` | tính Metabolic Score (tham khảo) |
| POST/DELETE | `/api/v1/patients/{id}/consents` | cấp/thu hồi consent |

> Auth hiện là placeholder qua header `X-User-Id` (Sprint 0). JWT + RBAC + MFA là P1.
