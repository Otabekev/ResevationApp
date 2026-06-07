"""
Universal Smart Booking Engine
===============================
Core algorithm for calculating available time slots and creating bookings
with double-booking prevention via database row locking.

Algorithm overview
------------------
get_available_slots(business_id, service_id, date, staff_id=None):
    1. Load the service (duration, buffer_before, buffer_after)
    2. Resolve eligible staff
       - if staff_id given: verify they can perform the service
       - if not given: all staff assigned to this service
    3. For each eligible staff member:
       a. Get working hours for that day (staff override > business default)
       b. Skip if day is off
       c. Build free intervals from working window
       d. Subtract break_times for that day
       e. Subtract blocked_times for that date
       f. Subtract existing bookings (each blocks: start - buffer_before … end + buffer_after)
       g. Walk free intervals in slot_step_minutes increments
          A start time T is valid when:
            T >= interval.start + service.buffer_before
            T + service.duration + service.buffer_after <= interval.end
       h. Collect valid T values with the staff_id who can serve them
    4. Return sorted unique times (plus which staff are available at each time)

create_booking(...)
    Uses SELECT FOR UPDATE inside a transaction to lock the staff's booking rows
    for the target date, preventing race conditions.
"""

from datetime import date, datetime, time, timedelta
from typing import NamedTuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, Customer
from app.models.business import Business
from app.models.schedule import BlockedTime, BreakTime, WorkingHours
from app.models.service import Service
from app.models.staff import Staff, StaffService
from app.timeutils import now_local, to_local


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------

class Interval(NamedTuple):
    start: time
    end: time


class SlotOption(NamedTuple):
    start_time: time
    end_time: time
    available_staff_ids: list[int]  # staff who can serve at this time


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _from_minutes(m: int) -> time:
    m = max(0, min(m, 1439))
    return time(m // 60, m % 60)


def _subtract_interval(
    free: list[Interval], blocked_start: time, blocked_end: time
) -> list[Interval]:
    """Remove [blocked_start, blocked_end) from a list of free intervals."""
    bs = _to_minutes(blocked_start)
    be = _to_minutes(blocked_end)
    result: list[Interval] = []
    for iv in free:
        s = _to_minutes(iv.start)
        e = _to_minutes(iv.end)
        if be <= s or bs >= e:
            # No overlap
            result.append(iv)
        else:
            if bs > s:
                result.append(Interval(_from_minutes(s), _from_minutes(bs)))
            if be < e:
                result.append(Interval(_from_minutes(be), _from_minutes(e)))
    return result


# ---------------------------------------------------------------------------
# Schedule resolution
# ---------------------------------------------------------------------------

async def _get_working_window(
    db: AsyncSession,
    staff: Staff,
    target_date: date,
) -> Interval | None:
    """
    Returns the working window for a staff member on a given date.
    Staff-level schedule takes priority over business-level schedule.
    Returns None if the day is a day off or no schedule is defined.
    """
    dow = target_date.weekday()  # 0=Monday, 6=Sunday

    # Try staff-specific schedule first
    stmt = select(WorkingHours).where(
        and_(WorkingHours.staff_id == staff.id, WorkingHours.day_of_week == dow)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    # Fall back to business schedule
    if row is None:
        stmt = select(WorkingHours).where(
            and_(
                WorkingHours.business_id == staff.business_id,
                WorkingHours.staff_id.is_(None),
                WorkingHours.day_of_week == dow,
            )
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()

    if row is None or row.is_day_off:
        return None

    return Interval(row.start_time, row.end_time)


async def _get_breaks(
    db: AsyncSession,
    staff: Staff,
    target_date: date,
) -> list[Interval]:
    """Returns all break intervals for a staff member on a given date."""
    dow = target_date.weekday()
    stmt = select(BreakTime).where(
        and_(
            or_(BreakTime.staff_id == staff.id, BreakTime.business_id == staff.business_id),
            or_(BreakTime.day_of_week == dow, BreakTime.day_of_week.is_(None)),
        )
    )
    result = await db.execute(stmt)
    return [Interval(b.start_time, b.end_time) for b in result.scalars().all()]


async def _get_blocked_intervals(
    db: AsyncSession,
    staff: Staff,
    target_date: date,
) -> list[Interval]:
    """Returns all blocked time intervals for a staff member on a specific date."""
    stmt = select(BlockedTime).where(
        and_(
            or_(BlockedTime.staff_id == staff.id, BlockedTime.business_id == staff.business_id),
            or_(
                BlockedTime.blocked_date == target_date,
                and_(
                    BlockedTime.start_datetime.isnot(None),
                    BlockedTime.start_datetime <= datetime.combine(target_date, time(23, 59)),
                    BlockedTime.end_datetime >= datetime.combine(target_date, time(0, 0)),
                ),
            ),
        )
    )
    result = await db.execute(stmt)
    intervals: list[Interval] = []
    for bt in result.scalars().all():
        if bt.full_day or bt.blocked_date == target_date:
            intervals.append(Interval(time(0, 0), time(23, 59)))
        elif bt.start_datetime and bt.end_datetime:
            s = bt.start_datetime.time() if bt.start_datetime.date() == target_date else time(0, 0)
            e = bt.end_datetime.time() if bt.end_datetime.date() == target_date else time(23, 59)
            intervals.append(Interval(s, e))
    return intervals


async def _get_booking_intervals(
    db: AsyncSession,
    staff_id: int,
    target_date: date,
) -> list[Interval]:
    """
    Returns time intervals occupied by existing active bookings for a staff member.
    Each booking blocks: (start_time - buffer_before) … (end_time + buffer_after)
    """
    stmt = (
        select(Booking)
        .where(
            and_(
                Booking.staff_id == staff_id,
                Booking.booking_date == target_date,
                Booking.status.in_(["pending", "confirmed"]),
            )
        )
    )
    result = await db.execute(stmt)
    bookings = result.scalars().all()
    if not bookings:
        return []

    # Batch-load all referenced services in one query (avoid N+1).
    service_ids = {b.service_id for b in bookings}
    svc_rows = await db.execute(select(Service).where(Service.id.in_(service_ids)))
    svc_by_id = {s.id: s for s in svc_rows.scalars().all()}

    intervals: list[Interval] = []
    for b in bookings:
        svc = svc_by_id.get(b.service_id)
        if svc is None:
            continue
        block_start = _from_minutes(
            max(0, _to_minutes(b.start_time) - svc.buffer_before_minutes)
        )
        block_end = _from_minutes(
            _to_minutes(b.end_time) + svc.buffer_after_minutes
        )
        intervals.append(Interval(block_start, block_end))
    return intervals


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_available_slots(
    db: AsyncSession,
    business_id: int,
    service_id: int,
    target_date: date,
    staff_id: int | None = None,
) -> list[SlotOption]:
    """
    Returns available booking slots for a given service on a given date.
    If staff_id is None, checks all eligible staff and aggregates availability.
    """
    # Load service
    svc_result = await db.execute(
        select(Service).where(and_(Service.id == service_id, Service.business_id == business_id))
    )
    service = svc_result.scalar_one_or_none()
    if service is None or not service.is_active:
        return []

    # Load business for slot_step_minutes
    biz_result = await db.execute(select(Business).where(Business.id == business_id))
    business = biz_result.scalar_one_or_none()
    if business is None or not business.is_online_booking_enabled:
        return []

    # Booking-window enforcement (timezone-aware, Asia/Tashkent).
    _now = now_local()
    if target_date < _now.date():
        return []
    if target_date > _now.date() + timedelta(days=business.max_advance_booking_days):
        return []
    earliest_allowed = _now + timedelta(minutes=business.min_advance_booking_minutes)

    step = business.slot_step_minutes or 15

    # Resolve eligible staff
    if staff_id is not None:
        # Verify this staff member can perform the service
        ss_result = await db.execute(
            select(StaffService).where(
                and_(StaffService.staff_id == staff_id, StaffService.service_id == service_id)
            )
        )
        if ss_result.scalar_one_or_none() is None:
            return []
        staff_result = await db.execute(
            select(Staff).where(and_(Staff.id == staff_id, Staff.is_active == True))
        )
        eligible_staff = [staff_result.scalar_one_or_none()]
        eligible_staff = [s for s in eligible_staff if s is not None]
    else:
        # All active staff who can perform this service
        stmt = (
            select(Staff)
            .join(StaffService, StaffService.staff_id == Staff.id)
            .where(
                and_(
                    StaffService.service_id == service_id,
                    Staff.business_id == business_id,
                    Staff.is_active == True,
                )
            )
        )
        staff_result = await db.execute(stmt)
        eligible_staff = staff_result.scalars().all()

    if not eligible_staff:
        return []

    # Collect availability per slot time
    slot_map: dict[time, list[int]] = {}

    for staff in eligible_staff:
        window = await _get_working_window(db, staff, target_date)
        if window is None:
            continue

        # Build free intervals starting from working window
        free = [window]

        for brk in await _get_breaks(db, staff, target_date):
            free = _subtract_interval(free, brk.start, brk.end)

        for blk in await _get_blocked_intervals(db, staff, target_date):
            free = _subtract_interval(free, blk.start, blk.end)

        for booking_iv in await _get_booking_intervals(db, staff.id, target_date):
            free = _subtract_interval(free, booking_iv.start, booking_iv.end)

        # Generate valid slot start times within free intervals
        for iv in free:
            iv_start_m = _to_minutes(iv.start)
            iv_end_m = _to_minutes(iv.end)

            # Earliest start: interval start + buffer_before so prep time fits before customer
            earliest_m = iv_start_m + service.buffer_before_minutes
            # Latest start: must finish service + buffer_after before interval ends
            latest_m = iv_end_m - service.duration_minutes - service.buffer_after_minutes

            if earliest_m > latest_m:
                continue

            # Align earliest to next step boundary
            if earliest_m % step != 0:
                earliest_m = (earliest_m // step + 1) * step

            current_m = earliest_m
            while current_m <= latest_m:
                slot_time = _from_minutes(current_m)
                if slot_time not in slot_map:
                    slot_map[slot_time] = []
                slot_map[slot_time].append(staff.id)
                current_m += step

    # Build result, dropping any slot earlier than now + min_advance.
    slots: list[SlotOption] = []
    for start_t in sorted(slot_map.keys()):
        if to_local(target_date, start_t) < earliest_allowed:
            continue
        end_m = _to_minutes(start_t) + service.duration_minutes
        slots.append(
            SlotOption(
                start_time=start_t,
                end_time=_from_minutes(end_m),
                available_staff_ids=slot_map[start_t],
            )
        )

    return slots


async def create_booking(
    db: AsyncSession,
    *,
    business_id: int,
    service_id: int,
    staff_id: int | None,
    customer: Customer,
    booking_date: date,
    start_time: time,
    notes: str | None = None,
) -> Booking:
    """
    Creates a booking with double-booking prevention.

    Uses SELECT FOR UPDATE inside the caller's transaction to lock existing
    bookings for the target staff + date, preventing race conditions.
    The caller is responsible for committing the transaction.
    Raises ValueError on conflict.
    """
    # Load service
    svc_result = await db.execute(select(Service).where(Service.id == service_id))
    service = svc_result.scalar_one_or_none()
    if service is None:
        raise ValueError("Service not found")

    # Re-validate the requested slot server-side against full availability
    # (working hours, breaks, blocked times, existing bookings, booking windows).
    # Never trust the slot the client sends.
    slots = await get_available_slots(db, business_id, service_id, booking_date, staff_id)
    slot = next((s for s in slots if s.start_time == start_time), None)
    if slot is None:
        raise ValueError("Time slot is not available")

    assigned_staff_id = staff_id
    auto_assigned = False

    if assigned_staff_id is None:
        # Pick the available staff member with the fewest bookings that day.
        counts: dict[int, int] = {}
        for sid in slot.available_staff_ids:
            cnt = await db.scalar(
                select(func.count(Booking.id)).where(
                    and_(
                        Booking.staff_id == sid,
                        Booking.booking_date == booking_date,
                        Booking.status.in_(["pending", "confirmed"]),
                    )
                )
            )
            counts[sid] = cnt or 0
        if not counts:
            raise ValueError("No available staff at requested time")
        assigned_staff_id = min(counts, key=lambda k: counts[k])
        auto_assigned = True

    # Lock existing bookings for this staff + date (prevents race conditions)
    lock_stmt = (
        select(Booking)
        .where(
            and_(
                Booking.staff_id == assigned_staff_id,
                Booking.booking_date == booking_date,
                Booking.status.in_(["pending", "confirmed"]),
            )
        )
        .with_for_update()
    )
    existing_result = await db.execute(lock_stmt)
    existing_bookings = existing_result.scalars().all()

    # Calculate the full blocked window for the new booking
    end_time = _from_minutes(_to_minutes(start_time) + service.duration_minutes)
    new_block_start = _from_minutes(_to_minutes(start_time) - service.buffer_before_minutes)
    new_block_end = _from_minutes(_to_minutes(end_time) + service.buffer_after_minutes)

    # Check for overlap with existing bookings (batch-load their services)
    ex_svc_by_id: dict[int, Service] = {}
    if existing_bookings:
        ex_ids = {e.service_id for e in existing_bookings}
        ex_rows = await db.execute(select(Service).where(Service.id.in_(ex_ids)))
        ex_svc_by_id = {s.id: s for s in ex_rows.scalars().all()}
    for existing in existing_bookings:
        ex_svc = ex_svc_by_id.get(existing.service_id)
        if ex_svc is None:
            continue
        ex_block_start = _from_minutes(
            _to_minutes(existing.start_time) - ex_svc.buffer_before_minutes
        )
        ex_block_end = _from_minutes(
            _to_minutes(existing.end_time) + ex_svc.buffer_after_minutes
        )
        if _to_minutes(new_block_start) < _to_minutes(ex_block_end) and \
           _to_minutes(new_block_end) > _to_minutes(ex_block_start):
            raise ValueError("Time slot is no longer available")

    # Insert booking — caller must commit
    booking = Booking(
        business_id=business_id,
        service_id=service_id,
        staff_id=assigned_staff_id,
        customer_id=customer.id,
        customer_name=customer.name,
        customer_phone=customer.phone or "",
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        status="pending" if service.requires_confirmation else "confirmed",
        notes=notes,
        was_auto_assigned=auto_assigned,
    )
    db.add(booking)
    try:
        await db.flush()
    except IntegrityError:
        # The Postgres exclusion constraint rejected an overlapping booking that
        # raced past the application check. Surface it as a clean conflict.
        await db.rollback()
        raise ValueError("Time slot is no longer available")
    await db.refresh(booking)
    return booking
