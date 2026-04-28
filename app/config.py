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

    # Clerk Authentication
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""

    # Meta WhatsApp (Phase 2)
    meta_verify_token: str = ""
    meta_access_token: str = ""
    meta_phone_number_id: str = ""
    meta_app_secret: str = ""

    # WAHA Integration
    waha_base_url: str = "http://localhost:3000"
    waha_api_key: str = ""
    waha_webhook_secret: str = ""
    # False = WAHA Core (only "default" session). True = WAHA PLUS (unique session per client).
    waha_multi_session: bool = False
    # Max DM chats (conversations) fetched per sync (0 = no limit, most-recently-active first)
    waha_max_chats: int = 100

    # Scheduler
    enable_whatsapp_scheduler: bool = True
    whatsapp_scheduler_interval_minutes: int = 15

    # Billing gate (set to true in production to enforce plan checks)
    enforce_billing: bool = False

    # Wompi payment gateway (Colombia)
    # Get keys from comercios.wompi.co → Mi cuenta → Llaves de autenticación
    wompi_public_key: str = ""            # pub_stagtest_... or pub_prod_...
    wompi_integrity_secret: str = ""      # Integridad secret (for hashing)
    wompi_events_secret: str = ""         # Eventos secret (for webhook verification)
    # Prices in COP centavos (1 COP = 100 centavos in Wompi)
    wompi_price_basic_cents: int = 160000     # stagtest: ~$1,600 COP; change to 16000000 in prod
    wompi_price_plus_cents: int = 250000     # stagtest: ~$2,500 COP; change to 25000000 in prod
    wompi_price_enterprise_cents: int = 400000  # stagtest: ~$4,000 COP; change to 40000000 in prod
    # Base URL for Wompi redirect after payment (your frontend)
    wompi_redirect_base_url: str = "http://localhost:5173"

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
