from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_business_owner, get_current_user, require_bot_secret
from app.limiter import limiter
from app.models.booking import Booking, Customer, booking_services
from app.models.business import Business
from app.models.service import Service
from app.models.staff import Staff
from app.models.user import User
from app.services.booking_engine import create_booking
from app.services.notification_service import (
    booking_confirmed_message,
    booking_cancelled_message,
    new_booking_alert_message,
    review_prompt_message,
    send_telegram_location,
    send_telegram_message,
)

router = APIRouter(tags=["bookings"])


# ── Schemas ──────────────────────────────────────────────────────────────────

def _normalize_service_ids(self):
    """Keep service_id and service_ids consistent. With no list, default it to
    [service_id]; with a list, the first id is the primary service_id. So
    downstream code can always use service_ids and the legacy service_id alike."""
    if not self.service_ids:
        self.service_ids = [self.service_id]
    else:
        self.service_id = self.service_ids[0]
    return self


class BookingCreatePublic(BaseModel):
    """Used by Telegram bot / Mini App customers."""
    business_id: int
    service_id: int
    # Optional multi-service booking (back-to-back, one staff). Omit → single.
    service_ids: list[int] | None = None
    staff_id: int | None = None
    booking_date: date
    start_time: time
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_phone: str = Field(..., min_length=7, max_length=20)
    notes: str | None = Field(None, max_length=1000)
    telegram_id: int  # passed by the bot
    language: str = "uz"  # customer's bot language — keeps notifications localized

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str) -> str:
        return v if v in ("uz", "ru", "en") else "uz"

    _fill_service_ids = model_validator(mode="after")(_normalize_service_ids)


class BookingCreateManual(BaseModel):
    """Used by business owner to manually create a booking."""
    service_id: int
    service_ids: list[int] | None = None
    staff_id: int | None = None
    booking_date: date
    start_time: time
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_phone: str = Field(..., min_length=3, max_length=20)
    notes: str | None = Field(None, max_length=1000)

    _fill_service_ids = model_validator(mode="after")(_normalize_service_ids)


class BookingOut(BaseModel):
    id: int
    business_id: int
    service_id: int
    staff_id: int | None
    customer_id: int | None
    customer_name: str
    customer_phone: str
    booking_date: date
    start_time: time
    end_time: time
    status: str
    notes: str | None
    was_auto_assigned: bool

    model_config = {"from_attributes": True}


class BookingListItem(BookingOut):
    """List view enriched with display names so clients never N+1."""
    service_name_uz: str | None = None
    service_name_ru: str | None = None
    service_name_en: str | None = None
    staff_name: str | None = None


class CancelRequest(BaseModel):
    reason: str | None = Field(None, max_length=500)


class StatusUpdateRequest(BaseModel):
    status: str  # confirmed | completed | no_show | cancelled_by_business


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _notify_business_side(
    db: AsyncSession, booking: Booking, business: Business, svc_name_for: dict[str, str]
) -> None:
    """Alert the owner and (if linked to Telegram) the assigned staff member."""
    notified: set[int] = set()

    if business and business.owner_id:
        owner = (
            await db.execute(select(User).where(User.id == business.owner_id))
        ).scalar_one_or_none()
        if owner and owner.telegram_id:
            notified.add(owner.telegram_id)
            await send_telegram_message(
                owner.telegram_id,
                new_booking_alert_message(
                    lang=owner.language,
                    customer_name=booking.customer_name,
                    service_name=svc_name_for.get(owner.language, svc_name_for["uz"]),
                    date_str=str(booking.booking_date),
                    time_str=booking.start_time.strftime("%H:%M"),
                ),
            )

    if booking.staff_id:
        staff = await db.get(Staff, booking.staff_id)
        if staff and staff.user_id:
            staff_user = (
                await db.execute(select(User).where(User.id == staff.user_id))
            ).scalar_one_or_none()
            if staff_user and staff_user.telegram_id and staff_user.telegram_id not in notified:
                await send_telegram_message(
                    staff_user.telegram_id,
                    new_booking_alert_message(
                        lang=staff_user.language,
                        customer_name=booking.customer_name,
                        service_name=svc_name_for.get(staff_user.language, svc_name_for["uz"]),
                        date_str=str(booking.booking_date),
                        time_str=booking.start_time.strftime("%H:%M"),
                    ),
                )


def _svc_names(service: Service | None) -> dict[str, str]:
    if service is None:
        return {"uz": "—", "ru": "—", "en": "—"}
    return {"uz": service.name_uz, "ru": service.name_ru, "en": service.name_en}


def _svc_names_all(services: list[Service]) -> dict[str, str]:
    """Combined per-language names for a multi-service booking, e.g.
    'Soch olish, Soqol olish'. One name for a single service; '—' for none."""
    if not services:
        return {"uz": "—", "ru": "—", "en": "—"}
    return {
        "uz": ", ".join(s.name_uz for s in services),
        "ru": ", ".join(s.name_ru for s in services),
        "en": ", ".join(s.name_en for s in services),
    }


# ── Public booking (Telegram bot) ────────────────────────────────────────────

@router.post("/bookings/public", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def create_public_booking(
    request: Request,
    body: BookingCreatePublic,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_bot_secret),
):
    """
    Creates a booking from the Telegram bot.
    Authenticated by the bot's shared secret (X-Bot-Secret header); only then is
    the telegram_id in the body trusted. Gets or creates the customer record.
    """
    # Get or create customer
    result = await db.execute(select(Customer).where(Customer.telegram_id == body.telegram_id))
    customer = result.scalar_one_or_none()
    if customer is None:
        customer = Customer(
            telegram_id=body.telegram_id,
            name=body.customer_name,
            phone=body.customer_phone,
            language=body.language,
        )
        db.add(customer)
        await db.flush()
    else:
        # Update name/phone/language in case they changed
        customer.name = body.customer_name
        customer.phone = body.customer_phone
        customer.language = body.language

    # The business's multi-service toggle is authoritative — if it's off, ignore
    # any extra services the client sent and book only the primary one.
    _biz = await db.get(Business, body.business_id)
    if _biz is None:
        raise HTTPException(status_code=404, detail="Business not found")
    service_ids = body.service_ids if _biz.allow_multi_service else [body.service_id]

    try:
        booking = await create_booking(
            db,
            business_id=body.business_id,
            service_id=body.service_id,
            staff_id=body.staff_id,
            customer=customer,
            booking_date=body.booking_date,
            start_time=body.start_time,
            notes=body.notes,
            service_ids=service_ids,
        )
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))

    await db.commit()
    await db.refresh(booking)

    # Send confirmation to customer
    business = await db.get(Business, booking.business_id)
    staff = await db.get(Staff, booking.staff_id) if booking.staff_id else None

    # Resolve every booked service (in order) so the confirmation and the owner
    # alert list all of them, not just the primary.
    svc_rows = await db.execute(select(Service).where(Service.id.in_(service_ids)))
    svc_by_id = {s.id: s for s in svc_rows.scalars().all()}
    ordered_services = [svc_by_id[sid] for sid in service_ids if sid in svc_by_id]

    lang = customer.language
    names = _svc_names_all(ordered_services)
    staff_name = staff.name if staff else "—"

    await send_telegram_message(
        customer.telegram_id,
        booking_confirmed_message(
            lang=lang,
            business_name=business.name,
            service_name=names.get(lang, names["uz"]),
            staff_name=staff_name,
            date_str=str(booking.booking_date),
            time_str=booking.start_time.strftime("%H:%M"),
        ),
    )

    # Send the business map pin alongside the confirmation so the customer can
    # find the place (best-effort; only when the business has coordinates).
    if business.latitude is not None and business.longitude is not None:
        await send_telegram_location(customer.telegram_id, business.latitude, business.longitude)

    await _notify_business_side(db, booking, business, names)

    return booking


# ── Business owner booking management ────────────────────────────────────────

@router.get("/businesses/{business_id}/bookings", response_model=list[BookingListItem])
async def list_bookings(
    business_id: int,
    booking_date: date | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    staff_id: int | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    business = await db.get(Business, business_id)
    if not business or (business.owner_id != user.id and user.role != "super_admin"):
        raise HTTPException(status_code=403)

    filters = [Booking.business_id == business_id]
    if booking_date:
        filters.append(Booking.booking_date == booking_date)
    if date_from:
        filters.append(Booking.booking_date >= date_from)
    if date_to:
        filters.append(Booking.booking_date <= date_to)
    if status_filter:
        filters.append(Booking.status == status_filter)
    if staff_id:
        filters.append(Booking.staff_id == staff_id)

    result = await db.execute(
        select(Booking)
        .where(and_(*filters))
        .order_by(Booking.booking_date, Booking.start_time)
        .limit(limit)
        .offset(offset)
    )
    bookings = result.scalars().all()

    # Batch-resolve display names (no N+1).
    # All services per booking — multi-service bookings list every service, not
    # just the primary. Legacy bookings with no booking_services rows fall back
    # to their primary service_id.
    booking_ids = [b.id for b in bookings]
    links: dict[int, list[int]] = {}
    if booking_ids:
        bs_rows = await db.execute(
            select(booking_services.c.booking_id, booking_services.c.service_id)
            .where(booking_services.c.booking_id.in_(booking_ids))
        )
        for bid, sid in bs_rows.all():
            links.setdefault(bid, []).append(sid)

    stf_ids = {b.staff_id for b in bookings if b.staff_id}
    svc_ids = {b.service_id for b in bookings} | {sid for sids in links.values() for sid in sids}
    svc_map: dict[int, Service] = {}
    stf_map: dict[int, Staff] = {}
    if svc_ids:
        rows = await db.execute(select(Service).where(Service.id.in_(svc_ids)))
        svc_map = {s.id: s for s in rows.scalars().all()}
    if stf_ids:
        rows = await db.execute(select(Staff).where(Staff.id.in_(stf_ids)))
        stf_map = {s.id: s for s in rows.scalars().all()}

    def _ordered_services(b: Booking) -> list[Service]:
        # Primary service first, then any other services linked to the booking.
        sids = links.get(b.id) or [b.service_id]
        ordered_ids = [b.service_id] + [s for s in sids if s != b.service_id]
        return [svc_map[s] for s in ordered_ids if s in svc_map]

    out: list[BookingListItem] = []
    for b in bookings:
        item = BookingListItem.model_validate(b)
        names = _svc_names_all(_ordered_services(b))
        item.service_name_uz = names["uz"]
        item.service_name_ru = names["ru"]
        item.service_name_en = names["en"]
        stf = stf_map.get(b.staff_id) if b.staff_id else None
        if stf:
            item.staff_name = stf.name
        out.append(item)
    return out


@router.post("/businesses/{business_id}/bookings", response_model=BookingOut, status_code=201)
async def create_manual_booking(
    business_id: int,
    body: BookingCreateManual,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    """Business owner manually creates a booking (walk-in, phone call, etc.)."""
    business = await db.get(Business, business_id)
    if not business or (business.owner_id != user.id and user.role != "super_admin"):
        raise HTTPException(status_code=403)

    # Walk-in customers have no Telegram account. Reuse an existing walk-in
    # record with the same phone (so repeat customers keep their history)
    # instead of inserting a duplicate each time.
    customer = (
        await db.execute(
            select(Customer)
            .where(
                and_(
                    Customer.telegram_id.is_(None),
                    Customer.phone == body.customer_phone,
                )
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if customer is None:
        customer = Customer(
            telegram_id=None,  # walk-in: no Telegram account
            name=body.customer_name,
            phone=body.customer_phone,
        )
        db.add(customer)
        await db.flush()
    else:
        customer.name = body.customer_name

    service_ids = body.service_ids if business.allow_multi_service else [body.service_id]
    try:
        booking = await create_booking(
            db,
            business_id=business_id,
            service_id=body.service_id,
            staff_id=body.staff_id,
            customer=customer,
            booking_date=body.booking_date,
            start_time=body.start_time,
            notes=body.notes,
            service_ids=service_ids,
        )
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))

    await db.commit()
    await db.refresh(booking)
    return booking


@router.patch("/bookings/{booking_id}/status", response_model=BookingOut)
async def update_booking_status(
    booking_id: int,
    body: StatusUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404)

    allowed_statuses = ["confirmed", "completed", "no_show", "cancelled_by_business"]
    if body.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Status must be one of {allowed_statuses}")

    # Verify permission
    business = await db.get(Business, booking.business_id)
    staff = await db.get(Staff, booking.staff_id) if booking.staff_id else None
    is_owner = business and business.owner_id == user.id
    is_assigned_staff = staff and staff.user_id == user.id

    if not is_owner and not is_assigned_staff and user.role != "super_admin":
        raise HTTPException(status_code=403)

    was_pending = booking.status == "pending"
    booking.status = body.status
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    customer = await db.get(Customer, booking.customer_id) if booking.customer_id else None
    service = await db.get(Service, booking.service_id)
    names = _svc_names(service)

    # Tell the customer their pending request was approved
    if body.status == "confirmed" and was_pending and customer and customer.telegram_id:
        staff_row = await db.get(Staff, booking.staff_id) if booking.staff_id else None
        await send_telegram_message(
            customer.telegram_id,
            booking_confirmed_message(
                lang=customer.language,
                business_name=business.name if business else "—",
                service_name=names.get(customer.language, names["uz"]),
                staff_name=staff_row.name if staff_row else "—",
                date_str=str(booking.booking_date),
                time_str=booking.start_time.strftime("%H:%M"),
            ),
        )
        if business and business.latitude is not None and business.longitude is not None:
            await send_telegram_location(customer.telegram_id, business.latitude, business.longitude)

    # Send review prompt to customer when booking is completed
    if body.status == "completed" and customer and customer.telegram_id:
        stars_markup = {
            "inline_keyboard": [[
                {"text": f"{'⭐' * i}", "callback_data": f"review_rate_{booking.id}_{i}"}
                for i in range(1, 6)
            ]]
        }
        await send_telegram_message(
            customer.telegram_id,
            review_prompt_message(
                lang=customer.language,
                business_name=business.name if business else "—",
                service_name=names.get(customer.language, names["uz"]),
                booking_id=booking.id,
            ),
            reply_markup=stars_markup,
        )

    return booking


@router.patch("/bookings/{booking_id}/cancel", response_model=BookingOut)
async def cancel_booking(
    booking_id: int,
    body: CancelRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone

    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404)

    if booking.status not in ("pending", "confirmed"):
        raise HTTPException(status_code=409, detail="Booking is not active")

    # Determine who is cancelling
    business = await db.get(Business, booking.business_id)
    customer = await db.get(Customer, booking.customer_id) if booking.customer_id else None
    is_owner = business and business.owner_id == user.id
    is_customer = (
        customer
        and customer.telegram_id is not None
        and customer.telegram_id == user.telegram_id
    )

    if not is_owner and not is_customer and user.role != "super_admin":
        raise HTTPException(status_code=403)

    booking.status = "cancelled_by_business" if (is_owner or user.role == "super_admin") and not is_customer else "cancelled_by_customer"
    booking.cancellation_reason = body.reason
    booking.cancelled_at = datetime.now(timezone.utc)
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    # Notify the other party
    if booking.status == "cancelled_by_business" and customer and customer.telegram_id:
        await send_telegram_message(
            customer.telegram_id,
            booking_cancelled_message(
                lang=customer.language,
                business_name=business.name if business else "—",
                date_str=str(booking.booking_date),
                time_str=booking.start_time.strftime("%H:%M"),
            ),
        )
    elif booking.status == "cancelled_by_customer":
        owner = None
        if business and business.owner_id:
            owner = (
                await db.execute(select(User).where(User.id == business.owner_id))
            ).scalar_one_or_none()
        if owner and owner.telegram_id:
            await send_telegram_message(
                owner.telegram_id,
                booking_cancelled_message(
                    lang=owner.language,
                    business_name=booking.customer_name,
                    date_str=str(booking.booking_date),
                    time_str=booking.start_time.strftime("%H:%M"),
                ),
            )

    return booking


# ── Customer: own bookings ────────────────────────────────────────────────────

@router.get("/customers/{telegram_id}/bookings", response_model=None)
async def get_customer_bookings(
    telegram_id: int,
    upcoming_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # A customer may only read their own bookings (their JWT telegram_id must
    # match the path). Super-admin may read anyone's.
    if user.telegram_id != telegram_id and user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    from datetime import date as date_type
    customer = (
        await db.execute(select(Customer).where(Customer.telegram_id == telegram_id))
    ).scalar_one_or_none()
    if not customer:
        return []

    filters = [Booking.customer_id == customer.id]
    if upcoming_only:
        filters.append(Booking.booking_date >= date_type.today())
        filters.append(Booking.status.in_(["pending", "confirmed"]))

    order = (
        (Booking.booking_date.asc(), Booking.start_time.asc())
        if upcoming_only
        else (Booking.booking_date.desc(), Booking.start_time.desc())
    )
    # Join business + service so the customer's bookings list can show WHICH
    # business and service each one is for (no N+1 in the bot).
    rows = await db.execute(
        select(Booking, Business.name, Service.name_uz, Service.name_ru, Service.name_en)
        .join(Business, Business.id == Booking.business_id, isouter=True)
        .join(Service, Service.id == Booking.service_id, isouter=True)
        .where(and_(*filters))
        .order_by(*order)
        .limit(limit)
    )
    out: list[dict] = []
    for b, biz_name, svc_uz, svc_ru, svc_en in rows.all():
        out.append({
            "id": b.id,
            "business_id": b.business_id,
            "service_id": b.service_id,
            "staff_id": b.staff_id,
            "customer_id": b.customer_id,
            "customer_name": b.customer_name,
            "customer_phone": b.customer_phone,
            "booking_date": b.booking_date.isoformat() if b.booking_date else None,
            "start_time": b.start_time.isoformat() if b.start_time else None,
            "end_time": b.end_time.isoformat() if b.end_time else None,
            "status": b.status,
            "notes": b.notes,
            "was_auto_assigned": b.was_auto_assigned,
            "business_name": biz_name,
            "service_name_uz": svc_uz,
            "service_name_ru": svc_ru,
            "service_name_en": svc_en,
        })
    return out
