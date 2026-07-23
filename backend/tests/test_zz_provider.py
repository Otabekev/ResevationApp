"""
Provider self-service dashboard — a doctor's access is row-scoped to their OWN
records: their bookings, their queue line, their hours, their setup. Never
business-wide, never another provider's data, never business settings/roster.
"""
from datetime import date, time, timedelta

from sqlalchemy import select

from app.config import settings
from app.models.schedule import BreakTime, WorkingHours
from app.services.booking_engine import get_available_slots
from tests import factories as f

API = "/api/v1"
BOT = {"X-Bot-Secret": settings.bot_secret}


async def _bookable_clinic(db, *, tid):
    """A clinic where docA + docB are appointment providers of a shared service,
    with business hours 09–18 every day (so availability is computable)."""
    owner, biz, userA, userB, docA, docB = await _clinic(db, tid=tid)
    docA.scheduling_mode = "appointments"
    docB.scheduling_mode = "appointments"
    svc = await f.create_service(db, business_id=biz.id, duration_minutes=30)
    await f.link_staff_service(db, staff_id=docA.id, service_id=svc.id)
    await f.link_staff_service(db, staff_id=docB.id, service_id=svc.id)
    for dow in range(7):
        db.add(WorkingHours(business_id=biz.id, day_of_week=dow, start_time=time(9, 0), end_time=time(18, 0)))
    await db.commit()
    return owner, biz, userA, userB, docA, docB, svc


async def _clinic(db, *, tid):
    """Owner + two linked doctors (A, B), both live-queue providers."""
    cat = await f.create_category(db, slug=f"p{tid}")
    owner = await f.create_user(db, role="business_owner", telegram_id=tid)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="active")
    userA = await f.create_user(db, role="staff", telegram_id=tid + 1, name="Dr A")
    userB = await f.create_user(db, role="staff", telegram_id=tid + 2, name="Dr B")
    docA = await f.create_staff(db, business_id=biz.id, user_id=userA.id, name="Dr A")
    docB = await f.create_staff(db, business_id=biz.id, user_id=userB.id, name="Dr B")
    docA.scheduling_mode = "queue"
    docB.scheduling_mode = "queue"
    await db.commit()
    return owner, biz, userA, userB, docA, docB


async def test_provider_mine_returns_business(client, db):
    # An already-linked doctor sees their business (access_role=provider) the moment
    # they open the app — no re-signup, the dashboard just appears.
    owner, biz, userA, userB, docA, docB = await _clinic(db, tid=8200)
    r = await client.get(f"{API}/businesses/mine", headers=f.auth_header(userA.id))
    assert r.status_code == 200, r.text
    rows = {b["id"]: b for b in r.json()}
    assert biz.id in rows
    assert rows[biz.id]["access_role"] == "provider"


async def test_provider_sees_only_own_bookings(client, db):
    owner, biz, userA, userB, docA, docB = await _clinic(db, tid=8210)
    svc = await f.create_service(db, business_id=biz.id)
    cust = await f.create_customer(db, telegram_id=9001)
    await f.create_booking(db, business_id=biz.id, service_id=svc.id, staff_id=docA.id,
                           customer_id=cust.id, start_time=time(10, 0), end_time=time(10, 30))
    await f.create_booking(db, business_id=biz.id, service_id=svc.id, staff_id=docA.id,
                           customer_id=cust.id, start_time=time(11, 0), end_time=time(11, 30))
    await f.create_booking(db, business_id=biz.id, service_id=svc.id, staff_id=docB.id,
                           customer_id=cust.id, start_time=time(12, 0), end_time=time(12, 30))
    r = await client.get(f"{API}/businesses/{biz.id}/bookings", headers=f.auth_header(userA.id))
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2  # Dr A's two only — never Dr B's


async def test_provider_queue_scoped_and_actions(client, db):
    owner, biz, userA, userB, docA, docB = await _clinic(db, tid=8220)
    jA = await client.post(f"{API}/public/queue/join", headers=BOT, json={
        "business_id": biz.id, "staff_id": docA.id, "customer_name": "PA", "telegram_id": 7001})
    jB = await client.post(f"{API}/public/queue/join", headers=BOT, json={
        "business_id": biz.id, "staff_id": docB.id, "customer_name": "PB", "telegram_id": 7002})
    eA, eB = jA.json()["entry_id"], jB.json()["entry_id"]
    hA = f.auth_header(userA.id)

    # Dr A's queue view shows only Dr A's line.
    lst = await client.get(f"{API}/businesses/{biz.id}/queue", headers=hA)
    assert lst.status_code == 200
    assert {e["staff_id"] for e in lst.json()} == {docA.id}

    # Dr A can't peek at Dr B's line, nor act on Dr B's patient.
    assert (await client.get(f"{API}/businesses/{biz.id}/queue?staff_id={docB.id}", headers=hA)).status_code == 403
    assert (await client.post(f"{API}/businesses/{biz.id}/queue/{eB}/call", headers=hA)).status_code == 403
    # …but can act on their own.
    assert (await client.post(f"{API}/businesses/{biz.id}/queue/{eA}/call", headers=hA)).status_code == 200


async def test_provider_cannot_manage_business(client, db):
    owner, biz, userA, userB, docA, docB = await _clinic(db, tid=8230)
    hA = f.auth_header(userA.id)
    # Staff roster is manager-only.
    assert (await client.get(f"{API}/businesses/{biz.id}/staff", headers=hA)).status_code == 403
    # Inviting staff is manager-only.
    assert (await client.post(f"{API}/businesses/{biz.id}/staff/{docB.id}/invite", headers=hA)).status_code == 403


async def test_provider_self_update_and_isolation(client, db):
    owner, biz, userA, userB, docA, docB = await _clinic(db, tid=8240)
    svc = await f.create_service(db, business_id=biz.id)
    hA = f.auth_header(userA.id)

    # Update own setup: mode + queue speed + services offered.
    r = await client.patch(f"{API}/businesses/{biz.id}/staff/me/{docA.id}", headers=hA, json={
        "scheduling_mode": "appointments", "queue_avg_minutes": 25, "service_ids": [svc.id]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scheduling_mode"] == "appointments"
    assert body["queue_avg_minutes"] == 25
    assert body["service_ids"] == [svc.id]

    # Cannot edit another doctor's record.
    assert (await client.patch(f"{API}/businesses/{biz.id}/staff/me/{docB.id}", headers=hA,
                               json={"queue_avg_minutes": 5})).status_code == 403

    # Cannot escalate: privilege fields aren't in the self schema, so they're ignored.
    r2 = await client.patch(f"{API}/businesses/{biz.id}/staff/me/{docA.id}", headers=hA, json={
        "can_manage": True, "is_provider": False, "name": "Dr A New"})
    assert r2.status_code == 200
    assert r2.json()["can_manage"] is False
    assert r2.json()["is_provider"] is True
    assert r2.json()["name"] == "Dr A New"


async def test_provider_own_working_hours(client, db):
    owner, biz, userA, userB, docA, docB = await _clinic(db, tid=8250)
    hA = f.auth_header(userA.id)
    hours = {"hours": [{"day_of_week": 1, "start_time": "09:00", "end_time": "17:00"}]}

    # Own hours: set + read.
    assert (await client.put(f"{API}/businesses/{biz.id}/staff/{docA.id}/working-hours",
                             headers=hA, json=hours)).status_code == 200
    assert (await client.get(f"{API}/businesses/{biz.id}/staff/{docA.id}/working-hours",
                             headers=hA)).status_code == 200

    # Dr B's hours are off-limits.
    assert (await client.get(f"{API}/businesses/{biz.id}/staff/{docB.id}/working-hours",
                             headers=hA)).status_code == 403
    assert (await client.put(f"{API}/businesses/{biz.id}/staff/{docB.id}/working-hours",
                             headers=hA, json=hours)).status_code == 403


async def test_provider_analytics_self_scoped(client, db):
    owner, biz, userA, userB, docA, docB, svc = await _bookable_clinic(db, tid=8260)
    cust = await f.create_customer(db, telegram_id=9100)
    today = date.today()
    await f.create_booking(db, business_id=biz.id, service_id=svc.id, staff_id=docA.id,
                           customer_id=cust.id, booking_date=today, start_time=time(10, 0), end_time=time(10, 30))
    await f.create_booking(db, business_id=biz.id, service_id=svc.id, staff_id=docA.id,
                           customer_id=cust.id, booking_date=today, start_time=time(11, 0), end_time=time(11, 30))
    await f.create_booking(db, business_id=biz.id, service_id=svc.id, staff_id=docB.id,
                           customer_id=cust.id, booking_date=today, start_time=time(12, 0), end_time=time(12, 30))
    # Dr A sees only their own two; the owner sees all three.
    rA = await client.get(f"{API}/businesses/{biz.id}/analytics?days=30", headers=f.auth_header(userA.id))
    assert rA.status_code == 200, rA.text
    assert rA.json()["total_bookings"] == 2
    rO = await client.get(f"{API}/businesses/{biz.id}/analytics?days=30", headers=f.auth_header(owner.id))
    assert rO.json()["total_bookings"] == 3


async def test_provider_cancel_own_not_others(client, db):
    owner, biz, userA, userB, docA, docB, svc = await _bookable_clinic(db, tid=8270)
    cust = await f.create_customer(db, telegram_id=9200)
    bA = await f.create_booking(db, business_id=biz.id, service_id=svc.id, staff_id=docA.id,
                                customer_id=cust.id, booking_date=date.today(), start_time=time(10, 0),
                                end_time=time(10, 30), status="pending")
    bB = await f.create_booking(db, business_id=biz.id, service_id=svc.id, staff_id=docB.id,
                                customer_id=cust.id, booking_date=date.today(), start_time=time(11, 0),
                                end_time=time(11, 30), status="pending")
    hA = f.auth_header(userA.id)
    # Cannot cancel Dr B's appointment…
    assert (await client.patch(f"{API}/bookings/{bB.id}/cancel", headers=hA, json={})).status_code == 403
    # …but can cancel their own (Dashboard/Bookings Decline button).
    r = await client.patch(f"{API}/bookings/{bA.id}/cancel", headers=hA, json={"reason": "sick"})
    assert r.status_code == 200, r.text


async def test_provider_create_booking_only_own_calendar(client, db):
    owner, biz, userA, userB, docA, docB, svc = await _bookable_clinic(db, tid=8280)
    hA = f.auth_header(userA.id)
    soon = (date.today() + timedelta(days=3)).isoformat()
    base = {"service_id": svc.id, "booking_date": soon, "start_time": "10:00:00",
            "customer_name": "P", "customer_phone": "+998901112233"}
    # Booking onto their OWN calendar succeeds.
    ok = await client.post(f"{API}/businesses/{biz.id}/bookings", headers=hA, json={**base, "staff_id": docA.id})
    assert ok.status_code == 201, ok.text
    # Onto another doctor's calendar → 403.
    assert (await client.post(f"{API}/businesses/{biz.id}/bookings", headers=hA,
                              json={**base, "staff_id": docB.id, "start_time": "11:00:00"})).status_code == 403
    # With no staff_id (would auto-assign to anyone) → 403.
    assert (await client.post(f"{API}/businesses/{biz.id}/bookings", headers=hA,
                              json={**base, "staff_id": None, "start_time": "12:00:00"})).status_code == 403


async def test_provider_break_is_personal_and_honored(client, db):
    owner, biz, userA, userB, docA, docB, svc = await _bookable_clinic(db, tid=8290)
    hA = f.auth_header(userA.id)
    # Dr A adds their own lunch break.
    r = await client.post(f"{API}/businesses/{biz.id}/staff/{docA.id}/breaks", headers=hA,
                          json={"day_of_week": None, "start_time": "13:00", "end_time": "14:00", "label": "Lunch"})
    assert r.status_code == 200, r.text
    row = (await db.execute(select(BreakTime).where(BreakTime.id == r.json()["id"]))).scalar_one()
    # CRITICAL: personal row — staff_id set, business_id NULL (else it blocks EVERYONE).
    assert row.staff_id == docA.id and row.business_id is None

    # Cannot add a break to Dr B.
    assert (await client.post(f"{API}/businesses/{biz.id}/staff/{docB.id}/breaks", headers=hA,
                              json={"day_of_week": None, "start_time": "15:00", "end_time": "16:00"})).status_code == 403

    # The engine honors it for Dr A only.
    soon = date.today() + timedelta(days=3)
    slotsA = await get_available_slots(db, biz.id, svc.id, soon, docA.id)
    slotsB = await get_available_slots(db, biz.id, svc.id, soon, docB.id)
    assert not any(time(13, 0) <= s.start_time < time(14, 0) for s in slotsA)  # A's break removed
    assert time(13, 0) in {s.start_time for s in slotsB}                       # B unaffected
    assert len(slotsA) < len(slotsB)


async def test_provider_blocked_time_is_personal(client, db):
    owner, biz, userA, userB, docA, docB, svc = await _bookable_clinic(db, tid=8300)
    hA = f.auth_header(userA.id)
    off = (date.today() + timedelta(days=4)).isoformat()
    r = await client.post(f"{API}/businesses/{biz.id}/staff/{docA.id}/blocked-times", headers=hA,
                          json={"blocked_date": off, "full_day": True, "reason": "day off"})
    assert r.status_code == 200, r.text
    # Cannot block Dr B's calendar.
    assert (await client.post(f"{API}/businesses/{biz.id}/staff/{docB.id}/blocked-times", headers=hA,
                              json={"blocked_date": off, "full_day": True})).status_code == 403
    # Dr A's full-day block clears their slots that day; Dr B still has slots.
    d = date.today() + timedelta(days=4)
    assert await get_available_slots(db, biz.id, svc.id, d, docA.id) == []
    assert len(await get_available_slots(db, biz.id, svc.id, d, docB.id)) > 0
