# 16 — Environment separation plan (PREPARED, NOT EXECUTED)

**Status:** proposal only. Nothing here has been applied. No DNS record, workflow, or
config has been changed by this document.

**Owner decision required before any step runs.**

---

## 1. Current state — `app.metocare.me` resolves to STAGING

Verified at runtime 2026-08-04/05:

```
$ dig +short app.metocare.me
ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io.
4.144.233.112
```

`wittyflower-55a3afa4` is the **staging** Container Apps environment — the same FQDN
`azure-staging.yml` prints as `FRONTEND_FQDN`. The bundle served from `app.metocare.me`
and from the staging FQDN is **byte-identical** (`sha256 6402410a…` before the 2026-08-05
deploy, `8b55adfe…` after).

| Fact | Value |
|---|---|
| `app.metocare.me` → | staging Container App |
| `NEXT_PUBLIC_API_URL` baked into that build | `https://ca-metocare-backend.wittyflower-…/api/v1` (**staging backend**) |
| `rg-metocare-prod` Container App | exists; last deployed **2026-07-14** from `30a65eb`; **no DNS points at it** |
| `azure-staging.yml` CORS step | explicitly allow-lists `https://app.metocare.me` (line 205) — the coupling is current and deliberate |

### Consequences today

1. **There is one live web environment.** Any staging deploy is immediately visible at
   the address the owner treats as production.
2. **`azure-production.yml` is effectively inert** — running it changes nothing anyone
   can reach, because no hostname routes there.
3. **Production data is not involved.** `app.metocare.me` talks to the staging backend
   and staging database; anything entered there is staging data.
4. This produced the original report ("the medication UI still appears unchanged"): the
   owner was looking at staging and reasoning about it as production.

---

## 2. Target state

| Host | Environment | Container App |
|---|---|---|
| `staging.metocare.me` | staging | `ca-metocare-frontend` in `wittyflower-…` |
| `app.metocare.me` | production | `ca-metocare-frontend` in `rg-metocare-prod` |

---

## 3. Sequenced plan

Ordered so no window exists where `app.metocare.me` serves nothing.

### Phase A — stand up the staging hostname (no user-visible change)

1. CNAME `staging.metocare.me` → `ca-metocare-frontend.wittyflower-…`.
2. Bind custom domain + managed certificate on the staging Container App.
3. Add `https://staging.metocare.me` to `MCP_CORS_ALLOWED_ORIGINS` on the staging
   backend, **keeping** `https://app.metocare.me` for now.
4. Update `azure-staging.yml` to bake `NEXT_PUBLIC_API_URL` for staging and allow-list
   `staging.metocare.me`.
5. Verify staging fully on the new hostname.

Both hostnames now serve staging. Nothing has broken.

### Phase B — make production real (still no cutover)

6. Deploy the approved candidate to `rg-metocare-prod` via `azure-production.yml`
   (`confirm=PRODUCTION`). **Requires the separate production approval.**
7. Verify on the Azure FQDN: `/api/v1/health`, `/api/v1/info` reporting
   `env=production` and the expected `migration_version`, plus a login smoke test.
8. Confirm production config: `MCP_DOCUMENT_SCAN_MODE` ≠ `skip` (now enforced by a
   startup guard), MFA on, no default secrets, `qa_fixture_enabled=false`.
9. **Run the `meto_consents` duplicate audit before this deploy** — see §6.

### Phase C — cutover

10. Lower the `app.metocare.me` DNS TTL (e.g. 300s) ahead of the change.
11. Repoint `app.metocare.me` → production Container App; bind domain + certificate.
12. **Remove** `https://app.metocare.me` from the staging backend's CORS allow-list so a
    stale cached staging bundle cannot talk to the staging API from the production host.
13. Verify `app.metocare.me/api/v1/info` reports `env=production`.
14. Restore the TTL.

### Rollback

Repoint `app.metocare.me` back to staging and re-add the CORS entry. Bounded by DNS TTL.
No data migration is involved in any phase, so rollback is a DNS operation only.

---

## 4. Environment-identifying version endpoint / banner

### 4.1 Extend `GET /api/v1/info`

The endpoint already returns `env` and `migration_version` but **not the build SHA**, so
there is no way to tell from the running system which commit is live — that had to be
reconstructed from workflow logs and bundle hashes during this investigation. Add:

```json
{
  "env": "staging",
  "build_sha": "c9bd98a",
  "build_time": "2026-08-05T00:58:07Z",
  "expected_host": "staging.metocare.me"
}
```

`build_sha` / `build_time` come from Docker build args already available in both
workflows (`steps.tag.outputs.sha8`). `expected_host` makes a hostname/environment
mismatch self-evident.

### 4.2 Non-production banner in the web client

A persistent, non-dismissable banner on every page when the build is not production:

> **MÔI TRƯỜNG THỬ NGHIỆM — dữ liệu ở đây không phải dữ liệu thật.**

Driven by a build-time `NEXT_PUBLIC_APP_ENV` baked alongside `NEXT_PUBLIC_API_URL`. It
must be build-time, not runtime-fetched, so it stays correct when the API is
unreachable. Include the short SHA so any screenshot identifies its build — which would
have answered the original question immediately.

---

## 5. Deployment safeguards

### 5.1 Staging must never target the production domain

Add to `azure-staging.yml`, before the CORS step:

```yaml
- name: Guard — staging must not target the production domain
  run: |
    if [ "${FRONTEND_FQDN}" = "app.metocare.me" ] || \
       echo "${MCP_CORS_ALLOWED_ORIGINS}" | grep -q "app\.metocare\.me"; then
      echo "::error::Staging deploy is targeting the production domain."
      exit 1
    fi
```

Inert during Phase A (the allow-list still legitimately contains `app.metocare.me`);
enable as part of Phase C step 12.

### 5.2 Production must never deploy an unreviewed build

`azure-production.yml` already requires `confirm=PRODUCTION`. Add:

- refuse unless the ref is `main` (today it is dispatchable from any ref);
- refuse if the resolved image tag does not already exist in the registry, so a
  production deploy cannot silently build from an unreviewed tree.

### 5.3 Post-deploy assertion

Both workflows should assert, after the health gate, that `/api/v1/info` reports the
`env` they intended to deploy. A staging job that finds `env=production` must fail
loudly rather than succeed quietly.

---

## 6. Pre-deploy data gate (carried from the migration review)

Before the **first** production deploy of the integration candidate, run:

```sql
SELECT user_id, context_type, count(*)
  FROM meto_consents
 GROUP BY 1, 2
HAVING count(*) > 1;
```

`j4_m8_consent_versioning` now dedupes automatically before adding its unique
constraint, but this query tells you in advance whether that dedupe will delete rows on
production — worth knowing before it happens rather than after.

---

## 7. Out of scope

- Database separation — staging and production already use separate Postgres servers;
  nothing moves.
- Staging seed/pilot accounts, which stay on staging.
- **When** to run the production deploy — that is the separate production approval gate.
