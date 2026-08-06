# 08 — Backup & Restore Runbook (WS8)

**Date:** 2026-08-04 · **Assessor:** independent Backup & Restore assessor (fresh context, direct source inspection)
**Branch:** `feat/patient-platform-journey2` · **HEAD:** `6ab3b04` · **Alembic head:** `j4_m8_consent_versioning` (single head — computed from all 75 revision files in `backend/alembic/versions/`)

**Method.** Every claim below is either backed by a `file:line` citation or a command I ran in this repo, or it is explicitly marked `UNVERIFIED` with the exact command to run. Azure portal/CLI access was **not** available this session, so **no live Azure state is asserted** — in particular I do **not** claim PITR is enabled, nor any retention value.

**Scope note.** Documentation only. No code, no Azure workflow file, and no Postgres firewall rule was modified.

---

## 0. Executive answer

> **If the staging container is redeployed tomorrow, every medical-document and lab-upload binary is permanently lost, while the database rows that point at them survive — leaving the system in an undetected orphan state with no reconciliation job and no way to 500-free reprocess.**

The Postgres side is in decent shape (a real, fail-closed pre-migration restore-point gate exists — `scripts/pre_migration_backup.sh`). The object-storage side has **no backup, no restore, and no reconciliation whatsoever**, and the "just flip `MCP_STORAGE_MODE=azure`" remediation recorded in `15-FINAL-LAUNCH-REVIEW.md` **does not work as written** (see BR-F2).

---

## 1. Asset inventory — what must survive

| # | Durable asset | Where it lives | Backup status today | Evidence |
|---|---|---|---|---|
| A1 | **Postgres relational data** (all 70+ tables incl. `medical_documents`, `document_pages`, `lab_documents`, `lab_results`, `health_metrics`, `medications`, `medication_schedules`, `dose_occurrences`, `consultations`, `meto_consents`, `users`, `patient_profiles`) | Azure PostgreSQL Flexible Server (name from `secrets.POSTGRES_SERVER_NAME`) | **Automated Azure backups assumed; PITR window verified only at deploy time by a gate script.** Retention value not in repo. | `.github/workflows/azure-staging.yml:26` (`RG: rg-metocare-staging`); `scripts/pre_migration_backup.sh:149-159` reads `backup.earliestRestoreDate` + `backup.backupRetentionDays` and **fails closed** if absent |
| A2 | **PHI-encrypted columns inside A1** (Fernet ciphertext in TEXT columns) | Same rows as A1 | Backed up *as ciphertext* with A1. **Useless without A3.** | `backend/app/core/crypto.py:120-176` (`EncryptedString` TypeDecorator); 27 encrypted columns — e.g. `app/models/patient.py:28-38` (`full_name`, `phone`, `address`, `known_conditions`, `allergies`, `family_history`), `app/models/user.py:54,61`, `app/models/medical_document.py:128` (`ocr_raw`), `app/models/clinical.py:98` (`raw_text`) |
| A3 | **PHI encryption keys** (`MCP_ENCRYPTION_KEYS`, comma-separated Fernet rotation list) | Azure Key Vault secret `mcp-encryption-keys`, vault `kv-metocare-stgd9e7` | **Key Vault soft-delete / purge-protection state UNVERIFIED.** No key escrow, no documented key-backup procedure anywhere in repo. | `.github/workflows/azure-staging.yml:29,122`; `backend/app/core/config.py:35-38` |
| A4 | **JWT signing secret** (`MCP_SECRET_KEY`) — also derives the **blob-token HMAC key** | Key Vault secret `mcp-secret-key` | Same as A3. Note: losing it invalidates every outstanding signed blob URL (recoverable — clients re-request). | `azure-staging.yml:121`; `backend/app/services/storage/signing.py:51-58` (`derive_blob_secret(app_secret)`); `backend/app/services/storage/local.py:101-105` |
| A5 | **DB connection string** | Key Vault secret `mcp-database-url` | Same as A3. | `azure-staging.yml:120` |
| A6 | **Object-storage blobs** — every uploaded medical document (quarantine + accepted copies), every per-page image reference, every lab-upload binary | **Container-local filesystem** `/app/storage` inside the ACA replica | **NONE. Zero backup, zero replication, zero volume mount.** Destroyed on every revision change, replica restart, or eviction. | `backend/app/core/config.py:86-87` (`storage_mode="local"`, `storage_local_dir="./storage"`); `azure-staging.yml:209` and `azure-production.yml:222` both set `MCP_STORAGE_MODE=local`; `backend/Dockerfile:19,30` (`WORKDIR /app`, `RUN mkdir -p /app/data /app/storage`) — no `VOLUME`, and no `--mount`/`az containerapp env storage` anywhere in `.github/workflows/` |
| A7 | **Audit log** (`audit_logs`, append-only) | Postgres table (part of A1) | Backed up with A1. **Retention purge implemented but never scheduled** — see §7. | `backend/app/models/governance.py:55-84`; `backend/app/services/audit_retention.py:43-71`; `backend/app/jobs/maintenance.py:23-30` |
| A8 | **App config / feature flags** | Env vars baked into the ACA revision by the workflow files | **Version-controlled for everything in the workflow**, but auth-posture vars (`MCP_ALLOW_RELAXED_AUTH`, `MCP_MFA_ENFORCEMENT_ENABLED`) are set out-of-band → config drift (already logged as PROD-F4). | `azure-staging.yml:203-218`; neither var appears in any workflow (`grep -n "ALLOW_RELAXED\|MFA_ENFORCEMENT" .github/workflows/*.yml` → no match) |
| A9 | **Container images** | GHCR `ghcr.io/<owner>/metocare-backend:<tag>` | Immutable, tag-per-SHA; effectively a rollback artifact. | `azure-staging.yml:147,189` |
| A10 | **Mobile on-device state** (SecureStore token/session) | Patient handset | Not a server asset; **not recoverable and not required** — re-login restores it. | `mobile/` (SecureStore AES on-device, per program docs) |
| A11 | **Alembic schema lineage** | `backend/alembic/versions/*.py` in git + `alembic_version` table | Git = backup. Single-head gate enforced in CI. | `.github/workflows/ci.yml:78-91` |

### Blob-key → DB-row mapping (needed for every restore below)

Server-generated keys only; clients never supply a key.

```
<container>/<patient_id>/<YYYYMM>/<uuid>.<ext>      # base.py:56-65
container ∈ { "quarantine", "accepted" }            # base.py:21-23
```

| DB column | Container | Notes |
|---|---|---|
| `medical_documents.quarantine_key` (NOT NULL) | `quarantine/` | Written at upload-session; best-effort deleted post-finalize (`app/api/v1/routes/documents.py:244-250`) |
| `medical_documents.accepted_key` (nullable) | `accepted/` | Set only after validate+scan; the bytes are **re-written**, not moved (`app/services/mdi/service.py:244-249`) |
| `document_pages.storage_key` | `accepted/` | **Same key as the parent document's `accepted_key`** — pages are not separate blobs (`app/services/mdi/service.py:368-378`) |
| `lab_documents.storage_key` (NOT NULL) | varies; manual entries use the sentinel `manual:<patient_id>` | `app/services/lab.py:323-325` (real upload) and `app/services/lab.py:496-498` (manual — **not a blob**, must be excluded from reconciliation) |

`StorageBackend.move()` exists (`base.py:109-111`, `local.py:86-92`) but is **never called by application code** (`grep -rn "\.move(" backend/app` → only its own definition). Quarantine→accepted is a copy; both blobs exist until the post-commit sweep deletes the quarantine one.

---

## 2. PROD-F1, stated bluntly

### What is actually true

`MCP_STORAGE_MODE=local` is hard-coded in **both** deploy workflows (`azure-staging.yml:209`, `azure-production.yml:222`). `LocalDiskStorage` writes to `settings.storage_local_dir` = `./storage`, resolved against `WORKDIR /app` → `/app/storage`, a directory created **in the image layer** (`backend/Dockerfile:30`). There is no Azure Files mount, no `az containerapp env storage` command, and no `VOLUME` declaration anywhere in the repo.

Azure Container Apps replicas have **ephemeral writable layers**. Therefore:

### What is lost, exactly

| Event | Postgres | `/app/storage` blobs | Resulting state |
|---|---|---|---|
| `azure-staging.yml` redeploy (new revision) | intact | **all destroyed** | every `medical_documents` row survives with a non-null `quarantine_key`/`accepted_key` pointing at nothing; every `lab_documents.storage_key` dangles |
| Replica restart / crash / node eviction | intact | **all destroyed** | same |
| Scale-to-zero | N/A today — both apps run `--min-replicas 1` (`azure-staging.yml:223,227`), so scale-to-zero is not the active risk; **replica replacement is** | | |
| ACA revision rollback to a prior image | intact | **destroyed again** (fresh replica) | rolling back does not recover blobs |

**The DB rows survive while their blobs do not.** Nothing in the codebase detects this, and nothing repairs it (§5c).

### Behaviour of the running app after blob loss (verified in source)

| Endpoint | Behaviour when the blob is gone | Verdict |
|---|---|---|
| `GET /documents` , `GET /documents/{id}` | 200, document listed as normal (metadata-only reads) | silently misleading |
| `GET /documents/{id}/file` | **200 with a valid signed URL** — no existence check before signing (`app/api/v1/routes/documents.py:338-345`) | misleading |
| `GET /documents/blob/{token}` | **404** `"Không tìm thấy tệp."` (`documents.py:290-292`, catches `ObjectNotFound`) | honest |
| `POST /documents/{id}/finalize` | **400** `"Chưa nhận được tệp tải lên."` (`app/services/mdi/service.py:161-163` → `UploadValidationError` → `documents.py:148-149`) | honest |
| `POST /documents/{id}/reprocess` | **HTTP 500.** `mdi.reprocess_document` calls `get_storage().get_bytes(doc.accepted_key)` with no guard (`app/services/mdi/service.py:545`); `ObjectNotFound` subclasses `StorageError`→`Exception` (`storage/base.py:33-38`), **not** `MdiError` (`mdi/service.py:66`), so the route's `except mdi.MdiError` (`documents.py:514`) does not catch it | **BR-F5 — unhandled 500** |

### The owner-side fix — and why the currently-recorded fix will not work

`15-FINAL-LAUNCH-REVIEW.md:42` records the remediation as *"set `MCP_STORAGE_MODE=azure` + connection string + Blob soft-delete/PITR"*. **Doing exactly that breaks the app.** `AzureBlobStorage.__init__` unconditionally raises:

```python
# backend/app/services/storage/azure_blob.py:27-30
def __init__(self, connection_string: str, container: str) -> None:
    self._connection_string = connection_string
    self._container = container
    raise StorageError(_DEFERRED)          # ← every method is a stub too (:32-54)
```

The adapter is **unimplemented**, not merely unconfigured. `get_storage()` is a process-global lazy singleton (`storage/factory.py:18-23,38-51`), so the first document request after flipping the flag raises `StorageError` and the whole document vertical fails.

**Correct owner-side sequence (all four steps required):**

1. **Implement** `AzureBlobStorage` against `azure-storage-blob`: account-key-signed SAS per blob + operation + expiry, mirroring the contract `LocalDiskStorage` emulates (`storage/base.py:79-115`). Required methods: `signed_put_url`, `signed_get_url`, `put_bytes`, `get_bytes`, `exists`, `size`, `move`, `delete`. Note `signed_get_url` must return an **absolute** URL (the local adapter returns one relative to `/api/v1/documents/blob` — `local.py:22,50`), and clients already treat `SignedUrl.url` as opaque.
2. **Provision** a Storage Account in `rg-metocare-staging`, one container (default name `documents`, `config.py:94`), with:
   - **blob soft-delete** ≥ 30 days,
   - **blob versioning** ON,
   - **container soft-delete** ≥ 7 days,
   - **point-in-time restore** ON (requires versioning + change feed),
   - **immutability/legal-hold OFF** (GDPR erasure must be able to hard-delete — see §5d/BR-F8),
   - public access **disabled**; access via connection string only.
3. **Store** the connection string in Key Vault as `storage-azure-connection-string`, and add to the deploy workflow (owner-gated file):
   ```
   MCP_STORAGE_MODE=azure
   MCP_STORAGE_AZURE_CONNECTION_STRING=secretref:storage-conn
   MCP_STORAGE_AZURE_CONTAINER=documents
   ```
   Setting names are fixed by `backend/app/core/config.py:86,93-94` (prefix `MCP_`).
4. **Migrate existing blobs** — there is no migration tool. For a synthetic pilot the answer is "re-seed"; for any real data, a one-shot copy job must run **before** the flag flip, or the flip itself becomes the data-loss event.

**Interim mitigation if step 1 is not funded now:** mount Azure Files at `/app/storage` via `az containerapp env storage set` + `--mount` (no code change; `LocalDiskStorage` is filesystem-agnostic and traversal-safe — `local.py:34-41`). This makes blobs survive redeploys and gives Azure Files snapshot/soft-delete. It does **not** give per-blob versioning. This is the cheapest path to "documents survive a redeploy".

---

## 3. RPO / RTO

### Proposed targets

| Asset | Controlled pilot (synthetic, ≤50 users) | Public beta (real PHI) |
|---|---|---|
| Postgres (A1/A2/A7) | RPO ≤ 30 min · RTO ≤ 8 h | RPO ≤ 15 min · RTO ≤ 4 h |
| Object storage (A6) | RPO ≤ 24 h · RTO ≤ 8 h (re-seed acceptable) | **RPO ≤ 15 min · RTO ≤ 4 h** (blob PITR) |
| Secrets/keys (A3–A5) | RPO 0 (KV soft-delete) · RTO ≤ 1 h | RPO 0 · RTO ≤ 30 min, purge-protection ON |
| Full environment rebuild | RTO ≤ 1 day | RTO ≤ 8 h |

### What today's posture actually achieves

| Asset | Actual RPO | Actual RTO | Evidence |
|---|---|---|---|
| Postgres | **UNVERIFIED but non-zero** — the deploy gate refuses to run migrations unless `earliestRestoreDate` is present and `backupRetentionDays ≥ 1` (`scripts/pre_migration_backup.sh:157-159`). Azure Flexible Server PITR granularity is sub-minute when enabled. Actual retention: **UNVERIFIED — run** `az postgres flexible-server show -g <rg> -n <server> --query "backup"` | **UNVERIFIED**, and **never drilled** — no restore has ever been performed against this repo's evidence trail (`grep -rn "flexible-server restore" .` → only the two `log`/summary strings inside `pre_migration_backup.sh:170-174,271-276`, i.e. instructions, never an execution) | as cited |
| Object storage | **RPO = ∞ (total loss)** | **RTO = never** — the data does not exist anywhere else | §2 |
| Secrets | KV soft-delete/purge-protection **UNVERIFIED — run** `az keyvault show -n kv-metocare-stgd9e7 --query "properties.{softDelete:enableSoftDelete,purgeProtection:enablePurgeProtection,retention:softDeleteRetentionInDays}"` | unknown | — |
| Full rebuild | Repo-complete (Dockerfile, workflows, migrations, seed scripts all in git) — **but has never been exercised** | est. 4-8 h | `backend/Dockerfile`, `.github/workflows/*`, `backend/scripts/seed_*.py` |

> **A backup that has never been restored is not a backup.** The Postgres restore path is *asserted* by a gate script that has never been followed by an actual `az postgres flexible-server restore`. §8 exists to close that gap locally at zero Azure cost.

---

## 4. Backup procedures

### 4.1 Postgres — automated (Azure platform)

Azure Flexible Server takes automated full+differential+WAL backups when the server is provisioned with retention ≥ 1 day. This repo's provisioning workflow does **not** pass `--backup-retention` or `--geo-redundant-backup`:

```
# .github/workflows/provision-postgres.yml:48-59
az postgres flexible-server create --name metocare-pg-dev ... \
  --sku-name Standard_B1ms --tier Burstable --version 16 --storage-size 32 --public-access 0.0.0.0 --yes
```

so whatever the server has is the **Azure default** (7 days, locally-redundant) unless changed out-of-band. Note this workflow provisions `metocare-pg-dev` in `rg-metocare-dev`/`malaysiawest`, which is **not** the staging RG (`rg-metocare-staging`, `azure-staging.yml:26`) — the staging/prod server identity comes from `secrets.POSTGRES_SERVER_NAME` and is **UNVERIFIED**.

**Vendor constraint (not repo-verified):** Azure PostgreSQL **Burstable** tier does not support customer-initiated on-demand backups (the repo confirms this empirically: `pre_migration_backup.sh:135-138` cites `CustomerOnDemandBackupCannotBePerformedOnBurstableServer`) and does not support geo-redundant backup. If the pilot must survive a regional outage, the tier must be raised to General Purpose.

**Owner actions (one-time):**
```bash
az postgres flexible-server show -g <rg> -n <server> \
  --query "{tier:sku.tier, retention:backup.backupRetentionDays, geo:backup.geoRedundantBackup, earliest:backup.earliestRestoreDate}"
# then, to meet the beta target:
az postgres flexible-server update -g <rg> -n <server> --backup-retention 14
```

### 4.2 Postgres — pre-migration restore point (implemented, fail-closed)

`scripts/pre_migration_backup.sh` is a genuine gate:

- validates `POSTGRES_SERVER_NAME` / `RESOURCE_GROUP` before any `az` call (`:56-72`);
- aborts unless the server state is `Ready` (`:130-132`);
- on **Burstable**, verifies the PITR window and records a restore point, dying if `earliestRestoreDate` is empty or retention < 1 (`:154-159`) — *fail closed, migration does not run*;
- on higher tiers, creates an on-demand backup and polls `completedTime` until non-empty, dying on timeout (`:206-306`);
- writes the exact rollback command into `$GITHUB_STEP_SUMMARY` (`:176-191`, `:255-279`).

It is wired into **two** of three deploy paths:

| Workflow | Backup gate | Migration step |
|---|---|---|
| `ci.yml` (auto-deploy on push to `main`) | ✅ `ci.yml:414-423` | `ci.yml:425-450` |
| `azure-production.yml` | ✅ `azure-production.yml:172-181` | `azure-production.yml:183-208` |
| `azure-staging.yml` (**workflow_dispatch — the path used for the pilot deploy**, run `30797337153` per `00-CURRENT-STATE.md:28`) | ❌ **absent** | `azure-staging.yml:145-186` |

→ **BR-F1** (P0), §9.

### 4.3 Object storage

**Nothing exists.** No `pg_dump`-equivalent, no `az storage blob copy`, no snapshot, no sync job — `grep -rn "az storage\|blob copy\|rsync" .github/ scripts/` returns no match.

### 4.4 Secrets

No export, no escrow, no documented rotation-with-retention procedure. `MCP_ENCRYPTION_KEYS` is a comma-separated rotation list and `crypto.py:58-65` builds a `MultiFernet` over **all** entries (first = encrypt, all = decrypt), so *retiring an old key silently makes every row still encrypted under it unreadable* (§5d).

### 4.5 Verification cadence (proposed)

| What | Cadence | How |
|---|---|---|
| Postgres restore drill to a scratch server | before pilot start, then monthly | §5a; record server name, restore time, row counts, alembic head in `docs/launch-readiness/evidence/` |
| Local restore drill (no Azure cost) | every release train | §8 |
| Blob reconciliation report | daily once §5c job exists | §5c |
| Key-integrity probe (decrypt a canary row) | on every deploy + after every restore | §6 step 5 |
| KV soft-delete/purge-protection assertion | quarterly | §3 command |

---

## 5. RESTORE RUNBOOK

> **Rule 0 — never restore in place.** Azure Flexible Server PITR always restores to a **new server**. Restore, verify (§6), then repoint `mcp-database-url`. Never `az postgres flexible-server restore` onto the live name.
>
> **Rule 1 — before any restore, freeze writes.** Set the backend to 0 replicas (`az containerapp update -g <rg> -n ca-metocare-backend --min-replicas 0 --max-replicas 0`) so no traffic lands on a half-restored world. Both apps currently run min=1 (`azure-staging.yml:223`).
>
> **Rule 2 — a DB restore can resurrect erased PHI.** Read §5d/BR-F8 *before* choosing a restore point.

### 5a. Full DB restore to a point in time

```bash
RG=rg-metocare-staging
SRC=<POSTGRES_SERVER_NAME>                 # value lives in GitHub secrets, not the repo
NEW=${SRC}-restore-$(date -u +%Y%m%d%H%M)
WHEN=2026-08-04T09:15:00Z                  # UTC; must be ≥ backup.earliestRestoreDate

# 0. Confirm the target time is inside the window (fail closed if not).
az postgres flexible-server show -g $RG -n $SRC --query "backup"

# 1. Freeze writes.
az containerapp update -g $RG -n ca-metocare-backend --min-replicas 0 --max-replicas 0

# 2. Restore to a NEW server.
az postgres flexible-server restore -g $RG --name $NEW --source-server $SRC --restore-time $WHEN

# 3. Re-apply the firewall/network posture of the source server to $NEW.
#    (Project guardrail: do NOT modify the SOURCE server's firewall. Configure the NEW one only.)
az postgres flexible-server firewall-rule create -g $RG --name $NEW \
  --rule-name AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0

# 4. Verify BEFORE cutting over — run the whole of §6 against $NEW.

# 5. Cut over: update the Key Vault secret, then redeploy so the app picks it up.
az keyvault secret set --vault-name kv-metocare-stgd9e7 -n mcp-database-url --value "postgresql+psycopg2://<user>:<pw>@${NEW}.postgres.database.azure.com:5432/metocare?sslmode=require"
gh workflow run azure-staging.yml            # re-deploy; re-reads KV at :120

# 6. Unfreeze (the deploy sets --min-replicas 1 at azure-staging.yml:223).
```

**Schema-vs-code check.** After restore, the DB is at whatever `alembic_version` held at `$WHEN`. The running image may be newer. Reconcile explicitly:

- **DB older than image** → run the migration job (`azure-staging.yml:145-186`), or locally `alembic upgrade head`.
- **DB newer than image** → roll the image back to the matching tag (GHCR tags are per-SHA, `azure-staging.yml:147`) rather than downgrading. Downgrade only if unavoidable — see the destructive-migration table below.

**Migration reversibility (scanned across all 75 revisions):**

| Class | Files | Restore implication |
|---|---|---|
| **Destructive upgrade (drops columns)** | `alembic/versions/k1_a1b_f1_schema_complete.py:221` drops `level`; its downgrade drops `action_level`/`frequency`/`label` (`:257-259`) | `downgrade` is **structurally** reversible but **data in the dropped columns is gone**. Never rely on downgrade to recover data. |
| **Data migrations (`op.execute` with UPDATE/INSERT)** | `k2_s0_integrity_guards.py`, `k2_s0_round3_hardening.py`, `p0_m01_medication_lifecycle_fields.py`, `t11_m1_health_metric_original.py`, `t13_p0_note_draft_status.py`, `hmbk_backfill_lab_metrics.py` | Downgrades restore *schema*, not *pre-migration values*. **PITR is the only real rollback for these.** `p0_m01_medication_lifecycle_fields.py:34` states this itself: "Pre-migration backup gate in CI has run and verified backup Succeeded". |
| **No-op downgrades** | `merge_c1m08_p0med_heads.py`, `t12_merge_p0_m1_heads.py` | Merge points — expected, harmless. |
| **Current head** | `j4_m8_consent_versioning.py:27-38` — additive column + unique constraint, downgrade is exact | Safe to `alembic downgrade -1`. |

### 5b. Single-table / single-row recovery

Azure has no table-level restore. The pattern is: **restore to a side server, extract, load, drop the side server.**

```bash
# 1. §5a steps 0-3, but STOP after the restore — do not cut over. Call it $NEW.

# 2. Extract only what you need (example: one patient's lab results).
pg_dump "postgresql://<user>:<pw>@${NEW}.postgres.database.azure.com:5432/metocare?sslmode=require" \
  --data-only --table=lab_results --column-inserts \
  | grep "'<patient_profile_id>'" > /tmp/recover_lab_results.sql

# 3. Review the file by eye. It contains PHI ciphertext — handle as PHI, delete after use.

# 4. Load into the LIVE database inside an explicit transaction, with a dry run first.
psql "$LIVE_URL" -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
\i /tmp/recover_lab_results.sql
-- inspect, then:
-- COMMIT;  or  ROLLBACK;
SQL

# 5. Delete the side server and the extract.
az postgres flexible-server delete -g $RG -n $NEW --yes
shred -u /tmp/recover_lab_results.sql
```

**Constraints to respect when re-inserting:**

- Clinical tables use **soft delete** (`deleted_at`/`deleted_by`) — recovering a "deleted" row is often just `UPDATE ... SET deleted_at = NULL`, no restore needed. Check first:
  ```sql
  SELECT id, deleted_at, deleted_by FROM lab_results WHERE patient_id = :pid ORDER BY created_at DESC;
  ```
- `document_pages` has `uq_document_page_no (document_id, page_no)` (`app/models/medical_document.py:120`) — re-inserting a page that already exists aborts the transaction.
- `meto_consents` has `uq_meto_consent_user_category (user_id, context_type)` (`j4_m8_consent_versioning.py:30-32`).
- `medical_documents` has a partial-unique accepted index on `(patient_id, sha256)` (inferred from the `IntegrityError`→409 handler at `app/api/v1/routes/documents.py:236-243`).
- `audit_logs` is append-only by policy (`app/models/governance.py:56`) — **never** re-insert audit rows with new ids; that fabricates history.

### 5c. Blob loss with DB intact — reconciliation

This is the **expected steady-state failure** today (§2), not a hypothetical.

**What exists / does not exist:**

- ❌ No reconciliation job. `grep -rni "reconcil\|orphan" backend/app backend/scripts` finds only `app/services/account.py:156` (a local variable) and a *comment* at `app/api/v1/routes/account.py:104-105` promising "the orphan-reconciliation sweep" that does not exist.
- ❌ `backend/scripts/data_integrity_cleanup.py` — named in `15-FINAL-LAUNCH-REVIEW.md:62` as the PROD-F6 remediation — **does not touch object storage at all**. Its entire scope is creatinine unit plausibility on `LabResult`/`HealthMetric` (`:52-88`, `:128-321`). Scheduling it would close nothing. → **BR-F3**.
- ❌ No quarantine TTL sweep, despite `medical_documents.upload_expires_at` existing for exactly that (`app/models/medical_document.py:105-106`) and two code comments asserting one runs (`app/api/v1/routes/documents.py:246`, model docstring). `grep -rn "upload_expires_at" backend/app` → the column definition and nothing else. → **BR-F4**.

**Step 1 — inventory the DB side (safe, read-only).**

```sql
-- Every blob key the DB believes exists, with its owning row.
SELECT 'medical_document.quarantine' AS kind, id AS row_id, patient_id, quarantine_key AS key
  FROM medical_documents WHERE quarantine_key IS NOT NULL AND deleted_at IS NULL
UNION ALL
SELECT 'medical_document.accepted', id, patient_id, accepted_key
  FROM medical_documents WHERE accepted_key IS NOT NULL AND deleted_at IS NULL
UNION ALL
SELECT 'document_page', p.id, d.patient_id, p.storage_key
  FROM document_pages p JOIN medical_documents d ON d.id = p.document_id
 WHERE p.storage_key IS NOT NULL AND d.deleted_at IS NULL
UNION ALL
SELECT 'lab_document', id, patient_id, storage_key
  FROM lab_documents
 WHERE storage_key IS NOT NULL AND storage_key NOT LIKE 'manual:%';   -- app/services/lab.py:498 sentinel
```

**Step 2 — probe storage and mark what is gone.** Run inside the container (local adapter) or against the Storage Account (once §2 step 1 lands). This is the job to add at `backend/app/jobs/reconcile_blobs.py`, invoked as `python -m app.jobs.reconcile_blobs [--apply]`; the read-only default mirrors `data_integrity_cleanup.py`'s `--dry-run` convention:

```python
# sketch — mirrors StorageBackend.exists() (app/services/storage/base.py:101-103)
from app.services.storage import get_storage
from app.models.medical_document import (
    MedicalDocument, DocumentPage,
    DOC_STATUS_FAILED, OBJECT_STATE_REJECTED,          # models/medical_document.py:48,54
)

storage = get_storage()
for doc in db.query(MedicalDocument).filter(MedicalDocument.deleted_at.is_(None)):
    if doc.accepted_key and not storage.exists(doc.accepted_key):
        if apply:
            doc.status = DOC_STATUS_FAILED                 # honest, already a modelled state
            doc.object_state = OBJECT_STATE_REJECTED
            doc.failure_reason = "blob_missing"            # column exists, models/...:104
        report["documents_missing_blob"].append(doc.id)
```

Use the **existing** enum values — `DOC_STATUS_FAILED = "failed"` and `failure_reason` are already modelled (`app/models/medical_document.py:48,104`), so no migration is required and the mobile client's existing failed-state rendering applies.

**Step 3 — the reverse direction (blobs with no DB row).** Enumerate storage keys, left-join against the Step-1 result, and **delete** unreferenced keys older than the upload TTL. Untracked blobs are un-erasable PHI: they cannot be reached by `delete_account`'s key collection (`app/services/account.py:183-215`), which derives keys **from DB rows only**.

**Step 4 — degrade honestly.** Even with rows marked, `POST /documents/{id}/reprocess` still 500s (BR-F5). Fix in `app/services/mdi/service.py:543-546`:

```python
if doc.object_state != OBJECT_STATE_ACCEPTED or not doc.accepted_key:
    raise InvalidDocumentState("Chỉ có thể xử lý lại tài liệu đã được chấp nhận.")
try:
    data = get_storage().get_bytes(doc.accepted_key)
except ObjectNotFound as exc:                       # already imported at :55
    raise UploadValidationError("Tệp gốc không còn khả dụng.") from exc   # → 400, documents.py:148
```

and add an existence check before signing in `app/api/v1/routes/documents.py:338-345` so `/file` returns 409/404 instead of a URL that will 404.

**Step 5 — for a synthetic pilot,** the pragmatic recovery is re-seed: `backend/scripts/seed_demo_pilot.py` / `seed_pilot_journeys.py` are idempotent seeders already used for the pilot cohort. This is the *documented caveat* in `12-PILOT-OPERATIONS-RUNBOOK.md` — it is **not** a recovery path for real patient data.

### 5d. Encryption-key loss

**Be blunt: if `MCP_ENCRYPTION_KEYS` is lost and no copy exists, the PHI encrypted under it is unrecoverable. There is no backdoor, no escrow, and no recovery procedure. Restoring the database does not help — the backup contains ciphertext (A2), and the key is not in it.**

What is lost vs. what survives:

| | Lost | Survives |
|---|---|---|
| Content | `full_name`, `date_of_birth`, `phone`, `address`, `known_conditions`, `allergies`, `family_history`, `lifestyle_profile` (`app/models/patient.py:28-38`); `users.email`, `users.mfa_secret` (`app/models/user.py:54,61`); `document_pages.ocr_raw` (`medical_document.py:128`); `lab_documents.raw_text` (`clinical.py:98`); Meto conversation content (`app/models/ai.py:44,91`); care-plan and consultation notes (`app/models/care.py:171,199,310-311,329`; `app/models/consultation.py:176`) | all non-encrypted columns: metrics, lab numeric values, medication schedules, dose history, audit log, IDs, timestamps, relationships |

**The dangerous part — failure is silent.** `EncryptedString(on_decrypt_failure="none")` returns `None` instead of raising (`app/core/crypto.py:120-176`). That is applied to **`allergies` and `known_conditions`** (`app/models/patient.py:34-35`). After a restore with a wrong or incomplete key list, the app does not error — **it renders the patient as having no allergies**. That is a clinical-safety hazard, not a data-availability one. → **BR-F7**.

Only two columns fail loud: `app/models/care.py:329` and `app/models/consultation.py:176` (`on_decrypt_failure="raise"`).

**Partial loss (key rotation gone wrong) — recoverable:** `_cipher()` builds a `MultiFernet` over *every* entry in the comma-separated list (`crypto.py:58-65`), so re-adding the retired key to `MCP_ENCRYPTION_KEYS` restores readability immediately, no data change needed. `config.py:251-256` scans **every** entry for the committed default, so the rotation list is safe to grow.

**Procedure on suspected key loss:**

1. **Do not** deploy, do not run migrations, do not let the app write — new writes would encrypt under a new key and permanently mix key generations.
2. Recover the key: Key Vault **soft-deleted secret versions** are the first place to look —
   `az keyvault secret list-versions --vault-name kv-metocare-stgd9e7 -n mcp-encryption-keys` and
   `az keyvault secret list-deleted --vault-name kv-metocare-stgd9e7` (`UNVERIFIED` whether soft-delete is on).
3. If recovered: append the old key to `MCP_ENCRYPTION_KEYS` (order matters only for *encryption*: first = encrypt), redeploy, verify with the canary probe (§6 step 5), then re-encrypt with `app.core.crypto.rotate()` (`crypto.py:96-98`) as a batch job.
4. If not recovered: **declare the encrypted columns lost.** Under GDPR this is a personal-data-availability incident — notify per `13-INCIDENT-RESPONSE.md`. Mark affected rows rather than deleting them (the non-encrypted clinical values are still valid and clinically useful). Prefer flipping the affected columns to `on_decrypt_failure="raise"` temporarily so the loss is *visible* rather than rendered as empty allergies.

**Prevention (owner action, do now):** enable Key Vault soft-delete + purge protection; store an offline copy of `mcp-encryption-keys` in the owner's password manager as a break-glass escrow; never rotate by *replacing* the list — only ever prepend.

### 5e. Full-environment rebuild from repo

Everything needed is in git except secrets and blobs.

```bash
# 1. Infra
az group create -n rg-metocare-staging -l southeastasia
az postgres flexible-server create -g rg-metocare-staging -n <server> \
  --tier GeneralPurpose --sku-name Standard_D2ds_v4 --version 16 \
  --backup-retention 14 --geo-redundant-backup Enabled --yes     # ⇐ NOT what provision-postgres.yml does
az postgres flexible-server db create -g rg-metocare-staging --server-name <server> --database-name metocare
az containerapp env create -g rg-metocare-staging -n cae-metocare-staging
az keyvault create -g rg-metocare-staging -n <kv> --enable-purge-protection true

# 2. Secrets — 8 Key Vault entries, names fixed by azure-staging.yml:120-130
for n in mcp-database-url mcp-secret-key mcp-encryption-keys appinsights-connection-string \
         azure-doc-intel-endpoint azure-doc-intel-key deepseek-api-key openrouter-api-key; do
  az keyvault secret set --vault-name <kv> -n "$n" --value "<value>"
done
# mcp-secret-key: >= 32 chars, never the "dev-insecure-secret" default (config.py:246)
# mcp-encryption-keys: MUST be the ORIGINAL key list if the DB is restored from backup

# 3. Schema
cd backend && MCP_DATABASE_URL="<url>" alembic upgrade head && alembic heads   # expect exactly 1

# 4. Data — restore Postgres (§5a) or seed synthetic (backend/scripts/seed_demo_pilot.py)

# 5. App
gh workflow run azure-staging.yml       # builds image, runs migration job, deploys both apps

# 6. Verify — §6 in full.
```

**Known gaps in this path:**
- `provision-postgres.yml` bakes a **Burstable B1ms, 32 GB, no retention flag, `malaysiawest`, `rg-metocare-dev`** server (`:48-59`) — do **not** reuse it verbatim for a staging/prod rebuild.
- Blobs cannot be rebuilt (§2).
- Auth-posture env vars are not in any workflow (A8) — a rebuilt staging will **refuse to boot** if MFA is disabled server-side without `MCP_ALLOW_RELAXED_AUTH=true` (`config.py:264-295`); production will refuse unconditionally (already logged as PROD-F2/SEC-F1).

---

## 6. Restore verification checklist

Run **all** of these against the restored server **before** cutting traffic over. Record output in `docs/launch-readiness/evidence/`.

| # | Check | Command / query | Pass criterion |
|---|---|---|---|
| 1 | Server ready | `az postgres flexible-server show -g $RG -n $NEW --query state -o tsv` | `Ready` |
| 2 | **Alembic head matches code** | `psql "$NEW_URL" -tAc "SELECT version_num FROM alembic_version"` vs `cd backend && alembic heads` | identical, and exactly **one** row / one head (`ci.yml:78-91` enforces one head in CI) |
| 3 | Live app agrees | `curl -s https://<backend-fqdn>/api/v1/info \| jq .migration_version` | equals #2 (`app/api/v1/routes/system.py:38-64`) |
| 4 | **Row counts sane** | `SELECT 'users',count(*) FROM users UNION ALL SELECT 'patient_profiles',count(*) FROM patient_profiles UNION ALL SELECT 'medical_documents',count(*) FROM medical_documents UNION ALL SELECT 'document_pages',count(*) FROM document_pages UNION ALL SELECT 'lab_documents',count(*) FROM lab_documents UNION ALL SELECT 'lab_results',count(*) FROM lab_results UNION ALL SELECT 'health_metrics',count(*) FROM health_metrics UNION ALL SELECT 'medications',count(*) FROM medications UNION ALL SELECT 'dose_occurrences',count(*) FROM dose_occurrences UNION ALL SELECT 'audit_logs',count(*) FROM audit_logs;` | within expected delta of the pre-incident snapshot; **no table at 0 that was non-zero** |
| 5 | **Encryption keys are the right ones** (canary) | `python -c "from app.core.crypto import try_decrypt; ..."` against one known `patient_profiles.full_name` ciphertext, or simply `GET /api/v1/patients/{id}` and confirm the name is not `null` | plaintext returns. **`null` here means wrong key, not missing data** — see BR-F7 |
| 6 | Referential integrity | `SELECT count(*) FROM document_pages p LEFT JOIN medical_documents d ON d.id=p.document_id WHERE d.id IS NULL;` and the same for `lab_results→patient_profiles`, `dose_occurrences→medication_schedules` | all `0` |
| 7 | **Login works** | `POST /api/v1/auth/login` with a known account | 200 + access token |
| 8 | **Document read works end-to-end** | `GET /api/v1/documents` → pick an `accepted` doc → `GET /api/v1/documents/{id}/file` → `GET` the returned signed URL | list 200, `/file` 200, **signed-blob fetch 200 with correct content-type**. A **404** on the last hop = blob loss (`documents.py:290-292`) → run §5c |
| 9 | Blob reconciliation clean | §5c step 1 + 2, dry-run | 0 missing blobs, or a listed, accepted set |
| 10 | Consent gate intact | `GET /api/v1/info \| jq .consent_gate` | `true` |
| 11 | Erasure replay done | §5d/BR-F8 query below returns 0 unreplayed deletions | 0 |
| 12 | Full backend suite against the restored DB | `cd backend && MCP_DATABASE_URL=$NEW_URL python -m pytest tests/ -m integration` | exit 0 (mirrors `ci.yml:113-189`, which already runs the suite against a real Postgres 16) |

---

## 7. Retention & purge (corrects PROD-F5)

**PROD-F5 as recorded (`15-FINAL-LAUNCH-REVIEW.md:61`) says "no enforcement job". That is half right: the job exists; the *schedule* does not.**

Implemented:

- `backend/app/services/audit_retention.py:43-71` — `purge_expired(db, now=None)` deletes per category and returns counts.
- Category mapping at `:20-30`: `auth` = login/logout/register/refresh/token_revoke/mfa_enroll; `admin` = admin_read/admin_action/config_change/role_change; **everything else** = `data_access`.
- TTLs from config (`app/core/config.py:193-197`): auth 365 d, data_access 730 d, admin 1095 d, default 365 d.
- `backend/app/jobs/maintenance.py:23-30` — `run_maintenance()` runs the audit purge **and** expired-refresh-token cleanup; `:33-47` is a CLI entrypoint: `python -m app.jobs.maintenance`.

Missing: **nothing invokes it.** `grep -rn "maintenance" backend/app backend/scripts .github` finds only the module itself. `app/main.py` has no scheduler (`grep -n "scheduler\|APScheduler\|cron" backend/app/main.py` → no match).

**Exact fix — one ACA scheduled job (owner-gated; belongs in `azure-staging.yml` / `azure-production.yml`):**

```bash
az containerapp job create \
  --name caj-metocare-maintenance --resource-group "$RG" --environment "$ENV_NAME" \
  --image "$IMG" \
  --trigger-type Schedule --cron-expression "0 3 * * *" \
  --replica-timeout 900 --replica-retry-limit 1 --parallelism 1 --replica-completion-count 1 \
  --cpu 0.25 --memory 0.5Gi \
  --secrets "db-url=$DB_URL" "enc-keys=$ENC_KEYS" \
  --env-vars "MCP_DATABASE_URL=secretref:db-url" "MCP_ENCRYPTION_KEYS=secretref:enc-keys" "MCP_ENV=staging" \
  --command "python" --args "-m" "app.jobs.maintenance"
```

**Equivalent raw SQL** (for a one-off manual purge; same semantics as `audit_retention.py:49-70`, values from `config.py:194-197`):

```sql
BEGIN;
-- auth: 365 days
DELETE FROM audit_logs
 WHERE timestamp < now() - interval '365 days'
   AND action IN ('login','logout','register','refresh','token_revoke','mfa_enroll');

-- admin: 1095 days
DELETE FROM audit_logs
 WHERE timestamp < now() - interval '1095 days'
   AND action IN ('admin_read','admin_action','config_change','role_change');

-- data_access: 730 days = everything not classified above
DELETE FROM audit_logs
 WHERE timestamp < now() - interval '730 days'
   AND action NOT IN ('login','logout','register','refresh','token_revoke','mfa_enroll',
                      'admin_read','admin_action','config_change','role_change');
COMMIT;
```

**Sizing check before scheduling** (a first purge on a long-lived table can be large):

```sql
SELECT date_trunc('month', timestamp) AS m, count(*) FROM audit_logs GROUP BY 1 ORDER BY 1;
```

Batch with `DELETE ... WHERE id IN (SELECT id ... LIMIT 10000)` in a loop if the first run exceeds ~1 M rows on a Burstable server.

**Interaction with restore:** a DB restore to a point *before* a purge **resurrects purged audit rows**. That is acceptable (audit over-retention is a policy, not a safety, breach), but re-run the purge immediately after any restore.

**Minor defect:** `audit_retention_default_days` is mapped at `audit_retention.py:39` but `purge_expired` only iterates `("auth","data_access","admin")` (`:49`), so the `default` TTL is dead configuration. → BR-F9.

**Not covered by any retention policy:** `medical_documents.upload_expires_at` (quarantine TTL — never enforced, BR-F4), and object-storage blobs generally. Under GDPR storage-limitation, blobs need their own lifecycle rule — once §2 step 1 lands, add an Azure Blob lifecycle-management policy deleting `quarantine/**` after 7 days.

---

## 8. Restore drill — executable locally, no Azure required

A drill a future session can run end-to-end against a scratch Postgres. It exercises the parts we can actually control: schema apply, dump, destroy, restore, and the §6 verification checks. Estimated 15 minutes.

```bash
set -euo pipefail
cd /Users/pth/Developer/Metocare/backend

# ── 1. Scratch Postgres (same image family as docker-compose.yml:9) ───────────
docker run --rm -d --name metocare-drill-pg \
  -e POSTGRES_USER=mcp -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=metocare_drill \
  -p 55432:5432 timescale/timescaledb-ha:pg16
until docker exec metocare-drill-pg pg_isready -U mcp >/dev/null 2>&1; do sleep 2; done

export MCP_ENV=dev
export MCP_DATABASE_URL="postgresql+psycopg2://mcp:drill@127.0.0.1:55432/metocare_drill"
PSQL="postgresql://mcp:drill@127.0.0.1:55432/metocare_drill"

# ── 2. Apply the full migration chain; assert a single head ──────────────────
alembic upgrade head
test "$(alembic heads | grep -c '(head)')" -eq 1        # mirrors ci.yml:78-91
psql "$PSQL" -tAc "SELECT version_num FROM alembic_version"   # expect j4_m8_consent_versioning

# ── 3. Seed synthetic data (NO real PHI) ─────────────────────────────────────
python scripts/seed_demo_pilot.py || python scripts/seed_patient.py

# ── 4. Snapshot the "pre-incident" truth ─────────────────────────────────────
psql "$PSQL" -c "\copy (SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname) TO '/tmp/drill_before.csv' CSV HEADER"
pg_dump "$PSQL" -Fc -f /tmp/metocare_drill.dump

# ── 5. Simulate the incident: destroy the data ───────────────────────────────
psql "$PSQL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
psql "$PSQL" -tAc "SELECT count(*) FROM pg_stat_user_tables"      # expect 0

# ── 6. RESTORE ───────────────────────────────────────────────────────────────
pg_restore -d "$PSQL" --no-owner --no-privileges /tmp/metocare_drill.dump

# ── 7. Verify (§6 checks 2, 4, 6 — the ones that don't need a live app) ──────
psql "$PSQL" -tAc "SELECT version_num FROM alembic_version"
psql "$PSQL" -c "ANALYZE;" >/dev/null
psql "$PSQL" -c "\copy (SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname) TO '/tmp/drill_after.csv' CSV HEADER"
diff /tmp/drill_before.csv /tmp/drill_after.csv && echo "ROW COUNTS MATCH"
psql "$PSQL" -tAc "SELECT count(*) FROM document_pages p LEFT JOIN medical_documents d ON d.id=p.document_id WHERE d.id IS NULL"   # expect 0

# ── 8. Verify the app runs against the restored DB ───────────────────────────
python -m pytest tests/ -m integration -q                      # mirrors ci.yml:166-181
python -m app.jobs.maintenance                                 # §7 job runs clean

# ── 9. Blob-loss drill: prove §5c's premise and BR-F5's 500 ──────────────────
export MCP_STORAGE_MODE=local MCP_STORAGE_LOCAL_DIR=/tmp/drill_storage
# upload a document through the API, confirm GET /documents/{id}/file → 200,
rm -rf /tmp/drill_storage/accepted                             # ← the redeploy, simulated
# then re-run:  GET /documents/{id}         → 200 (row intact, looks fine)
#               GET /documents/{id}/file    → 200 (signed URL still issued — documents.py:338-345)
#               GET  <that signed URL>      → 404 (documents.py:290-292)
#               POST /documents/{id}/reprocess → 500  ← BR-F5, the thing to fix

# ── 10. Teardown ─────────────────────────────────────────────────────────────
docker rm -f metocare-drill-pg; rm -f /tmp/metocare_drill.dump /tmp/drill_*.csv; rm -rf /tmp/drill_storage
```

**What this drill does and does not prove.** It proves the schema chain applies cleanly to a real Postgres 16, that a logical dump round-trips, that row counts and FK integrity survive, that the app's integration suite passes against restored data, and that blob loss behaves as described. It does **not** prove Azure PITR works — only an actual `az postgres flexible-server restore` does that, and that drill is **still owed** (§3).

---

## 9. NEW findings (BR-F*)

| ID | Sev | Finding | Evidence | Exact fix |
|---|---|---|---|---|
| **BR-F1** | **P0** | **The staging deploy path actually used for the pilot runs migrations with no verified restore point.** `azure-staging.yml` (workflow_dispatch — run `30797337153`, `00-CURRENT-STATE.md:28`) runs `alembic upgrade head` with **no** pre-migration backup gate, while `ci.yml` and `azure-production.yml` both have one. A manual staging deploy can therefore apply a destructive/data migration with zero confirmed rollback point. | gate present: `ci.yml:414-423`, `azure-production.yml:172-181`; migration step without it: `azure-staging.yml:145-186`; `grep -n "pre_migration_backup" .github/workflows/*.yml` → only ci.yml + azure-production.yml | Insert before the "Run Alembic migration" step in `azure-staging.yml` (owner-gated file — not edited here):<br>`- name: Pre-migration DB backup`<br>`  run: bash scripts/pre_migration_backup.sh staging $(date +%Y%m%dT%H%M%S) ${{ github.sha }}`<br>`  env: {AZURE_CREDENTIALS, POSTGRES_SERVER_NAME, RESOURCE_GROUP}` |
| **BR-F2** | **P0** | **The recorded PROD-F1 remediation does not work.** `AzureBlobStorage.__init__` raises unconditionally and every method is a stub — the adapter is **unimplemented**, not unconfigured. Setting `MCP_STORAGE_MODE=azure` + a connection string, as `15-FINAL-LAUNCH-REVIEW.md:42` instructs, makes the first document request raise `StorageError` and takes the whole document vertical down. Beta-readiness is therefore gated on **engineering work**, not on a config flip. | `backend/app/services/storage/azure_blob.py:24-54`; `storage/factory.py:44-49` | Implement the adapter (§2, step 1) **before** the flag flip; or, as an interim with no code change, mount Azure Files at `/app/storage` via `az containerapp env storage set` + `--mount` so blobs survive a redeploy. Correct the disposition text in `15-FINAL-LAUNCH-REVIEW.md:42` and `TRACKING.md`. |
| **BR-F3** | **P1** | **PROD-F6's named remediation is a mis-citation.** `15-FINAL-LAUNCH-REVIEW.md:62` says to schedule `data_integrity_cleanup.py` for DB↔blob orphan reconciliation. That script contains **no storage code at all** — its entire scope is creatinine unit plausibility. Scheduling it closes nothing, and the register would then report PROD-F6 as fixed while nothing reconciles. | `backend/scripts/data_integrity_cleanup.py:52-88` (all three patterns), `:107-108` (imports only `HealthMetric`, `LabResult`), `:128-321`; `grep -rn "storage" backend/scripts/data_integrity_cleanup.py` → no match | Write `backend/app/jobs/reconcile_blobs.py` per §5c (dry-run default, `--apply` to mark), schedule it on the same ACA cron as §7, and fix the PROD-F6 row to point at it. |
| **BR-F4** | **P1** | **The quarantine TTL sweep does not exist**, though two code comments assert it does and a column exists for it. Never-finalized and rejected uploads leave `quarantine/` blobs forever: unbounded storage growth, and **PHI retained past its intended lifetime** (GDPR storage limitation). | column: `backend/app/models/medical_document.py:105-106` (`upload_expires_at`, comment "TTL for quarantine sweep… §1.7.7"); claim: `app/api/v1/routes/documents.py:246` ("a stray quarantine blob is caught by the TTL sweep"); `grep -rn "upload_expires_at" backend/app` → definition only | Add to `app/jobs/maintenance.py`: delete `quarantine_key` blobs for `MedicalDocument` rows where `upload_expires_at < now()` and `object_state != 'accepted'`, plus (post-BR-F2) an Azure Blob lifecycle rule deleting `quarantine/**` after 7 days. |
| **BR-F5** | **P1** | **`POST /documents/{id}/reprocess` returns HTTP 500 when the blob is missing** — i.e. for *every* document after any redeploy. `ObjectNotFound` is not an `MdiError`, so the route's handler misses it. The app fails opaquely exactly in the failure mode that is guaranteed to happen. | `app/services/mdi/service.py:545` (unguarded `get_bytes`); class hierarchy `mdi/service.py:66` vs `storage/base.py:33-38`; route handler `app/api/v1/routes/documents.py:512-516` | Wrap in `try/except ObjectNotFound → raise UploadValidationError(...)` (already imported at `mdi/service.py:55`) → maps to 400 at `documents.py:148-149`. Also add `storage.exists(key)` before signing at `documents.py:338-345` so `/file` doesn't hand out a URL that will 404. |
| **BR-F6** | **P1** | **The production and CI migration jobs run without `MCP_ENCRYPTION_KEYS` while declaring `MCP_ENV=production`/`staging`.** Any future data migration touching an `EncryptedString` column would encrypt with the **committed, publicly-known** default Fernet key (`config.py:38`) — the exact scenario `config.py:244-262` was written to prevent, bypassed because the boot guard runs in the app lifespan, not in `alembic/env.py`. Six migrations already touch encrypted tables. | omitted: `azure-production.yml:196-197`, `ci.yml:438-439` (`--secrets "db-url=$DB_URL"` only); present: `azure-staging.yml:161-164` (passes `enc-keys`); guard is lifespan-only — `backend/alembic/env.py:1-60` never calls `validate_required_env_vars()`; encryption-touching migrations: `fad70c6f2d60_encrypt_phi_fields.py`, `mdi_s0_medical_documents.py`, `t10_m1_consultation_marketplace.py`, `t12_p0_doctor_review_decisions.py`, `65849f86200f_refresh_tokens_and_mfa.py`, `t4_m2_ext_sess_extend_ai_session_fields.py` | Pass `enc-keys` (and `secret-key`) secretrefs to the migration job in `ci.yml` and `azure-production.yml`, matching `azure-staging.yml:161-164`. Optionally call `get_settings().validate_required_env_vars()` from `alembic/env.py` so the migration container fails loud too. |
| **BR-F7** | **P1** | **Wrong-key restore silently blanks allergies.** `allergies` and `known_conditions` use `on_decrypt_failure="none"`, so a restore with a mismatched/incomplete key list renders the patient as having **no known allergies** instead of raising. A restore is precisely when key mismatch is likely. This is a clinical hazard, not just a data one. | `backend/app/core/crypto.py:151-176`; `backend/app/models/patient.py:34-35`; contrast the fail-loud columns `app/models/care.py:329`, `app/models/consultation.py:176` | (a) Make §6 check 5 (canary decrypt) a **mandatory blocking gate** on every restore and every deploy; (b) evaluate switching the allergy/condition columns to `on_decrypt_failure="raise"`, or add a `phi_decrypt_failures` counter to `app/core/metrics.py` and alert on non-zero. |
| **BR-F8** | **P1** | **A PITR restore resurrects GDPR-erased PHI, and nothing re-erases it.** `delete_account` **soft**-deletes rows and leaves `quarantine_key`/`accepted_key` populated (`account.py:183-215`); the blobs are erased post-commit (`routes/account.py:105-112`). Restoring to a point before a deletion therefore brings the account back **active** with all PHI, while the blobs stay gone — and there is no erasure ledger or replay step. | `backend/app/services/account.py:137-215`; `backend/app/api/v1/routes/account.py:89-113`; no replay logic anywhere (`grep -rn "account_deleted" backend/app` → only the audit `action` string at `routes/account.py:95`) | Make erasure replay a **mandatory post-restore step** (§6 check 11). The `audit_logs` row is the ledger:<br>`SELECT resource_id AS patient_id, actor_id AS user_id, timestamp FROM audit_logs WHERE action='account_deleted' AND timestamp > :restore_point ORDER BY timestamp;`<br>Re-run `delete_account(db, user_id=…, patient_id=…)` for each (it is idempotent by construction, `account.py:140-151`). **Caveat:** if the restore point predates the audit rows themselves, keep an out-of-band erasure register — add an `erasure_requests` table (append-only, deletion timestamp + subject id, no PHI) so the ledger survives any restore point. |
| **BR-F9** | P2 | `audit_retention_default_days` is dead configuration — mapped but never used, so the "default" category silently never purges. | mapped `app/services/audit_retention.py:33-40`; loop covers only auth/data_access/admin `:49` | Either drop the setting or make `data_access` fall back to it; today `data_access` (730 d) already absorbs every unclassified action (`:57-64`). |
| **BR-F10** | P2 | The pre-migration gate accepts **any** retention ≥ 1 day. A server silently reconfigured to 1-day retention passes the gate while offering an RPO window far below target. | `scripts/pre_migration_backup.sh:157-159` (`RETENTION_DAYS -lt 1`) | Raise the threshold to the §3 target (`-lt 7` for pilot, `-lt 14` for beta) and echo the value into `$GITHUB_STEP_SUMMARY` so drift is visible in every run. |
| **BR-F11** | P2 | `docker-compose.yml` ships a **MinIO** service (`:34-49`) but no S3/MinIO adapter exists in `backend/app/services/storage/` (only `local` and the stubbed `azure`). New contributors will wire local dev against a bucket the app cannot use. | `docker-compose.yml:34-49`; `storage/factory.py:38-51` (`local` \| `azure` only) | Remove the MinIO service, or implement an S3 adapter — MinIO would also make the local drill in §8 exercise a real object store. |

### Corrections to the existing register

| Existing entry | Correction |
|---|---|
| **PROD-F1** disposition (`15-FINAL-LAUNCH-REVIEW.md:42`) — *"Owner action: set `MCP_STORAGE_MODE=azure` + connection string"* | **Insufficient.** The Azure adapter is unimplemented (BR-F2). Also add: scale-to-zero is **not** the live risk (both apps run `--min-replicas 1`, `azure-staging.yml:223`) — **revision replacement on every deploy** is. |
| **PROD-F5** (`:61`) — *"declared but no enforcement job"* | **The job exists** (`app/services/audit_retention.py`, `app/jobs/maintenance.py`, runnable as `python -m app.jobs.maintenance`); only the **schedule** is missing. Exact cron job in §7. |
| **PROD-F6** (`:62`) — *"Schedule `data_integrity_cleanup.py`"* | **Wrong script** (BR-F3). It performs no storage reconciliation. |
| **WS8 verdict** (`:29`) — *"Postgres PITR gate solid; object-storage backup missing"* | Accurate for `ci.yml`/`azure-production.yml`; **not** for the staging manual path (BR-F1). And "PITR gate solid" ≠ "PITR verified" — no restore has ever been executed (§3). |

---

## 10. Gate recommendation

| Gate | WS8 verdict | Rationale |
|---|---|---|
| **Internal pilot (synthetic)** | 🟡 **READY-WITH-ACCEPTED-LIMITATION** | Blob loss on redeploy is real but the data is synthetic and re-seedable. Owner must accept in writing: *"documents are lost on every backend deploy; the cohort is re-seeded."* |
| **Controlled pilot with any real patient data** | ⛔ **BLOCKED** | BR-F2 + PROD-F1: uploading a real medical document to a store with no backup and no reconciliation is not defensible. BR-F1 must also close (a staging migration today has no verified restore point). |
| **Public beta** | ⛔ **BLOCKED** | All of: BR-F1, BR-F2, BR-F3, BR-F4, BR-F5, BR-F6, BR-F7, BR-F8; plus one **executed** Azure PITR restore drill with §6 evidence recorded; plus Key Vault soft-delete/purge-protection verified; plus the §7 maintenance job scheduled. |

**Minimum set to unblock real-data pilot:** BR-F1 (workflow line, ~10 min) → Azure Files mount **or** BR-F2 adapter (interim vs. proper) → BR-F5 + BR-F3 (honest degradation + reconciliation) → one executed Azure restore drill.
