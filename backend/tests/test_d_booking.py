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
            "tsrange((booking_date + start_time), (booking_date + end_time)) WITH &&) "
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
