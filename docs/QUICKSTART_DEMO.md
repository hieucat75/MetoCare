# QUICKSTART — Test thử bằng Swagger UI

> Hiện tại MCP **chỉ có backend FastAPI**. Web/mobile (Next.js/Flutter) là roadmap chưa làm.
> Để test tương tác ngay, dùng **Swagger UI** (auto-generate ở `/docs`) và **ReDoc** (`/redoc`).
> Mọi tài khoản + dữ liệu demo đều **giả**, không phải PHI thật. Chỉ dùng cho dev.

---

## 1. Setup (1 lần)

```bash
# từ thư mục gốc repo
cp .env.example .env
```

Sửa `.env`, bật docs và sinh secret thật cho dev:

```bash
# Swagger UI bật cho dev (đã có sẵn trong .env.example):
#   MCP_ENABLE_DOCS=true

# Sinh JWT secret (HS256, ≥32 ký tự):
python -c "import secrets; print('MCP_SECRET_KEY=' + secrets.token_urlsafe(48))"

# Sinh khóa mã hóa PHI (Fernet):
python -c "from cryptography.fernet import Fernet; print('MCP_ENCRYPTION_KEYS=' + Fernet.generate_key().decode())"
```

Dán 2 dòng kết quả vào `.env` (ghi đè placeholder). Lưu ý tên biến **thật** trong repo:
`MCP_SECRET_KEY` và `MCP_ENCRYPTION_KEYS` (số nhiều) — không phải `JWT_SECRET`.

## 2. Cài deps + migrate + seed

```bash
cd backend
python -m venv ../.venv && source ../.venv/bin/activate   # nếu chưa có venv
pip install -r requirements.txt -r requirements-dev.txt

# SQLite dev tạo bảng tự động khi chạy app; nếu muốn dùng Alembic:
alembic upgrade head

# Seed 3 tài khoản demo + 30 ngày chỉ số + 1 consent (idempotent):
python scripts/seed_demo.py
```

## 3. Chạy server

```bash
cd backend
uvicorn app.main:app --reload
```

Mở **http://localhost:8000/docs** (Swagger UI) hoặc http://localhost:8000/redoc.

---

## 4. Tài khoản demo

| Role | Email | Password | MFA |
|------|-------|----------|-----|
| patient | `demo.patient@example.com` | `DemoPatient123!` | không bắt buộc |
| doctor | `demo.doctor@example.com` | `DemoDoctor123!` | không bắt buộc (tự nguyện) |
| admin (internal_admin) | `demo.admin@example.com` | `DemoAdmin123!` | **bị ép enroll** |

## 5. Flow test trên Swagger UI (patient)

1. **Login** → `POST /api/v1/auth/login`
   ```json
   { "email": "demo.patient@example.com", "password": "DemoPatient123!" }
   ```
   Copy `access_token` trong response.
2. Bấm nút **Authorize** (góc trên phải Swagger) → dán `access_token` → Authorize.
   - `patient_id` (profile) in ra ở cuối log của `seed_demo.py`; cũng có thể lấy từ `GET /api/v1/auth/me` (trả user) — health endpoints dùng **patient profile id**, không phải user id. Lấy nhanh từ output seed.
3. **Xem xu hướng** → `GET /api/v1/patients/{patient_id}/metrics/trend?metric_type=fasting_glucose`
4. **Liệt kê chỉ số** → `GET /api/v1/patients/{patient_id}/metrics`
5. **Thêm chỉ số** → `POST /api/v1/patients/{patient_id}/metrics`
   ```json
   { "metric_type": "fasting_glucose", "value": 95, "unit": "mg/dL" }
   ```
6. **AI chat (guardrailed)** → `POST /api/v1/ai/chat`
   ```json
   { "message": "Tôi nên ăn gì buổi tối để kiểm soát đường huyết?" }
   ```
   → response luôn kèm disclaimer "Thông tin này không thay thế tư vấn bác sĩ".
   - Thử red flag: `{"message": "Tôi bị đau ngực và khó thở"}` → `escalated_to_doctor: true`.
   - Thử hỏi thuốc: `{"message": "Tôi có nên tăng liều thuốc không?"}` → chuyển hướng bác sĩ.
7. **Lab pipeline** →
   - `POST /api/v1/patients/{patient_id}/lab-documents` `{"storage_key":"mock://lab/doc-1.pdf","file_type":"pdf"}`
   - `POST /api/v1/lab-documents/{document_id}/process` → 202, `status: ocr_pending`
   - `GET /api/v1/lab-documents/{document_id}` → poll tới `status: interpreted`
   - (hoặc `POST /api/v1/lab-documents/{document_id}/interpret` cho path đồng bộ cũ)
8. **Consent** → `POST /api/v1/patients/{patient_id}/consents`
   ```json
   { "consent_type": "data_sharing", "data_scope": "lab", "granted_to": "<doctor_user_id>" }
   ```

## 6. Flow demo ÉP MFA (admin)

> Doctor **không còn bị ép MFA** (bỏ để sales onboard bác sĩ dễ hơn) — login `demo.doctor@example.com` / `DemoDoctor123!` là dùng được ngay; MFA với doctor là tự nguyện qua `POST /api/v1/auth/mfa/enroll`.

1. **Login** `demo.admin@example.com` / `DemoAdmin123!` → có `access_token` nhưng claim `mfa_enrollment_required=true`.
2. Authorize bằng token đó, thử endpoint bất kỳ (vd `GET /api/v1/auth/me` vẫn cho) nhưng endpoint nghiệp vụ → **403 `mfa_enrollment_required`**.
3. **Enroll** → `POST /api/v1/auth/mfa/enroll` → trả về `secret` + `provisioning_uri` + `backup_codes` (nhập secret/URI vào Google Authenticator; lưu backup codes).
4. Lấy mã 6 số từ app authenticator → **Verify** → `POST /api/v1/auth/mfa/verify` `{"totp_code":"123456"}`.
5. **Login lại** kèm `totp_code` → token mới `mfa=true`, hết bị chặn; thử `GET /api/v1/admin/audit-logs`.

## 7. curl nhanh (không cần Swagger)

```bash
BASE=http://localhost:8000/api/v1

# Login -> lấy token
TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"demo.patient@example.com","password":"DemoPatient123!"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# AI chat (guardrailed)
curl -s -X POST $BASE/ai/chat -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"message":"Tôi nên ăn gì buổi tối?"}'

# Triage red flag
curl -s -X POST $BASE/ai/triage -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"symptom_text":"đau ngực dữ dội"}'
```

## 8. Ghi chú an toàn

- `MCP_ENABLE_DOCS` **luôn bị tắt ở prod** dù đặt `true` (gate trong `create_app`).
- AI chạy **mock mode** — không gọi LLM/OCR thật, không cần API key.
- Đừng commit `.env`. Secret demo chỉ dùng local.
