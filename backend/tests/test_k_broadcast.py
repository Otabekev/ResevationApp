"""
Broadcast / announcements (super-admin → bot users).

  K1. Audience counts exclude users with no Telegram, inactive users, and the
      super-admin themselves; each audience targets the right roles.
  K2. "Send now" creates a row (no schedule) and dispatches delivery.
  K3. A future schedule stores scheduled_at and does NOT dispatch immediately.
  K4. A scheduled broadcast can be cancelled; cancelling a non-scheduled one 400s.
  K5. "Send test to me" delivers only to the calling admin.
  K6. Non-super-admins are rejected (403).
  K7. run_broadcast delivers to every recipient and records the tally.
"""
import pytest

from app.models.broadcast import Broadcast
from app.services import broadcast_service
from tests import factories as f

URL = "/api/v1/admin"


async def _admin(db):
    return await f.create_user(db, role="super_admin", telegram_id=9000, name="Founder")


async def _seed_users(db):
    """4 reachable users (2 owners/staff, 2 customers) + 3 that must be excluded."""
    await f.create_user(db, role="business_owner", telegram_id=101, name="Owner")
    await f.create_user(db, role="staff", telegram_id=102, name="Barber")
    await f.create_user(db, role="customer", telegram_id=103, name="Cust1")
    await f.create_user(db, role="customer", telegram_id=104, name="Cust2")
    await f.create_user(db, role="customer", telegram_id=None, name="NoTg")  # no Telegram
    inactive = await f.create_user(db, role="customer", telegram_id=105, name="Inactive")
    inactive.is_active = False
    await db.commit()


async def test_k1_audience_counts(client, db):
    admin = await _admin(db)
    await _seed_users(db)

    r = await client.get(f"{URL}/broadcast/audience-counts", headers=f.auth_header(admin.id))
    assert r.status_code == 200
    # super-admin (9000) excluded from all; no-Telegram and inactive excluded.
    assert r.json() == {"all": 4, "owners_staff": 2, "customers": 2}


async def test_k2_send_now_dispatches(client, db, monkeypatch):
    admin = await _admin(db)
    await _seed_users(db)

    dispatched = []
    async def _rec(bid):
        dispatched.append(bid)
    monkeypatch.setattr(broadcast_service, "run_broadcast", _rec)

    r = await client.post(
        f"{URL}/broadcast",
        headers=f.auth_header(admin.id),
        json={"audience": "all", "text": "We are live!"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["scheduled_at"] is None
    assert body["total_recipients"] == 4
    assert dispatched == [body["id"]]  # background delivery was kicked off


async def test_k3_future_schedule_not_dispatched(client, db, monkeypatch):
    admin = await _admin(db)
    await _seed_users(db)

    dispatched = []
    async def _rec(bid):
        dispatched.append(bid)
    monkeypatch.setattr(broadcast_service, "run_broadcast", _rec)

    r = await client.post(
        f"{URL}/broadcast",
        headers=f.auth_header(admin.id),
        json={"audience": "owners_staff", "text": "Heads up", "scheduled_at": "2999-01-01T09:00:00"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["scheduled_at"] is not None
    assert body["status"] == "scheduled"
    assert dispatched == []  # nothing sent now


async def test_k4_cancel_scheduled(client, db, monkeypatch):
    admin = await _admin(db)
    monkeypatch.setattr(broadcast_service, "run_broadcast", lambda bid: None)

    created = await client.post(
        f"{URL}/broadcast",
        headers=f.auth_header(admin.id),
        json={"audience": "all", "text": "later", "scheduled_at": "2999-01-01T09:00:00"},
    )
    bid = created.json()["id"]

    r = await client.post(f"{URL}/broadcasts/{bid}/cancel", headers=f.auth_header(admin.id))
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"

    # Cancelling again (no longer 'scheduled') is rejected.
    r2 = await client.post(f"{URL}/broadcasts/{bid}/cancel", headers=f.auth_header(admin.id))
    assert r2.status_code == 400


async def test_k5_test_send_to_self(client, db, monkeypatch):
    admin = await _admin(db)
    sent = []
    async def _send(chat_id, text, parse_mode="HTML"):
        sent.append((chat_id, text))
        return True
    monkeypatch.setattr(broadcast_service, "send_telegram_message", _send)

    r = await client.post(
        f"{URL}/broadcast/test",
        headers=f.auth_header(admin.id),
        json={"text": "preview me"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert sent == [(9000, "preview me")]


async def test_k6_non_admin_forbidden(client, db):
    owner = await f.create_user(db, role="business_owner", telegram_id=200, name="Owner")
    r = await client.get(f"{URL}/broadcast/audience-counts", headers=f.auth_header(owner.id))
    assert r.status_code == 403


async def test_k7_run_broadcast_delivers_and_tallies(db, sessionmaker_, monkeypatch):
    admin = await _admin(db)
    await _seed_users(db)
    b = Broadcast(created_by=admin.id, audience="customers", text="hi customers", status="scheduled")
    db.add(b)
    await db.commit()
    await db.refresh(b)

    sent = []
    async def _send(chat_id, text, parse_mode="HTML"):
        sent.append(chat_id)
        return True
    # Point the sender's own session factory at the test DB and stub Telegram.
    monkeypatch.setattr(broadcast_service, "AsyncSessionLocal", sessionmaker_)
    monkeypatch.setattr(broadcast_service, "send_telegram_message", _send)
    monkeypatch.setattr(broadcast_service, "_SEND_INTERVAL_S", 0)

    await broadcast_service.run_broadcast(b.id)

    assert sorted(sent) == [103, 104]  # the two customers only
    refreshed = await db.get(Broadcast, b.id)
    await db.refresh(refreshed)
    assert refreshed.status == "done"
    assert refreshed.total_recipients == 2
    assert refreshed.sent_count == 2
    assert refreshed.failed_count == 0


async def test_k8_customers_audience_reaches_customers_table(db, sessionmaker_, monkeypatch):
    """Regression: real customers live in the `customers` table (created when they
    book via the bot), NOT `users`. The customers/all audiences must reach them,
    dedup against a User with the same telegram_id, and never include the founder
    even when they also have a customer record. Previously this queried `users`
    for role=customer and reported 0 sent."""
    from app.models.booking import Customer

    admin = await _admin(db)  # super-admin, telegram_id 9000
    db.add_all([
        Customer(telegram_id=501, name="RealCust"),
        Customer(telegram_id=502, name="RealCust2"),
        Customer(telegram_id=None, name="WalkIn"),        # no Telegram → excluded
        Customer(telegram_id=9000, name="FounderAsCust"),  # super-admin → excluded
    ])
    # An owner who *also* booked once (same telegram_id 501) — must dedup.
    await f.create_user(db, role="business_owner", telegram_id=501, name="OwnerWhoBooks")
    await db.commit()

    counts = await broadcast_service.count_audiences(db)
    assert counts["customers"] == 2     # {501, 502}; 9000 + NULL excluded
    assert counts["owners_staff"] == 1  # {501}
    assert counts["all"] == 2           # {501, 502} after dedup

    b = Broadcast(created_by=admin.id, audience="all", text="hello everyone", status="scheduled")
    db.add(b)
    await db.commit()
    await db.refresh(b)

    sent = []
    async def _send(chat_id, text, parse_mode="HTML"):
        sent.append(chat_id)
        return True
    monkeypatch.setattr(broadcast_service, "AsyncSessionLocal", sessionmaker_)
    monkeypatch.setattr(broadcast_service, "send_telegram_message", _send)
    monkeypatch.setattr(broadcast_service, "_SEND_INTERVAL_S", 0)

    await broadcast_service.run_broadcast(b.id)

    assert sorted(sent) == [501, 502]   # each once; founder (9000) never messaged
    refreshed = await db.get(Broadcast, b.id)
    await db.refresh(refreshed)
    assert refreshed.sent_count == 2
    assert refreshed.failed_count == 0
