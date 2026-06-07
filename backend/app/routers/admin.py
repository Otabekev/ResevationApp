from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_super_admin
from app.models.booking import Booking, Customer
from app.models.business import Business, BusinessCategory
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


class BusinessStatusUpdate(BaseModel):
    status: str  # active | trial | suspended | blocked


class CategoryCreate(BaseModel):
    slug: str
    name_uz: str
    name_ru: str
    name_en: str
    icon: str | None = None
    description_uz: str | None = None
    description_ru: str | None = None
    description_en: str | None = None
    default_slot_step_minutes: int = 15
    sort_order: int = 0


class PlatformStats(BaseModel):
    total_businesses: int
    active_businesses: int
    trial_businesses: int
    total_bookings: int
    total_customers: int
    bookings_today: int


class AdminUserOut(BaseModel):
    """Admin view of a user — deliberately excludes hashed_password."""
    id: int
    telegram_id: int | None
    name: str
    username: str | None
    role: str
    language: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("/stats", response_model=PlatformStats)
async def get_platform_stats(
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date

    total_biz = await db.scalar(select(func.count(Business.id)))
    active_biz = await db.scalar(select(func.count(Business.id)).where(Business.status == "active"))
    trial_biz = await db.scalar(select(func.count(Business.id)).where(Business.status == "trial"))
    total_bookings = await db.scalar(select(func.count(Booking.id)))
    total_customers = await db.scalar(select(func.count(Customer.id)))
    today_bookings = await db.scalar(
        select(func.count(Booking.id)).where(Booking.booking_date == date.today())
    )

    return PlatformStats(
        total_businesses=total_biz or 0,
        active_businesses=active_biz or 0,
        trial_businesses=trial_biz or 0,
        total_bookings=total_bookings or 0,
        total_customers=total_customers or 0,
        bookings_today=today_bookings or 0,
    )


@router.get("/businesses")
async def list_all_businesses(
    status_filter: str | None = Query(None, alias="status"),
    region: str | None = Query(None),
    district: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import and_

    filters = []
    if status_filter:
        filters.append(Business.status == status_filter)
    if region:
        filters.append(Business.region == region)
    if district:
        filters.append(Business.district == district)

    stmt = select(Business)
    if filters:
        stmt = stmt.where(and_(*filters))
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch("/businesses/{business_id}/status")
async def update_business_status(
    business_id: int,
    body: BusinessStatusUpdate,
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed = {"active", "trial", "suspended", "blocked", "pending"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status must be one of {allowed}")

    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404)

    business.status = body.status
    db.add(business)
    await db.commit()
    return {"ok": True, "status": business.status}


@router.post("/categories")
async def create_category(
    body: CategoryCreate,
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    cat = BusinessCategory(**body.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.patch("/categories/{category_id}")
async def update_category(
    category_id: int,
    body: dict,
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    cat = await db.get(BusinessCategory, category_id)
    if not cat:
        raise HTTPException(status_code=404)
    for k, v in body.items():
        if hasattr(cat, k):
            setattr(cat, k, v)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    role: str | None = Query(None),
    page: int = Query(1, ge=1),
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    stmt = stmt.offset((page - 1) * 20).limit(20)
    result = await db.execute(stmt)
    return result.scalars().all()
