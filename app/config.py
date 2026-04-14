from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "DeepLook"
    app_env: str = "development"
    debug: bool = False
    api_secret_key: str = "changeme-use-a-real-32-char-secret"
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # Supabase / Database
    supabase_url: str = ""
    supabase_key: str = ""
    database_url: str = ""

    # AI Providers
    ai_provider: str = "openai"
    ai_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    # File Upload
    max_upload_size_mb: int = 50
    max_files_per_upload: int = 100

    # Meta WhatsApp (Phase 2)
    meta_verify_token: str = ""
    meta_access_token: str = ""
    meta_phone_number_id: str = ""
    meta_app_secret: str = ""

    # Rate limiting delays (seconds)
    openai_request_delay: float = 0.15
    anthropic_request_delay: float = 1.5
    gemini_request_delay: float = 0.1

    @field_validator("database_url", mode="before")
    @classmethod
    def ensure_asyncpg_scheme(cls, v: str) -> str:
        if not v:
            return v
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        # Strip query params that must not appear in the URL
        # (pgbouncer=true is rejected by asyncpg; prepared_statement_cache_size
        #  is passed via connect_args in database.py instead)
        _strip = {"pgbouncer", "prepared_statement_cache_size"}
        parsed = urlparse(v)
        params = {k: vals[0] for k, vals in parse_qs(parsed.query, keep_blank_values=True).items()
                  if k not in _strip}
        return urlunparse(parsed._replace(query=urlencode(params)))

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
