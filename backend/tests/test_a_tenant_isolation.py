"""
Category A — multi-tenant isolation & authorization (IDOR).

These tests assert the SECURE behaviour. They are expected to FAIL against the
current code (proving the vulnerability) and PASS after the fixes.
"""
import pytest

from tests.factories import (
    auth_header, create_booking, create_business, create_category,
    create_customer, create_service, create_staff, create_user,
)

API = "/api/v1"


# ── A1: customer bookings must not be world-readable by telegram_id ───────────

async def test_customer_bookings_requires_auth(client, db):
    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=111, name="Owner")
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await create_service(db, business_id=biz.id)
    staff = await create_staff(db, business_id=biz.id)
    cust = await create_customer(db, telegram_id=555, phone="+998901112233")
    await create_booking(db, business_id=biz.id, service_id=svc.id, staff_id=staff.id, customer_id=cust.id)

    # No credentials at all → must not leak the customer's bookings / phone.
    resp = await client.get(f"{API}/customers/555/bookings")
    assert resp.status_code == 401, resp.text


async def test_customer_cannot_read_another_customers_bookings(client, db):
    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=111, name="Owner")
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await create_service(db, business_id=biz.id)
    staff = await create_staff(db, business_id=biz.id)
    victim = await create_customer(db, telegram_id=555, phone="+998905554433")
    await create_booking(db, business_id=biz.id, service_id=svc.id, staff_id=staff.id, customer_id=victim.id)

    # Attacker is a legitimately-authenticated user, but for a different telegram_id.
    attacker = await create_user(db, role="customer", telegram_id=777, name="Attacker")
    resp = await client.get(f"{API}/customers/555/bookings", headers=auth_header(attacker.id))
    assert resp.status_code in (403, 404), resp.text
    assert "+998905554433" not in resp.text


# ── A2: public booking endpoint must require the bot's shared secret ──────────

async def test_public_booking_rejected_without_bot_secret(client, db):
    body = {
        "business_id": 1, "service_id": 1, "booking_date": "2030-01-01",
        "start_time": "10:00:00", "customer_name": "X", "customer_phone": "+998900000000",
        "telegram_id": 555,
    }
    resp = await client.post(f"{API}/bookings/public", json=body)
    assert resp.status_code in (401, 403), resp.text


async def test_public_booking_rejected_with_wrong_bot_secret(client, db):
    body = {
        "business_id": 1, "service_id": 1, "booking_date": "2030-01-01",
        "start_time": "10:00:00", "customer_name": "X", "customer_phone": "+998900000000",
        "telegram_id": 555,
    }
    resp = await client.post(f"{API}/bookings/public", json=body, headers={"X-Bot-Secret": "wrong"})
    assert resp.status_code in (401, 403), resp.text


# ── A3: review submission must require the bot's shared secret ────────────────

async def test_review_rejected_without_bot_secret(client, db):
    body = {"booking_id": 1, "rating": 5, "telegram_id": 555}
    resp = await client.post(f"{API}/reviews", json=body)
    assert resp.status_code in (401, 403), resp.text


# ── A4: admin user list must not leak password hashes ────────────────────────

async def test_admin_users_does_not_leak_password_hash(client, db):
    admin = await create_user(db, role="super_admin", telegram_id=999000999, name="Admin")
    leaky = await create_user(db, role="business_owner", telegram_id=222, name="Owner")
    leaky.hashed_password = "$2b$12$SECRETHASHSHOULDNOTLEAK"
    await db.commit()

    resp = await client.get(f"{API}/admin/users", headers=auth_header(admin.id))
    assert resp.status_code == 200, resp.text
    assert "hashed_password" not in resp.text
    assert "SECRETHASHSHOULDNOTLEAK" not in resp.text


# ── A5: full business record must not be world-readable ──────────────────────

async def test_get_business_requires_auth(client, db):
    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=111)
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)

    resp = await client.get(f"{API}/businesses/{biz.id}")
    assert resp.status_code == 401, resp.text


async def test_get_business_forbidden_cross_tenant(client, db):
    cat = await create_category(db)
    owner_a = await create_user(db, role="business_owner", telegram_id=111, name="A")
    owner_b = await create_user(db, role="business_owner", telegram_id=222, name="B")
    biz_a = await create_business(db, owner_id=owner_a.id, category_id=cat.id, name="A-Biz")
    await create_business(db, owner_id=owner_b.id, category_id=cat.id, name="B-Biz")

    resp = await client.get(f"{API}/businesses/{biz_a.id}", headers=auth_header(owner_b.id))
    assert resp.status_code in (403, 404), resp.text


# ── A6 (regression matrix): owner B is denied on business A's resources ───────

@pytest.fixture
async def two_tenants(db):
    cat = await create_category(db)
    owner_a = await create_user(db, role="business_owner", telegram_id=111, name="A")
    owner_b = await create_user(db, role="business_owner", telegram_id=222, name="B")
    biz_a = await create_business(db, owner_id=owner_a.id, category_id=cat.id, name="A-Biz")
    biz_b = await create_business(db, owner_id=owner_b.id, category_id=cat.id, name="B-Biz")
    return {"owner_a": owner_a, "owner_b": owner_b, "biz_a": biz_a, "biz_b": biz_b}


async def test_cross_tenant_bookings_list_forbidden(client, two_tenants):
    a, b = two_tenants["biz_a"], two_tenants["owner_b"]
    resp = await client.get(f"{API}/businesses/{a.id}/bookings", headers=auth_header(b.id))
    assert resp.status_code in (403, 404), resp.text


async def test_cross_tenant_business_update_forbidden(client, two_tenants):
    a, b = two_tenants["biz_a"], two_tenants["owner_b"]
    resp = await client.patch(f"{API}/businesses/{a.id}", json={"name": "Hacked"}, headers=auth_header(b.id))
    assert resp.status_code in (403, 404), resp.text


async def test_cross_tenant_analytics_forbidden(client, two_tenants):
    a, b = two_tenants["biz_a"], two_tenants["owner_b"]
    resp = await client.get(f"{API}/businesses/{a.id}/analytics", headers=auth_header(b.id))
    assert resp.status_code in (403, 404), resp.text


async def test_cross_tenant_service_create_forbidden(client, two_tenants):
    a, b = two_tenants["biz_a"], two_tenants["owner_b"]
    body = {"name_uz": "x", "name_ru": "x", "name_en": "x", "duration_minutes": 30}
    resp = await client.post(f"{API}/businesses/{a.id}/services", json=body, headers=auth_header(b.id))
    assert resp.status_code in (403, 404), resp.text
