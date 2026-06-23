import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_business_owner, get_current_staff, get_current_user
from app.models.booking import Booking
from app.models.business import Business
from app.models.service import Service
from app.models.staff import Staff, StaffInvite, StaffService
from app.models.user import User

router = APIRouter(prefix="/businesses/{business_id}/staff", tags=["staff"])
invite_router = APIRouter(tags=["staff"])


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
    return [await _staff_with_services(s, db) for s in staff_list]


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

    for service_id in body.service_ids:
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

    for service_id in body.service_ids:
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

    # Remove old assignments
    existing = await db.execute(select(StaffService).where(StaffService.staff_id == staff_id))
    for ss in existing.scalars().all():
        await db.delete(ss)

    # Add new
    for sid in service_ids:
        svc = await db.get(Service, sid)
        if svc and svc.business_id == business_id:
            db.add(StaffService(staff_id=staff_id, service_id=sid))

    await db.commit()
    await db.refresh(staff)
    return await _staff_with_services(staff, db)


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

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
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


@invite_router.post("/staff/join/{token}")
async def join_via_invite(
    token: str,
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
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invite expired")

    staff = await db.get(Staff, invite.staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff record not found")

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
    return [await _staff_with_services(s, db) for s in staff_list]


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
        filters.append(Booking.booking_date >= date.today())

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
