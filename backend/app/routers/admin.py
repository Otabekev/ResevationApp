import hmac
import time
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_current_super_admin
from app.models.booking import Booking, Customer
from app.models.broadcast import Broadcast
from app.models.business import Business, BusinessCategory
from app.models.service import Service
from app.models.staff import Staff
from app.models.user import User
from app.services import broadcast_service

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


class CategoryUpdate(BaseModel):
    """Explicit allow-list of mutable fields — never setattr from a raw dict."""
    slug: str | None = None
    name_uz: str | None = None
    name_ru: str | None = None
    name_en: str | None = None
    icon: str | None = None
    description_uz: str | None = None
    description_ru: str | None = None
    description_en: str | None = None
    default_slot_step_minutes: int | None = None
    sort_order: int | None = None
    is_active: bool | None = None


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
    body: CategoryUpdate,
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    cat = await db.get(BusinessCategory, category_id)
    if not cat:
        raise HTTPException(status_code=404)
    for k, v in body.model_dump(exclude_none=True).items():
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


# ── Drill-down + activity feed for the admin overview ────────────────────────

def _booking_row(b: Booking, business_name: str | None, service_name: str | None) -> dict:
    """Compact booking row for admin feeds — names included so the client
    doesn't N+1 fetch."""
    return {
        "id": b.id,
        "business_id": b.business_id,
        "business_name": business_name,
        "service_name": service_name,
        "customer_name": b.customer_name,
        "booking_date": b.booking_date.isoformat() if b.booking_date else None,
        "booking_time": b.start_time.isoformat() if b.start_time else None,
        "status": b.status,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


@router.get("/businesses/{business_id}/detail")
async def get_business_detail(
    business_id: int,
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin drill-down: business fields + owner + counts + recent bookings."""
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404)

    owner = await db.get(User, business.owner_id) if business.owner_id else None

    services_count = await db.scalar(
        select(func.count(Service.id)).where(Service.business_id == business_id)
    ) or 0
    staff_count = await db.scalar(
        select(func.count(Staff.id)).where(Staff.business_id == business_id)
    ) or 0
    bookings_total = await db.scalar(
        select(func.count(Booking.id)).where(Booking.business_id == business_id)
    ) or 0
    bookings_today = await db.scalar(
        select(func.count(Booking.id)).where(
            Booking.business_id == business_id,
            Booking.booking_date == date.today(),
        )
    ) or 0
    bookings_month = await db.scalar(
        select(func.count(Booking.id)).where(
            Booking.business_id == business_id,
            Booking.booking_date >= date.today().replace(day=1),
        )
    ) or 0
    bookings_confirmed = await db.scalar(
        select(func.count(Booking.id)).where(
            Booking.business_id == business_id,
            Booking.status.in_(["confirmed", "completed"]),
        )
    ) or 0

    # Recent 10 bookings with service name joined (no client N+1).
    rows = await db.execute(
        select(Booking, Service.name_uz)
        .join(Service, Service.id == Booking.service_id, isouter=True)
        .where(Booking.business_id == business_id)
        .order_by(desc(Booking.created_at))
        .limit(10)
    )
    recent = [_booking_row(b, business.name, svc_name) for b, svc_name in rows.all()]

    return {
        "id": business.id,
        "name": business.name,
        "category_id": business.category_id,
        "status": business.status,
        "region": business.region,
        "district": business.district,
        "address": business.address,
        "phone": business.phone,
        "is_online_booking_enabled": business.is_online_booking_enabled,
        "trial_ends_at": business.trial_ends_at.isoformat() if business.trial_ends_at else None,
        "created_at": business.created_at.isoformat() if business.created_at else None,
        "owner": {
            "id": owner.id,
            "name": owner.name,
            "username": owner.username,
            "telegram_id": owner.telegram_id,
            "role": owner.role,
        } if owner else None,
        "counts": {
            "services": services_count,
            "staff": staff_count,
            "bookings_total": bookings_total,
            "bookings_today": bookings_today,
            "bookings_month": bookings_month,
            "bookings_confirmed": bookings_confirmed,
        },
        "recent_bookings": recent,
    }


@router.get("/recent")
async def get_recent_activity(
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Drives the overview page: who's waiting for approval, who signed up
    recently, and what bookings are flowing through the platform."""
    pending_rows = await db.execute(
        select(Business).where(Business.status == "pending").order_by(desc(Business.created_at)).limit(20)
    )
    pending = [
        {
            "id": b.id, "name": b.name, "district": b.district,
            "region": b.region, "status": b.status,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in pending_rows.scalars().all()
    ]

    recent_biz_rows = await db.execute(
        select(Business).order_by(desc(Business.created_at)).limit(5)
    )
    recent_businesses = [
        {
            "id": b.id, "name": b.name, "district": b.district,
            "status": b.status,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in recent_biz_rows.scalars().all()
    ]

    booking_rows = await db.execute(
        select(Booking, Business.name, Service.name_uz)
        .join(Business, Business.id == Booking.business_id, isouter=True)
        .join(Service, Service.id == Booking.service_id, isouter=True)
        .order_by(desc(Booking.created_at))
        .limit(10)
    )
    recent_bookings = [_booking_row(b, biz_name, svc_name) for b, biz_name, svc_name in booking_rows.all()]

    return {
        "pending": pending,
        "recent_businesses": recent_businesses,
        "recent_bookings": recent_bookings,
    }


# ── Investor growth-map feed (secret-gated, cached) ──────────────────────────
# Powers the standalone investor map (QN_Investor). Gated by GROWTH_SECRET (NOT
# the admin JWT) so the static site can read it with a token; disabled (403)
# until GROWTH_SECRET is set. Cached in-process to keep it off the booking hot
# path, and it sets its own permissive CORS header (it's already secret-gated)
# so the static investor site can fetch it without any allowed-origins juggling.

_growth_cache: dict = {"at": 0.0, "data": None}
_GROWTH_TTL = 600.0  # seconds

# Uzbekistan bounding box. A business location is shared via Telegram's "send
# location" — which captures wherever the PHONE is — so a test shared from abroad
# lands thousands of km away. Drop anything outside the country so a stray pin can
# never appear in another country on the investor map.
_UZ_LAT_MIN, _UZ_LAT_MAX = 37.1, 45.6
_UZ_LNG_MIN, _UZ_LNG_MAX = 55.9, 73.2


def _in_uzbekistan(lat: float | None, lng: float | None) -> bool:
    return (
        lat is not None and lng is not None
        and _UZ_LAT_MIN <= lat <= _UZ_LAT_MAX
        and _UZ_LNG_MIN <= lng <= _UZ_LNG_MAX
    )


@router.get("/growth")
async def growth_map(secret: str = Query(""), db: AsyncSession = Depends(get_db)):
    # Constant-time compare so the secret can't be guessed by timing.
    if not settings.growth_secret or not hmac.compare_digest(secret, settings.growth_secret):
        raise HTTPException(status_code=403, detail="Forbidden")

    now = time.monotonic()
    cached = _growth_cache["data"]
    if cached is None or (now - _growth_cache["at"]) >= _GROWTH_TTL:
        rows = (
            await db.execute(
                select(Business, BusinessCategory.name_en)
                .join(BusinessCategory, BusinessCategory.id == Business.category_id, isouter=True)
                .where(
                    Business.latitude.is_not(None),
                    Business.longitude.is_not(None),
                    ~Business.status.in_(["blocked", "suspended"]),
                )
                .order_by(Business.created_at)
            )
        ).all()
        # Only businesses physically inside Uzbekistan reach the map.
        located = [(b, cat) for (b, cat) in rows if _in_uzbekistan(b.latitude, b.longitude)]

        # Week 1 = the earliest located business; everyone else is weeks-after that.
        earliest = None
        for b, _name in located:
            if b.created_at and (earliest is None or b.created_at < earliest):
                earliest = b.created_at

        def _week_of(dt) -> int:
            return (dt.date() - earliest.date()).days // 7 + 1 if (dt and earliest) else 1

        items = []
        for b, cat_name in located:
            items.append({
                "id": b.id,
                "name": b.name,
                "lat": b.latitude,
                "lng": b.longitude,
                "category": cat_name or "Other",
                "district": b.district or b.region or "",
                "status": b.status,
                "week": _week_of(b.created_at),
                "joined": b.created_at.date().isoformat() if b.created_at else None,
            })

        # ── Traction stats (for the investor charts) ─────────────────────────
        total_businesses = await db.scalar(select(func.count(Business.id))) or 0
        active_businesses = await db.scalar(
            select(func.count(Business.id)).where(Business.status.in_(["active", "trial"]))
        ) or 0
        total_bookings = await db.scalar(select(func.count(Booking.id))) or 0

        new_by_week: dict[int, int] = {}
        for it in items:
            new_by_week[it["week"]] = new_by_week.get(it["week"], 0) + 1

        bookings_by_week: dict[int, int] = {}
        if earliest:
            for (created,) in (await db.execute(select(Booking.created_at))).all():
                if created:
                    w = max(1, _week_of(created))
                    bookings_by_week[w] = bookings_by_week.get(w, 0) + 1

        max_w = max([1, *new_by_week.keys(), *bookings_by_week.keys()])
        weekly = []
        cum_biz = cum_bk = 0
        for w in range(1, max_w + 1):
            cum_biz += new_by_week.get(w, 0)
            cum_bk += bookings_by_week.get(w, 0)
            weekly.append({
                "week": w,
                "new_businesses": new_by_week.get(w, 0),
                "cum_businesses": cum_biz,
                "bookings": bookings_by_week.get(w, 0),
                "cum_bookings": cum_bk,
            })

        # ── Extra investor signals ───────────────────────────────────────────
        avg_bpb = round(total_bookings / active_businesses, 1) if active_businesses else 0.0

        cat_rows = (
            await db.execute(
                select(BusinessCategory.name_en, func.count(Business.id))
                .join(Business, Business.category_id == BusinessCategory.id)
                .where(~Business.status.in_(["blocked", "suspended"]))
                .group_by(BusinessCategory.name_en)
                .order_by(func.count(Business.id).desc())
                .limit(6)
            )
        ).all()
        top_categories = [{"name": name or "Other", "count": cnt} for name, cnt in cat_rows]

        region_rows = (
            await db.execute(
                select(Business.region)
                .where(~Business.status.in_(["blocked", "suspended"]))
                .group_by(Business.region)
            )
        ).all()
        regions_with_businesses = sorted({r for (r,) in region_rows if r})

        first_bk = await db.scalar(select(func.min(Booking.created_at)))
        first_booking_date = first_bk.date().isoformat() if first_bk else None

        top_performer_bookings = int(
            await db.scalar(
                select(func.count(Booking.id))
                .group_by(Booking.business_id)
                .order_by(func.count(Booking.id).desc())
                .limit(1)
            ) or 0
        )

        cached = {
            "businesses": items,
            "max_week": max((i["week"] for i in items), default=1),
            "stats": {
                "total_businesses": total_businesses,
                "located_businesses": len(items),
                "active_businesses": active_businesses,
                "total_bookings": total_bookings,
                "avg_bookings_per_business": avg_bpb,
                "top_categories": top_categories,
                "regions_with_businesses": regions_with_businesses,
                "first_booking_date": first_booking_date,
                "top_performer_bookings": top_performer_bookings,
                "weekly": weekly,
            },
        }
        _growth_cache["data"] = cached
        _growth_cache["at"] = now

    return JSONResponse(
        content=cached,
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=300"},
    )


# ── Broadcasts (super-admin announcements to bot users) ──────────────────────

class BroadcastCreate(BaseModel):
    audience: Literal["all", "owners_staff", "customers"]
    text: str = Field(min_length=1, max_length=4000)
    # Naive datetimes are read as Tashkent local time; null/past = send now.
    scheduled_at: datetime | None = None


class BroadcastTest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _broadcast_out(b: Broadcast) -> dict:
    return {
        "id": b.id,
        "audience": b.audience,
        "text": b.text,
        "status": b.status,
        "scheduled_at": b.scheduled_at.isoformat() if b.scheduled_at else None,
        "total_recipients": b.total_recipients,
        "sent_count": b.sent_count,
        "failed_count": b.failed_count,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "finished_at": b.finished_at.isoformat() if b.finished_at else None,
    }


@router.get("/broadcast/audience-counts")
async def broadcast_audience_counts(
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Recipient count per audience, for the pre-send preview."""
    return await broadcast_service.count_audiences(db)


@router.get("/broadcasts")
async def list_broadcasts(
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(select(Broadcast).order_by(desc(Broadcast.created_at)).limit(50))
    ).scalars().all()
    return [_broadcast_out(b) for b in rows]


@router.post("/broadcast")
async def create_broadcast(
    body: BroadcastCreate,
    background: BackgroundTasks,
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    scheduled_at = broadcast_service.normalize_scheduled_at(body.scheduled_at)
    now = broadcast_service._now_utc()
    send_now = scheduled_at is None or scheduled_at <= now

    b = Broadcast(
        created_by=admin.id,
        audience=body.audience,
        text=body.text,
        status="scheduled",
        scheduled_at=None if send_now else scheduled_at,
        total_recipients=await broadcast_service.audience_count(db, body.audience),
    )
    db.add(b)
    await db.commit()
    await db.refresh(b)

    # "Send now" dispatches immediately in the background; a future schedule is
    # left for the scheduler's poller to pick up at its time.
    if send_now:
        background.add_task(broadcast_service.run_broadcast, b.id)

    return _broadcast_out(b)


@router.post("/broadcast/test")
async def send_broadcast_test(
    body: BroadcastTest,
    admin: User = Depends(get_current_super_admin),
):
    """Send the message only to the calling admin, to preview how it looks."""
    if not admin.telegram_id:
        raise HTTPException(status_code=400, detail="Your account has no Telegram chat to preview to.")
    ok = await broadcast_service.send_test(admin.telegram_id, body.text)
    return {"ok": ok}


@router.post("/broadcasts/{broadcast_id}/cancel")
async def cancel_broadcast(
    broadcast_id: int,
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    b = await db.get(Broadcast, broadcast_id)
    if not b:
        raise HTTPException(status_code=404)
    if b.status != "scheduled":
        raise HTTPException(status_code=400, detail="Only a scheduled broadcast can be cancelled.")
    b.status = "cancelled"
    await db.commit()
    return {"ok": True, "status": b.status}
