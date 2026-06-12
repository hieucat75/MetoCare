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
            if self.database_url.startswith("sqlite"):
                warnings.append("SQLite database in PROD; use PostgreSQL + TimescaleDB.")
            if self.ai_mode == "mock":
                warnings.append("AI is in mock mode in PROD.")
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
