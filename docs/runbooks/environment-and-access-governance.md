# Environment and access governance

Written after the 2026-08-06 staging privacy incident. Every control here exists
because its absence contributed to that incident or would hide the next one.

Two kinds of item:

* **IMPLEMENTED** — enforced in this repository and covered by a test. Nothing to
  do; the row records what is enforced and what breaks if it is removed.
* **OWNER** — requires a GitHub or Azure permission this repository does not
  have. Exact command given, least privilege needed. **Not executed.**

---

## G1. Every deploy path is gated — IMPLEMENTED

`test_no_deploy_path_can_bypass_the_crypto_smoke` discovers deploying workflows
from the tree (runs `--command "alembic"` **and** `az containerapp update|create`)
and requires each to run the crypto smoke, ordered `migration → smoke → rollout`,
failing closed on failure *and* timeout, polling its own execution.

Covers `ci.yml`, `azure-staging.yml`, `azure-production.yml`.

**Why discovery, not a list:** `azure-staging.yml` had no smoke at all while
`ci.yml` — the path used daily — was correctly gated. A hardcoded list is what
lets that survive review.

## G2. Production provenance and confirmation — IMPLEMENTED

`github.ref == refs/heads/main` **and** `inputs.confirm == "PRODUCTION"`, both
exit 1 otherwise, pinned by
`test_production_deploys_only_from_main_with_explicit_confirmation`.

**Gap this does not close:** it stops the wrong *branch*, not the wrong *person*.
See G4.

## G3. No job may keep the PHI key — IMPLEMENTED

`test_no_workflow_leaves_a_job_holding_the_phi_key`: any workflow handing a job
`enc-keys=` must also delete a job with `if: always()`. Deliberately coarse — a
precise version would parse shell variables out of `-n "$JOB"` and break on the
first refactor. Coarse and always-true beats precise and disabled.

**State:** zero Container Apps Jobs exist in any resource group.

## G4. Protected production environment + human approver — OWNER

GitHub environments `azure-production` and `azure-staging` currently have **no
protection rules and no deployment branch policy**. "Owner approval" is a
convention, not a control.

```bash
# Required reviewer on production. <REVIEWER_USER_ID> from:
#   gh api users/<login> --jq .id
gh api -X PUT repos/hieucat75/MetoCare/environments/azure-production \
  -F "wait_timer=0" \
  -F "prevent_self_review=false" \
  -f "reviewers[][type]=User" -F "reviewers[][id]=<REVIEWER_USER_ID>" \
  -f "deployment_branch_policy[protected_branches]=true" \
  -f "deployment_branch_policy[custom_branch_policies]=false"
```

**Honest caveat:** this project has one human principal. A required reviewer who
is also the only person who can dispatch is theatre, and `prevent_self_review=true`
would be a hard block with nobody able to clear it. The control becomes real when
a second maintainer exists. Until then its value is the **audit trail** — an
approval event per deploy — not the second opinion. Decide on that basis rather
than because a checklist says so.

## G5. Separate staging and production identities — OWNER

One service principal, `MetoCare-GitHub-Staging`, holds Contributor **and** Key
Vault Secrets User on **both** resource groups. Its name says staging; its reach
is both. It has no stored client secret (OIDC, subject-scoped) — that part is
done well.

```bash
# 1. Production-only identity with its own federated credential.
az ad app create --display-name "MetoCare-GitHub-Production" --sign-in-audience AzureADMyOrg
APP_ID=$(az ad app list --display-name "MetoCare-GitHub-Production" --query "[0].appId" -o tsv)
az ad sp create --id "$APP_ID"
az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name":"github-env-azure-production",
  "issuer":"https://token.actions.githubusercontent.com",
  "subject":"repo:hieucat75/MetoCare:environment:azure-production",
  "audiences":["api://AzureADTokenExchange"]}'

SP_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
SUB=$(az account show --query id -o tsv)
az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
  --role Contributor --scope "/subscriptions/$SUB/resourceGroups/rg-metocare-prod"
az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "/subscriptions/$SUB/resourceGroups/rg-metocare-prod/providers/Microsoft.KeyVault/vaults/kv-metocare-prdcfbb"

# 2. Point the production environment at it.
gh secret set AZURE_CLIENT_ID --env azure-production --body "$APP_ID"

# 3. THEN remove production reach from the staging identity — LAST, so a mistake
#    in 1–2 does not leave production undeployable.
STG=$(az ad sp list --display-name "MetoCare-GitHub-Staging" --query "[0].id" -o tsv)
az role assignment delete --assignee "$STG" --scope "/subscriptions/$SUB/resourceGroups/rg-metocare-prod"
az role assignment delete --assignee "$STG" \
  --scope "/subscriptions/$SUB/resourceGroups/rg-metocare-prod/providers/Microsoft.KeyVault/vaults/kv-metocare-prdcfbb"
az ad app federated-credential delete \
  --id $(az ad sp show --id "$STG" --query appId -o tsv) \
  --federated-credential-id github-env-azure-production
```

**Order matters.** Step 3 last, and only after a production dispatch has been
verified with the new identity — otherwise the next deploy fails at Azure login.

## G6. Prohibit ad-hoc jobs containing secrets — OWNER + operating rule

Four hand-created Container Apps Jobs held secrets; one held the staging PHI key,
the JWT signing key and two live account passwords for three days. All deleted.

G3 covers jobs a *workflow* creates. **No test can see a job someone creates by
hand at a terminal** — that is the residual.

```bash
az policy definition create --name deny-aca-job-inline-secrets \
  --display-name "Container Apps Jobs must not carry inline secrets" \
  --mode Indexed --rules '{
    "if": {"allOf":[
      {"field":"type","equals":"Microsoft.App/jobs"},
      {"field":"Microsoft.App/jobs/configuration.secrets","exists":"true"}]},
    "then": {"effect":"audit"}}'
az policy assignment create --name aca-job-secrets-audit \
  --policy deny-aca-job-inline-secrets \
  --scope "/subscriptions/$(az account show --query id -o tsv)"
```

Start at `audit`. Moving to `deny` would break the deploy workflows, which
legitimately create such jobs — pair that move with a managed-identity rewrite of
those jobs, or exclude the two known job names.

**Operating rule until then:** a one-off job needing a secret is created by
`scripts/staging_reencrypt_job.sh` or an equivalent script with `trap cleanup
EXIT`. Never by hand at a prompt.

## G7. Key Vault and database audit logging — OWNER

The single biggest evidence gap. **No Key Vault diagnostic settings exist**, so
it is impossible to say whether the keys were read during the incident. It cannot
be applied retroactively — no configuration now produces logs for 2026-08-06.

```bash
WS=$(az monitor log-analytics workspace show -g rg-metocare-staging \
       -n log-metocare-staging --query id -o tsv)
for RG in staging prod; do
  KV=$(az keyvault list -g "rg-metocare-$RG" --query "[0].id" -o tsv)
  az monitor diagnostic-settings create --name kv-audit --resource "$KV" --workspace "$WS" \
    --logs '[{"category":"AuditEvent","enabled":true}]' \
    --metrics '[{"category":"AllMetrics","enabled":true}]'
done
```

Also consider `pgaudit` on both Postgres servers, so a future incident can answer
"which rows were read". It costs storage — decide deliberately rather than
defaulting.

## G8. Branch protection on `main` — OWNER

`main` has none. G2's main-only guard protects against dispatching from a feature
branch, not against pushing straight to `main`.

```bash
gh api -X PUT repos/hieucat75/MetoCare/branches/main/protection \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=Backend Tests" \
  -f "required_status_checks[contexts][]=Backend PostgreSQL Integration Tests" \
  -f "required_status_checks[contexts][]=Frontend Tests" \
  -f "required_status_checks[contexts][]=Mobile Tests" \
  -F "enforce_admins=false" \
  -F "required_pull_request_reviews=null" \
  -F "restrictions=null"
```

`required_pull_request_reviews=null` and `enforce_admins=false` are deliberate:
with one maintainer, requiring review blocks all work. The **status checks** carry
the value today — they would have caught the mobile failure before `main`.

## G9. Staging is synthetic-only — IMPLEMENTED

`app/core/environment_lock.py`, enabled on both staging deploy paths
(`MCP_SYNTHETIC_ONLY_MODE=true`), default **off** so production is unaffected by
construction.

| Behaviour when locked | Rationale |
|---|---|
| Registration refused for non-reserved-domain identifiers | 90 real accounts arrived because nothing asked |
| **Login** refused for the same | Registration alone is not enough — those accounts exist and can still upload |
| Push/email suppressed | Inert today only because no credentials are configured; "inert by accident" ends when someone adds them |
| Warning banner via `/api/v1/info` | So a person looking at the UI knows |

Only RFC 2606 reserved domains count as synthetic (`example.com`, `.test`,
`.invalid`, `.localhost`), plus an explicit operator allowlist for phone numbers.
**Local-part markers were removed after the module's own spoofing test caught
that `demo.attacker@gmail.com` would have been admitted** — a marker that can
appear in the part of an address the sender chooses is not a marker.

Fails closed: an unclassifiable identifier is not synthetic.

## G10. Staging domain separation — PARTIAL

Target: `staging.metocare.me` for staging, `app.metocare.me` reserved for
production.

| Item | State |
|---|---|
| Staging must not deploy onto `app.metocare.me` | **Implemented** — guard in `azure-staging.yml` exits 1 |
| CORS separation once split | **Implemented, conditional** — same guard fails if `STAGING_DOMAIN_SPLIT_DONE=true` and staging still allow-lists `app.metocare.me` |
| Environment identity in the UI | **Implemented** — `/api/v1/info` returns `synthetic_only_mode` + `environment_banner` |
| Signup allowlist | **Implemented** — G9 |
| `staging.metocare.me` DNS + custom domain | **OWNER** |
| Flip `STAGING_DOMAIN_SPLIT_DONE` | **OWNER**, after the DNS step |

```bash
# After creating the CNAME staging.metocare.me → staging frontend FQDN:
az containerapp hostname add -g rg-metocare-staging -n ca-metocare-frontend \
  --hostname staging.metocare.me
az containerapp hostname bind -g rg-metocare-staging -n ca-metocare-frontend \
  --hostname staging.metocare.me --environment cae-metocare-staging --validation-method CNAME
gh variable set STAGING_DOMAIN_SPLIT_DONE --body true
```

**Do not cut `app.metocare.me` over to production without owner approval.** It
resolves to staging today; moving it is user-visible and outside incident
remediation.

## G11. Production pre-deploy roles — OWNER, unassigned

`production-predeploy-checklist.md` records every technical precondition. These
three are people, and all three are blank:

| Role | Name | Responsibility |
|---|---|---|
| Incident Commander | `<unassigned>` | Owns the deploy while it runs; the only person who calls an abort |
| Rollback owner | `<unassigned>` | Executes the `ingress traffic set` rollback if called |
| Legal/privacy incident owner | `<unassigned>` | Owns the notification decision in the incident pack — **independent of the deploy** |

A deploy with no named commander has nobody who can decide to stop it.

---

## Summary

| Control | State |
|---|---|
| G1 gate on every deploy path | ✅ implemented + test |
| G2 main-only + confirm | ✅ implemented + test |
| G3 no workflow leaves a key-bearing job | ✅ implemented + test |
| G4 protected production environment | ⚠️ OWNER — read the caveat first |
| G5 separate identities | ⚠️ OWNER — order matters |
| G6 prohibit ad-hoc secret jobs | ⚠️ OWNER (policy) + operating rule |
| G7 Key Vault / DB audit logging | ⚠️ OWNER — the biggest evidence gap |
| G8 branch protection | ⚠️ OWNER — status checks are the valuable part |
| G9 staging synthetic-only | ✅ implemented + tests |
| G10 domain separation | 🟡 guards implemented, DNS is OWNER |
| G11 named roles | ⛔ unassigned |
