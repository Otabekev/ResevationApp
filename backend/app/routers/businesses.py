from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_business_owner, get_current_super_admin, get_current_user
from app.models.business import Business, BusinessCategory
from app.models.user import User

router = APIRouter(prefix="/businesses", tags=["businesses"])


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
    name: str
    region: str = "Namangan"
    district: str = "Pop"
    city: str
    address: str
    phone: str
    telegram_username: str | None = None
    instagram_link: str | None = None
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class BusinessUpdate(BaseModel):
    name: str | None = None
    city: str | None = None
    region: str | None = None
    district: str | None = None
    address: str | None = None
    phone: str | None = None
    telegram_username: str | None = None
    instagram_link: str | None = None
    description: str | None = None
    is_online_booking_enabled: bool | None = None
    min_advance_booking_minutes: int | None = None
    max_advance_booking_days: int | None = None
    cancellation_policy_hours: int | None = None
    slot_step_minutes: int | None = None
    custom_message_uz: str | None = None
    custom_message_ru: str | None = None
    custom_message_en: str | None = None
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
    latitude: float | None
    longitude: float | None
    custom_message_uz: str | None
    custom_message_ru: str | None
    custom_message_en: str | None

    model_config = {"from_attributes": True}


# ── Category endpoints ───────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BusinessCategory).where(BusinessCategory.is_active == True).order_by(BusinessCategory.sort_order)
    )
    return result.scalars().all()


# ── Business CRUD ────────────────────────────────────────────────────────────

@router.post("", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
async def register_business(
    body: BusinessCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    return result.scalars().all()


@router.get("/{business_id}", response_model=BusinessOut)
async def get_business(
    business_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner/admin view of the full business record. Customers use /{id}/public."""
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    if business.owner_id != user.id and user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return business


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
    latitude: float | None
    longitude: float | None
    custom_message_uz: str | None
    custom_message_ru: str | None
    custom_message_en: str | None

    model_config = {"from_attributes": True}


@router.get("/{business_id}/public", response_model=PublicBusinessOut)
async def get_public_profile(business_id: int, db: AsyncSession = Depends(get_db)):
    business = await db.get(Business, business_id)
    if not business or business.status not in ("active", "trial"):
        raise HTTPException(status_code=404, detail="Business not found")
    return business
