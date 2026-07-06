from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Uzbekistan is UTC+5 year-round (no daylight saving). A fixed offset keeps the
# launch-date check correct without depending on the system tz database (tzdata)
# being present inside the container.
_UZ_TZ = timezone(timedelta(hours=5))


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
    # Optional: point rate-limit counters at Redis so they survive deploys/restarts
    # and would work across >1 instance. Empty → in-process memory (fine for a
    # single instance; it just resets on restart). Set RATE_LIMIT_STORAGE_URL to a
    # real Redis URL when you provision backend Redis (the Upstash paid-tier item).
    rate_limit_storage_url: str = ""

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

    # Log every SQL statement (SQLAlchemy echo). Default OFF — echo renders +
    # writes every statement to stdout synchronously on the event loop, which is
    # real per-query latency in production. Set SQL_ECHO=true only for local
    # debugging. (Kept independent of ENVIRONMENT so a missing/!=production env
    # var can never silently turn this back on in prod.)
    sql_echo: bool = False

    # Shared secret between bot and backend (BOT_SECRET in bot's .env)
    bot_secret: str = ""

    # Secret that gates the investor growth-map feed (GET /admin/growth?secret=…).
    # Unset by default → the endpoint is disabled (403) until GROWTH_SECRET is set.
    growth_secret: str = ""

    # ISO date (YYYY-MM-DD) the platform opens to the public. Before it, the bot's
    # booking flow is closed to everyone EXCEPT business owners/staff (who test
    # during onboarding). Blank/unset → already open (no gate). Set LAUNCH_DATE on
    # the server; the gate auto-opens on that date — no redeploy needed.
    launch_date: str = ""

    @property
    def super_admin_ids(self) -> list[int]:
        return [int(x.strip()) for x in self.super_admin_telegram_ids.split(",") if x.strip()]

    @property
    def launch_date_value(self) -> date | None:
        try:
            return date.fromisoformat(self.launch_date) if self.launch_date else None
        except ValueError:
            return None

    @property
    def has_launched(self) -> bool:
        """True once the public launch date has arrived (Tashkent time), or if no
        launch date is configured (then the platform is always open)."""
        ld = self.launch_date_value
        return ld is None or datetime.now(_UZ_TZ).date() >= ld

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
