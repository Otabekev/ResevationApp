"""
Public read-only endpoints used by the Telegram bot.
No authentication required.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.business import Business
from app.models.staff import Staff, StaffService

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/businesses")
async def list_active_businesses(
    category_id: int | None = Query(None),
    region: str | None = Query(None),
    district: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = [Business.status.in_(["active", "trial"]), Business.is_online_booking_enabled == True]
    if category_id:
        filters.append(Business.category_id == category_id)
    if region:
        filters.append(Business.region == region)
    if district:
        filters.append(Business.district == district)

    result = await db.execute(select(Business).where(and_(*filters)).order_by(Business.name))
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
    return [{"id": s.id, "name": s.name} for s in staff_list]
