import re
from datetime import date, time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import (
    authorize_business_access,
    authorize_business_or_provider,
    get_current_business_owner,
    get_current_dashboard_user,
    get_current_user,
    is_business_manager,
    require_bot_secret,
)
from app.limiter import limiter
from app.models.booking import Booking, Customer, booking_services
from app.models.business import Business
from app.models.service import Service
from app.models.staff import Staff
from app.models.user import User
from app.services.booking_engine import create_booking
from app.timeutils import now_local, to_local
from app.services.notification_service import (
    booking_confirmed_message,
    booking_cancelled_message,
    customer_cancelled_alert_message,
    new_booking_alert_message,
    review_prompt_message,
    send_telegram_location,
    send_telegram_message,
    treatment_plan_message,
)

router = APIRouter(tags=["bookings"])


# ── Schemas ──────────────────────────────────────────────────────────────────

_UZ_PHONE_RE = re.compile(r"^\+998\d{9}$")


def _normalize_uz_phone(raw: str) -> str | None:
    """Normalize an Uzbek number to canonical +998XXXXXXXXX, or None if it can't
    be one. Accepts '+998901234567', '998901234567', '901234567', with spaces or
    dashes — the same rule the bot uses — so a manual booking can't store junk
    like 'asdf' the owner can never call back."""
    digits = re.sub(r"[^\d]", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        candidate = "+" + digits
        return candidate if _UZ_PHONE_RE.match(candidate) else None
    return None


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

    @field_validator("customer_phone")
    @classmethod
    def _valid_phone(cls, v: str) -> str:
        # Normalize server-side too (the bot already does, but a Mini App or any
        # future caller must not be able to store junk the owner can't call back).
        normalized = _normalize_uz_phone(v)
        if normalized is None:
            raise ValueError("Enter a valid phone, e.g. +998 90 123 45 67")
        return normalized

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

    @field_validator("customer_phone")
    @classmethod
    def _valid_phone(cls, v: str) -> str:
        normalized = _normalize_uz_phone(v)
        if normalized is None:
            raise ValueError("Enter a valid phone, e.g. +998 90 123 45 67")
        return normalized

    _fill_service_ids = model_validator(mode="after")(_normalize_service_ids)


class TreatmentPlanSlot(BaseModel):
    booking_date: date
    start_time: time


class TreatmentPlanCreate(BaseModel):
    """Reserve several days for one patient in a single action (e.g. a dentist's
    multi-day treatment scheduled by the secretary after a checkup)."""
    service_id: int
    service_ids: list[int] | None = None
    staff_id: int | None = None
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_phone: str = Field(..., min_length=3, max_length=20)
    notes: str | None = Field(None, max_length=1000)
    slots: list[TreatmentPlanSlot] = Field(..., min_length=1, max_length=60)

    @field_validator("customer_phone")
    @classmethod
    def _valid_phone(cls, v: str) -> str:
        normalized = _normalize_uz_phone(v)
        if normalized is None:
            raise ValueError("Enter a valid phone, e.g. +998 90 123 45 67")
        return normalized

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

async def _booking_alert_jobs(
    db: AsyncSession, booking: Booking, business: Business, svc_name_for: dict[str, str]
) -> list[dict]:
    """Resolve the owner + assigned-staff 'new booking' alert recipients into send
    jobs. Pure DB reads — the actual Telegram sends happen later in the background
    task so no pooled connection is held across the external HTTP."""
    jobs: list[dict] = []
    notified: set[int] = set()

    if business and business.owner_id:
        owner = (
            await db.execute(select(User).where(User.id == business.owner_id))
        ).scalar_one_or_none()
        if owner and owner.telegram_id:
            notified.add(owner.telegram_id)
            jobs.append({
                "kind": "message",
                "chat_id": owner.telegram_id,
                "text": new_booking_alert_message(
                    lang=owner.language,
                    customer_name=booking.customer_name,
                    service_name=svc_name_for.get(owner.language, svc_name_for["uz"]),
                    date_str=str(booking.booking_date),
                    time_str=booking.start_time.strftime("%H:%M"),
                ),
            })

    if booking.staff_id:
        staff = await db.get(Staff, booking.staff_id)
        if staff and staff.user_id:
            staff_user = (
                await db.execute(select(User).where(User.id == staff.user_id))
            ).scalar_one_or_none()
            if staff_user and staff_user.telegram_id and staff_user.telegram_id not in notified:
                jobs.append({
                    "kind": "message",
                    "chat_id": staff_user.telegram_id,
                    "text": new_booking_alert_message(
                        lang=staff_user.language,
                        customer_name=booking.customer_name,
                        service_name=svc_name_for.get(staff_user.language, svc_name_for["uz"]),
                        date_str=str(booking.booking_date),
                        time_str=booking.start_time.strftime("%H:%M"),
                    ),
                })
    return jobs


async def _deliver_notifications(jobs: list[dict]) -> None:
    """Best-effort Telegram sends, run as a background task AFTER the response is
    returned — so no request-scoped DB connection is held during external HTTP.
    send_telegram_* already swallow + log their own errors; the guard here just
    keeps one malformed job from aborting the rest."""
    for j in jobs:
        try:
            if j["kind"] == "message":
                await send_telegram_message(j["chat_id"], j["text"])
            elif j["kind"] == "location":
                await send_telegram_location(j["chat_id"], j["lat"], j["lng"])
        except Exception:
            continue


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
    background: BackgroundTasks,
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
    # Refuse bookings for a business the platform has turned off (suspended for
    # non-payment / blocked for abuse) — the public listing hides these, but a
    # cached deep-link or stale button could still reach this endpoint.
    if _biz.status in ("suspended", "blocked"):
        raise HTTPException(status_code=409, detail="This business is not accepting bookings")
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

    # Resolve every notification's data WHILE the request session is open, then
    # hand the actual Telegram sends to a background task. The response returns —
    # and the pooled DB connection is freed — before any slow external HTTP, so a
    # Telegram latency spike during a booking burst can't pin connections and
    # starve the pool (and the customer's booking never fails on a slow send).
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
    total_price = sum(float(s.price) for s in ordered_services if s.price is not None)

    jobs: list[dict] = [{
        "kind": "message",
        "chat_id": customer.telegram_id,
        "text": booking_confirmed_message(
            lang=lang,
            business_name=business.name,
            service_name=names.get(lang, names["uz"]),
            staff_name=staff_name,
            date_str=str(booking.booking_date),
            time_str=booking.start_time.strftime("%H:%M"),
            address=business.address,
            phone=business.phone,
            price=total_price or None,
        ),
    }]
    # The business map pin, so the customer can find the place (only with coords).
    if business.latitude is not None and business.longitude is not None:
        jobs.append({
            "kind": "location", "chat_id": customer.telegram_id,
            "lat": business.latitude, "lng": business.longitude,
        })
    # Owner + assigned-staff "new booking" alerts.
    jobs.extend(await _booking_alert_jobs(db, booking, business, names))

    background.add_task(_deliver_notifications, jobs)
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
    user: User = Depends(get_current_dashboard_user),
    db: AsyncSession = Depends(get_db),
):
    # Owner OR desk-manager sees the whole business; a provider (doctor) sees only
    # their own appointments, row-scoped to their staff_id.
    allowed = await authorize_business_or_provider(business_id, user, db)

    filters = [Booking.business_id == business_id]
    if allowed is not None:
        filters.append(Booking.staff_id.in_(allowed))
    if booking_date:
        filters.append(Booking.booking_date == booking_date)
    if date_from:
        filters.append(Booking.booking_date >= date_from)
    if date_to:
        filters.append(Booking.booking_date <= date_to)
    if status_filter:
        filters.append(Booking.status == status_filter)
    if staff_id:
        if allowed is not None and staff_id not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")
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


async def _resolve_manual_customer(db: AsyncSession, name: str, phone: str) -> Customer:
    """Resolve the customer for a staff-created booking. Prefers a Telegram-linked
    account matched by phone (so the booking reaches them with reminders), then a
    walk-in match by phone AND name, else creates a fresh walk-in. Phones are
    normalized identically on every path, so the match is reliable."""
    customer = (
        await db.execute(
            select(Customer)
            .where(and_(Customer.telegram_id.is_not(None), Customer.phone == phone))
            .order_by(Customer.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if customer is None:
        customer = (
            await db.execute(
                select(Customer)
                .where(and_(Customer.telegram_id.is_(None), Customer.phone == phone, Customer.name == name))
                .limit(1)
            )
        ).scalar_one_or_none()
    if customer is None:
        customer = Customer(telegram_id=None, name=name, phone=phone)
        db.add(customer)
        await db.flush()
    return customer


async def _authorize_booking_write(business_id: int, body_staff_id, user: User, db: AsyncSession) -> Business:
    """Write access for manual booking / treatment plan. Owner/manager may book any
    staff (returns the Business for status + allow_multi_service checks). A provider
    may ONLY create a booking assigned to their OWN staff record — a null or foreign
    staff_id is rejected 403, so the engine can never auto-assign it to another
    doctor (client-side forcing is not enough on its own)."""
    allowed = await authorize_business_or_provider(business_id, user, db)
    business = await db.get(Business, business_id)  # helper returns set|None; identity-map cached
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    if allowed is not None:  # provider — must target their own calendar
        if not body_staff_id or body_staff_id not in allowed:
            raise HTTPException(status_code=403, detail="A provider can only book onto their own calendar")
    return business


@router.post("/businesses/{business_id}/bookings", response_model=BookingOut, status_code=201)
async def create_manual_booking(
    business_id: int,
    body: BookingCreateManual,
    user: User = Depends(get_current_dashboard_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner or desk-manager manually creates a booking (walk-in, phone call)."""
    business = await _authorize_booking_write(business_id, body.staff_id, user, db)
    if business.status in ("suspended", "blocked"):
        raise HTTPException(status_code=409, detail="This business is not accepting bookings")

    # Links to the patient's Telegram account by phone when possible, so a manual
    # booking (e.g. a dentist's treatment day) reaches them with reminders.
    customer = await _resolve_manual_customer(db, body.customer_name, body.customer_phone)

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


@router.post("/businesses/{business_id}/bookings/plan")
async def create_treatment_plan(
    business_id: int,
    body: TreatmentPlanCreate,
    background: BackgroundTasks,
    user: User = Depends(get_current_dashboard_user),
    db: AsyncSession = Depends(get_db),
):
    """Reserve several days for one patient at once (dentist treatment plan). Each
    day is validated independently against availability; the response reports which
    were created and which couldn't be (e.g. that slot was taken), so the secretary
    can retry just the failures. The patient is linked by phone to their Telegram
    account when possible, so every reserved day sends them reminders."""
    business = await _authorize_booking_write(business_id, body.staff_id, user, db)
    if business.status in ("suspended", "blocked"):
        raise HTTPException(status_code=409, detail="This business is not accepting bookings")

    customer = await _resolve_manual_customer(db, body.customer_name, body.customer_phone)
    await db.commit()  # persist the customer so a per-day rollback below can't lose it
    customer = await db.get(Customer, customer.id)  # fresh, live reference after commit
    # Capture what the summary message needs NOW — the per-visit commits below expire
    # ORM objects, and we don't want a lazy reload after the loop.
    cust_tg = customer.telegram_id
    cust_lang = customer.language if customer.language in ("uz", "ru", "en") else "uz"
    biz_name = business.name
    _svc = await db.get(Service, body.service_id)
    plan_service_name = (getattr(_svc, f"name_{cust_lang}", None) or _svc.name_uz) if _svc else "—"

    service_ids = body.service_ids if business.allow_multi_service else [body.service_id]
    created, failed = [], []
    for slot in body.slots:
        label = {"booking_date": str(slot.booking_date), "start_time": str(slot.start_time)[:5]}
        try:
            booking = await create_booking(
                db,
                business_id=business_id,
                service_id=body.service_id,
                staff_id=body.staff_id,
                customer=customer,
                booking_date=slot.booking_date,
                start_time=slot.start_time,
                notes=body.notes,
                service_ids=service_ids,
            )
            await db.commit()
            created.append({**label, "booking_id": booking.id})
        except ValueError as e:
            await db.rollback()
            failed.append({**label, "reason": str(e)})
        except Exception:
            await db.rollback()
            failed.append({**label, "reason": "error"})

    # One up-front summary to the patient IF they've used the bot before (linked by
    # phone) AND at least one visit was reserved — otherwise they'd only learn the
    # dates from the per-visit reminders. Background send keeps the DB pool free.
    if cust_tg and created:
        visits = sorted(
            ((c["booking_date"], c["start_time"]) for c in created),
            key=lambda s: (s[0], s[1]),
        )
        pretty = [(date.fromisoformat(d).strftime("%d.%m.%Y"), tm) for d, tm in visits]
        background.add_task(
            send_telegram_message,
            cust_tg,
            treatment_plan_message(cust_lang, biz_name, plan_service_name, pretty),
        )

    return {"created": created, "failed": failed}


# Allowed booking-status transitions, keyed on the CURRENT status. Terminal states
# (completed / no_show / cancelled_* / rescheduled) accept no further change, so a
# finished booking can't be resurrected — which would re-fire customer messages and
# corrupt no-show/analytics counts. Cancellation to cancelled_by_customer goes
# through the dedicated /cancel endpoint, not here.
_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "completed", "no_show", "cancelled_by_business"},
    "confirmed": {"completed", "no_show", "cancelled_by_business"},
}


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
    is_manager = await is_business_manager(booking.business_id, user, db)

    if not is_owner and not is_assigned_staff and not is_manager and user.role != "super_admin":
        raise HTTPException(status_code=403)

    # Idempotent: re-applying the current status is a no-op and must NOT re-fire
    # the confirmation / review-prompt messages (owners double-tap on slow nets).
    if body.status == booking.status:
        return booking

    # State machine: only forward transitions from a non-terminal status.
    if body.status not in _STATUS_TRANSITIONS.get(booking.status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change booking from '{booking.status}' to '{body.status}'",
        )

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


@router.patch("/bookings/{booking_id}/cancel", response_model=None)
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
    is_manager = await is_business_manager(booking.business_id, user, db)
    # The provider this booking is assigned to may cancel their own appointment.
    assigned_staff = await db.get(Staff, booking.staff_id) if booking.staff_id else None
    is_assigned_provider = bool(
        assigned_staff
        and assigned_staff.user_id == user.id
        and assigned_staff.is_provider
        and assigned_staff.is_active
    )
    is_customer = (
        customer
        and customer.telegram_id is not None
        and customer.telegram_id == user.telegram_id
    )

    if not is_owner and not is_manager and not is_assigned_provider and not is_customer and user.role != "super_admin":
        raise HTTPException(status_code=403)

    # Owner/manager/admin/assigned-provider cancelling on the business side → cancelled_by_business.
    cancelled_by_business_side = (
        is_owner or is_manager or is_assigned_provider or user.role == "super_admin"
    ) and not is_customer
    booking.status = "cancelled_by_business" if cancelled_by_business_side else "cancelled_by_customer"
    booking.cancellation_reason = body.reason
    booking.cancelled_at = datetime.now(timezone.utc)
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    # Notify the other party. customer_notified lets the owner's UI reassure them
    # the customer actually got the message — and stay honest for a walk-in who
    # has no Telegram (never notified).
    customer_notified = False
    if booking.status == "cancelled_by_business" and customer and customer.telegram_id:
        customer_notified = await send_telegram_message(
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
            # Flag a LATE cancel — one that lands inside the business's
            # cancellation window. We allow it (freeing the slot beats a silent
            # no-show), but the owner is told so they can try to rebook the slot.
            apt = to_local(booking.booking_date, booking.start_time)
            hours_until = (apt - now_local()).total_seconds() / 3600
            policy = business.cancellation_policy_hours if business else 0
            is_late = policy and hours_until < policy
            await send_telegram_message(
                owner.telegram_id,
                customer_cancelled_alert_message(
                    lang=owner.language,
                    customer_name=booking.customer_name,
                    date_str=str(booking.booking_date),
                    time_str=booking.start_time.strftime("%H:%M"),
                    late_policy_hours=policy if is_late else None,
                ),
            )

    out = BookingOut.model_validate(booking).model_dump(mode="json")
    out["customer_notified"] = bool(customer_notified)
    return out


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

    customer = (
        await db.execute(select(Customer).where(Customer.telegram_id == telegram_id))
    ).scalar_one_or_none()
    if not customer:
        return []

    filters = [Booking.customer_id == customer.id]
    if upcoming_only:
        # Local (Asia/Tashkent) today, not server-local (UTC) — otherwise for ~5h
        # every night a customer's "upcoming" list leaks yesterday's appointment.
        filters.append(Booking.booking_date >= now_local().date())
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
