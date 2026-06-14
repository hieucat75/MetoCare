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

    # ---- AI / OCR / Storage modes (mock by default = no external calls) ----
    ai_mode: str = "mock"        # mock | gateway
    llm_gateway_url: str = ""
    llm_api_key: str = ""
    ocr_mode: str = "mock"       # mock | provider
    ocr_provider_url: str = ""
    ocr_api_key: str = ""
    storage_mode: str = "local"  # local | s3 | minio
    storage_local_dir: str = "./storage"

    # ---- LLM Gateway (P2 #1) — provider abstraction, never calls real LLM in mock ----
    llm_provider: str = "mock"   # mock | openai | anthropic (openai/anthropic = skeleton)
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
    embedding_provider: str = "mock"   # mock | openai (openai = skeleton)
    embedding_dim: int = 256
    vector_store: str = "memory"       # memory | pgvector | qdrant (latter two = skeleton)
    rag_top_k: int = 3
    rag_seed_dir: str = "./data/rag_seed"

    # ---- OCR worker (P2 #3) — async queue, mock provider by default ----
    ocr_provider: str = "mock"         # mock | tesseract | cloud (latter two = skeleton)
    ocr_worker_enabled: bool = True
    ocr_queue_max_size: int = 256

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

    # ---- Rate limiting & account lockout ----
    ratelimit_enabled: bool = True
    ratelimit_backend: str = "memory"  # memory | redis (redis = optional, lazy-imported)
    ratelimit_redis_url: str = ""      # required when ratelimit_backend=redis
    ratelimit_auth_capacity: int = 20  # max burst per window per client+action
    ratelimit_auth_window_seconds: int = 60
    lockout_max_failures: int = 5
    lockout_cooldown_minutes: int = 15

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in ("prod", "production")

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
