"""
Admin operator-control endpoints: user search + ban, needs-attention,
booking lookup, insights, system-health.
"""
from datetime import time

from app.models.schedule import WorkingHours
from tests import factories as f


async def test_admin_users_search_and_ban(client, db):
    admin = await f.create_user(db, role="super_admin", telegram_id=999, name="Boss")
    u = await f.create_user(db, role="customer", telegram_id=555, name="Spammer")
    hdr = f.auth_header(admin.id)

    r = await client.get("/api/v1/admin/users", params={"q": "Spam"}, headers=hdr)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1 and any(x["name"] == "Spammer" and "is_active" in x for x in body["items"])

    rb = await client.patch(f"/api/v1/admin/users/{u.id}/active", json={"is_active": False}, headers=hdr)
    assert rb.status_code == 200 and rb.json()["is_active"] is False
    await db.refresh(u)
    assert u.is_active is False

    # A banned user's token is rejected on the next request (get_current_user re-checks).
    r401 = await client.get("/api/v1/businesses/mine", headers=f.auth_header(u.id))
    assert r401.status_code == 401


async def test_admin_cannot_ban_self_or_superadmin(client, db):
    admin = await f.create_user(db, role="super_admin", telegram_id=999)
    admin2 = await f.create_user(db, role="super_admin", telegram_id=998)
    hdr = f.auth_header(admin.id)
    assert (await client.patch(f"/api/v1/admin/users/{admin.id}/active",
                               json={"is_active": False}, headers=hdr)).status_code == 400
    assert (await client.patch(f"/api/v1/admin/users/{admin2.id}/active",
                               json={"is_active": False}, headers=hdr)).status_code == 403


async def test_admin_needs_attention_flags_incomplete(client, db):
    admin = await f.create_user(db, role="super_admin", telegram_id=999)
    owner = await f.create_user(db, role="business_owner", telegram_id=1)
    cat = await f.create_category(db)

    good = await f.create_business(db, owner_id=owner.id, category_id=cat.id, name="Good", status="active")
    good.latitude, good.longitude = 40.86, 71.16
    svc = await f.create_service(db, business_id=good.id)
    await f.create_staff(db, business_id=good.id)
    db.add(WorkingHours(business_id=good.id, day_of_week=0, start_time=time(9, 0), end_time=time(18, 0)))

    await f.create_business(db, owner_id=owner.id, category_id=cat.id, name="Empty", status="active")
    await db.commit()

    r = await client.get("/api/v1/admin/needs-attention", headers=f.auth_header(admin.id))
    assert r.status_code == 200, r.text
    items = {i["name"]: i for i in r.json()["items"]}
    assert "Good" not in items  # fully set up → not flagged
    assert set(items["Empty"]["missing"]) == {"services", "staff", "hours", "location"}


async def test_admin_booking_search(client, db):
    admin = await f.create_user(db, role="super_admin", telegram_id=999)
    owner = await f.create_user(db, role="business_owner", telegram_id=1)
    cat = await f.create_category(db)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await f.create_service(db, business_id=biz.id)
    st = await f.create_staff(db, business_id=biz.id)
    cust = await f.create_customer(db, telegram_id=5, phone="+998901112233")
    await f.create_booking(db, business_id=biz.id, service_id=svc.id, staff_id=st.id,
                           customer_id=cust.id, customer_phone="+998901112233", customer_name="Ali")

    r = await client.get("/api/v1/admin/bookings/search", params={"q": "901112233"},
                         headers=f.auth_header(admin.id))
    assert r.status_code == 200 and r.json()["total"] == 1, r.text
    assert r.json()["items"][0]["customer_phone"] == "+998901112233"


async def test_admin_insights_and_health(client, db):
    admin = await f.create_user(db, role="super_admin", telegram_id=999)
    hdr = f.auth_header(admin.id)

    ins = await client.get("/api/v1/admin/insights", headers=hdr)
    assert ins.status_code == 200, ins.text
    body = ins.json()
    assert len(body["daily_last_7_days"]) == 7
    assert "no_show_rate_percent" in body and "top_businesses" in body

    h = await client.get("/api/v1/admin/system-health", headers=hdr)
    assert h.status_code == 200 and h.json()["db"] is True
