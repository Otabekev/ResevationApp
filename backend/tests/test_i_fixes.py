"""
Regression tests for the 2026-06 production-readiness pass.

Covers:
  I1. Walk-in (manual) bookings: a second manual booking must NOT 500 on the
      customers.telegram_id unique constraint, and repeat walk-ins with the
      same phone reuse one customer record.
  I2. Staff invite links are built from the bot USERNAME (t.me/<username>),
      never from the bot token.
  I3. Blocked-times API: list endpoint exists, create returns a serializable
      payload (the old schema 500-ed on date→str), delete works, and a
      full-day block actually removes availability.
  I4. Customer language flows from the public booking payload onto the
      customer record (notifications localize correctly).
  I5. Cancelling an already-cancelled booking is rejected (409), not silently
      re-cancelled.
"""
from datetime import date, time, timedelta

import pytest

from tests import factories as f

BOT_HEADERS = {"X-Bot-Secret": "test-bot-secret-shared-32-characters-minimum-000"}


async def _setup_bookable_business(db):
    """Owner + active business with one service, one staff, open hours."""
    from app.models.schedule import WorkingHours

    owner = await f.create_user(db, role="business_owner", telegram_id=111)
    cat = await f.create_category(db)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await f.create_service(db, business_id=biz.id, duration_minutes=30)
    staff = await f.create_staff(db, business_id=biz.id)
    await f.link_staff_service(db, staff_id=staff.id, service_id=svc.id)
    for dow in range(7):
        db.add(WorkingHours(business_id=biz.id, day_of_week=dow,
                            start_time=time(9, 0), end_time=time(18, 0)))
    await db.commit()
    return owner, biz, svc, staff


def _future_date() -> str:
    return (date.today() + timedelta(days=7)).isoformat()


# ── I1: walk-in customers ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_manual_bookings_do_not_collide(client, db):
    owner, biz, svc, staff = await _setup_bookable_business(db)
    headers = f.auth_header(owner.id)

    payload = {
        "service_id": svc.id,
        "staff_id": staff.id,
        "booking_date": _future_date(),
        "start_time": "10:00:00",
        "customer_name": "Walk In One",
        "customer_phone": "+998901111111",
    }
    r1 = await client.post(f"/api/v1/businesses/{biz.id}/bookings", json=payload, headers=headers)
    assert r1.status_code == 201, r1.text

    # Second walk-in with a DIFFERENT phone — the old code died here (unique
    # violation on telegram_id=0 → 500).
    payload2 = {**payload, "start_time": "11:00:00",
                "customer_name": "Walk In Two", "customer_phone": "+998902222222"}
    r2 = await client.post(f"/api/v1/businesses/{biz.id}/bookings", json=payload2, headers=headers)
    assert r2.status_code == 201, r2.text


@pytest.mark.asyncio
async def test_repeat_walkin_same_phone_reuses_customer(client, db):
    owner, biz, svc, staff = await _setup_bookable_business(db)
    headers = f.auth_header(owner.id)

    base = {
        "service_id": svc.id,
        "staff_id": staff.id,
        "booking_date": _future_date(),
        "customer_name": "Regular Guy",
        "customer_phone": "+998903333333",
    }
    r1 = await client.post(f"/api/v1/businesses/{biz.id}/bookings",
                           json={**base, "start_time": "10:00:00"}, headers=headers)
    r2 = await client.post(f"/api/v1/businesses/{biz.id}/bookings",
                           json={**base, "start_time": "12:00:00"}, headers=headers)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["customer_id"] == r2.json()["customer_id"]


# ── I2: invite links ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invite_url_uses_bot_username_not_token(client, db):
    owner, biz, svc, staff = await _setup_bookable_business(db)
    headers = f.auth_header(owner.id)

    r = await client.post(f"/api/v1/businesses/{biz.id}/staff/{staff.id}/invite", headers=headers)
    assert r.status_code == 200, r.text
    url = r.json()["invite_url"]
    assert url.startswith("https://t.me/TestRezerv_bot?start=join_"), url
    assert "123456" not in url  # no fragment of the bot token


# ── I3: blocked times ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_blocked_time_full_day_lifecycle(client, db):
    owner, biz, svc, staff = await _setup_bookable_business(db)
    headers = f.auth_header(owner.id)
    target = _future_date()

    # Slots exist before blocking
    r = await client.get("/api/v1/availability", params={
        "business_id": biz.id, "service_id": svc.id, "date": target})
    assert r.status_code == 200 and len(r.json()) > 0

    # Create a full-day block (old schema 500-ed serializing this response)
    r = await client.post(f"/api/v1/businesses/{biz.id}/blocked-times",
                          json={"blocked_date": target, "reason": "Holiday"}, headers=headers)
    assert r.status_code == 200, r.text
    block = r.json()
    assert block["full_day"] is True
    assert block["blocked_date"] == target

    # It appears in the list endpoint (did not exist before)
    r = await client.get(f"/api/v1/businesses/{biz.id}/blocked-times", headers=headers)
    assert r.status_code == 200
    assert any(b["id"] == block["id"] for b in r.json())

    # Availability is now empty for that date
    r = await client.get("/api/v1/availability", params={
        "business_id": biz.id, "service_id": svc.id, "date": target})
    assert r.status_code == 200 and r.json() == []

    # Delete restores availability
    r = await client.delete(f"/api/v1/businesses/{biz.id}/blocked-times/{block['id']}",
                            headers=headers)
    assert r.status_code == 204
    r = await client.get("/api/v1/availability", params={
        "business_id": biz.id, "service_id": svc.id, "date": target})
    assert len(r.json()) > 0


@pytest.mark.asyncio
async def test_blocked_time_requires_date_or_range(client, db):
    owner, biz, *_ = await _setup_bookable_business(db)
    headers = f.auth_header(owner.id)
    r = await client.post(f"/api/v1/businesses/{biz.id}/blocked-times",
                          json={"reason": "nothing"}, headers=headers)
    assert r.status_code == 422


# ── I4: customer language from public bookings ───────────────────────────────

@pytest.mark.asyncio
async def test_public_booking_persists_customer_language(client, db):
    from sqlalchemy import select
    from app.models.booking import Customer

    owner, biz, svc, staff = await _setup_bookable_business(db)

    r = await client.post("/api/v1/bookings/public", headers=BOT_HEADERS, json={
        "business_id": biz.id,
        "service_id": svc.id,
        "staff_id": staff.id,
        "booking_date": _future_date(),
        "start_time": "14:00:00",
        "customer_name": "Русский Клиент",
        "customer_phone": "+998904444444",
        "telegram_id": 777001,
        "language": "ru",
    })
    assert r.status_code == 201, r.text

    cust = (await db.execute(select(Customer).where(Customer.telegram_id == 777001))).scalar_one()
    assert cust.language == "ru"


# ── I5: double-cancel guard ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_twice_rejected(client, db):
    owner, biz, svc, staff = await _setup_bookable_business(db)
    cust = await f.create_customer(db, telegram_id=888)
    booking = await f.create_booking(
        db, business_id=biz.id, service_id=svc.id, staff_id=staff.id,
        customer_id=cust.id, booking_date=date.today() + timedelta(days=3),
    )
    headers = f.auth_header(owner.id)

    r1 = await client.patch(f"/api/v1/bookings/{booking.id}/cancel", json={}, headers=headers)
    assert r1.status_code == 200
    assert r1.json()["status"] == "cancelled_by_business"

    r2 = await client.patch(f"/api/v1/bookings/{booking.id}/cancel", json={}, headers=headers)
    assert r2.status_code == 409


# ── I6: admin overview recent-activity feed ──────────────────────────────────

@pytest.mark.asyncio
async def test_admin_recent_feed_renders_bookings(client, db):
    """Regression: admin _booking_row read b.booking_time (no such column on the
    Booking model — it's start_time), so the admin overview's /recent feed 500-ed
    the moment any booking existed. The business side was unaffected."""
    owner, biz, svc, staff = await _setup_bookable_business(db)
    cust = await f.create_customer(db, telegram_id=909)
    await f.create_booking(
        db, business_id=biz.id, service_id=svc.id, staff_id=staff.id,
        customer_id=cust.id, booking_date=date.today() + timedelta(days=2),
        start_time=time(10, 0),
    )
    admin = await f.create_user(db, role="super_admin", telegram_id=222)

    r = await client.get("/api/v1/admin/recent", headers=f.auth_header(admin.id))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recent_bookings"], "the booking should appear in the feed"
    assert body["recent_bookings"][0]["booking_time"] == "10:00:00"
