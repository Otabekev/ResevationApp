"""
Deploy B (before-deployment fixes) regression tests.

  B6. Staff-invite identity hardening — an already-linked staff slot can't be
      claimed by a second person (create OR join), the owner slot can't be
      invited, and issuing a new invite invalidates the prior one.
  B7. Reminder sweep claims each row before sending, so a repeat sweep sends
      nothing (no duplicate reminders).
  B8. Auto-assign booking still works with the advisory-lock guard in place
      (the guard is a no-op on SQLite; Postgres serializes concurrent inserts).

  (B5, the bot's Tashkent-time date picker, isn't in the backend suite — it's a
   pure bot-side change verified by a syntax check + the fixed UTC+5 offset.)
"""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app.models.staff import StaffInvite
from app.services import scheduler
from app.timeutils import PLATFORM_TZ
from tests import factories as f

BOT_HEADERS = {"X-Bot-Secret": "test-bot-secret-shared-32-characters-minimum-000"}


async def _owner_biz_staff(db, *, owner_tg=111):
    owner = await f.create_user(db, role="business_owner", telegram_id=owner_tg)
    cat = await f.create_category(db)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)
    staff = await f.create_staff(db, business_id=biz.id)
    return owner, biz, staff


# ── B6: staff-invite identity hardening ───────────────────────────────────────

async def test_b6_create_invite_rejected_when_staff_already_linked(client, db):
    owner, biz, staff = await _owner_biz_staff(db)
    member = await f.create_user(db, role="staff", telegram_id=222)
    staff.user_id = member.id
    await db.commit()

    r = await client.post(f"/api/v1/businesses/{biz.id}/staff/{staff.id}/invite",
                          headers=f.auth_header(owner.id))
    assert r.status_code == 409, r.text


async def test_b6_create_invite_rejected_for_owner_slot(client, db):
    owner, biz, staff = await _owner_biz_staff(db)
    staff.is_owner = True
    await db.commit()

    r = await client.post(f"/api/v1/businesses/{biz.id}/staff/{staff.id}/invite",
                          headers=f.auth_header(owner.id))
    assert r.status_code == 400, r.text


async def test_b6_new_invite_invalidates_prior_one(client, db):
    owner, biz, staff = await _owner_biz_staff(db)
    r1 = await client.post(f"/api/v1/businesses/{biz.id}/staff/{staff.id}/invite",
                           headers=f.auth_header(owner.id))
    assert r1.status_code == 200, r1.text
    token1 = r1.json()["token"]

    r2 = await client.post(f"/api/v1/businesses/{biz.id}/staff/{staff.id}/invite",
                           headers=f.auth_header(owner.id))
    assert r2.status_code == 200, r2.text

    inv1 = (await db.execute(select(StaffInvite).where(StaffInvite.token == token1))).scalar_one()
    await db.refresh(inv1)
    assert inv1.is_active is False, "issuing a new invite must deactivate the old one"

    # The stale first token is no longer redeemable.
    joiner = await f.create_user(db, role="customer", telegram_id=333)
    rj = await client.post(f"/api/v1/staff/join/{token1}", headers=f.auth_header(joiner.id))
    assert rj.status_code == 404, rj.text


async def test_b6_join_rejected_when_slot_already_claimed(client, db):
    owner, biz, staff = await _owner_biz_staff(db)
    r = await client.post(f"/api/v1/businesses/{biz.id}/staff/{staff.id}/invite",
                          headers=f.auth_header(owner.id))
    token = r.json()["token"]

    # Someone claims the slot before this (forwarded) token is redeemed.
    member = await f.create_user(db, role="staff", telegram_id=222)
    staff.user_id = member.id
    await db.commit()

    joiner = await f.create_user(db, role="customer", telegram_id=333)
    rj = await client.post(f"/api/v1/staff/join/{token}", headers=f.auth_header(joiner.id))
    assert rj.status_code == 409, rj.text


async def test_b6_join_rejected_for_owner_slot(client, db):
    owner, biz, staff = await _owner_biz_staff(db)
    staff.is_owner = True
    inv = StaffInvite(
        business_id=biz.id, staff_id=staff.id, created_by=owner.id,
        token="owner-slot-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(inv)
    await db.commit()

    joiner = await f.create_user(db, role="customer", telegram_id=333)
    rj = await client.post("/api/v1/staff/join/owner-slot-token", headers=f.auth_header(joiner.id))
    assert rj.status_code == 400, rj.text


async def _invite_token(client, db, biz, staff, owner):
    r = await client.post(f"/api/v1/businesses/{biz.id}/staff/{staff.id}/invite",
                          headers=f.auth_header(owner.id))
    assert r.status_code == 200, r.text
    return r.json()["token"]


async def test_b6_join_succeeds_when_shared_phone_matches(client, db):
    owner, biz, staff = await _owner_biz_staff(db)
    staff.phone = "+998901112233"
    await db.commit()
    token = await _invite_token(client, db, biz, staff, owner)

    joiner = await f.create_user(db, role="customer", telegram_id=333)
    # Different formatting, same number — must normalize and match.
    rj = await client.post(f"/api/v1/staff/join/{token}",
                           json={"phone": "998 90 111 22 33"},
                           headers=f.auth_header(joiner.id))
    assert rj.status_code == 200, rj.text
    await db.refresh(staff)
    assert staff.user_id == joiner.id


async def test_b6_join_rejected_when_shared_phone_differs(client, db):
    owner, biz, staff = await _owner_biz_staff(db)
    staff.phone = "+998901112233"
    await db.commit()
    token = await _invite_token(client, db, biz, staff, owner)

    joiner = await f.create_user(db, role="customer", telegram_id=333)
    rj = await client.post(f"/api/v1/staff/join/{token}",
                           json={"phone": "+998907776655"},
                           headers=f.auth_header(joiner.id))
    assert rj.status_code == 403, rj.text


async def test_b6_join_rejected_when_phone_required_but_absent(client, db):
    owner, biz, staff = await _owner_biz_staff(db)
    staff.phone = "+998901112233"
    await db.commit()
    token = await _invite_token(client, db, biz, staff, owner)

    joiner = await f.create_user(db, role="customer", telegram_id=333)
    rj = await client.post(f"/api/v1/staff/join/{token}", headers=f.auth_header(joiner.id))
    assert rj.status_code == 403, rj.text


async def test_b6_join_captures_phone_when_staff_record_blank(client, db):
    owner, biz, staff = await _owner_biz_staff(db)  # staff.phone is None
    token = await _invite_token(client, db, biz, staff, owner)

    joiner = await f.create_user(db, role="customer", telegram_id=333)
    rj = await client.post(f"/api/v1/staff/join/{token}",
                           json={"phone": "+998901112233"},
                           headers=f.auth_header(joiner.id))
    assert rj.status_code == 200, rj.text
    await db.refresh(staff)
    assert staff.user_id == joiner.id
    assert staff.phone == "+998901112233"  # captured from the verified joiner


# ── B7: reminder claim prevents double-send ───────────────────────────────────

async def test_b7_repeat_sweep_does_not_resend(db, sessionmaker_, monkeypatch):
    cat = await f.create_category(db)
    owner = await f.create_user(db, role="business_owner", telegram_id=6001)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await f.create_service(db, business_id=biz.id)
    cust = await f.create_customer(db, telegram_id=6000)
    target = (datetime.now(timezone.utc) + timedelta(hours=24)).astimezone(PLATFORM_TZ)
    await f.create_booking(
        db, business_id=biz.id, service_id=svc.id, staff_id=None, customer_id=cust.id,
        booking_date=target.date(), start_time=target.time().replace(second=0, microsecond=0),
        status="confirmed",
    )

    sent = []

    async def _send(chat_id, *a, **k):
        sent.append(chat_id)
        return True

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", sessionmaker_)
    monkeypatch.setattr(scheduler, "send_telegram_message", _send)
    monkeypatch.setattr(scheduler, "send_telegram_location", _send)

    await scheduler._send_reminders()
    await scheduler._send_reminders()  # immediate re-run must NOT resend

    assert sent == [6000], f"expected exactly one reminder, got {sent}"


# ── B8: booking still works with the advisory-lock guard ──────────────────────

async def test_b8_autoassign_booking_still_succeeds(client, db):
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

    # staff_id=None exercises the auto-assign path where the advisory lock lives.
    r = await client.post("/api/v1/bookings/public", headers=BOT_HEADERS, json={
        "business_id": biz.id, "service_id": svc.id, "staff_id": None,
        "booking_date": (date.today() + timedelta(days=5)).isoformat(),
        "start_time": "10:00:00",
        "customer_name": "X", "customer_phone": "+998901234567",
        "telegram_id": 7001, "language": "uz",
    })
    assert r.status_code == 201, r.text
