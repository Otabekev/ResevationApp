import hmac

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

bearer = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"


def require_bot_secret(x_bot_secret: str | None = Header(default=None)) -> None:
    """
    Choke point for endpoints that are only ever called by the trusted Telegram
    bot (public booking, review submit). The bot proves its identity with the
    shared BOT_SECRET; only then do we trust the telegram_id it sends in the body.

    Fails closed: if BOT_SECRET is unset, every call is rejected.
    """
    expected = settings.bot_secret
    if not expected or not x_bot_secret or not hmac.compare_digest(x_bot_secret, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bot secret")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(credentials.credentials)
    if payload.get("type") == "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token cannot be used for access",
        )
    user_id: int | None = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_current_business_owner(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("business_owner", "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Business owner required")
    return user


async def get_current_staff(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("staff", "business_owner", "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required")
    return user


async def get_current_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin required")
    return user
