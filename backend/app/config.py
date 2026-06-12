from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str
    postgres_user: str = "rezerv"
    postgres_password: str = "changeme"
    postgres_db: str = "rezerv_db"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Security
    secret_key: str
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 30

    # Telegram
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""  # e.g. "QulayNavbat_bot" — used to build t.me deep links
    telegram_webhook_secret: str = ""
    webhook_base_url: str = ""

    # Platform
    platform_name: str = "Qulay Navbat"
    super_admin_telegram_ids: str = ""  # comma-separated

    # CORS
    allowed_origins: str = "http://localhost:5173"

    # Environment
    environment: Literal["development", "production"] = "development"

    # Shared secret between bot and backend (BOT_SECRET in bot's .env)
    bot_secret: str = ""

    @property
    def super_admin_ids(self) -> list[int]:
        return [int(x.strip()) for x in self.super_admin_telegram_ids.split(",") if x.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def database_url_async(self) -> str:
        """
        Normalizes DATABASE_URL for SQLAlchemy asyncpg driver.
        - Converts postgres:// or postgresql:// → postgresql+asyncpg://
        - Appends ?sslmode=require for non-local hosts (required for Neon)
        """
        url = self.database_url
        # Normalize scheme
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]
        # Add SSL for non-local hosts
        if not any(h in url for h in ("localhost", "127.0.0.1", "@db", "@db:")):
            separator = "&" if "?" in url else "?"
            if "sslmode" not in url:
                url = f"{url}{separator}ssl=require"
        return url


def validate_runtime_config(s: "Settings") -> None:
    """
    Fail fast at startup in production if required secrets are missing or weak.
    No-op in development so local runs stay frictionless.
    """
    if not s.is_production:
        return
    errors: list[str] = []
    if not s.secret_key or len(s.secret_key) < 32 or "change-this" in s.secret_key.lower():
        errors.append("SECRET_KEY must be a strong random value (>= 32 chars)")
    if not s.bot_secret or len(s.bot_secret) < 16:
        errors.append("BOT_SECRET must be set (>= 16 chars)")
    if not s.telegram_bot_token:
        errors.append("TELEGRAM_BOT_TOKEN must be set")
    if not s.telegram_bot_username:
        errors.append("TELEGRAM_BOT_USERNAME must be set (bot username without @, for t.me links)")
    if not s.database_url:
        errors.append("DATABASE_URL must be set")
    if errors:
        raise RuntimeError("Invalid production configuration:\n  - " + "\n  - ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
