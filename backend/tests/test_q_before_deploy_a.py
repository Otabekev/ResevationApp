"""
Deploy A (before-deployment fixes) regression tests.

  A1. Growth feed accepts the secret via the X-Growth-Secret header (not just the
      logged query string); wrong header still 403s.
  A2. Trial enforcement — the expiry sweep suspends lapsed trials ONLY; the
      record-payment endpoint activates the business + logs a Subscription;
      approving into trial (re)starts the 14-day window.
  A3. Business-status gate — suspended/blocked businesses serve no availability and
      reject bookings (public + manual); active still works.
  A4. Booking status state-machine — terminal bookings can't be resurrected;
      re-applying the same status is a no-op; legal forward transitions still work.
"""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.models.business import Business
from app.models.subscription import Subscription
from app.routers import admin
from app.services import scheduler
from tests import factories as f

BOT_HEADERS = {"X-Bot-Secret": "test-bot-secret-shared-32-characters-minimum-000"}


async def _setup_bookable_business(db, *, status="active", telegram_id=111):
    """Owner + business (given status) with one service, one staff, open hours."""
    from app.models.schedule import WorkingHours

    owner = await f.create_user(db, role="business_owner", telegram_id=telegram_id)
    cat = await f.create_category(db)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status=status)
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


def _reset_growth_cache():
    admin._growth_cache["data"] = None
    admin._growth_cache["at"] = 0.0


# ── A1: growth feed header auth ───────────────────────────────────────────────

async def test_a1_growth_accepts_header_secret(client, db, monkeypatch):
    monkeypatch.setattr(settings, "growth_secret", "hdr-secret")
    _reset_growth_cache()
    # Seed one located business so the 200 path renders real data.
    owner = await f.create_user(db, role="business_owner", telegram_id=1)
    cat = await f.create_category(db)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, name="Pop Barber")
    biz.latitude, biz.longitude = 40.86, 71.16
    await db.commit()

    ok = await client.get("/api/v1/admin/growth", headers={"X-Growth-Secret": "hdr-secret"})
    assert ok.status_code == 200, ok.text
    assert any(b["name"] == "Pop Barber" for b in ok.json()["businesses"])


async def test_a1_growth_rejects_wrong_header(client, monkeypatch):
    monkeypatch.setattr(settings, "growth_secret", "hdr-secret")
    _reset_growth_cache()
    r = await client.get("/api/v1/admin/growth", headers={"X-Growth-Secret": "nope"})
    assert r.status_code == 403


# ── A2: trial enforcement ─────────────────────────────────────────────────────

async def test_a2_expire_trials_suspends_lapsed_only(db, sessionmaker_, monkeypatch):
    cat = await f.create_category(db)
    o1 = await f.create_user(db, role="business_owner", telegram_id=1)
    o2 = await f.create_user(db, role="business_owner", telegram_id=2)
    o3 = await f.create_user(db, role="business_owner", telegram_id=3)
    now = datetime.now(timezone.utc)
    lapsed = await f.create_business(db, owner_id=o1.id, category_id=cat.id, name="Lapsed", status="trial")
    fresh = await f.create_business(db, owner_id=o2.id, category_id=cat.id, name="Fresh", status="trial")
    active = await f.create_business(db, owner_id=o3.id, category_id=cat.id, name="Active", status="active")
    lapsed.trial_ends_at = now - timedelta(days=1)
    fresh.trial_ends_at = now + timedelta(days=5)
    active.trial_ends_at = now - timedelta(days=1)  # active but past — must NOT be touched
    await db.commit()

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", sessionmaker_)
    await scheduler._expire_trials()

    for b in (lapsed, fresh, active):
        await db.refresh(b)
    assert lapsed.status == "suspended", "a lapsed trial must be suspended"
    assert fresh.status == "trial", "a trial still in its window is untouched"
    assert active.status == "active", "an active (paid) business is never auto-suspended"


async def test_a2_record_payment_activates_and_logs(client, db):
    admin_user = await f.create_user(db, role="super_admin", telegram_id=999)
    owner = await f.create_user(db, role="business_owner", telegram_id=1)
    cat = await f.create_category(db)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="suspended")

    r = await client.post(
        f"/api/v1/admin/businesses/{biz.id}/record-payment",
        headers=f.auth_header(admin_user.id),
        json={"plan": "basic", "months": 3, "paid_amount": 150000, "payment_note": "cash"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"

    await db.refresh(biz)
    assert biz.status == "active"
    subs = (
        await db.execute(select(Subscription).where(Subscription.business_id == biz.id))
    ).scalars().all()
    assert len(subs) == 1
    assert subs[0].paid_amount == 150000 and subs[0].plan == "basic"


async def test_a2_approve_to_trial_starts_window(client, db):
    admin_user = await f.create_user(db, role="super_admin", telegram_id=999)
    owner = await f.create_user(db, role="business_owner", telegram_id=1)
    cat = await f.create_category(db)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="pending")
    biz.trial_ends_at = None
    await db.commit()

    r = await client.patch(
        f"/api/v1/admin/businesses/{biz.id}/status",
        headers=f.auth_header(admin_user.id),
        json={"status": "trial"},
    )
    assert r.status_code == 200, r.text

    await db.refresh(biz)
    assert biz.status == "trial"
    assert biz.trial_ends_at is not None
    ends = biz.trial_ends_at
    if ends.tzinfo is None:  # SQLite may return naive; treat stored value as UTC
        ends = ends.replace(tzinfo=timezone.utc)
    delta = ends - datetime.now(timezone.utc)
    assert timedelta(days=13) < delta < timedelta(days=15)


# ── A3: business-status booking gate ──────────────────────────────────────────

async def test_a3_suspended_business_serves_no_slots(client, db):
    owner, biz, svc, staff = await _setup_bookable_business(db, status="suspended")
    r = await client.get("/api/v1/availability", params={
        "business_id": biz.id, "service_id": svc.id, "date": _future_date()})
    assert r.status_code == 200 and r.json() == []


async def test_a3_active_business_serves_slots(client, db):
    owner, biz, svc, staff = await _setup_bookable_business(db, status="active")
    r = await client.get("/api/v1/availability", params={
        "business_id": biz.id, "service_id": svc.id, "date": _future_date()})
    assert r.status_code == 200 and len(r.json()) > 0


async def test_a3_public_booking_rejected_when_suspended(client, db):
    owner, biz, svc, staff = await _setup_bookable_business(db, status="suspended")
    r = await client.post("/api/v1/bookings/public", headers=BOT_HEADERS, json={
        "business_id": biz.id, "service_id": svc.id, "staff_id": staff.id,
        "booking_date": _future_date(), "start_time": "10:00:00",
        "customer_name": "X", "customer_phone": "+998901234567",
        "telegram_id": 4242, "language": "uz",
    })
    assert r.status_code == 409, r.text


async def test_a3_manual_booking_rejected_when_blocked(client, db):
    owner, biz, svc, staff = await _setup_bookable_business(db, status="blocked")
    r = await client.post(
        f"/api/v1/businesses/{biz.id}/bookings",
        headers=f.auth_header(owner.id),
        json={
            "service_id": svc.id, "staff_id": staff.id,
            "booking_date": _future_date(), "start_time": "10:00:00",
            "customer_name": "X", "customer_phone": "+998901234567",
        },
    )
    assert r.status_code == 409, r.text


# ── A4: booking status state-machine ──────────────────────────────────────────

async def _booking_with_status(db, *, status):
    owner, biz, svc, staff = await _setup_bookable_business(db, status="active")
    cust = await f.create_customer(db, telegram_id=888)
    booking = await f.create_booking(
        db, business_id=biz.id, service_id=svc.id, staff_id=staff.id,
        customer_id=cust.id, booking_date=date.today() + timedelta(days=3), status=status,
    )
    return owner, booking


async def test_a4_terminal_booking_cannot_be_resurrected(client, db):
    owner, booking = await _booking_with_status(db, status="completed")
    r = await client.patch(f"/api/v1/bookings/{booking.id}/status",
                           headers=f.auth_header(owner.id), json={"status": "confirmed"})
    assert r.status_code == 409, r.text


async def test_a4_cancelled_cannot_be_completed(client, db):
    owner, booking = await _booking_with_status(db, status="cancelled_by_business")
    r = await client.patch(f"/api/v1/bookings/{booking.id}/status",
                           headers=f.auth_header(owner.id), json={"status": "completed"})
    assert r.status_code == 409, r.text


async def test_a4_idempotent_same_status_is_noop(client, db):
    owner, booking = await _booking_with_status(db, status="completed")
    r = await client.patch(f"/api/v1/bookings/{booking.id}/status",
                           headers=f.auth_header(owner.id), json={"status": "completed"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"


async def test_a4_legal_forward_transitions_work(client, db):
    owner, booking = await _booking_with_status(db, status="pending")
    r1 = await client.patch(f"/api/v1/bookings/{booking.id}/status",
                            headers=f.auth_header(owner.id), json={"status": "confirmed"})
    assert r1.status_code == 200 and r1.json()["status"] == "confirmed", r1.text
    r2 = await client.patch(f"/api/v1/bookings/{booking.id}/status",
                            headers=f.auth_header(owner.id), json={"status": "completed"})
    assert r2.status_code == 200 and r2.json()["status"] == "completed", r2.text
