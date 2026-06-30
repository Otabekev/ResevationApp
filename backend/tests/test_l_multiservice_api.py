"""
Multi-service bookings — Phase 3 (endpoints).

The engine already supports multi-service (tested in test_d_booking.py D7); these
cover the API surface that exposes it:

  L1. allow_multi_service is settable via PATCH and shown on BusinessOut + the
      public profile.
  L2. /public/businesses/{id}/staff returns each staff's service_ids.
  L3. /availability with repeated service_ids sizes slots to the combined block.
  L4. A public booking with service_ids (toggle ON) links every service.
  L5. With the toggle OFF, extra service_ids are ignored — only the primary books.
"""
from datetime import date, time, timedelta

from sqlalchemy import func, select

from app.models.booking import booking_services
from app.models.schedule import WorkingHours
from tests import factories as f

BOT_HEADERS = {"X-Bot-Secret": "test-bot-secret-shared-32-characters-minimum-000"}


async def _multi_biz(db, *, allow_multi, telegram_id, durations=(30, 20)):
    """Active business + one staff who can do every service, open 9–18 daily."""
    cat = await f.create_category(db)
    owner = await f.create_user(db, role="business_owner", telegram_id=telegram_id)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)
    biz.allow_multi_service = allow_multi
    svcs = [await f.create_service(db, business_id=biz.id, duration_minutes=d) for d in durations]
    staff = await f.create_staff(db, business_id=biz.id)
    for s in svcs:
        await f.link_staff_service(db, staff_id=staff.id, service_id=s.id)
    for dow in range(7):
        db.add(WorkingHours(business_id=biz.id, day_of_week=dow, start_time=time(9, 0), end_time=time(18, 0)))
    await db.commit()
    return owner, biz, svcs, staff


async def test_l1_toggle_settable_and_exposed(client, db):
    owner = await f.create_user(db, role="business_owner", telegram_id=701)
    cat = await f.create_category(db)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)

    r = await client.patch(
        f"/api/v1/businesses/{biz.id}",
        headers=f.auth_header(owner.id),
        json={"allow_multi_service": True},
    )
    assert r.status_code == 200
    assert r.json()["allow_multi_service"] is True

    pub = await client.get(f"/api/v1/businesses/{biz.id}/public")
    assert pub.status_code == 200
    assert pub.json()["allow_multi_service"] is True


async def test_l2_public_staff_includes_service_ids(client, db):
    _, biz, (svc1, svc2), staff = await _multi_biz(db, allow_multi=True, telegram_id=702)

    r = await client.get(f"/api/v1/public/businesses/{biz.id}/staff")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["id"] == staff.id
    assert sorted(rows[0]["service_ids"]) == sorted([svc1.id, svc2.id])


async def test_l3_availability_combined_duration(client, db):
    _, biz, (svc1, svc2), staff = await _multi_biz(db, allow_multi=True, telegram_id=703)
    soon = (date.today() + timedelta(days=3)).isoformat()

    r = await client.get(
        "/api/v1/availability",
        params={
            "business_id": biz.id, "service_id": svc1.id, "date": soon,
            "service_ids": [svc1.id, svc2.id],
        },
    )
    assert r.status_code == 200
    slots = r.json()
    assert slots, "expected slots for the 50-minute combined block"
    sh, sm = map(int, slots[0]["start_time"].split(":"))
    eh, em = map(int, slots[0]["end_time"].split(":"))
    assert (eh * 60 + em) - (sh * 60 + sm) == 50


async def test_l4_public_booking_links_all_services(client, db):
    _, biz, (svc1, svc2), staff = await _multi_biz(db, allow_multi=True, telegram_id=704)
    soon = (date.today() + timedelta(days=3)).isoformat()

    avail = await client.get(
        "/api/v1/availability",
        params={"business_id": biz.id, "service_id": svc1.id, "date": soon,
                "service_ids": [svc1.id, svc2.id]},
    )
    start = avail.json()[0]["start_time"]

    r = await client.post(
        "/api/v1/bookings/public",
        headers=BOT_HEADERS,
        json={
            "business_id": biz.id, "service_id": svc1.id, "service_ids": [svc1.id, svc2.id],
            "booking_date": soon, "start_time": f"{start}:00",
            "customer_name": "Multi", "customer_phone": "+998901112233", "telegram_id": 9904,
        },
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    linked = (await db.execute(
        select(booking_services.c.service_id).where(booking_services.c.booking_id == bid)
    )).scalars().all()
    assert sorted(linked) == sorted([svc1.id, svc2.id])


async def test_l5_toggle_off_ignores_extra_services(client, db):
    _, biz, (svc1, svc2), staff = await _multi_biz(db, allow_multi=False, telegram_id=705)
    soon = (date.today() + timedelta(days=3)).isoformat()

    # With the toggle off, slots are sized to the single primary service (30 min).
    avail = await client.get(
        "/api/v1/availability",
        params={"business_id": biz.id, "service_id": svc1.id, "date": soon},
    )
    start = avail.json()[0]["start_time"]

    r = await client.post(
        "/api/v1/bookings/public",
        headers=BOT_HEADERS,
        json={
            "business_id": biz.id, "service_id": svc1.id, "service_ids": [svc1.id, svc2.id],
            "booking_date": soon, "start_time": f"{start}:00",
            "customer_name": "Solo", "customer_phone": "+998901112244", "telegram_id": 9905,
        },
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    linked = (await db.execute(
        select(booking_services.c.service_id).where(booking_services.c.booking_id == bid)
    )).scalars().all()
    assert linked == [svc1.id]  # extra service dropped — toggle is authoritative


async def test_l6_set_staff_services_adds_to_existing(client, db):
    """Regression: a provider already assigned service A re-saves the set as
    [A, B]. The endpoint must not 500 on the uq_staff_services unique constraint
    — a blanket delete-then-reinsert flushes INSERT(A) before DELETE(old A) and
    collides. This is the 'something went wrong' the owner hit when adding a 2nd
    service to themselves."""
    owner = await f.create_user(db, role="business_owner", telegram_id=706)
    cat = await f.create_category(db)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)
    svc_a = await f.create_service(db, business_id=biz.id, name="A")
    svc_b = await f.create_service(db, business_id=biz.id, name="B")
    staff = await f.create_staff(db, business_id=biz.id, user_id=owner.id)
    await f.link_staff_service(db, staff_id=staff.id, service_id=svc_a.id)
    await db.commit()

    base = f"/api/v1/businesses/{biz.id}/staff/{staff.id}/services"
    hdr = f.auth_header(owner.id)

    # Add B while keeping the already-assigned A — used to 500.
    r = await client.put(base, headers=hdr, json=[svc_a.id, svc_b.id])
    assert r.status_code == 200, r.text
    assert sorted(r.json()["service_ids"]) == sorted([svc_a.id, svc_b.id])

    # Re-saving the identical set is idempotent (still no collision).
    r_again = await client.put(base, headers=hdr, json=[svc_a.id, svc_b.id])
    assert r_again.status_code == 200, r_again.text
    assert sorted(r_again.json()["service_ids"]) == sorted([svc_a.id, svc_b.id])

    # Removing one diffs cleanly down to just A.
    r_rm = await client.put(base, headers=hdr, json=[svc_a.id])
    assert r_rm.status_code == 200, r_rm.text
    assert r_rm.json()["service_ids"] == [svc_a.id]


async def test_l7_bookings_list_shows_all_services(client, db):
    """Regression: the owner's bookings list (and the web/bot display it feeds)
    must show EVERY service of a multi-service booking, not just the primary."""
    owner, biz, (svc1, svc2), staff = await _multi_biz(db, allow_multi=True, telegram_id=707)
    svc1.name_uz = "Soch olish"
    svc2.name_uz = "Soqol olish"
    await db.commit()
    soon = (date.today() + timedelta(days=3)).isoformat()

    avail = await client.get(
        "/api/v1/availability",
        params={"business_id": biz.id, "service_id": svc1.id, "date": soon,
                "service_ids": [svc1.id, svc2.id]},
    )
    start = avail.json()[0]["start_time"]
    booked = await client.post(
        "/api/v1/bookings/public",
        headers=BOT_HEADERS,
        json={"business_id": biz.id, "service_id": svc1.id, "service_ids": [svc1.id, svc2.id],
              "booking_date": soon, "start_time": f"{start}:00",
              "customer_name": "Multi", "customer_phone": "+998901112255", "telegram_id": 9907},
    )
    assert booked.status_code == 201, booked.text

    lst = await client.get(f"/api/v1/businesses/{biz.id}/bookings", headers=f.auth_header(owner.id))
    assert lst.status_code == 200
    name = lst.json()[0]["service_name_uz"]
    assert "Soch olish" in name and "Soqol olish" in name, name  # both shown
    assert name.startswith("Soch olish")  # primary first
