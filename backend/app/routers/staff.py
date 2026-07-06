import re
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_business_owner, get_current_staff, get_current_user
from app.models.booking import Booking
from app.models.business import Business
from app.models.service import Service
from app.models.staff import Staff, StaffInvite, StaffService
from app.models.user import User
from app.timeutils import now_local

router = APIRouter(prefix="/businesses/{business_id}/staff", tags=["staff"])
invite_router = APIRouter(tags=["staff"])

_UZ_PHONE_RE = re.compile(r"^\+998\d{9}$")


def _normalize_phone(raw: str | None) -> str | None:
    """Canonical +998XXXXXXXXX, or None if it can't be an Uzbek number. Same rule
    the bot and booking endpoints use, so a Telegram-shared contact matches the
    phone the owner typed regardless of spaces/dashes/leading country code."""
    digits = re.sub(r"[^\d]", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        candidate = "+" + digits
        return candidate if _UZ_PHONE_RE.match(candidate) else None
    return None


# ── Schemas ──────────────────────────────────────────────────────────────────

class StaffCreate(BaseModel):
    name: str
    phone: str | None = None
    bio: str | None = None
    role: str = "staff"
    can_set_own_hours: bool = False
    service_ids: list[int] = []


class StaffUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    bio: str | None = None
    role: str | None = None
    can_set_own_hours: bool | None = None
    is_active: bool | None = None


class StaffOut(BaseModel):
    id: int
    business_id: int
    name: str
    phone: str | None
    bio: str | None
    role: str
    is_active: bool
    can_set_own_hours: bool
    is_owner: bool = False
    user_id: int | None
    service_ids: list[int] = []

    model_config = {"from_attributes": True}


class SelfProviderCreate(BaseModel):
    name: str | None = None  # defaults to the owner's account name
    phone: str | None = None
    service_ids: list[int] = []


class InviteOut(BaseModel):
    token: str
    invite_url: str
    expires_at: datetime


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_owned_business(business_id: int, user: User, db: AsyncSession) -> Business:
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    if business.owner_id != user.id and user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return business


async def _staff_with_services(staff: Staff, db: AsyncSession) -> StaffOut:
    result = await db.execute(select(StaffService).where(StaffService.staff_id == staff.id))
    service_ids = [ss.service_id for ss in result.scalars().all()]
    data = StaffOut.model_validate(staff)
    data.service_ids = service_ids
    return data


async def _staff_list_with_services(staff_list, db: AsyncSession) -> list[StaffOut]:
    """Batch version of _staff_with_services: ONE query for every staff member's
    service links instead of one query per staff (avoids an N+1 on the list
    endpoints — a 20-provider shop went from 21 queries to 2)."""
    ids = [s.id for s in staff_list]
    by_staff: dict[int, list[int]] = {sid: [] for sid in ids}
    if ids:
        rows = await db.execute(
            select(StaffService.staff_id, StaffService.service_id).where(
                StaffService.staff_id.in_(ids)
            )
        )
        for staff_id, service_id in rows.all():
            by_staff.setdefault(staff_id, []).append(service_id)
    out = []
    for s in staff_list:
        data = StaffOut.model_validate(s)
        data.service_ids = by_staff.get(s.id, [])
        out.append(data)
    return out


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[StaffOut])
async def list_staff(
    business_id: int,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_business(business_id, user, db)
    result = await db.execute(select(Staff).where(Staff.business_id == business_id))
    staff_list = result.scalars().all()
    return await _staff_list_with_services(staff_list, db)


@router.post("", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
async def add_staff(
    business_id: int,
    body: StaffCreate,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_business(business_id, user, db)

    staff = Staff(
        business_id=business_id,
        name=body.name,
        phone=body.phone,
        bio=body.bio,
        role=body.role,
        can_set_own_hours=body.can_set_own_hours,
    )
    db.add(staff)
    await db.flush()

    for service_id in set(body.service_ids):
        svc = await db.get(Service, service_id)
        if svc and svc.business_id == business_id:
            db.add(StaffService(staff_id=staff.id, service_id=service_id))

    await db.commit()
    await db.refresh(staff)
    return await _staff_with_services(staff, db)


@router.post("/me", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
async def add_self_as_provider(
    business_id: int,
    body: SelfProviderCreate,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    """Create a bookable provider profile for the owner themselves — auto-linked
    to their account (no invite needed), so they can take appointments with
    their own schedule. One per business; separate from the business profile."""
    await _get_owned_business(business_id, user, db)

    existing = await db.execute(
        select(Staff).where(and_(Staff.business_id == business_id, Staff.is_owner == True))
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Owner provider already exists")

    staff = Staff(
        business_id=business_id,
        user_id=user.id,
        is_owner=True,
        name=(body.name or user.name or "Owner").strip(),
        phone=body.phone,
        role="manager",
        can_set_own_hours=True,
    )
    db.add(staff)
    await db.flush()

    for service_id in set(body.service_ids):
        svc = await db.get(Service, service_id)
        if svc and svc.business_id == business_id:
            db.add(StaffService(staff_id=staff.id, service_id=service_id))

    await db.commit()
    await db.refresh(staff)
    return await _staff_with_services(staff, db)


@router.patch("/{staff_id}", response_model=StaffOut)
async def update_staff(
    business_id: int,
    staff_id: int,
    body: StaffUpdate,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_business(business_id, user, db)
    staff = await db.get(Staff, staff_id)
    if not staff or staff.business_id != business_id:
        raise HTTPException(status_code=404, detail="Staff not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(staff, field, value)

    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return await _staff_with_services(staff, db)


@router.put("/{staff_id}/services", response_model=StaffOut)
async def set_staff_services(
    business_id: int,
    staff_id: int,
    service_ids: list[int],
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    """Replace the full set of services assigned to a staff member."""
    await _get_owned_business(business_id, user, db)
    staff = await db.get(Staff, staff_id)
    if not staff or staff.business_id != business_id:
        raise HTTPException(status_code=404, detail="Staff not found")

    # Diff the assignment set instead of blanket delete-then-reinsert. A blanket
    # rewrite trips the uq_staff_services_staff_service unique constraint, because
    # SQLAlchemy flushes INSERTs before DELETEs — so re-adding an already-assigned
    # service collides with its not-yet-deleted row and 500s. Diffing also avoids
    # needless row churn.
    requested = set(service_ids)
    existing_rows = (
        await db.execute(select(StaffService).where(StaffService.staff_id == staff_id))
    ).scalars().all()
    current = {ss.service_id for ss in existing_rows}

    # Drop assignments that are no longer wanted.
    for ss in existing_rows:
        if ss.service_id not in requested:
            await db.delete(ss)

    # Add only genuinely-new services that belong to this business.
    for sid in requested - current:
        svc = await db.get(Service, sid)
        if svc and svc.business_id == business_id:
            db.add(StaffService(staff_id=staff_id, service_id=sid))

    await db.commit()
    await db.refresh(staff)
    return await _staff_with_services(staff, db)


@router.delete("/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_staff(
    business_id: int,
    staff_id: int,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    """Permanently remove a staff record. Two guards protect real data:
      1. Must be inactive first — deactivate ('stop') is a distinct, reversible
         step; delete is the final one, so it must be an explicit second action.
      2. No active bookings — refuse if any pending/confirmed booking still
         references this staff. Old bookings (completed / cancelled / no_show)
         are detached (staff_id → NULL) so booking history is preserved.

    Cascades handled automatically by the ORM (delete-orphan) for
    staff_services / working_hours / blocked_times; invites are cleared here."""
    await _get_owned_business(business_id, user, db)
    staff = await db.get(Staff, staff_id)
    if not staff or staff.business_id != business_id:
        raise HTTPException(status_code=404, detail="Staff not found")
    if staff.is_active:
        raise HTTPException(
            status_code=400,
            detail="Stop this staff first, then delete.",
        )

    active_booking = (
        await db.execute(
            select(Booking.id)
            .where(
                and_(
                    Booking.staff_id == staff_id,
                    Booking.status.in_(("pending", "confirmed")),
                )
            )
            .limit(1)
        )
    ).first()
    if active_booking is not None:
        raise HTTPException(
            status_code=400,
            detail="This staff has upcoming bookings. Cancel or complete them first.",
        )

    # Detach historical bookings so we preserve the record instead of failing on
    # the FK. staff_id is nullable on bookings by design.
    await db.execute(
        update(Booking).where(Booking.staff_id == staff_id).values(staff_id=None)
    )
    # Clear invites (no cascade defined on this relationship).
    invites = (
        await db.execute(select(StaffInvite).where(StaffInvite.staff_id == staff_id))
    ).scalars().all()
    for inv in invites:
        await db.delete(inv)

    await db.delete(staff)
    await db.commit()
    return None


@router.post("/{staff_id}/invite", response_model=InviteOut)
async def create_invite(
    business_id: int,
    staff_id: int,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    """Generate an invite link for a staff member to join via Telegram."""
    await _get_owned_business(business_id, user, db)
    staff = await db.get(Staff, staff_id)
    if not staff or staff.business_id != business_id:
        raise HTTPException(status_code=404, detail="Staff not found")
    if staff.is_owner:
        raise HTTPException(status_code=400, detail="The owner cannot be invited as staff")
    if staff.user_id is not None:
        raise HTTPException(status_code=409, detail="This staff member is already linked to an account")

    # One live invite per staff: invalidate any earlier unused invites so a stale
    # forwarded link can't still be redeemed after a fresh one is issued.
    await db.execute(
        update(StaffInvite)
        .where(and_(StaffInvite.staff_id == staff_id, StaffInvite.is_active == True))  # noqa: E712
        .values(is_active=False)
    )

    token = secrets.token_urlsafe(32)
    # Short window (48h) — an invite is meant to be tapped promptly; a long-lived
    # link is just a bigger forwarding target.
    expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
    invite = StaffInvite(
        business_id=business_id,
        staff_id=staff_id,
        created_by=user.id,
        token=token,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.commit()

    from app.config import settings

    # t.me deep links require the bot USERNAME. (Never derive this from the bot
    # token — that link is dead and leaks the token's numeric prefix.)
    if not settings.telegram_bot_username:
        raise HTTPException(status_code=500, detail="TELEGRAM_BOT_USERNAME is not configured")
    invite_url = f"https://t.me/{settings.telegram_bot_username}?start=join_{token}"

    return InviteOut(token=token, invite_url=invite_url, expires_at=expires_at)


class JoinRequest(BaseModel):
    # The phone the joiner shared via Telegram's "share contact" button. Verified
    # against the staff record's phone so a forwarded link can't be redeemed by
    # the wrong person. Optional for backward compatibility.
    phone: str | None = None


@invite_router.post("/staff/join/{token}")
async def join_via_invite(
    token: str,
    body: JoinRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Called when a user taps the invite link in Telegram."""
    result = await db.execute(
        select(StaffInvite).where(
            and_(
                StaffInvite.token == token,
                StaffInvite.is_active == True,
                StaffInvite.used_at.is_(None),
            )
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found or expired")
    expires_at = invite.expires_at
    if expires_at.tzinfo is None:  # some drivers return naive for TIMESTAMPTZ — normalize
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invite expired")

    staff = await db.get(Staff, invite.staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff record not found")
    if staff.is_owner:
        raise HTTPException(status_code=400, detail="The owner cannot be invited as staff")
    # Refuse to hand an already-claimed staff slot to a second person — a forwarded
    # link must never be able to take over an active staff member's record (and
    # their customers' contact details).
    if staff.user_id is not None:
        raise HTTPException(status_code=409, detail="This staff member is already linked to an account")

    # Verify the joiner is the intended person. The owner sets the staff member's
    # phone when creating the record; the bot has the joiner share their verified
    # Telegram phone. If a phone is on file, the shared number MUST match it — this
    # is what stops a forwarded link from being redeemed by the wrong person. If
    # the owner left the phone blank, capture the shared number onto the record
    # instead of failing (so onboarding isn't blocked).
    shared_phone = _normalize_phone(body.phone) if (body and body.phone) else None
    staff_phone = _normalize_phone(staff.phone)
    if staff_phone:
        if shared_phone != staff_phone:
            raise HTTPException(
                status_code=403,
                detail="This invite is for a different phone number",
            )
    elif shared_phone:
        staff.phone = shared_phone

    # Link the user to this staff record
    staff.user_id = user.id
    invite.used_at = datetime.now(timezone.utc)
    invite.is_active = False

    # Upgrade user role
    if user.role == "customer":
        user.role = "staff"
        db.add(user)

    db.add(staff)
    db.add(invite)
    await db.commit()

    return {"ok": True, "business_id": invite.business_id, "staff_id": staff.id}


@invite_router.get("/staff/me", response_model=list[StaffOut])
async def get_my_staff_profiles(
    user: User = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    """Returns all staff records linked to the authenticated user."""
    result = await db.execute(select(Staff).where(Staff.user_id == user.id))
    staff_list = result.scalars().all()
    return await _staff_list_with_services(staff_list, db)


@invite_router.get("/staff/me/bookings", response_model=list)
async def get_my_bookings(
    booking_date: date | None = Query(None),
    user: User = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    """Returns bookings for the current staff member."""
    staff_result = await db.execute(select(Staff).where(Staff.user_id == user.id))
    staff_list = staff_result.scalars().all()
    if not staff_list:
        return []

    staff_ids = [s.id for s in staff_list]
    filters = [Booking.staff_id.in_(staff_ids), Booking.status.in_(["pending", "confirmed"])]
    if booking_date:
        filters.append(Booking.booking_date == booking_date)
    else:
        filters.append(Booking.booking_date >= now_local().date())

    result = await db.execute(
        select(Booking).where(and_(*filters)).order_by(Booking.booking_date, Booking.start_time)
    )
    bookings = result.scalars().all()
    return [
        {
            "id": b.id, "booking_date": str(b.booking_date),
            "start_time": str(b.start_time)[:5], "end_time": str(b.end_time)[:5],
            "status": b.status, "customer_name": b.customer_name,
            "customer_phone": b.customer_phone, "notes": b.notes,
            "service_id": b.service_id, "staff_id": b.staff_id,
        }
        for b in bookings
    ]
