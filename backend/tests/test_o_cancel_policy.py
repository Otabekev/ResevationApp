"""
Cancellation policy (cancellation_policy_hours).

Policy: a customer may ALWAYS cancel (freeing the slot beats a silent no-show),
but a cancel INSIDE the policy window flags the owner's notification as late.

  O1. Late customer cancel (inside the window) → allowed (200) + owner alert
      carries the late warning.
  O2. Early customer cancel (outside the window) → allowed + owner alert has NO
      late warning.
"""
from datetime import datetime, timedelta, timezone

from app.timeutils import PLATFORM_TZ
from tests import factories as f


async def _setup(db, *, hours_out, telegram_base, policy=2):
    cat = await f.create_category(db)
    owner = await f.create_user(db, role="business_owner", telegram_id=telegram_base, name="Owner")
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)
    biz.cancellation_policy_hours = policy
    svc = await f.create_service(db, business_id=biz.id)
    # Customer needs BOTH a User (to authenticate) and a Customer row (the booking).
    cust_user = await f.create_user(db, role="customer", telegram_id=telegram_base + 1, name="Cust")
    cust = await f.create_customer(db, telegram_id=telegram_base + 1)
    apt = (datetime.now(timezone.utc) + timedelta(hours=hours_out)).astimezone(PLATFORM_TZ)
    booking = await f.create_booking(
        db, business_id=biz.id, service_id=svc.id, staff_id=None, customer_id=cust.id,
        booking_date=apt.date(), start_time=apt.time().replace(second=0, microsecond=0),
        status="confirmed",
    )
    await db.commit()
    return owner, cust_user, booking


def _capture(monkeypatch):
    sent = []

    async def _send(chat_id, text, *a, **k):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr("app.routers.bookings.send_telegram_message", _send)
    return sent


async def test_o1_late_cancel_allowed_and_flags_owner(client, db, monkeypatch):
    sent = _capture(monkeypatch)
    owner, cust_user, booking = await _setup(db, hours_out=1, telegram_base=8001, policy=2)

    r = await client.patch(
        f"/api/v1/bookings/{booking.id}/cancel",
        headers=f.auth_header(cust_user.id),
        json={"reason": "can't make it"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled_by_customer"  # allowed, not blocked

    owner_msgs = [txt for (cid, txt) in sent if cid == owner.telegram_id]
    assert owner_msgs, "owner should be notified"
    assert "Kech" in owner_msgs[0], f"expected late flag, got: {owner_msgs[0]!r}"


async def test_o2_early_cancel_allowed_no_late_flag(client, db, monkeypatch):
    sent = _capture(monkeypatch)
    owner, cust_user, booking = await _setup(db, hours_out=8, telegram_base=8010, policy=2)

    r = await client.patch(
        f"/api/v1/bookings/{booking.id}/cancel",
        headers=f.auth_header(cust_user.id),
        json={"reason": "changed plans"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled_by_customer"

    owner_msgs = [txt for (cid, txt) in sent if cid == owner.telegram_id]
    assert owner_msgs, "owner should still be notified"
    assert "Kech" not in owner_msgs[0], f"early cancel must NOT be flagged late: {owner_msgs[0]!r}"
