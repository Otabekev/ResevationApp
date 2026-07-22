import hmac
import io
import logging
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status,
)
from PIL import Image, ImageOps

# iPhones (and some Androids) shoot HEIC/HEIF by default; teach Pillow to decode
# them so an owner's camera-roll photo never bounces. Guarded so a missing wheel
# degrades to "HEIC unsupported" instead of killing the whole API at import.
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover - only hit if the dependency is absent
    pass
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import location_share_store
from app.config import settings
from app.database import get_db
from app.deps import (
    authorize_business_access,
    get_current_business_owner,
    get_current_dashboard_user,
    get_current_super_admin,
    get_current_user,
    is_business_manager,
)
from app.limiter import limiter
from app.models.business import Business, BusinessCategory, BusinessPhoto
from app.models.staff import Staff
from app.models.user import User

router = APIRouter(prefix="/businesses", tags=["businesses"])

logger = logging.getLogger("rezerv.businesses")

# A genuine owner runs a handful of shops, never dozens. Cap non-terminated
# businesses per account so one user can't flood the admin approval queue with
# junk pending registrations (blocked = deactivated, so it doesn't count).
_MAX_BUSINESSES_PER_OWNER = 5

# A real owner runs a handful of shops, never d


# ── Schemas ─────────────────────────────────────────────────────────────────

class CategoryOut(BaseModel):
    id: int
    slug: str
    name_uz: str
    name_ru: str
    name_en: str
    icon: str | None
    sort_order: int

    model_config = {"from_attributes": True}


class BusinessCreate(BaseModel):
    category_id: int
    name: str = Field(..., min_length=1, max_length=255)
    region: str = Field("Namangan", max_length=100)
    district: str = Field("Pop", max_length=100)
    city: str = Field(..., max_length=100)
    address: str = Field(..., max_length=500)
    phone: str = Field(..., max_length=20)
    telegram_username: str | None = Field(None, max_length=100)
    instagram_link: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=2000)
    latitude: float | None = None
    longitude: float | None = None


class BusinessUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    region: str | None = Field(None, max_length=100)
    district: str | None = Field(None, max_length=100)
    address: str | None = Field(None, max_length=500)
    phone: str | None = Field(None, max_length=20)
    telegram_username: str | None = Field(None, max_length=100)
    instagram_link: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=2000)
    is_online_booking_enabled: bool | None = None
    min_advance_booking_minutes: int | None = None
    max_advance_booking_days: int | None = None
    cancellation_policy_hours: int | None = None
    slot_step_minutes: int | None = None
    allow_multi_service: bool | None = None
    allow_any_staff: bool | None = None
    custom_message_uz: str | None = Field(None, max_length=2000)
    custom_message_ru: str | None = Field(None, max_length=2000)
    custom_message_en: str | None = Field(None, max_length=2000)
    latitude: float | None = None
    longitude: float | None = None


class BusinessOut(BaseModel):
    id: int
    name: str
    slug: str | None
    category_id: int
    region: str
    district: str
    city: str
    address: str
    phone: str
    telegram_username: str | None
    instagram_link: str | None
    description: str | None
    status: str
    is_online_booking_enabled: bool
    min_advance_booking_minutes: int
    max_advance_booking_days: int
    cancellation_policy_hours: int
    slot_step_minutes: int
    allow_multi_service: bool
    allow_any_staff: bool
    latitude: float | None
    longitude: float | None
    custom_message_uz: str | None
    custom_message_ru: str | None
    custom_message_en: str | None
    photo_url: str | None = None
    # How the current user relates to this business: "owner" (full control) or
    # "manager" (desk-manager — the frontend hides owner-only pages). Defaults to
    # owner; set explicitly on the /mine + /{id} endpoints.
    access_role: str = "owner"

    model_config = {"from_attributes": True}


# ── Category endpoints ───────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BusinessCategory).where(BusinessCategory.is_active == True).order_by(BusinessCategory.sort_order)
    )
    return result.scalars().all()


# ── Set business location via the Telegram bot (deep-link + poll) ─────────────
# Owners can't easily get raw coordinates from a phone, so instead of a map/paste
# field we reuse the web-login handshake: the browser makes a nonce, opens
# t.me/<bot>?start=setloc_<nonce>, the owner taps Telegram's native "Send
# location", the bot posts the coords here (bot_secret), and the browser's poll
# drops them into the setup form. Same one-time, self-expiring nonce store.

class LocationShareComplete(BaseModel):
    nonce: str
    latitude: float
    longitude: float
    bot_secret: str  # shared secret between bot and backend


@router.post("/location-share/complete")
async def complete_location_share(body: LocationShareComplete):
    """Called by the bot when an owner shares their location. Parks the coords
    keyed by the browser's nonce. Protected by BOT_SECRET, fail-closed."""
    if not settings.bot_secret or not hmac.compare_digest(body.bot_secret, settings.bot_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bot secret")

    nonce = body.nonce.strip()
    if not nonce or len(nonce) > 64 or not all(c.isalnum() or c in "-_" for c in nonce):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid nonce")
    if not (-90 <= body.latitude <= 90 and -180 <= body.longitude <= 180):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid coordinates")

    await location_share_store.save(
        nonce, {"latitude": round(body.latitude, 6), "longitude": round(body.longitude, 6)}
    )
    return {"ok": True}


@router.get("/location-share/poll/{nonce}")
async def poll_location_share(nonce: str):
    """Polled by the browser. Returns the shared coordinates once (one-time
    read), otherwise {status: pending}."""
    data = await location_share_store.take(nonce)
    if not data:
        return {"status": "pending"}
    return {"status": "ok", **data}


# ── Business CRUD ────────────────────────────────────────────────────────────

@router.post("", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def register_business(
    request: Request,
    body: BusinessCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Cap how many businesses one account can own (excludes 'blocked', which is a
    # terminated shop). Stops a single user flooding the approval queue; the
    # 5/hour rate limit above stops a scripted burst even within the cap.
    owned = await db.scalar(
        select(func.count(Business.id)).where(
            Business.owner_id == user.id, Business.status != "blocked"
        )
    )
    if (owned or 0) >= _MAX_BUSINESSES_PER_OWNER:
        raise HTTPException(
            status_code=409,
            detail=f"You've reached the maximum of {_MAX_BUSINESSES_PER_OWNER} businesses. Contact support to add more.",
        )

    # Verify category exists
    cat = await db.get(BusinessCategory, body.category_id)
    if not cat:
        raise HTTPException(status_code=400, detail="Invalid category")

    # Update user role to business_owner if they're currently a customer
    if user.role == "customer":
        user.role = "business_owner"
        db.add(user)

    # New businesses are 'pending' — invisible to customers until a super_admin
    # approves them. Promotion to 'active' (or 'trial') happens in /admin.
    business = Business(
        owner_id=user.id,
        **body.model_dump(),
        status="pending",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db.add(business)
    await db.commit()
    await db.refresh(business)
    return business


@router.get("/mine", response_model=list[BusinessOut])
async def get_my_businesses(
    user: User = Depends(get_current_dashboard_user),
    db: AsyncSession = Depends(get_db),
):
    """Businesses this user can act on: ones they OWN, plus ones they manage as a
    desk-manager (secretary). Each carries access_role so the dashboard knows
    whether to show owner-only pages."""
    owned = (await db.execute(select(Business).where(Business.owner_id == user.id))).scalars().all()
    out: list[BusinessOut] = []
    seen: set[int] = set()
    for b in owned:
        item = BusinessOut.model_validate(b)
        item.access_role = "owner"
        out.append(item)
        seen.add(b.id)

    # Businesses where this user is an active desk-manager (and doesn't already
    # own it). Managers never see owned + managed duplicates.
    managed = (
        await db.execute(
            select(Business)
            .join(Staff, Staff.business_id == Business.id)
            .where(
                and_(
                    Staff.user_id == user.id,
                    Staff.can_manage.is_(True),
                    Staff.is_active.is_(True),
                )
            )
        )
    ).scalars().all()
    for b in managed:
        if b.id in seen:
            continue
        item = BusinessOut.model_validate(b)
        item.access_role = "manager"
        out.append(item)
        seen.add(b.id)
    return out


@router.get("/{business_id}", response_model=BusinessOut)
async def get_business(
    business_id: int,
    user: User = Depends(get_current_dashboard_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner/admin/manager view of the full business record. Customers use
    /{id}/public. authorize_business_access allows owner, super_admin, or an
    active desk-manager; anyone else gets 403/404."""
    business = await authorize_business_access(business_id, user, db)
    item = BusinessOut.model_validate(business)
    if business.owner_id != user.id and user.role != "super_admin":
        item.access_role = "manager"
    return item


@router.patch("/{business_id}", response_model=BusinessOut)
async def update_business(
    business_id: int,
    body: BusinessUpdate,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Not found")
    if business.owner_id != user.id and user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(business, field, value)

    db.add(business)
    await db.commit()
    await db.refresh(business)
    return business


# ── Public profile (for Telegram bot/customers) ──────────────────────────────

class PublicBusinessOut(BaseModel):
    id: int
    name: str
    category_id: int
    address: str
    phone: str
    telegram_username: str | None
    instagram_link: str | None
    description: str | None
    is_online_booking_enabled: bool
    allow_multi_service: bool
    allow_any_staff: bool
    latitude: float | None
    longitude: float | None
    custom_message_uz: str | None
    custom_message_ru: str | None
    custom_message_en: str | None
    photo_url: str | None = None

    model_config = {"from_attributes": True}


@router.get("/{business_id}/public", response_model=PublicBusinessOut)
async def get_public_profile(business_id: int, db: AsyncSession = Depends(get_db)):
    business = await db.get(Business, business_id)
    if not business or business.status not in ("active", "trial"):
        raise HTTPException(status_code=404, detail="Business not found")
    return business


# ── Business photo (one storefront image) ────────────────────────────────────
# Owners upload from the web dashboard; the image is shown on the web and — via a
# public serve endpoint — sent as the Telegram business card. We accept ANY image
# the owner picks and do the compression ourselves: the browser shrinks it before
# upload (so it clears Vercel's ~4.5MB body limit), and the server re-decodes,
# strips camera metadata, downscales, and re-encodes to a clean small JPEG. The
# byte ceiling below is an anti-abuse backstop, not a limit a real photo hits.
_PHOTO_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB hard backstop (abuse only)
_PHOTO_MAX_DIM = 1024                        # longest edge after downscale
_PHOTO_JPEG_QUALITY = 85

# Guard against decompression bombs: refuse to allocate a pixel buffer bigger than
# this even if the file is small on disk (a crafted PNG can be tiny yet enormous
# decoded). 40 MP comfortably covers any phone/camera photo.
Image.MAX_IMAGE_PIXELS = 40_000_000


def _process_image(raw: bytes) -> bytes:
    """Decode any supported image, normalize orientation, flatten transparency
    onto white, downscale so the longest edge is <= _PHOTO_MAX_DIM, and re-encode
    as an optimized JPEG. Returns the JPEG bytes. Raises 400 if the bytes aren't a
    readable image (so a PDF/renamed file gets a clean error, not a 500)."""
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)  # honor camera rotation
            if img.mode in ("RGBA", "LA", "P"):
                # Composite onto white so transparent areas don't turn black in JPEG.
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")
            img.thumbnail((_PHOTO_MAX_DIM, _PHOTO_MAX_DIM))  # keeps aspect ratio
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=_PHOTO_JPEG_QUALITY, optimize=True)
            return out.getvalue()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Could not read that image. Please try another photo.",
        )


async def _owned_business_or_403(business_id: int, user: User, db: AsyncSession) -> Business:
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Not found")
    if business.owner_id != user.id and user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return business


@router.put("/{business_id}/photo", response_model=BusinessOut)
async def upload_business_photo(
    business_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    """Replace the business's single storefront photo. Accepts any image; the
    server recompresses it to a small JPEG before storing."""
    business = await _owned_business_or_403(business_id, user, db)

    # Read one byte past the ceiling so we can tell "at the limit" from "over it".
    raw = await file.read(_PHOTO_MAX_UPLOAD_BYTES + 1)
    # One log line per attempt — makes "did the upload ever reach us, and with
    # what?" answerable from the server logs alone (was undiagnosable before).
    logger.info(
        "Photo upload: business=%s user=%s file=%r content_type=%r bytes=%s",
        business_id, user.id, file.filename, file.content_type, len(raw or b""),
    )
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(raw) > _PHOTO_MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large.")

    try:
        processed = _process_image(raw)
    except HTTPException:
        logger.warning(
            "Photo upload REJECTED (undecodable image): business=%s file=%r content_type=%r bytes=%s",
            business_id, file.filename, file.content_type, len(raw),
        )
        raise
    now = datetime.now(timezone.utc)

    photo = await db.get(BusinessPhoto, business_id)
    if photo is None:
        db.add(BusinessPhoto(
            business_id=business_id, data=processed, content_type="image/jpeg", updated_at=now,
        ))
    else:
        photo.data = processed
        photo.content_type = "image/jpeg"
        photo.updated_at = now
        db.add(photo)
    business.photo_updated_at = now
    db.add(business)
    await db.commit()
    await db.refresh(business)
    logger.info(
        "Photo upload STORED: business=%s stored_bytes=%s", business_id, len(processed)
    )
    return business


@router.delete("/{business_id}/photo", response_model=BusinessOut)
async def delete_business_photo(
    business_id: int,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    business = await _owned_business_or_403(business_id, user, db)
    photo = await db.get(BusinessPhoto, business_id)
    if photo is not None:
        await db.delete(photo)
    business.photo_updated_at = None
    db.add(business)
    await db.commit()
    await db.refresh(business)
    return business


@router.get("/{business_id}/photo")
async def get_business_photo(
    business_id: int, request: Request, db: AsyncSession = Depends(get_db),
):
    """Public — serves the stored photo bytes. Cached hard/immutable because the
    URL carries a ?v=<updated-at> token that changes on every new upload, so a
    stale image is impossible while an unchanged one caches for a year."""
    photo = await db.get(BusinessPhoto, business_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="No photo")
    etag = f'"{business_id}-{int(photo.updated_at.timestamp())}"'
    cache_headers = {"Cache-Control": "public, max-age=31536000, immutable", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cache_headers)
    return Response(content=photo.data, media_type=photo.content_type or "image/jpeg", headers=cache_headers)
