# Archived workflows

Workflows here are **deactivated** — GitHub Actions only loads `*.yml` files in
the `.github/workflows/` root, so files in this subdirectory (and the `.archived`
suffix) never trigger.

## `main_metocare.yml.archived`

Azure **App Service** (Docker/GHCR) deploy path. Deprecated per the architecture
decision to standardize Azure staging on **Azure Container Apps** (`azure-staging.yml`)
instead of App Service. Kept for reference only; do not reactivate.

- Production: DigitalOcean (`deploy-do.yml`) — unchanged.
- Azure staging: Container Apps (`azure-staging.yml`).
