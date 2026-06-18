# MetoCare Pilot Onboarding Runbook

**Version:** 1.0 — 2026-06-18  
**Audience:** Ops engineers and DevOps leads running the MetoCare pilot  
**Scope:** Admin seeding, patient onboarding, MFA enrollment, first-login verification

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Seed Pilot Admin Account](#2-seed-pilot-admin-account)
3. [Seed Pilot Patient Accounts](#3-seed-pilot-patient-accounts)
4. [MFA Enrollment for Admin Accounts](#4-mfa-enrollment-for-admin-accounts)
5. [First Login Test — All Roles](#5-first-login-test--all-roles)
6. [PatientProfile Verification](#6-patientprofile-verification)
7. [Troubleshooting Common Issues](#7-troubleshooting-common-issues)

---

## 1. Prerequisites

### 1.1 Software

| Requirement | Version | Check |
|-------------|---------|-------|
| Docker Desktop or Colima | ≥ 0.5.5 | `colima status` or `docker info` |
| Python | ≥ 3.11 | `python --version` |
| `psql` client | any | `psql --version` (optional, for DB inspection) |

### 1.2 Start Container Runtime

```bash
# If using Colima (macOS)
colima start

# Verify Docker daemon is reachable
docker ps
```

### 1.3 Environment Variables

All scripts read `MCP_DATABASE_URL`. Export it for every shell session that will run seeding commands:

```bash
# SQLite (development / local smoke test)
export MCP_DATABASE_URL="sqlite:///./data/mcp_dev.sqlite3"

# PostgreSQL (staging / production pilot)
export MCP_DATABASE_URL="postgresql+psycopg2://mcp:<PASSWORD>@localhost:5432/mcp"
```

Additional required env vars for the application server (not needed for seeding scripts alone):

```bash
export SECRET_KEY="<your-secret-key>"          # JWT signing key
export FIELD_ENCRYPTION_KEY="<fernet-key>"     # PHI field-level encryption
export MFA_ISSUER="MetoCare"                   # TOTP issuer shown in authenticator apps
```

### 1.4 Activate Python Virtual Environment

```bash
cd /Users/pth/Developer/Metocare
source .venv/bin/activate

# Verify dependencies
pip show sqlalchemy argon2-cffi > /dev/null && echo "OK"
```

### 1.5 Database Must Be Running and Migrated

```bash
# Start the DB stack (PostgreSQL + TimescaleDB)
docker compose up -d db

# Wait for health check
docker compose ps db   # should show "healthy"

# Verify connection
psql "$MCP_DATABASE_URL" -c "SELECT version();"
```

> **Note:** For SQLite (dev), the database file is auto-created when the first script runs.

---

## 2. Seed Pilot Admin Account

Admin accounts cannot be created via the public API — `POST /auth/register` is restricted to PATIENT role. Use `seed_admin.py` directly against the database.

### 2.1 Dry Run First (Strongly Recommended)

Always validate inputs without touching the database:

```bash
cd /Users/pth/Developer/Metocare/backend

python scripts/seed_admin.py \
  --email admin@metocare.vn \
  --password "SecurePass!2026" \
  --role super_admin \
  --full-name "MetoCare Admin" \
  --dry-run
```

Expected output:
```
[DRY RUN] Would create admin account:
  email     : admin@metocare.vn
  role      : super_admin
  full_name : MetoCare Admin
  password  : ****************  (length=16, strength=OK)
```

### 2.2 Create the Admin Account

```bash
cd /Users/pth/Developer/Metocare/backend

python scripts/seed_admin.py \
  --email admin@metocare.vn \
  --password "SecurePass!2026" \
  --role super_admin \
  --full-name "MetoCare Admin"
```

Expected output:
```
[OK] Created admin account.
  email   : admin@metocare.vn
  role    : super_admin
  user_id : <uuid>
```

**Save the `user_id`** — it is needed for audit queries.

### 2.3 Create an Internal Admin (Optional)

```bash
python scripts/seed_admin.py \
  --email ops@metocare.vn \
  --password "OpsSecure!2026" \
  --role internal_admin \
  --full-name "Ops Team"
```

### 2.4 Idempotency Check

Re-running with the same email produces a SKIP (no error, no duplicate):
```
[SKIP] Account already exists — no changes made.
  email   : admin@metocare.vn
  role    : super_admin
  user_id : <same-uuid>
```

### 2.5 Password Policy

All admin passwords must satisfy:
- Minimum **12 characters**
- At least one **uppercase** letter (A–Z)
- At least one **lowercase** letter (a–z)
- At least one **digit** (0–9)
- At least one **special character** from: `!@#$%^&*()_+-=[]{};\\':\"|,.<>/?`~`

The script enforces this and exits with `[ERROR]` if the policy is not met.

---

## 3. Seed Pilot Patient Accounts

### 3.1 Seed a Patient

```bash
cd /Users/pth/Developer/Metocare/backend

python scripts/seed_patient.py \
  --email patient01@pilot.metocare.vn \
  --password "Patient01!Pass" \
  --full-name "Nguyen Van A" \
  --dob 1980-04-12 \
  --gender male \
  --height-cm 170 \
  --weight-kg 72
```

Expected output:
```
[OK] Created patient account.
  email              : patient01@pilot.metocare.vn
  user_id            : <uuid-user>
  patient_profile_id : <uuid-profile>

Save these IDs — you will need them for API calls.
```

**Save both IDs:**
- `user_id` — used in auth endpoints and audit logs
- `patient_profile_id` — used in all clinical data endpoints (`/health-metrics`, `/lab-results`, `/ai/sessions`, etc.)

### 3.2 Optional Demographics

`--dob`, `--gender`, `--height-cm`, `--weight-kg` are all optional. The metabolic scoring engine requires height and weight for BMI calculation; omitting them returns a partial score.

### 3.3 Seed Multiple Patients

For pilot batches, use a loop:

```bash
cd /Users/pth/Developer/Metocare/backend

while IFS=',' read -r email password full_name dob gender height weight; do
  python scripts/seed_patient.py \
    --email "$email" \
    --password "$password" \
    --full-name "$full_name" \
    --dob "$dob" \
    --gender "$gender" \
    --height-cm "$height" \
    --weight-kg "$weight"
done < /path/to/pilot_patients.csv
```

---

## 4. MFA Enrollment for Admin Accounts

Admin roles (`super_admin`, `internal_admin`, `doctor`, `clinic_admin`) require TOTP MFA before accessing protected resources. A 403 with `{"detail":"MFA not enrolled"}` is returned if MFA is not set up.

### 4.1 Obtain a Login Token

```bash
curl -sX POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@metocare.vn","password":"SecurePass!2026"}' \
  | jq .
```

Expected response:
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "mfa_required": true
}
```

Store the token:
```bash
export TOKEN="<access_token from above>"
```

### 4.2 Enroll TOTP

```bash
curl -sX POST http://localhost:8000/api/v1/auth/mfa/enroll \
  -H "Authorization: Bearer $TOKEN" \
  | jq .
```

Expected response:
```json
{
  "secret": "BASE32SECRET...",
  "otpauth_uri": "otpauth://totp/MetoCare:admin@metocare.vn?secret=...&issuer=MetoCare",
  "qr_code": "data:image/png;base64,..."
}
```

### 4.3 Add to Authenticator App

1. Open **Google Authenticator**, **Authy**, or any TOTP-compatible app.
2. Tap **Add account** → **Scan QR code**.
3. Scan the QR code embedded in `qr_code` (base64 PNG). Alternatively, enter the `secret` manually.
4. Note the 6-digit code shown in the app.

### 4.4 Verify and Confirm Enrollment

```bash
# Replace <6-digit-code> with the current TOTP code from your authenticator
curl -sX POST http://localhost:8000/api/v1/auth/mfa/verify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"<6-digit-code>"}' \
  | jq .
```

Expected response (success):
```json
{
  "message": "MFA enrollment confirmed",
  "mfa_enabled": true
}
```

> **TOTP codes expire every 30 seconds.** If you receive `{"detail":"Invalid MFA code"}`, wait for the next code rotation and retry.

### 4.5 Subsequent Logins with MFA

After enrollment, every login returns `mfa_required: true`. Complete login with:

```bash
# Step 1: initial login (returns limited token + mfa_required flag)
RESP=$(curl -sX POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@metocare.vn","password":"SecurePass!2026"}')

PARTIAL_TOKEN=$(echo $RESP | jq -r .access_token)

# Step 2: provide TOTP code
curl -sX POST http://localhost:8000/api/v1/auth/mfa/login \
  -H "Authorization: Bearer $PARTIAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"<6-digit-code>"}' \
  | jq .
```

The full `access_token` returned can be used for all admin API calls.

---

## 5. First Login Test — All Roles

Run these checks to verify each seeded account is functional.

### 5.1 Admin Login

```bash
curl -sX POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@metocare.vn","password":"SecurePass!2026"}' \
  | jq '{token_type, mfa_required}'
```

Expected: `{"token_type": "bearer", "mfa_required": true}`

Complete MFA login (Section 4.5), then test an admin-only endpoint:

```bash
export ADMIN_TOKEN="<full token after MFA>"
curl -s http://localhost:8000/api/v1/admin/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | jq '. | length'   # should return a number >= 1
```

### 5.2 Patient Login

```bash
PATIENT_RESP=$(curl -sX POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"patient01@pilot.metocare.vn","password":"Patient01!Pass"}')

echo $PATIENT_RESP | jq '{token_type, mfa_required}'
# Expected: {"token_type": "bearer", "mfa_required": false}

export PATIENT_TOKEN=$(echo $PATIENT_RESP | jq -r .access_token)
```

Test patient profile access:

```bash
curl -s http://localhost:8000/api/v1/patients/me \
  -H "Authorization: Bearer $PATIENT_TOKEN" \
  | jq '{id, full_name, gender}'
```

---

## 6. PatientProfile Verification

### 6.1 Confirm Profile Exists and Fields Are Set

```bash
curl -s http://localhost:8000/api/v1/patients/me \
  -H "Authorization: Bearer $PATIENT_TOKEN" \
  | jq .
```

Expected response (fields depend on what was seeded):
```json
{
  "id": "<patient_profile_id>",
  "user_id": "<user_id>",
  "full_name": "Nguyen Van A",
  "dob": "1980-04-12",
  "gender": "male",
  "height_cm": 170.0,
  "weight_kg": 72.0,
  "risk_segment": null
}
```

### 6.2 Verify IDs Match Seed Output

Cross-reference the `id` (patient_profile_id) and `user_id` against the values printed by `seed_patient.py`. Mismatch indicates a data issue — do not proceed until resolved.

### 6.3 Verify via Database (Direct SQL)

```bash
# SQLite
sqlite3 backend/data/mcp_dev.sqlite3 \
  "SELECT u.id, u.email, u.role, pp.id AS profile_id
   FROM users u LEFT JOIN patient_profiles pp ON pp.user_id = u.id
   WHERE u.email = 'patient01@pilot.metocare.vn';"

# PostgreSQL
psql "$MCP_DATABASE_URL" -c \
  "SELECT u.id, u.email, u.role, pp.id AS profile_id
   FROM users u LEFT JOIN patient_profiles pp ON pp.user_id = u.id
   WHERE u.email = 'patient01@pilot.metocare.vn';"
```

---

## 7. Troubleshooting Common Issues

### 7.1 `403 Forbidden — MFA not enrolled`

**Symptom:** Admin API call returns `{"detail": "MFA not enrolled"}`.

**Cause:** The admin account was created but MFA has not been set up.

**Fix:** Follow Section 4 (MFA Enrollment). The account must go through the full enroll → verify flow before accessing protected endpoints.

---

### 7.2 `patient_profile_id` vs `user_id` Confusion

**Symptom:** Clinical endpoints return 404 or 403 even with a valid token.

**Cause:** Most clinical endpoints (e.g., `GET /health-metrics/{patient_id}`) expect the **PatientProfile UUID** (`patient_profile_id`), not the **User UUID** (`user_id`). These are different values.

**Fix:**
1. Retrieve the correct IDs from `seed_patient.py` output.
2. Or call `GET /api/v1/patients/me` — the `id` field is the `patient_profile_id`.
3. Store both and use the correct one per endpoint.

---

### 7.3 `[ERROR] Password must contain ...`

**Symptom:** `seed_admin.py` or `seed_patient.py` exits with a password policy error.

**Fix:** Use a password that meets all of:
- ≥ 12 characters
- 1+ uppercase, 1+ lowercase, 1+ digit, 1+ special character

Example: `PilotPass!2026`

---

### 7.4 `ImportError` or `ModuleNotFoundError`

**Symptom:** Script exits with `ModuleNotFoundError: No module named 'app'`.

**Cause:** Scripts must be run from the `backend/` directory with the virtual environment active.

**Fix:**
```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
python scripts/seed_admin.py ...
```

---

### 7.5 `OperationalError: unable to open database file`

**Symptom:** SQLite error when running scripts.

**Fix:** Ensure `backend/data/` directory exists:
```bash
mkdir -p /Users/pth/Developer/Metocare/backend/data
```

---

### 7.6 `OperationalError: could not connect to server` (PostgreSQL)

**Symptom:** PostgreSQL connection error.

**Cause:** The database container is not running or `MCP_DATABASE_URL` is wrong.

**Fix:**
```bash
docker compose up -d db
docker compose ps db       # should show "healthy"
echo $MCP_DATABASE_URL     # verify the URL
```

---

### 7.7 `[SKIP] Account already exists`

**Symptom:** Script prints SKIP instead of creating the account.

**Cause:** The email is already registered. This is expected idempotent behaviour.

**Action:** If you need to update an existing account (e.g., reset password), use the admin API:
```bash
curl -sX PATCH http://localhost:8000/api/v1/admin/users/<user_id> \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"password": "NewPass!2026"}' \
  | jq .
```

---

### 7.8 MFA Code Invalid

**Symptom:** `{"detail": "Invalid MFA code"}` when verifying TOTP.

**Cause:** The 6-digit code expired (30-second window) or device clock is skewed.

**Fix:**
1. Wait for the next TOTP rotation and use the new code.
2. Ensure your device clock is synchronised: `sudo ntpdate -u pool.ntp.org` (Linux) or check Date & Time settings (macOS).

---

*Last updated: 2026-06-18 by PA-01 automation.*
