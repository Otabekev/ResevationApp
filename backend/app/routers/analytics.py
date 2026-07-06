from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_business_owner
from app.models.booking import Booking
from app.models.business import Business
from app.models.service import Service
from app.models.staff import Staff
from app.timeutils import now_local
from app.models.user import User

router = APIRouter(prefix="/businesses/{business_id}/analytics", tags=["analytics"])


@router.get("")
async def get_analytics(
    business_id: int,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    business = await db.get(Business, business_id)
    if not business or (business.owner_id != user.id and user.role != "super_admin"):
        raise HTTPException(status_code=403)

    # Local (Asia/Tashkent) "today" — date.today() is server-local (UTC on
    # Railway) and would be a day off for ~5h every night for UZ users.
    since = now_local().date() - timedelta(days=days)

    # Total bookings in period
    total = await db.scalar(
        select(func.count(Booking.id)).where(
            and_(Booking.business_id == business_id, Booking.booking_date >= since)
        )
    )

    # By status
    status_rows = await db.execute(
        select(Booking.status, func.count(Booking.id))
        .where(and_(Booking.business_id == business_id, Booking.booking_date >= since))
        .group_by(Booking.status)
    )
    by_status = {row[0]: row[1] for row in status_rows.all()}

    # Busiest services
    service_rows = await db.execute(
        select(Service.name_uz, func.count(Booking.id).label("count"))
        .join(Service, Service.id == Booking.service_id)
        .where(and_(Booking.business_id == business_id, Booking.booking_date >= since))
        .group_by(Service.name_uz)
        .order_by(func.count(Booking.id).desc())
        .limit(5)
    )
    top_services = [{"name": r[0], "bookings": r[1]} for r in service_rows.all()]

    # Busiest staff
    staff_rows = await db.execute(
        select(Staff.name, func.count(Booking.id).label("count"))
        .join(Staff, Staff.id == Booking.staff_id)
        .where(and_(Booking.business_id == business_id, Booking.booking_date >= since))
        .group_by(Staff.name)
        .order_by(func.count(Booking.id).desc())
        .limit(5)
    )
    top_staff = [{"name": r[0], "bookings": r[1]} for r in staff_rows.all()]

    # Bookings per day (last 7 days)
    daily_rows = await db.execute(
        select(Booking.booking_date, func.count(Booking.id))
        .where(
            and_(
                Booking.business_id == business_id,
                Booking.booking_date >= now_local().date() - timedelta(days=7),
            )
        )
        .group_by(Booking.booking_date)
        .order_by(Booking.booking_date)
    )
    # Zero-fill the last 7 calendar days so the chart always shows 7 bars — a quiet
    # business shouldn't render as a sparse/broken-looking chart with missing days.
    counts = {str(r[0]): r[1] for r in daily_rows.all()}
    today = now_local().date()
    daily = [
        {"date": d.isoformat(), "bookings": counts.get(d.isoformat(), 0)}
        for d in (today - timedelta(days=i) for i in range(6, -1, -1))
    ]

    no_show_rate = 0
    if total:
        no_shows = by_status.get("no_show", 0)
        no_show_rate = round(no_shows / total * 100, 1)

    return {
        "period_days": days,
        "total_bookings": total or 0,
        "by_status": by_status,
        "no_show_rate_percent": no_show_rate,
        "top_services": top_services,
        "top_staff": top_staff,
        "daily_last_7_days": daily,
    }
