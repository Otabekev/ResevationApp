"""
Pre-launch gate (GET /api/v1/public/launch-status).

Until the configured LAUNCH_DATE the bot's booking flow is closed to the public:
business owners and staff may test during onboarding, everyone else waits. The
endpoint is the single source of truth the bot consults.

  J1. No launch date configured → always open (launched=True).
  J2. Launch date already passed → open for everyone, no telegram_id needed.
  J3. Before launch, a plain customer (or unknown/blank telegram_id) is blocked.
  J4. Before launch, a business OWNER is let through.
  J5. Before launch, an active STAFF member is let through.
  J6. Before launch, an INACTIVE staff member is still blocked.
  J7. Before launch, a platform super-admin is let through (founder testing).
"""
import pytest

from app.config import settings
from tests import factories as f

URL = "/api/v1/public/launch-status"

FUTURE = "2999-01-01"  # safely before launch
PAST = "2000-01-01"    # safely after launch


async def test_j1_no_date_always_open(client, monkeypatch):
    monkeypatch.setattr(settings, "launch_date", "")
    r = await client.get(URL)
    assert r.status_code == 200
    assert r.json() == {"open": True, "launched": True}


async def test_j2_after_launch_open_for_everyone(client, monkeypatch):
    monkeypatch.setattr(settings, "launch_date", PAST)
    r = await client.get(URL)  # no telegram_id at all
    assert r.status_code == 200
    assert r.json() == {"open": True, "launched": True}


async def test_j3_before_launch_customer_blocked(client, db, monkeypatch):
    monkeypatch.setattr(settings, "launch_date", FUTURE)
    customer = await f.create_user(db, role="customer", telegram_id=555001, name="Cust")

    r = await client.get(URL, params={"telegram_id": customer.telegram_id})
    assert r.status_code == 200
    assert r.json() == {"open": False, "launched": False}

    # Unknown id and no-id are likewise blocked pre-launch.
    assert (await client.get(URL, params={"telegram_id": 424242})).json()["open"] is False
    assert (await client.get(URL)).json()["open"] is False


async def test_j4_before_launch_owner_allowed(client, db, monkeypatch):
    monkeypatch.setattr(settings, "launch_date", FUTURE)
    cat = await f.create_category(db)
    owner = await f.create_user(db, role="business_owner", telegram_id=555002, name="Owner")
    await f.create_business(db, owner_id=owner.id, category_id=cat.id)

    r = await client.get(URL, params={"telegram_id": owner.telegram_id})
    assert r.status_code == 200
    assert r.json() == {"open": True, "launched": False}


async def test_j5_before_launch_active_staff_allowed(client, db, monkeypatch):
    monkeypatch.setattr(settings, "launch_date", FUTURE)
    cat = await f.create_category(db)
    owner = await f.create_user(db, role="business_owner", telegram_id=555003, name="Owner")
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)
    member = await f.create_user(db, role="staff", telegram_id=555004, name="Barber")
    await f.create_staff(db, business_id=biz.id, user_id=member.id)

    r = await client.get(URL, params={"telegram_id": member.telegram_id})
    assert r.status_code == 200
    assert r.json()["open"] is True


async def test_j6_before_launch_inactive_staff_blocked(client, db, monkeypatch):
    monkeypatch.setattr(settings, "launch_date", FUTURE)
    cat = await f.create_category(db)
    owner = await f.create_user(db, role="business_owner", telegram_id=555005, name="Owner")
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)
    member = await f.create_user(db, role="customer", telegram_id=555006, name="ExStaff")
    staff = await f.create_staff(db, business_id=biz.id, user_id=member.id)
    staff.is_active = False
    await db.commit()

    r = await client.get(URL, params={"telegram_id": member.telegram_id})
    assert r.status_code == 200
    assert r.json()["open"] is False


async def test_j7_before_launch_super_admin_allowed(client, monkeypatch):
    # conftest sets SUPER_ADMIN_TELEGRAM_IDS=999000999. No business needed — the
    # founder's account gets in by super-admin id alone.
    monkeypatch.setattr(settings, "launch_date", FUTURE)
    r = await client.get(URL, params={"telegram_id": 999000999})
    assert r.status_code == 200
    assert r.json() == {"open": True, "launched": False}
