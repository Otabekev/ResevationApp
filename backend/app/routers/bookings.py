from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_business_owner, get_current_user, require_bot_secret
from app.models.booking import Booking, Customer
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
    send_telegram_message,
)

router = APIRouter(tags=["bookings"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class BookingCreatePublic(BaseModel):
    """Used by Telegram bot / Mini App customers."""
    business_id: int
    service_id: int
    staff_id: int | None = None
    booking_date: date
    start_time: time
    customer_name: str
    customer_phone: str
    notes: str | None = None
    telegram_id: int  # passed by the bot


class BookingCreateManual(BaseModel):
    """Used by business owner to manually create a booking."""
    service_id: int
    staff_id: int | None = None
    booking_date: date
    start_time: time
    customer_name: str
    customer_phone: str
    notes: str | None = None


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


class CancelRequest(BaseModel):
    reason: str | None = None


class StatusUpdateRequest(BaseModel):
    status: str  # confirmed | completed | no_show | cancelled_by_business


# ── Public booking (Telegram bot) ────────────────────────────────────────────

@router.post("/bookings/public", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def create_public_booking(
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
        )
        db.add(customer)
        await db.flush()
    else:
        # Update name/phone in case they changed
        customer.name = body.customer_name
        customer.phone = body.customer_phone

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
        )
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))

    await db.commit()
    await db.refresh(booking)

    # Send confirmation to customer
    business = await db.get(Business, booking.business_id)
    service = await db.get(Service, booking.service_id)
    staff = await db.get(Staff, booking.staff_id) if booking.staff_id else None

    lang = customer.language
    svc_name = getattr(service, f"name_{lang}", service.name_uz)
    staff_name = staff.name if staff else "—"

    await send_telegram_message(
        customer.telegram_id,
        booking_confirmed_message(
            lang=lang,
            business_name=business.name,
            service_name=svc_name,
            staff_name=staff_name,
            date_str=str(booking.booking_date),
            time_str=booking.start_time.strftime("%H:%M"),
        ),
    )

    # Notify business owner / staff
    if business and business.owner_id:
        owner_result = await db.execute(
            select(User).where(User.id == business.owner_id)
        )
        owner = owner_result.scalar_one_or_none()
        if owner and owner.telegram_id:
            await send_telegram_message(
                owner.telegram_id,
                new_booking_alert_message(
                    lang=owner.language,
                    customer_name=customer.name,
                    service_name=svc_name,
                    date_str=str(booking.booking_date),
                    time_str=booking.start_time.strftime("%H:%M"),
                ),
            )

    return booking


# ── Business owner booking management ────────────────────────────────────────

@router.get("/businesses/{business_id}/bookings", response_model=list[BookingOut])
async def list_bookings(
    business_id: int,
    booking_date: date | None = Query(None),
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
    return result.scalars().all()


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

    # Use a placeholder customer record for manual bookings
    customer = Customer(
        telegram_id=0,  # no telegram account
        name=body.customer_name,
        phone=body.customer_phone,
    )
    db.add(customer)
    await db.flush()

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

    booking.status = body.status
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    # Send review prompt to customer when booking is completed
    if body.status == "completed" and booking.customer_id:
        customer = await db.get(Customer, booking.customer_id)
        if customer and customer.telegram_id:
            service = await db.get(Service, booking.service_id)
            biz = await db.get(Business, booking.business_id)
            svc_name = getattr(service, f"name_{customer.language}", service.name_uz) if service else "—"
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
                    business_name=biz.name if biz else "—",
                    service_name=svc_name,
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

    # Determine who is cancelling
    business = await db.get(Business, booking.business_id)
    customer = await db.get(Customer, booking.customer_id) if booking.customer_id else None
    is_owner = business and business.owner_id == user.id
    is_customer = customer and hasattr(user, "telegram_id") and customer.telegram_id == user.telegram_id

    if not is_owner and not is_customer and user.role != "super_admin":
        raise HTTPException(status_code=403)

    booking.status = "cancelled_by_business" if is_owner else "cancelled_by_customer"
    booking.cancellation_reason = body.reason
    booking.cancelled_at = datetime.now(timezone.utc)
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    # Notify the other party
    if is_owner and customer and customer.telegram_id:
        service = await db.get(Service, booking.service_id)
        await send_telegram_message(
            customer.telegram_id,
            booking_cancelled_message(
                lang=customer.language,
                business_name=business.name,
                date_str=str(booking.booking_date),
                time_str=booking.start_time.strftime("%H:%M"),
            ),
        )

    return booking


# ── Customer: own bookings ────────────────────────────────────────────────────

@router.get("/customers/{telegram_id}/bookings", response_model=list[BookingOut])
async def get_customer_bookings(
    telegram_id: int,
    upcoming_only: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # A customer may only read their own bookings (their JWT telegram_id must
    # match the path). Super-admin may read anyone's.
    if user.telegram_id != telegram_id and user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    from datetime import date as date_type
    customer_result = await db.execute(select(Customer).where(Customer.telegram_id == telegram_id))
    customer = customer_result.scalar_one_or_none()
    if not customer:
        return []

    filters = [Booking.customer_id == customer.id]
    if upcoming_only:
        filters.append(Booking.booking_date >= date_type.today())
        filters.append(Booking.status.in_(["pending", "confirmed"]))

    result = await db.execute(
        select(Booking).where(and_(*filters)).order_by(Booking.booking_date, Booking.start_time)
    )
    return result.scalars().all()
