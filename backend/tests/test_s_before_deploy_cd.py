"""
Deploy C + D (scale hardening / polish) regression tests. Grows batch by batch.

  C6. Staff list returns service_ids (now batch-loaded — no N+1).
  C8. Public booking normalizes/validates the phone server-side (junk → 422).
  D7. Two walk-ins with the same phone but different names stay distinct records.
"""
from datetime import date, time, timedelta

from tests import factories as f

BOT_HEADERS = {"X-Bot-Secret": "test-bot-secret-shared-32-characters-minimum-000"}


def _future_date() -> str:
    return (date.today() + timedelta(days=7)).isoformat()


# ── C8: public booking phone validation ───────────────────────────────────────

async def test_c8_public_booking_rejects_junk_phone(client):
    r = await client.post("/api/v1/bookings/public", headers=BOT_HEADERS, json={
        "business_id": 1, "service_id": 1,
        "booking_date": _future_date(), "start_time": "10:00:00",
        "customer_name": "X", "customer_phone": "asdf",
        "telegram_id": 1, "language": "uz",
    })
    assert r.status_code == 422, r.text


# ── C6: staff list is batch-loaded and still carries service_ids ──────────────

async def test_c6_list_staff_returns_service_ids(client, db):
    owner = await f.create_user(db, role="business_owner", telegram_id=111)
    cat = await f.create_category(db)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await f.create_service(db, business_id=biz.id)
    s1 = await f.create_staff(db, business_id=biz.id, name="A")
    s2 = await f.create_staff(db, business_id=biz.id, name="B")
    await f.link_staff_service(db, staff_id=s1.id, service_id=svc.id)

    r = await client.get(f"/api/v1/businesses/{biz.id}/staff", headers=f.auth_header(owner.id))
    assert r.status_code == 200, r.text
    by_name = {s["name"]: s for s in r.json()}
    assert by_name["A"]["service_ids"] == [svc.id]
    assert by_name["B"]["service_ids"] == []


# ── D7: shared-phone walk-ins with different names stay distinct ──────────────

async def test_d7_shared_phone_different_names_stay_distinct(client, db):
    from app.models.schedule import WorkingHours
    owner = await f.create_user(db, role="business_owner", telegram_id=111)
    cat = await f.create_category(db)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="active")
    svc = await f.create_service(db, business_id=biz.id, duration_minutes=30)
    staff = await f.create_staff(db, business_id=biz.id)
    await f.link_staff_service(db, staff_id=staff.id, service_id=svc.id)
    for dow in range(7):
        db.add(WorkingHours(business_id=biz.id, day_of_week=dow,
                            start_time=time(9, 0), end_time=time(18, 0)))
    await db.commit()

    base = {"service_id": svc.id, "staff_id": staff.id, "booking_date": _future_date(),
            "customer_phone": "+998901112233"}
    r1 = await client.post(f"/api/v1/businesses/{biz.id}/bookings", headers=f.auth_header(owner.id),
                           json={**base, "start_time": "10:00:00", "customer_name": "Ali"})
    r2 = await client.post(f"/api/v1/businesses/{biz.id}/bookings", headers=f.auth_header(owner.id),
                           json={**base, "start_time": "11:00:00", "customer_name": "Vali"})
    assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
    assert r1.json()["customer_id"] != r2.json()["customer_id"], "different people must not merge"


# ── C7: public business browse is paginated ───────────────────────────────────

async def test_c7_public_businesses_respects_limit(client, db):
    owner = await f.create_user(db, role="business_owner", telegram_id=111)
    cat = await f.create_category(db)
    for i in range(3):
        await f.create_business(db, owner_id=owner.id, category_id=cat.id,
                                name=f"Biz{i}", status="active")
    r = await client.get("/api/v1/public/businesses", params={"limit": 2})
    assert r.status_code == 200 and len(r.json()) == 2, r.text


# ── H3: admin business list is paginated + server-side searchable ─────────────

async def test_h3_admin_businesses_paginated_and_searchable(client, db):
    admin = await f.create_user(db, role="super_admin", telegram_id=999)
    owner = await f.create_user(db, role="business_owner", telegram_id=1)
    cat = await f.create_category(db)
    for i in range(25):
        await f.create_business(db, owner_id=owner.id, category_id=cat.id,
                                name=f"Shop{i:02d}", status="active")
    hdr = f.auth_header(admin.id)

    r1 = await client.get("/api/v1/admin/businesses", params={"page": 1, "page_size": 20}, headers=hdr)
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["total"] == 25 and len(body["items"]) == 20  # capped page, true total

    r2 = await client.get("/api/v1/admin/businesses", params={"page": 2, "page_size": 20}, headers=hdr)
    assert len(r2.json()["items"]) == 5  # the remainder is reachable

    r3 = await client.get("/api/v1/admin/businesses", params={"q": "Shop23"}, headers=hdr)
    assert r3.json()["total"] == 1 and r3.json()["items"][0]["name"] == "Shop23"  # search hits any page
