# Colima Boot Diagnosis & Fix Plan
> Date: 2026-06-17 18:45 GMT+7
> Status: BLOCKED — VM disk cannot be created on ExFAT volume

---

## Root Cause

Colima's Lima VM (VZ/Virtualization.framework) needs to create sparse disk image files  
(`basedisk`, `diffdisk`) inside:

```
/Volumes/Extreme SSD/DevCache/colima-cache/_lima/colima/
```

**Problem:** This path is on an **ExFAT** volume. ExFAT does not support:
- Sparse files (required by VZ disk images)
- POSIX hardlinks (required by Lima)
- Case-sensitive filenames (required by Lima)

Result: Lima loops forever on `"waiting 5 secs for VM"` — the VM kernel never boots.

**Secondary issue found and fixed:** `lima.yaml` had the base image path pointing at  
`/Users/pth/Library/Caches/colima/caches/...` (default macOS path), but the actual  
image is at `/Volumes/Extreme SSD/DevCache/colima-cache/caches/...`.  
→ This has been corrected in `lima.yaml` (backup at `lima.yaml.backup.20260617_183444`).

---

## Options (PTH to choose one)

### Option A — Recommended: Move Lima instance dir to internal SSD (fastest)

Lima instance data (the 9MB dir with lima.yaml, no disk yet) can be moved to  
`~/Library/Application Support/Lima/` on the internal APFS drive, then symlinked.

```bash
# 1. Kill any stuck colima
pkill -f colima; pkill -f limactl; sleep 2

# 2. Copy instance dir to internal APFS location
mkdir -p "$HOME/Library/Application Support/Lima/colima"
cp -a "/Volumes/Extreme SSD/DevCache/colima-cache/_lima/colima/." \
      "$HOME/Library/Application Support/Lima/colima/"

# 3. Replace SSD dir with symlink
mv "/Volumes/Extreme SSD/DevCache/colima-cache/_lima/colima" \
   "/Volumes/Extreme SSD/DevCache/colima-cache/_lima/colima.exfat-backup"
ln -s "$HOME/Library/Application Support/Lima/colima" \
      "/Volumes/Extreme SSD/DevCache/colima-cache/_lima/colima"

# 4. Start Colima  
COLIMA_HOME="/Volumes/Extreme SSD/DevCache/colima-cache" colima start
```

The Lima VZ disk images will now live on APFS (internal SSD) where sparse files work.  
Everything else (Docker socket, Colima config, caches) stays on the SSD.

---

### Option B — Alternative: Use Homebrew PostgreSQL directly (skip Docker)

If Docker/Colima is too painful to fix right now, install Postgres natively:

```bash
brew install postgresql@17
brew services start postgresql@17

# Create the MCP database
/opt/homebrew/opt/postgresql@17/bin/createdb mcp 2>/dev/null || true
/opt/homebrew/opt/postgresql@17/bin/psql mcp -c "
  CREATE USER mcp WITH PASSWORD 'mcp_dev_only';
  GRANT ALL PRIVILEGES ON DATABASE mcp TO mcp;
  ALTER DATABASE mcp OWNER TO mcp;
"

# Then run migration:
cd /Users/pth/Developer/metocare/backend
MCP_DATABASE_URL="postgresql+psycopg://mcp:mcp_dev_only@localhost:5432/mcp" \
  bash scripts/verify_postgres_t4.sh
```

This is the **quickest path to Postgres verification** — no VM, no Docker, native process.

---

### Option C — Defer to CI/CD (if Option A/B too complex right now)

If neither option is feasible today:
1. PTH approves merge of `integration/t4-medical-domain` → `main` with explicit note:
   > "Postgres upgrade deferred to CI/CD pipeline; T4 code gates all passed"
2. Add GitHub Actions job to run `alembic upgrade head` + verify_postgres_t4.sh  
   against a CI Postgres service container on merge.

---

## What PTH needs to do

**Fastest:** Option B (Homebrew Postgres, ~5 minutes):
```bash
brew install postgresql@17 && brew services start postgresql@17
```
Then tell me — I'll run the full verification immediately.

**Proper fix:** Option A (Lima → APFS symlink, ~10 minutes).

**Skip for now:** Option C — tell me to note it as deferred.

---

*Diagnosed by: OpenClaw Master Coordinator*
*No merge to main until one option is chosen and verification completes.*
