"""
Category E — performance.

E1: the availability hot path must not issue one Service query per existing
booking (N+1). We assert the number of `FROM services` queries stays flat as the
number of bookings grows.
"""
from datetime import date, time, timedelta

from sqlalchemy import event

from app.models.schedule import WorkingHours
from app.services.booking_engine import get_available_slots
from tests.factories import (
    create_booking, create_business, create_category, create_customer,
    create_service, create_staff, link_staff_service, create_user,
)


async def test_availability_no_n_plus_one_on_services(db, engine):
    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=1)
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await create_service(db, business_id=biz.id, duration_minutes=30)
    staff = await create_staff(db, business_id=biz.id)
    await link_staff_service(db, staff_id=staff.id, service_id=svc.id)
    for dow in range(7):
        db.add(WorkingHours(business_id=biz.id, day_of_week=dow, start_time=time(9, 0), end_time=time(18, 0)))
    await db.commit()
    cust = await create_customer(db, telegram_id=500)

    soon = date.today() + timedelta(days=3)
    # Five existing bookings on this staff/day.
    for hour in (9, 10, 11, 12, 13):
        await create_booking(
            db, business_id=biz.id, service_id=svc.id, staff_id=staff.id, customer_id=cust.id,
            booking_date=soon, start_time=time(hour, 0), end_time=time(hour, 30),
        )

    # Count queries against the services table.
    service_queries = {"n": 0}

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        if "FROM services" in statement:
            service_queries["n"] += 1

    await get_available_slots(db, biz.id, svc.id, soon, staff.id)

    # 1 to load the requested service, 1 batched load for the bookings' services.
    # Without the fix this is 1 + 5 = 6.
    assert service_queries["n"] <= 2, f"N+1 detected: {service_queries['n']} service queries"


async def test_bookings_list_respects_limit(client, db):
    from tests.factories import auth_header

    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=1)
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await create_service(db, business_id=biz.id)
    staff = await create_staff(db, business_id=biz.id)
    cust = await create_customer(db, telegram_id=7)
    soon = date.today() + timedelta(days=2)
    for hour in (9, 10, 11):
        await create_booking(
            db, business_id=biz.id, service_id=svc.id, staff_id=staff.id, customer_id=cust.id,
            booking_date=soon, start_time=time(hour, 0), end_time=time(hour, 30),
        )

    resp = await client.get(
        f"/api/v1/businesses/{biz.id}/bookings?limit=2", headers=auth_header(owner.id)
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 2
