import hmac

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.business import Business
from app.models.staff import Staff
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


async def get_current_dashboard_user(user: User = Depends(get_current_user)) -> User:
    """Gate for dashboard-management endpoints. Excludes 'customer' (no dashboard),
    but lets any 'staff'-role account through — because a desk-manager (secretary)
    has the global 'staff' role. This is ONLY a coarse gate: the real, per-business
    authorization MUST be done by authorize_business_access in the handler. Never
    put a business-scoped endpoint behind this gate without that call, or any staff
    account could reach another business's data."""
    if user.role not in ("business_owner", "staff", "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dashboard access required")
    return user


async def is_business_manager(business_id: int, user: User, db: AsyncSession) -> bool:
    """True if `user` is an active desk-manager (Staff.can_manage) of this business."""
    row = await db.execute(
        select(Staff.id).where(
            and_(
                Staff.business_id == business_id,
                Staff.user_id == user.id,
                Staff.can_manage.is_(True),
                Staff.is_active.is_(True),
            )
        ).limit(1)
    )
    return row.first() is not None


async def authorize_business_access(business_id: int, user: User, db: AsyncSession) -> Business:
    """THE single choke point for every manager-allowed endpoint. Returns the
    business if `user` may MANAGE it — owner, super_admin, or an active
    desk-manager linked to it. 404 if the business doesn't exist, 403 otherwise.
    Owner-only endpoints (business settings, storefront photo, register/delete)
    must NOT use this — they keep their own strict owner check."""
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    if business.owner_id == user.id or user.role == "super_admin":
        return business
    if await is_business_manager(business_id, user, db):
        return business
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


async def get_provider_staff(business_id: int, user: User, db: AsyncSession) -> list[Staff]:
    """The active provider (bookable-doctor) Staff records this user holds in
    `business_id`. A plain provider is scoped to THESE staff_ids only — never
    business-wide. Empty list if the user isn't an active provider here."""
    rows = await db.execute(
        select(Staff).where(
            and_(
                Staff.business_id == business_id,
                Staff.user_id == user.id,
                Staff.is_provider.is_(True),
                Staff.is_active.is_(True),
            )
        )
    )
    return list(rows.scalars().all())


async def authorize_provider_access(business_id: int, user: User, db: AsyncSession) -> list[Staff]:
    """THE choke point for provider self-service endpoints. Returns the user's own
    active provider Staff record(s) in this business, or raises: 404 if the
    business is missing, 403 if the user isn't a provider here. Callers MUST scope
    every row they read or write to the returned staff_ids — this grants
    self-access only, never business-wide powers (those go through
    authorize_business_access). An owner/manager who is ALSO a provider passes
    here too, but only ever sees their own provider rows through this path."""
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    staff = await get_provider_staff(business_id, user, db)
    if not staff:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return staff


async def authorize_business_or_provider(
    business_id: int, user: User, db: AsyncSession
) -> set[int] | None:
    """Access for endpoints usable by BOTH managers and providers, where a
    provider is row-scoped to their own staff records. Returns:
      • None  → the user may act on the WHOLE business (owner / super_admin /
                active desk-manager) — apply no staff filter.
      • {ids} → the user is a provider; every row read or written MUST have its
                staff_id in this set, or the caller returns 403.
    Raises 404 if the business is missing, 403 if the user is neither. This is the
    single place that decides 'manager-wide vs provider-own' — callers only apply
    the returned filter."""
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    if business.owner_id == user.id or user.role == "super_admin":
        return None
    if await is_business_manager(business_id, user, db):
        return None
    provider = await get_provider_staff(business_id, user, db)
    if provider:
        return {s.id for s in provider}
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


async def get_current_staff(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("staff", "business_owner", "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required")
    return user


async def get_current_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin required")
    return user
