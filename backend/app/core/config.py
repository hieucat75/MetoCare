"""Application configuration — environment-driven, no hardcoded secrets.

Reads from environment variables / `.env` (see `.env.example`) with the `MCP_`
prefix. Secrets (SECRET_KEY, LLM/OCR keys, DB credentials) are NEVER hardcoded
here; production must inject them via a secret manager.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- App ----
    env: str = "dev"
    debug: bool = True
    api_prefix: str = "/api/v1"
    app_name: str = "Metabolic Care Platform"

    # ---- Security ----
    # Dev default is an obvious placeholder (>=32 chars for HS256); prod MUST
    # override via a secret manager.
    secret_key: str = "dev-insecure-secret-change-me-in-production-0123456789"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_minutes: int = 60 * 24 * 7
    # Comma-separated Fernet keys for PHI field-level encryption (first = encrypt,
    # all = decrypt for rotation). Dev default is an obvious placeholder; prod MUST
    # inject real keys via a secret manager.
    encryption_keys: str = "CSuRdJSn8APsbQJ3u91m71ZoHvdpn0IzMj6i7H9kMFg="

    # ---- Database ----
    # Default SQLite so the stack runs with zero infra in dev/test.
    database_url: str = "sqlite:///./data/mcp_dev.sqlite3"

    # ---- Meto AI — provider configuration ----
    # Primary provider for Meto conversational AI (always use meto_* prefix)
    meto_primary_provider: str = "claude"
    meto_fallback_provider: str = "openai"
    # API keys (injected via secret manager in prod; empty = provider disabled)
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # ---- 9Router — local OpenAI-compatible proxy (preferred for staging/prod) ----
    # 9Router manages billing, rate-limiting, and model routing centrally.
    # Set MCP_NINE_ROUTER_API_KEY to enable. All traffic goes through
    # http://127.0.0.1:20128/v1 by default (override via MCP_NINE_ROUTER_BASE_URL).
    nine_router_api_key: str = ""        # MCP_NINE_ROUTER_API_KEY
    nine_router_base_url: str = "http://127.0.0.1:20128/v1"  # MCP_NINE_ROUTER_BASE_URL
    nine_router_primary_model: str = "cc/claude-sonnet-4-6"  # MCP_NINE_ROUTER_PRIMARY_MODEL
    nine_router_fallback_model: str = "cx/gpt-5.4-mini"     # MCP_NINE_ROUTER_FALLBACK_MODEL

    # ---- OpenRouter — cloud LLM gateway (preferred for staging/prod when 9Router unavailable) ----
    # Set MCP_OPENROUTER_API_KEY to enable. Routes through https://openrouter.ai/api/v1.
    openrouter_api_key: str = ""                             # MCP_OPENROUTER_API_KEY
    openrouter_base_url: str = "https://openrouter.ai/api/v1"  # MCP_OPENROUTER_BASE_URL
    openrouter_primary_model: str = "openai/gpt-4o-mini"    # MCP_OPENROUTER_PRIMARY_MODEL
    openrouter_fallback_model: str = "openai/gpt-4o-mini"  # MCP_OPENROUTER_FALLBACK_MODEL

    # ---- DeepSeek — low-cost fallback provider (OpenAI-compatible endpoint) ----
    # Set MCP_DEEPSEEK_API_KEY to enable. Routes through https://api.deepseek.com.
    deepseek_api_key: str = ""                               # MCP_DEEPSEEK_API_KEY
    deepseek_base_url: str = "https://api.deepseek.com"     # MCP_DEEPSEEK_BASE_URL
    deepseek_model: str = "deepseek-chat"                   # MCP_DEEPSEEK_MODEL
    # ---- AI provider allow-list (AI-F2) — PHI egress control ----
    # Comma-separated provider names that are permitted to receive patient PHI
    # (e.g. "nine_router_claude,nine_router_gpt"). Enforced in
    # ProviderRegistry.get_available_providers. A provider is reachable ONLY when
    # it is BOTH registered (key present) AND named here — key presence alone must
    # never be enough to route PHI to a vendor with no data-processing record.
    # Empty outside dev/test = FAIL CLOSED (no provider available → the existing
    # 503 readiness path), same posture as the secret checks below.
    ai_allowed_providers: str = ""  # MCP_AI_ALLOWED_PROVIDERS

    # Generation settings
    meto_max_tokens: int = 2048
    # Whole provider-chain budget (PROD-F10). MUST stay well inside the gunicorn
    # worker timeout (120s) — the retry chain would otherwise outlive the worker
    # and take the single-worker replica down for every user.
    meto_timeout_seconds: int = 30
    # Per-user daily message cap (PROD-F11, abuse/cost). Counted from persisted
    # meto_messages, so it survives a process restart. 0 = disabled.
    meto_daily_message_cap: int = 100  # MCP_METO_DAILY_MESSAGE_CAP
    meto_enable_streaming: bool = True
    meto_temperature: float = 0.3

    # ---- AI / OCR / Storage modes (mock by default = no external calls) ----
    ai_mode: str = "mock"  # mock | gateway
    llm_gateway_url: str = ""
    llm_api_key: str = ""
    ocr_mode: str = "mock"  # mock | provider
    ocr_provider_url: str = ""
    ocr_api_key: str = ""
    storage_mode: str = "local"  # local | azure (azure = DIST-RC, deferred)
    storage_local_dir: str = "./storage"
    # Signed-URL time-to-live (seconds). PUT is short (client uploads immediately);
    # GET a little longer for the mobile viewer to load an image.
    storage_upload_url_ttl_seconds: int = 600
    storage_download_url_ttl_seconds: int = 900
    # Azure Blob adapter (DIST-RC) — inert until a credential is provided (§1.7/§12).
    storage_azure_connection_string: str = ""  # MCP_STORAGE_AZURE_CONNECTION_STRING
    storage_azure_container: str = "documents"
    # Medical Document Intelligence upload limits (§1.7 finalize validation).
    document_max_pages: int = 20  # PDF page cap for general medical documents
    # Malware-scan posture at finalize (§1.7.3). An EXPLICIT decision — never a
    # silent accept. "skip" = no AV configured, accept + record scan_status=skipped
    # (ENG-RC default; loud + audited). "hold" = quarantine posture: object stays
    # quarantined, flagged, never handed to a worker. "clamav" = real scan (DIST-RC).
    document_scan_mode: str = "skip"  # skip | hold | clamav

    # ---- LLM Gateway (P2 #1) — provider abstraction, never calls real LLM in mock ----
    llm_provider: str = "mock"  # mock | openai | anthropic (openai/anthropic = skeleton)
    llm_model: str = "mock-vi-1"
    llm_max_tokens: int = 512
    llm_temperature: float = 0.2
    # Cost / rate guard per user (sliding 60s window). 429 when exceeded.
    llm_max_requests_per_minute: int = 20
    llm_max_tokens_per_minute: int = 20000
    # In-memory LRU response cache (identical prompt + user) to cut cost.
    llm_cache_enabled: bool = True
    llm_cache_max_entries: int = 512
    llm_cache_ttl_seconds: int = 300

    # ---- RAG retrieval (P2 #2) ----
    rag_enabled: bool = True
    embedding_provider: str = "mock"  # mock | openai (openai = skeleton)
    embedding_dim: int = 256
    vector_store: str = "memory"  # memory | pgvector | qdrant (latter two = skeleton)
    rag_top_k: int = 3
    rag_seed_dir: str = "./data/rag_seed"

    # ---- OCR worker (P2 #3) — async queue, mock provider by default ----
    ocr_provider: str = "mock"  # mock | tesseract | cloud (latter two = skeleton)
    ocr_worker_enabled: bool = True
    ocr_queue_max_size: int = 256

    # ---- OCR Lab Upload track — synchronous draft pipeline (default Tesseract local) ----
    # Primary OCR is Tesseract running locally in-container, cost $0. Cloud OCR is an
    # opt-in fallback gated by FeatureFlag.OCR_CLOUD_FALLBACK + a provider key (read
    # from the unprefixed ANTHROPIC_API_KEY / AZURE_DOC_INTEL_* env at call time).
    ocr_lang: str = "vie+eng"  # Tesseract language packs
    ocr_cloud_provider: str = ""  # "" | anthropic | azure (only read when fallback ON)
    ocr_max_upload_mb: int = 10  # reject larger uploads with 413
    # Explicit opt-in for OCR dataset export (writes corrected rows to ocr_dataset/).
    # Must be true in addition to env=staging|dev to allow export. Prevents accidental
    # PHI writes if MCP_ENV is unset or misconfigured. Set MCP_OCR_DATASET_EXPORT_ENABLED=true.
    ocr_dataset_export_enabled: bool = False
    ocr_url_fetch_timeout_seconds: int = 10  # SSRF-guarded URL paste fetch
    ocr_pdf_max_pages: int = 3  # rasterize/scan at most N pages

    # ---- CORS ----
    # Comma-separated list of allowed origins for CORS preflight.
    # Default includes localhost variants for local dev.
    # In internal DEV, add http://172.20.0.100:13000 via MCP_CORS_ALLOWED_ORIGINS.
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:13000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # ---- Dev / Test flags ----
    # Set MCP_SKIP_MFA_IN_DEV=true to bypass MFA enforcement in local dev/smoke.
    # MUST be false (default) in production.
    skip_mfa_in_dev: bool = False

    # Temporary relaxed authentication policy for the build/test phase.
    # MFA enforcement is OFF by default (development/staging): no role is
    # forced to enroll, no mfa_enrollment_required claim/redirect, and the
    # require_mfa endpoint gates are no-ops. Set
    # MCP_MFA_ENFORCEMENT_ENABLED=true to restore mandatory MFA for the roles
    # in MFA_REQUIRED_ROLES. The MFA enroll/verify/TOTP APIs and DB fields
    # stay fully functional either way (voluntary MFA keeps working).
    mfa_enforcement_enabled: bool = False

    # ---- Password policy ----
    # Secure by default; dev/test relax via env. Enforced at every password entry
    # point (register / change / reset / admin-create) via core.password.
    password_min_length: int = 8
    password_require_complexity: bool = True

    # Escape hatch that lets STAGING (never production) boot with relaxed auth
    # (MFA off or weak password policy) during the build phase — logged loudly.
    # Production always fails loud on relaxed auth regardless of this flag.
    allow_relaxed_auth: bool = False

    # ---- QA fixture ingestion (dev/staging automation ONLY) ----
    # Enables POST /documents/qa-fixture, which ingests a BUNDLED synthetic
    # document through the real ingestion pipeline so Journey A (document OCR)
    # can be automated without the native camera. NEVER for production: the
    # startup guard below refuses to boot prod when this is true. Set
    # MCP_QA_FIXTURE_ENABLED=true only on dev/staging QA builds.
    qa_fixture_enabled: bool = False

    # ---- Observability ----
    log_level: str = "INFO"
    metrics_enabled: bool = True  # exposes /metrics; disable on untrusted edges
    # Interactive API docs (Swagger UI /docs + ReDoc /redoc). On in dev for easy
    # manual testing; FORCED off in prod regardless of this flag (see create_app).
    enable_docs: bool = True

    # ---- Audit retention (days) by action category ----
    audit_retention_auth_days: int = 365
    audit_retention_data_access_days: int = 730
    audit_retention_admin_days: int = 1095
    audit_retention_default_days: int = 365

    # ---- Doctor Marketplace (T10) ----
    # Platform commission rate applied to each consultation price.
    platform_fee_rate: float = 0.15  # MCP_PLATFORM_FEE_RATE
    marketplace_currency: str = "VND"  # MCP_MARKETPLACE_CURRENCY

    # ---- Rate limiting & account lockout ----
    ratelimit_enabled: bool = True
    ratelimit_backend: str = "memory"  # memory | redis (redis = optional, lazy-imported)
    ratelimit_redis_url: str = ""  # required when ratelimit_backend=redis
    ratelimit_redis_prefix: str = "metocare:ratelimit:"  # namespace; reset() only touches this
    ratelimit_auth_capacity: int = 20  # max burst per window per client+action
    ratelimit_auth_window_seconds: int = 60
    lockout_max_failures: int = 5
    lockout_cooldown_minutes: int = 15

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in ("prod", "production")

    def validate_required_env_vars(self) -> None:
        """Raise RuntimeError at startup if required env vars are missing or empty.

        Called during application startup (lifespan) to fail fast rather than
        silently starting a broken server. Required vars: SECRET_KEY, DATABASE_URL.
        """
        # Pairs of (setting_attribute, env_var_name, description)
        required = [
            (self.secret_key, "MCP_SECRET_KEY", "JWT signing secret"),
            (self.database_url, "MCP_DATABASE_URL", "database connection string"),
        ]
        missing: list[str] = []
        for value, env_name, description in required:
            if not value or not value.strip():
                missing.append(f"{env_name} ({description})")
        if missing:
            raise RuntimeError(
                "Required environment variables are not set or empty. "
                "The server cannot start safely. Missing: " + ", ".join(missing)
            )

        # Fail loud on committed insecure default secrets in any real environment.
        # The defaults are non-empty, so the missing-check above never trips on
        # them; without this a staging/prod boot where secret injection silently
        # failed would run with a publicly-known JWT secret (token forgery) and a
        # committed Fernet key (all PHI decryptable). Local dev/test keep them.
        if self.env.lower() not in ("dev", "test", "local"):
            insecure: list[str] = []
            if self.secret_key.startswith("dev-insecure-secret"):
                insecure.append("MCP_SECRET_KEY (JWT signing secret)")
            # Scan every entry in the comma-separated rotation list, not just the
            # first — the committed default must never appear even as a secondary
            # decrypt-only key.
            enc_entries = [k.strip() for k in self.encryption_keys.split(",")]
            if any(
                k.startswith("CSuRdJSn8APsbQJ3u91m71ZoHvdpn0IzMj6i7H9kMFg")
                for k in enc_entries
            ):
                insecure.append("MCP_ENCRYPTION_KEYS (PHI field-encryption key)")
            if insecure:
                raise RuntimeError(
                    f"Refusing to start in env={self.env!r} with committed insecure "
                    "default secret(s): " + ", ".join(insecure)
                    + ". Set real values via the deployment secret store."
                )

        # Fail loud on relaxed AUTHENTICATION in real environments (BRD §C).
        # Production must never run with MFA off or a weak password policy.
        # Staging may during the build phase ONLY via an explicit, logged override.
        env = self.env.lower()
        if env in ("staging", "prod", "production"):
            relaxed: list[str] = []
            if not self.mfa_enforcement_enabled:
                relaxed.append("MFA enforcement off (MCP_MFA_ENFORCEMENT_ENABLED)")
            if self.skip_mfa_in_dev:
                relaxed.append("MFA dev-skip on (MCP_SKIP_MFA_IN_DEV)")
            if self.password_min_length < 8:
                relaxed.append("password_min_length < 8 (MCP_PASSWORD_MIN_LENGTH)")
            if not self.password_require_complexity:
                relaxed.append("password complexity off (MCP_PASSWORD_REQUIRE_COMPLEXITY)")
            if relaxed:
                is_production = env in ("prod", "production")
                if is_production or not self.allow_relaxed_auth:
                    hint = (
                        ". Production never permits relaxed auth."
                        if is_production
                        else ". Set MCP_ALLOW_RELAXED_AUTH=true to override on staging."
                    )
                    raise RuntimeError(
                        f"Refusing to start in env={self.env!r} with relaxed "
                        "authentication: " + "; ".join(relaxed) + hint
                    )
                import logging

                logging.getLogger(__name__).warning(
                    "STAGING booting with RELAXED AUTH (build-phase override): %s",
                    "; ".join(relaxed),
                )

        # Fail loud on the QA fixture path in production. The bundled-fixture
        # ingestion endpoint is a dev/staging automation aid and must be
        # unreachable in prod; refuse to boot rather than expose it there.
        if env in ("prod", "production") and self.qa_fixture_enabled:
            raise RuntimeError(
                f"Refusing to start in env={self.env!r} with the QA fixture path "
                "enabled (MCP_QA_FIXTURE_ENABLED). It is a dev/staging automation "
                "aid only and must never be reachable in production."
            )

        # Fail loud on an unscanned document pipeline in production.
        #
        # `document_scan_mode="skip"` accepts an upload and promotes the object
        # straight to the servable `accepted` container with `scan_status=skipped`
        # (services/mdi/service.py). That is a deliberate ENG-RC default, but the
        # bytes are then parsed SERVER-SIDE before any human sees them — Pillow and
        # pytesseract in services/ocr_engine.py, pypdf for page counting — so a
        # crafted file that still passes the magic-byte check reaches those parsers
        # unscanned. Every other risk factor of this shape (default secrets, relaxed
        # auth, the QA fixture path) already refuses to boot in prod; this one did
        # not, so production could ship with no AV and nothing would say so.
        #
        # Scoped to prod only: staging deliberately runs "skip" today, and turning
        # this into a staging boot failure would break the existing deploy.
        if (
            env in ("prod", "production")
            and (self.document_scan_mode or "skip").lower() == "skip"
        ):
            raise RuntimeError(
                f"Refusing to start in env={self.env!r} with "
                "MCP_DOCUMENT_SCAN_MODE='skip'. Uploaded documents would be accepted "
                "and parsed server-side (Pillow/Tesseract/pypdf) with no malware "
                "scan. Set 'clamav' once real scanning is wired, or 'hold' to "
                "quarantine uploads pending review."
            )

    def warn_if_insecure(self) -> list[str]:
        """Return a list of insecure-config warnings (used at startup)."""
        warnings: list[str] = []
        if self.is_prod:
            if self.secret_key.startswith("dev-insecure-secret"):
                warnings.append("SECRET_KEY is the insecure dev default in PROD.")
            elif len(self.secret_key) < 32:
                warnings.append("SECRET_KEY is shorter than 32 chars (weak for HS256).")
            if self.encryption_keys.startswith("CSuRdJSn8APsbQJ3u91m71ZoHvdpn0IzMj6i7H9kMFg"):
                warnings.append("ENCRYPTION_KEYS is the insecure dev default in PROD.")
            if self.database_url.startswith("sqlite"):
                warnings.append("SQLite database in PROD; use PostgreSQL + TimescaleDB.")
            if self.ai_mode == "mock":
                warnings.append("AI is in mock mode in PROD.")
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# Doctor Marketplace constants + fee helper (T10)
# ---------------------------------------------------------------------------

# Legal disclaimer surfaced by consultation/marketplace endpoints and the FE.
MARKETPLACE_DISCLAIMER = (
    "MetoCare không thay thế cấp cứu hoặc khám trực tiếp khi có dấu hiệu nguy hiểm."
)


def compute_fees(price: float) -> tuple[float, float]:
    """Split a consultation *price* into (platform_fee, doctor_payout).

    Pure function: ``platform_fee = round(price * rate)`` and
    ``doctor_payout = price - platform_fee``. Rate comes from settings
    (``PLATFORM_FEE_RATE``, default 0.15).
    """
    rate = get_settings().platform_fee_rate
    safe_price = float(price or 0.0)
    platform_fee = float(round(safe_price * rate))
    doctor_payout = safe_price - platform_fee
    return platform_fee, doctor_payout
