"""
Category D — double-booking prevention, booking windows, timezones.

SQLite-provable: window enforcement (D4), confirm-time validation (D5),
sequential double-book guard (D1 app level), timezone math (D3).
Postgres-only: true concurrency (D1/D2) — marked and skipped without TEST_DATABASE_URL.
"""
from datetime import date, time, timedelta

import pytest

from app.models.schedule import WorkingHours
from app.services.booking_engine import create_booking, get_available_slots
from tests.factories import (
    create_business, create_category, create_customer, create_service,
    create_staff, link_staff_service, create_user,
)


async def _setup(db, *, day_off=False, start=time(9, 0), end=time(18, 0),
                 min_advance=60, max_advance=30):
    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=1)
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)
    biz.min_advance_booking_minutes = min_advance
    biz.max_advance_booking_days = max_advance
    svc = await create_service(db, business_id=biz.id, duration_minutes=30)
    staff = await create_staff(db, business_id=biz.id)
    await link_staff_service(db, staff_id=staff.id, service_id=svc.id)
    # Working hours for every weekday
    for dow in range(7):
        db.add(WorkingHours(business_id=biz.id, day_of_week=dow, start_time=start, end_time=end))
    await db.commit()
    cust = await create_customer(db, telegram_id=500)
    return biz, svc, staff, cust


# ── D3: timezone helper ──────────────────────────────────────────────────────

def test_to_utc_tashkent_offset():
    from app.timeutils import to_utc
    assert to_utc(date(2030, 6, 1), time(14, 0)).strftime("%H:%M") == "09:00"


# ── D4: booking windows ──────────────────────────────────────────────────────

async def test_availability_excludes_past_dates(db):
    biz, svc, staff, _ = await _setup(db)
    yesterday = date.today() - timedelta(days=1)
    slots = await get_available_slots(db, biz.id, svc.id, yesterday, staff.id)
    assert slots == []


async def test_availability_excludes_beyond_max_advance(db):
    biz, svc, staff, _ = await _setup(db, max_advance=30)
    far = date.today() + timedelta(days=45)
    slots = await get_available_slots(db, biz.id, svc.id, far, staff.id)
    assert slots == []


async def test_availability_has_slots_within_window(db):
    biz, svc, staff, _ = await _setup(db)
    soon = date.today() + timedelta(days=3)
    slots = await get_available_slots(db, biz.id, svc.id, soon, staff.id)
    assert len(slots) > 0


async def test_buffer_keeps_next_booking_clear_of_the_gap(db):
    """A service's before/after buffers must keep the next booking clear of the
    GAP, not just of the appointment itself — so two bookings can't sit too close.
    (Scale-audit item: "buffer overlap".) One transaction throughout: create_booking
    flushes internally, so each booking is visible to the next check without a commit
    (a commit would expire the ORM objects and break the async session)."""
    biz, svc, staff, cust = await _setup(db)
    await db.refresh(svc)                 # svc was expired by _setup's commit
    svc.buffer_before_minutes = 15
    svc.buffer_after_minutes = 15
    await db.flush()                      # persist buffers in-transaction, don't expire cust/staff
    target = date.today() + timedelta(days=3)

    # Book 12:00–12:30 → with 15‑min buffers this reserves 11:45–12:45.
    await create_booking(
        db, business_id=biz.id, service_id=svc.id, staff_id=staff.id,
        customer=cust, booking_date=target, start_time=time(12, 0),
    )

    # 12:30 is back‑to‑back with the appointment but INSIDE its after‑buffer → must be
    # rejected (without buffers this would have been allowed). The overlap check raises
    # before any write, so the session stays usable.
    with pytest.raises(ValueError):
        await create_booking(
            db, business_id=biz.id, service_id=svc.id, staff_id=staff.id,
            customer=cust, booking_date=target, start_time=time(12, 30),
        )

    # Availability must not even OFFER a start inside the reserved 11:45–12:45 window.
    starts = {s.start_time for s in await get_available_slots(db, biz.id, svc.id, target, staff.id)}
    assert time(12, 0) not in starts and time(12, 30) not in starts

    # A booking that clears the buffer (13:00, its own before‑buffer starting exactly
    # at 12:45) is still accepted — the buffer blocks *too‑close*, not everything.
    ok = await create_booking(
        db, business_id=biz.id, service_id=svc.id, staff_id=staff.id,
        customer=cust, booking_date=target, start_time=time(13, 0),
    )
    assert ok.id is not None


async def test_create_booking_rejects_past_date(db):
    biz, svc, staff, cust = await _setup(db)
    with pytest.raises(ValueError):
        await create_booking(
            db, business_id=biz.id, service_id=svc.id, staff_id=staff.id,
            customer=cust, booking_date=date.today() - timedelta(days=1), start_time=time(10, 0),
        )


# ── D5: confirm-time validation against working hours ────────────────────────

async def test_create_booking_rejects_outside_working_hours(db):
    biz, svc, staff, cust = await _setup(db, start=time(9, 0), end=time(12, 0))
    soon = date.today() + timedelta(days=3)
    # 15:00 is outside the 09:00–12:00 window → must be rejected, not silently booked.
    with pytest.raises(ValueError):
        await create_booking(
            db, business_id=biz.id, service_id=svc.id, staff_id=staff.id,
            customer=cust, booking_date=soon, start_time=time(15, 0),
        )


# ── D6: business schedule is the ceiling over staff schedules ────────────────

async def test_business_day_off_blocks_staff_with_open_hours(db):
    """Shop closed that day → a staff member who left their own hours open must
    still NOT be bookable."""
    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=11)
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await create_service(db, business_id=biz.id, duration_minutes=30)
    staff = await create_staff(db, business_id=biz.id)
    await link_staff_service(db, staff_id=staff.id, service_id=svc.id)

    target = date.today() + timedelta(days=3)
    dow = target.weekday()
    for d in range(7):
        db.add(WorkingHours(
            business_id=biz.id, day_of_week=d,
            start_time=time(9, 0), end_time=time(18, 0), is_day_off=(d == dow),
        ))
    # Staff accidentally left their own schedule OPEN on the shop's closed day.
    db.add(WorkingHours(
        business_id=biz.id, staff_id=staff.id, day_of_week=dow,
        start_time=time(9, 0), end_time=time(18, 0), is_day_off=False,
    ))
    await db.commit()

    slots = await get_available_slots(db, biz.id, svc.id, target, staff.id)
    assert slots == []


async def test_staff_hours_clamped_to_business_hours(db):
    """A staff member's open hours can't extend past the shop's open hours."""
    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=12)
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await create_service(db, business_id=biz.id, duration_minutes=30)
    staff = await create_staff(db, business_id=biz.id)
    await link_staff_service(db, staff_id=staff.id, service_id=svc.id)

    target = date.today() + timedelta(days=3)
    dow = target.weekday()
    for d in range(7):  # shop open 09:00–12:00
        db.add(WorkingHours(business_id=biz.id, day_of_week=d, start_time=time(9, 0), end_time=time(12, 0)))
    # Staff "open" 09:00–18:00 — must be clamped to 09:00–12:00.
    db.add(WorkingHours(
        business_id=biz.id, staff_id=staff.id, day_of_week=dow,
        start_time=time(9, 0), end_time=time(18, 0),
    ))
    await db.commit()

    slots = await get_available_slots(db, biz.id, svc.id, target, staff.id)
    assert slots, "expected morning slots within shop hours"
    assert max(s.start_time for s in slots) == time(11, 30)  # last 30-min start before 12:00


# ── D1 (app level): sequential double-book is rejected cleanly ───────────────

async def test_sequential_double_book_rejected(db):
    biz, svc, staff, cust = await _setup(db)
    soon = date.today() + timedelta(days=3)
    await create_booking(
        db, business_id=biz.id, service_id=svc.id, staff_id=staff.id,
        customer=cust, booking_date=soon, start_time=time(10, 0),
    )
    await db.commit()
    with pytest.raises(ValueError):
        await create_booking(
            db, business_id=biz.id, service_id=svc.id, staff_id=staff.id,
            customer=cust, booking_date=soon, start_time=time(10, 0),
        )


# ── D7: multi-service bookings (back-to-back, one staff) ─────────────────────

async def _multi_setup(db, *, durations, telegram_id):
    """Business + one staff who can do every given service, open 9–18 daily."""
    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=telegram_id)
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)
    svcs = [await create_service(db, business_id=biz.id, duration_minutes=d) for d in durations]
    staff = await create_staff(db, business_id=biz.id)
    for s in svcs:
        await link_staff_service(db, staff_id=staff.id, service_id=s.id)
    for dow in range(7):
        db.add(WorkingHours(business_id=biz.id, day_of_week=dow, start_time=time(9, 0), end_time=time(18, 0)))
    await db.commit()
    return biz, svcs, staff


def _mins(t: time) -> int:
    return t.hour * 60 + t.minute


async def test_multi_service_sums_duration(db):
    biz, (svc1, svc2), staff = await _multi_setup(db, durations=[30, 20], telegram_id=41)
    soon = date.today() + timedelta(days=3)
    slots = await get_available_slots(db, biz.id, svc1.id, soon, staff.id, service_ids=[svc1.id, svc2.id])
    assert slots, "expected slots for the 50-minute combined block"
    assert _mins(slots[0].end_time) - _mins(slots[0].start_time) == 50


async def test_multi_service_staff_must_do_all(db):
    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=42)
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)
    svc1 = await create_service(db, business_id=biz.id, duration_minutes=30)
    svc2 = await create_service(db, business_id=biz.id, duration_minutes=20)
    a = await create_staff(db, business_id=biz.id, name="A")
    b = await create_staff(db, business_id=biz.id, name="B")
    await link_staff_service(db, staff_id=a.id, service_id=svc1.id)
    await link_staff_service(db, staff_id=a.id, service_id=svc2.id)
    await link_staff_service(db, staff_id=b.id, service_id=svc1.id)  # B can't do svc2
    for dow in range(7):
        db.add(WorkingHours(business_id=biz.id, day_of_week=dow, start_time=time(9, 0), end_time=time(18, 0)))
    await db.commit()
    soon = date.today() + timedelta(days=3)
    # "any staff" for [svc1, svc2] → only A is eligible at every slot.
    slots = await get_available_slots(db, biz.id, svc1.id, soon, None, service_ids=[svc1.id, svc2.id])
    assert slots
    assert all(set(s.available_staff_ids) == {a.id} for s in slots)
    # Asking specifically for B (who can't do svc2) → nothing.
    assert await get_available_slots(db, biz.id, svc1.id, soon, b.id, service_ids=[svc1.id, svc2.id]) == []


async def test_multi_service_single_service_path_unchanged(db):
    """A one-element service_ids list must behave exactly like the legacy call."""
    biz, (svc,), staff = await _multi_setup(db, durations=[30], telegram_id=43)
    soon = date.today() + timedelta(days=3)
    legacy = await get_available_slots(db, biz.id, svc.id, soon, staff.id)
    as_list = await get_available_slots(db, biz.id, svc.id, soon, staff.id, service_ids=[svc.id])
    assert legacy == as_list and legacy != []


async def test_multi_service_create_persists_all_and_primary_first(db):
    from sqlalchemy import select as _select

    from app.models.booking import booking_services

    biz, (svc1, svc2), staff = await _multi_setup(db, durations=[30, 20], telegram_id=44)
    cust = await create_customer(db, telegram_id=600)
    soon = date.today() + timedelta(days=3)
    bk = await create_booking(
        db, business_id=biz.id, service_id=svc1.id, staff_id=staff.id,
        customer=cust, booking_date=soon, start_time=time(10, 0),
        service_ids=[svc1.id, svc2.id],
    )
    await db.commit()
    assert bk.service_id == svc1.id        # primary = first selected
    assert bk.end_time == time(10, 50)     # 30 + 20 = 50 minutes
    rows = (await db.execute(
        _select(booking_services.c.service_id).where(booking_services.c.booking_id == bk.id)
    )).all()
    assert {r[0] for r in rows} == {svc1.id, svc2.id}


# ── D1/D2: true concurrency — Postgres only ──────────────────────────────────

@pytest.mark.postgres
async def test_concurrent_booking_single_winner():
    """N parallel requests for the same slot → exactly one booking wins.
    Requires a real Postgres (the btree_gist exclusion constraint)."""
    import asyncio
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.database import Base
    from app.models.booking import Customer

    pg_url = os.environ.get("TEST_DATABASE_URL")
    if not pg_url:
        pytest.skip("set TEST_DATABASE_URL to a Postgres URL to run this test")

    eng = create_async_engine(pg_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await conn.execute(text(
            "ALTER TABLE bookings ADD CONSTRAINT no_overlapping_bookings "
            "EXCLUDE USING gist (staff_id WITH =, "
            "(tsrange((booking_date + start_time)::timestamp, (booking_date + end_time)::timestamp)) WITH &&) "
            "WHERE (status IN ('pending','confirmed') AND staff_id IS NOT NULL)"
        ))

    maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        biz, svc, staff, cust = await _setup(s, min_advance=0)
        biz_id, svc_id, staff_id, cust_id = biz.id, svc.id, staff.id, cust.id

    soon = date.today() + timedelta(days=2)

    async def attempt() -> bool:
        async with maker() as s:
            cust = await s.get(Customer, cust_id)
            try:
                await create_booking(
                    s, business_id=biz_id, service_id=svc_id, staff_id=staff_id,
                    customer=cust, booking_date=soon, start_time=time(10, 0),
                )
                await s.commit()
                return True
            except Exception:
                await s.rollback()
                return False

    results = await asyncio.gather(*[attempt() for _ in range(8)])
    await eng.dispose()
    assert sum(results) == 1, f"expected exactly one winner, got {sum(results)}"


@pytest.mark.postgres
async def test_duplicate_customer_slot_rejected_across_staff():
    """A retry that lands on a DIFFERENT auto-assigned staff must not create a
    second booking for the same customer + slot. Requires Postgres (the partial
    unique index uq_active_booking_customer_slot from migration 0008)."""
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.database import Base
    from app.models.booking import Customer

    pg_url = os.environ.get("TEST_DATABASE_URL")
    if not pg_url:
        pytest.skip("set TEST_DATABASE_URL to a Postgres URL to run this test")

    eng = create_async_engine(pg_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "CREATE UNIQUE INDEX uq_active_booking_customer_slot "
            "ON bookings (customer_id, business_id, booking_date, start_time) "
            "WHERE status IN ('pending','confirmed') AND customer_id IS NOT NULL"
        ))

    maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        biz, svc, staff, cust = await _setup(s, min_advance=0)
        staff2 = await create_staff(s, business_id=biz.id, name="Barber2")
        await link_staff_service(s, staff_id=staff2.id, service_id=svc.id)
        await s.commit()
        biz_id, svc_id, staff_id, staff2_id, cust_id = biz.id, svc.id, staff.id, staff2.id, cust.id

    soon = date.today() + timedelta(days=2)
    async with maker() as s:
        cust = await s.get(Customer, cust_id)
        await create_booking(s, business_id=biz_id, service_id=svc_id, staff_id=staff_id,
                             customer=cust, booking_date=soon, start_time=time(10, 0))
        await s.commit()

    # The retry gets the OTHER staff — the staff-keyed EXCLUDE wouldn't catch it,
    # but the customer+slot index must.
    with pytest.raises(ValueError):
        async with maker() as s:
            cust = await s.get(Customer, cust_id)
            await create_booking(s, business_id=biz_id, service_id=svc_id, staff_id=staff2_id,
                                 customer=cust, booking_date=soon, start_time=time(10, 0))
            await s.commit()
    await eng.dispose()
