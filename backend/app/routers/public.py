"""
Public read-only endpoints used by the Telegram bot.
No authentication required.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.business import Business
from app.models.staff import Staff, StaffService
from app.models.user import User

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/launch-status")
async def launch_status(
    telegram_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Pre-launch gate for the bot's booking flow.

    Returns ``{"open": bool, "launched": bool}``:
      - ``launched`` — the public launch date has arrived (or none is configured).
        User-independent; the bot caches this so the gate is a no-op after launch.
      - ``open`` — may THIS user enter the booking flow. Always true once launched;
        before launch only business owners/staff (testing during onboarding) get in.
    """
    if settings.has_launched:
        return {"open": True, "launched": True}

    # Pre-launch: only business owners/staff (and platform super-admins) may proceed.
    if telegram_id is None:
        return {"open": False, "launched": False}
    if telegram_id in settings.super_admin_ids:
        return {"open": True, "launched": False}

    user = (
        await db.execute(select(User).where(User.telegram_id == telegram_id))
    ).scalar_one_or_none()
    if user is None:
        return {"open": False, "launched": False}

    owns = (
        await db.execute(select(Business.id).where(Business.owner_id == user.id).limit(1))
    ).first() is not None
    is_staff = False
    if not owns:
        is_staff = (
            await db.execute(
                select(Staff.id)
                .where(and_(Staff.user_id == user.id, Staff.is_active == True))
                .limit(1)
            )
        ).first() is not None

    return {"open": owns or is_staff, "launched": False}


@router.get("/businesses")
async def list_active_businesses(
    category_id: int | None = Query(None),
    region: str | None = Query(None),
    district: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    filters = [Business.status.in_(["active", "trial"]), Business.is_online_booking_enabled == True]
    if category_id:
        filters.append(Business.category_id == category_id)
    if region:
        filters.append(Business.region == region)
    if district:
        filters.append(Business.district == district)

    # Bounded + backed by the (district,status)/(category_id,status) composite
    # indexes (migration 0009). A single district at launch is well under the
    # default page; multi-district expansion should drive offset from the bot.
    result = await db.execute(
        select(Business).where(and_(*filters)).order_by(Business.name).limit(limit).offset(offset)
    )
    businesses = result.scalars().all()
    return [
        {
            "id": b.id, "name": b.name, "category_id": b.category_id,
            "address": b.address, "phone": b.phone,
            "telegram_username": b.telegram_username,
        }
        for b in businesses
    ]


@router.get("/businesses/{business_id}/staff")
async def list_public_staff(business_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Staff).where(and_(Staff.business_id == business_id, Staff.is_active == True))
    )
    staff_list = result.scalars().all()

    # Attach each staff member's service ids so the bot can pre-filter to staff
    # who can perform a multi-service selection (one batched query, no N+1).
    by_staff: dict[int, list[int]] = {}
    if staff_list:
        links = await db.execute(
            select(StaffService.staff_id, StaffService.service_id).where(
                StaffService.staff_id.in_([s.id for s in staff_list])
            )
        )
        for sid, svc_id in links.all():
            by_staff.setdefault(sid, []).append(svc_id)

    return [{"id": s.id, "name": s.name, "service_ids": by_staff.get(s.id, [])} for s in staff_list]
