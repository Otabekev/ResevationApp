import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import decode_token, get_current_user
from app.limiter import limiter
from app.models.user import User
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    get_or_create_user_from_telegram,
    verify_telegram_init_data,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramAuthRequest(BaseModel):
    init_data: str  # raw Telegram initData string


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    role: str
    name: str
    language: str


@router.post("/telegram", response_model=TokenResponse)
@limiter.limit("20/minute")
async def auth_telegram(request: Request, body: TelegramAuthRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticates a Telegram Mini App user using initData.
    Creates the user if they don't exist yet.
    """
    params = verify_telegram_init_data(body.init_data)
    if params is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram data")

    user_json = params.get("user")
    if not user_json:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No user data in initData")

    tg_user = json.loads(user_json)  # already URL-decoded by verify_telegram_init_data
    telegram_id = int(tg_user["id"])
    name = f"{tg_user.get('first_name', '')} {tg_user.get('last_name', '')}".strip()
    username = tg_user.get("username")
    language = tg_user.get("language_code", "uz")
    if language not in ("uz", "ru", "en"):
        language = "uz"

    user = await get_or_create_user_from_telegram(db, telegram_id, name, username, language)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
        role=user.role,
        name=user.name,
        language=user.language,
    )


class BotAuthRequest(BaseModel):
    telegram_id: int
    name: str
    username: str | None = None
    language: str = "uz"
    bot_secret: str  # shared secret between bot and backend


@router.post("/bot", response_model=TokenResponse)
@limiter.limit("60/minute")
async def auth_bot(request: Request, body: BotAuthRequest, db: AsyncSession = Depends(get_db)):
    """
    Internal endpoint for the Telegram bot to obtain tokens for a user.
    Protected by a shared secret (BOT_SECRET). Fails closed if the secret is unset.
    """
    if not settings.bot_secret or not hmac.compare_digest(body.bot_secret, settings.bot_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bot secret")

    lang = body.language if body.language in ("uz", "ru", "en") else "uz"
    user = await get_or_create_user_from_telegram(db, body.telegram_id, body.name, body.username, lang)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
        role=user.role,
        name=user.name,
        language=user.language,
    )


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh_tokens(request: Request, body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a fresh access + refresh pair (rotation)."""
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
        role=user.role,
        name=user.name,
        language=user.language,
    )


class MeResponse(BaseModel):
    id: int
    name: str
    role: str
    language: str
    telegram_id: int | None

    model_config = {"from_attributes": True}


@router.get("/me", response_model=MeResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user


class UpdateLanguageRequest(BaseModel):
    language: str


@router.patch("/me/language")
async def update_language(
    body: UpdateLanguageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.language not in ("uz", "ru", "en"):
        raise HTTPException(status_code=400, detail="Invalid language")
    user.language = body.language
    db.add(user)
    await db.commit()
    return {"ok": True}
