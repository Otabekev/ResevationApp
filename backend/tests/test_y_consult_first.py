"""
Phase 1 — consult-first (dentist) model:
  - online_bookable=False hides a service from customers (staff-scheduled only)
  - max_per_day caps a service's daily self-bookings (the "Checkup" limit)
  - manual bookings link to a patient's Telegram account by phone (reminders)
  - the treatment-plan endpoint reserves several days at once
"""
from datetime import date, time, timedelta

from app.models.schedule import WorkingHours
from app.services.booking_engine import create_booking, get_available_slots
from tests import factories as f

API = "/api/v1"


async def _bookable(db, *, tid, max_per_day=None, online_bookable=True):
    cat = await f.create_category(db, slug=f"sch{tid}")
    owner = await f.create_user(db, role="business_owner", telegram_id=tid)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="active")
    svc = await f.create_service(db, business_id=biz.id, duration_minutes=30)
    svc.max_per_day = max_per_day
    svc.online_bookable = online_bookable
    staff = await f.create_staff(db, business_id=biz.id)
    await f.link_staff_service(db, staff_id=staff.id, service_id=svc.id)
    for dow in range(7):
        db.add(WorkingHours(business_id=biz.id, day_of_week=dow, start_time=time(9, 0), end_time=time(18, 0)))
    await db.commit()
    return owner, biz, svc, staff


async def test_non_bookable_service_hidden_from_customers_only(client, db):
    owner, biz, svc, staff = await _bookable(db, tid=7701, online_bookable=False)
    pub = await client.get(f"{API}/businesses/{biz.id}/services")
    assert all(s["id"] != svc.id for s in pub.json()), "treatment service must be hidden from customers"
    owned = await client.get(f"{API}/businesses/{biz.id}/services/all", headers=f.auth_header(owner.id))
    assert any(s["id"] == svc.id for s in owned.json()), "owner must still see + manage it"


async def test_max_per_day_caps_the_day(db):
    owner, biz, svc, staff = await _bookable(db, tid=7702, max_per_day=1)
    target = date.today() + timedelta(days=2)
    slots = await get_available_slots(db, biz.id, svc.id, target, staff.id)
    assert slots, "should have slots before the cap is hit"
    cust = await f.create_customer(db, telegram_id=7002)
    await create_booking(
        db, business_id=biz.id, service_id=svc.id, staff_id=staff.id,
        customer=cust, booking_date=target, start_time=slots[0].start_time,
    )
    await db.commit()
    assert await get_available_slots(db, biz.id, svc.id, target, staff.id) == [], "cap=1 → no more slots that day"
    # A different day is unaffected.
    other = target + timedelta(days=1)
    assert await get_available_slots(db, biz.id, svc.id, other, staff.id), "next day still open"


async def test_manual_booking_links_to_telegram_patient(client, db):
    owner, biz, svc, staff = await _bookable(db, tid=7703)
    tg_patient = await f.create_customer(db, telegram_id=7003, name="Patient", phone="+998901112233")
    target = date.today() + timedelta(days=2)
    slots = await get_available_slots(db, biz.id, svc.id, target, staff.id)
    r = await client.post(
        f"{API}/businesses/{biz.id}/bookings",
        json={
            "service_id": svc.id, "staff_id": staff.id, "booking_date": str(target),
            "start_time": str(slots[0].start_time), "customer_name": "Patient",
            "customer_phone": "998 90 111 22 33",  # different formatting, same number
        },
        headers=f.auth_header(owner.id),
    )
    assert r.status_code == 201, r.text
    assert r.json()["customer_id"] == tg_patient.id, "must attach to the bot account so reminders reach them"


async def test_treatment_plan_reserves_several_days(client, db):
    owner, biz, svc, staff = await _bookable(db, tid=7704)
    d1 = date.today() + timedelta(days=2)
    d2 = date.today() + timedelta(days=3)
    s1 = await get_available_slots(db, biz.id, svc.id, d1, staff.id)
    s2 = await get_available_slots(db, biz.id, svc.id, d2, staff.id)
    r = await client.post(
        f"{API}/businesses/{biz.id}/bookings/plan",
        json={
            "service_id": svc.id, "staff_id": staff.id,
            "customer_name": "Plan Patient", "customer_phone": "998905556677",
            "slots": [
                {"booking_date": str(d1), "start_time": str(s1[0].start_time)},
                {"booking_date": str(d2), "start_time": str(s2[0].start_time)},
            ],
        },
        headers=f.auth_header(owner.id),
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["created"]) == 2
    assert r.json()["failed"] == []


async def test_treatment_plan_manager_scoped(client, db):
    """A manager of another clinic can't create a plan here (cross-tenant)."""
    owner, biz, svc, staff = await _bookable(db, tid=7705)
    other = await f.create_user(db, role="staff", telegram_id=7006)
    r = await client.post(
        f"{API}/businesses/{biz.id}/bookings/plan",
        json={"service_id": svc.id, "customer_name": "X", "customer_phone": "998905550000",
              "slots": [{"booking_date": str(date.today() + timedelta(days=2)), "start_time": "09:00:00"}]},
        headers=f.auth_header(other.id),
    )
    assert r.status_code in (403, 404)
