import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "type": "refresh"},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_telegram_init_data(init_data: str) -> dict | None:
    """
    Validates a Telegram Mini App initData string.
    Returns the parsed (URL-decoded) data dict on success, None on failure.

    Per Telegram's spec the data-check-string is built from URL-DECODED values,
    sorted by key. We fail closed if the bot token is unset (otherwise the secret
    key is derivable and any initData could be forged).
    """
    try:
        if not settings.telegram_bot_token:
            return None

        pairs: list[tuple[str, str]] = []
        received_hash: str | None = None
        for part in init_data.split("&"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            value = unquote(value)
            if key == "hash":
                received_hash = value
            else:
                pairs.append((key, value))

        if not received_hash:
            return None

        data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs))
        secret_key = hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(received_hash, expected_hash):
            return None

        params = dict(pairs)

        # Reject stale initData (replay window — 10 minutes in production)
        auth_date = int(params.get("auth_date", 0))
        if settings.is_production and (time.time() - auth_date) > 600:
            return None

        return params
    except Exception:
        return None


async def get_or_create_user_from_telegram(
    db: AsyncSession,
    telegram_id: int,
    name: str,
    username: str | None = None,
    language: str = "uz",
) -> User:
    """Finds existing user by telegram_id or creates one."""
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user is None:
        role = "super_admin" if telegram_id in settings.super_admin_ids else "customer"
        user = User(
            telegram_id=telegram_id,
            name=name,
            username=username,
            language=language,
            role=role,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

    return user
