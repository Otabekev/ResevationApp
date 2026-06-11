from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_business_owner, get_current_user
from app.models.business import Business
from app.models.schedule import BlockedTime, BreakTime, WorkingHours
from app.models.staff import Staff
from app.models.user import User

router = APIRouter(tags=["schedules"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class WorkingHoursEntry(BaseModel):
    day_of_week: int  # 0=Mon … 6=Sun
    start_time: time
    end_time: time
    is_day_off: bool = False

    @model_validator(mode="after")
    def _check_order(self):
        if not (0 <= self.day_of_week <= 6):
            raise ValueError("day_of_week must be 0–6")
        if not self.is_day_off and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class WorkingHoursSet(BaseModel):
    hours: list[WorkingHoursEntry] = Field(..., max_length=7)


class WorkingHoursOut(BaseModel):
    id: int
    day_of_week: int
    start_time: time
    end_time: time
    is_day_off: bool

    model_config = {"from_attributes": True}


class BreakCreate(BaseModel):
    day_of_week: int | None = Field(None, ge=0, le=6)
    start_time: time
    end_time: time
    label: str | None = Field(None, max_length=100)

    @model_validator(mode="after")
    def _check_order(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class BreakOut(BaseModel):
    id: int
    day_of_week: int | None
    start_time: time
    end_time: time
    label: str | None

    model_config = {"from_attributes": True}


class BlockedTimeCreate(BaseModel):
    blocked_date: date | None = None       # full-day block on this date
    start_datetime: datetime | None = None  # …or a partial-day range
    end_datetime: datetime | None = None
    full_day: bool = False
    reason: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def _check_shape(self):
        from app.timeutils import PLATFORM_TZ

        # Clients send local wall time ("2026-06-12T13:00"); store tz-aware.
        if self.start_datetime is not None and self.start_datetime.tzinfo is None:
            self.start_datetime = self.start_datetime.replace(tzinfo=PLATFORM_TZ)
        if self.end_datetime is not None and self.end_datetime.tzinfo is None:
            self.end_datetime = self.end_datetime.replace(tzinfo=PLATFORM_TZ)

        has_range = self.start_datetime is not None and self.end_datetime is not None
        if self.blocked_date is None and not has_range:
            raise ValueError("Provide blocked_date (full day) or start/end datetime range")
        if has_range and self.end_datetime <= self.start_datetime:
            raise ValueError("end_datetime must be after start_datetime")
        if self.blocked_date is not None and not has_range:
            self.full_day = True
        return self


class BlockedTimeOut(BaseModel):
    id: int
    blocked_date: date | None
    start_datetime: datetime | None
    end_datetime: datetime | None
    full_day: bool
    reason: str | None

    model_config = {"from_attributes": True}


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_owned_business(business_id: int, user: User, db: AsyncSession) -> Business:
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    if business.owner_id != user.id and user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return business


# ── Business working hours ────────────────────────────────────────────────────

@router.get("/businesses/{business_id}/working-hours", response_model=list[WorkingHoursOut])
async def get_business_hours(business_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WorkingHours).where(
            and_(WorkingHours.business_id == business_id, WorkingHours.staff_id.is_(None))
        ).order_by(WorkingHours.day_of_week)
    )
    return result.scalars().all()


@router.put("/businesses/{business_id}/working-hours", response_model=list[WorkingHoursOut])
async def set_business_hours(
    business_id: int,
    body: WorkingHoursSet,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_business(business_id, user, db)

    await db.execute(
        delete(WorkingHours).where(
            and_(WorkingHours.business_id == business_id, WorkingHours.staff_id.is_(None))
        )
    )
    rows = []
    for entry in body.hours:
        wh = WorkingHours(business_id=business_id, **entry.model_dump())
        db.add(wh)
        rows.append(wh)

    await db.commit()
    for r in rows:
        await db.refresh(r)
    return rows


# ── Staff working hours ───────────────────────────────────────────────────────

@router.get("/businesses/{business_id}/staff/{staff_id}/working-hours", response_model=list[WorkingHoursOut])
async def get_staff_hours(
    business_id: int,
    staff_id: int,
    db: AsyncSession = Depends(get_db),
):
    staff = await db.get(Staff, staff_id)
    if not staff or staff.business_id != business_id:
        raise HTTPException(status_code=404, detail="Staff not found")
    result = await db.execute(
        select(WorkingHours).where(WorkingHours.staff_id == staff_id).order_by(WorkingHours.day_of_week)
    )
    return result.scalars().all()


@router.put("/businesses/{business_id}/staff/{staff_id}/working-hours", response_model=list[WorkingHoursOut])
async def set_staff_hours(
    business_id: int,
    staff_id: int,
    body: WorkingHoursSet,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    staff = await db.get(Staff, staff_id)
    if not staff or staff.business_id != business_id:
        raise HTTPException(status_code=404, detail="Staff not found")

    business = await db.get(Business, business_id)
    is_owner = business and business.owner_id == user.id
    is_self = staff.user_id == user.id and staff.can_set_own_hours
    if not is_owner and not is_self and user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    await db.execute(delete(WorkingHours).where(WorkingHours.staff_id == staff_id))
    rows = []
    for entry in body.hours:
        wh = WorkingHours(staff_id=staff_id, **entry.model_dump())
        db.add(wh)
        rows.append(wh)

    await db.commit()
    for r in rows:
        await db.refresh(r)
    return rows


@router.delete("/businesses/{business_id}/staff/{staff_id}/working-hours", status_code=204)
async def clear_staff_hours(
    business_id: int,
    staff_id: int,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    """Remove staff-specific hours so the member falls back to business hours."""
    await _get_owned_business(business_id, user, db)
    staff = await db.get(Staff, staff_id)
    if not staff or staff.business_id != business_id:
        raise HTTPException(status_code=404, detail="Staff not found")
    await db.execute(delete(WorkingHours).where(WorkingHours.staff_id == staff_id))
    await db.commit()


# ── Breaks ────────────────────────────────────────────────────────────────────

@router.get("/businesses/{business_id}/breaks", response_model=list[BreakOut])
async def get_breaks(business_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BreakTime).where(
            and_(BreakTime.business_id == business_id, BreakTime.staff_id.is_(None))
        ).order_by(BreakTime.start_time)
    )
    return result.scalars().all()


@router.post("/businesses/{business_id}/breaks", response_model=BreakOut)
async def add_break(
    business_id: int,
    body: BreakCreate,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_business(business_id, user, db)
    brk = BreakTime(business_id=business_id, **body.model_dump())
    db.add(brk)
    await db.commit()
    await db.refresh(brk)
    return brk


@router.delete("/businesses/{business_id}/breaks/{break_id}", status_code=204)
async def delete_break(
    business_id: int,
    break_id: int,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_business(business_id, user, db)
    brk = await db.get(BreakTime, break_id)
    if not brk or brk.business_id != business_id:
        raise HTTPException(status_code=404)
    await db.delete(brk)
    await db.commit()


# ── Blocked times ─────────────────────────────────────────────────────────────

@router.get("/businesses/{business_id}/blocked-times", response_model=list[BlockedTimeOut])
async def list_blocked_times(
    business_id: int,
    include_past: bool = False,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_business(business_id, user, db)
    from app.timeutils import now_local, to_local

    filters = [BlockedTime.business_id == business_id, BlockedTime.staff_id.is_(None)]
    if not include_past:
        today = now_local().date()
        filters.append(
            (BlockedTime.blocked_date >= today)
            | (BlockedTime.end_datetime >= to_local(today, time.min))
        )
    result = await db.execute(
        select(BlockedTime).where(and_(*filters)).order_by(
            BlockedTime.blocked_date, BlockedTime.start_datetime
        )
    )
    return result.scalars().all()


@router.post("/businesses/{business_id}/blocked-times", response_model=BlockedTimeOut)
async def add_blocked_time(
    business_id: int,
    body: BlockedTimeCreate,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_business(business_id, user, db)

    bt = BlockedTime(
        business_id=business_id,
        blocked_date=body.blocked_date,
        start_datetime=body.start_datetime,
        end_datetime=body.end_datetime,
        full_day=body.full_day,
        reason=body.reason,
    )
    db.add(bt)
    await db.commit()
    await db.refresh(bt)
    return bt


@router.delete("/businesses/{business_id}/blocked-times/{blocked_id}", status_code=204)
async def delete_blocked_time(
    business_id: int,
    blocked_id: int,
    user: User = Depends(get_current_business_owner),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_business(business_id, user, db)
    bt = await db.get(BlockedTime, blocked_id)
    if not bt or bt.business_id != business_id:
        raise HTTPException(status_code=404)
    await db.delete(bt)
    await db.commit()
