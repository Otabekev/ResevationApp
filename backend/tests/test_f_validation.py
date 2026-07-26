"""
Category F — input validation & injection.

F2: user content escaped in Telegram HTML messages (backend).
F3: numeric Pydantic constraints reject engine-breaking values.
F5: working-hours end must be after start.
F6: the BOT escapes user content before HTML messages too.
F7: business text fields are length-bounded.
F8: business NUMERIC settings are bounded, and the availability engine clamps
    the slot step even when the stored row is already out of range.
F9: staff text fields are length-bounded, so an over-long value is a clean 422
    instead of a column-overflow 500.
"""
import asyncio
import os
import sys
from datetime import date, time, timedelta

from tests.factories import (
    auth_header, create_business, create_category, create_service, create_staff,
    create_user, link_staff_service,
)

API = "/api/v1"


# ── F2: stored-XSS / HTML injection in notifications ─────────────────────────

def test_notification_escapes_user_html():
    from app.services.notification_service import new_booking_alert_message

    msg = new_booking_alert_message(
        lang="en", customer_name="<b>boss</b>&", service_name="Cut",
        date_str="2030-01-01", time_str="10:00",
    )
    # The customer's literal markup must be escaped...
    assert "<b>boss</b>" not in msg
    assert "&lt;b&gt;boss&lt;/b&gt;&amp;" in msg
    # ...while the template's own formatting stays intact.
    assert "<b>New booking!</b>" in msg


# ── F3: numeric constraints ──────────────────────────────────────────────────

async def _owner_biz(db):
    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=1)
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)
    return owner, biz


async def test_service_create_rejects_zero_duration(client, db):
    owner, biz = await _owner_biz(db)
    body = {"name_uz": "x", "name_ru": "x", "name_en": "x", "duration_minutes": 0}
    resp = await client.post(f"{API}/businesses/{biz.id}/services", json=body, headers=auth_header(owner.id))
    assert resp.status_code == 422, resp.text


async def test_service_create_rejects_negative_price(client, db):
    owner, biz = await _owner_biz(db)
    body = {"name_uz": "x", "name_ru": "x", "name_en": "x", "duration_minutes": 30, "price": -5}
    resp = await client.post(f"{API}/businesses/{biz.id}/services", json=body, headers=auth_header(owner.id))
    assert resp.status_code == 422, resp.text


async def test_service_create_accepts_valid(client, db):
    owner, biz = await _owner_biz(db)
    body = {"name_uz": "x", "name_ru": "x", "name_en": "x", "duration_minutes": 30, "price": 50000}
    resp = await client.post(f"{API}/businesses/{biz.id}/services", json=body, headers=auth_header(owner.id))
    assert resp.status_code == 201, resp.text


# ── F5: working hours ordering ───────────────────────────────────────────────

async def test_working_hours_rejects_end_before_start(client, db):
    owner, biz = await _owner_biz(db)
    body = {"hours": [{"day_of_week": 0, "start_time": "18:00:00", "end_time": "09:00:00"}]}
    resp = await client.put(
        f"{API}/businesses/{biz.id}/working-hours", json=body, headers=auth_header(owner.id)
    )
    assert resp.status_code == 422, resp.text


# ── F6: the bot escapes user content before HTML messages ────────────────────

def test_bot_escapes_user_html():
    """The bot defaults every message to parse_mode=HTML, so an unescaped & or <
    in a business/customer name would break the send. textutils.esc must escape
    it (mirrors the backend's _esc)."""
    bot_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "bot"))
    sys.path.insert(0, bot_dir)
    try:
        from textutils import esc
    finally:
        sys.path.remove(bot_dir)

    assert esc("<b>x</b>&") == "&lt;b&gt;x&lt;/b&gt;&amp;"
    assert esc("Cut & Style") == "Cut &amp; Style"   # the realistic case
    assert esc(None) == ""


# ── F7: business text fields are length-bounded ──────────────────────────────

async def test_business_update_rejects_oversized_name(client, db):
    owner, biz = await _owner_biz(db)
    resp = await client.patch(
        f"{API}/businesses/{biz.id}", json={"name": "x" * 300}, headers=auth_header(owner.id)
    )
    assert resp.status_code == 422, resp.text


# ── F8: business numeric settings are bounded ────────────────────────────────
# A zero/negative slot step is the dangerous one: it's the increment of the
# availability slot-walk, so it would turn the next anonymous /availability call
# into an infinite loop that blocks the event loop for every tenant.

async def test_business_update_rejects_engine_breaking_numbers(client, db):
    owner, biz = await _owner_biz(db)
    for field, value in [
        ("slot_step_minutes", 0),
        ("slot_step_minutes", -1),
        ("slot_step_minutes", 100000),
        ("min_advance_booking_minutes", -1),
        ("min_advance_booking_minutes", 10**9),
        ("max_advance_booking_days", 0),
        ("max_advance_booking_days", 10**9),
        ("cancellation_policy_hours", -1),
        ("latitude", 200),
        ("longitude", -500),
    ]:
        resp = await client.patch(
            f"{API}/businesses/{biz.id}", json={field: value}, headers=auth_header(owner.id)
        )
        assert resp.status_code == 422, f"{field}={value} was accepted: {resp.text}"


async def test_business_update_accepts_normal_settings(client, db):
    owner, biz = await _owner_biz(db)
    resp = await client.patch(
        f"{API}/businesses/{biz.id}",
        json={
            "slot_step_minutes": 30, "min_advance_booking_minutes": 60,
            "max_advance_booking_days": 90, "cancellation_policy_hours": 24,
            "latitude": 40.86, "longitude": 71.16,
        },
        headers=auth_header(owner.id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["slot_step_minutes"] == 30


async def test_availability_survives_a_poisoned_slot_step(db):
    """Defense in depth: even if a row carries a non-positive step (written before
    the bound existed, or by raw SQL), the engine must clamp instead of spinning
    forever. Wrapped in a timeout so a regression fails the suite instead of
    hanging it."""
    from app.services.booking_engine import get_available_slots

    cat = await create_category(db)
    owner = await create_user(db, role="business_owner", telegram_id=1)
    biz = await create_business(db, owner_id=owner.id, category_id=cat.id)
    svc = await create_service(db, business_id=biz.id, duration_minutes=30)
    staff = await create_staff(db, business_id=biz.id)
    await link_staff_service(db, staff_id=staff.id, service_id=svc.id)
    from app.models.schedule import WorkingHours
    for dow in range(7):
        db.add(WorkingHours(business_id=biz.id, day_of_week=dow,
                            start_time=time(9, 0), end_time=time(18, 0)))
    biz.slot_step_minutes = 0          # the poisoned value, straight into the DB
    await db.commit()

    slots = await asyncio.wait_for(
        get_available_slots(db, biz.id, svc.id, date.today() + timedelta(days=3), staff.id),
        timeout=10,
    )
    assert len(slots) > 0, "clamped step should still produce a normal slot list"


# ── F9: staff text fields are bounded ────────────────────────────────────────

async def test_staff_create_rejects_oversized_strings(client, db):
    """Every bound tracks a real column width (name 255, phone/role 20). Without
    them the value sails through validation and dies at INSERT as a 500 — a free
    error-log filler for anyone with a dashboard account."""
    owner, biz = await _owner_biz(db)
    for field, value in [
        ("name", "n" * 256),
        ("phone", "9" * 21),
        ("role", "r" * 21),
        ("bio", "b" * 1001),
        ("scheduling_mode", "s" * 21),
    ]:
        body = {"name": "Ok", "service_ids": [], field: value}
        resp = await client.post(
            f"{API}/businesses/{biz.id}/staff", json=body, headers=auth_header(owner.id)
        )
        assert resp.status_code == 422, f"{field} of len {len(value)} accepted: {resp.text}"


async def test_staff_update_rejects_oversized_strings(client, db):
    owner, biz = await _owner_biz(db)
    staff = await create_staff(db, business_id=biz.id)
    for field, value in [("name", "n" * 256), ("phone", "9" * 21), ("bio", "b" * 1001)]:
        resp = await client.patch(
            f"{API}/businesses/{biz.id}/staff/{staff.id}",
            json={field: value},
            headers=auth_header(owner.id),
        )
        assert resp.status_code == 422, f"{field} of len {len(value)} accepted: {resp.text}"


async def test_staff_create_accepts_realistic_values(client, db):
    """The bounds must clear a real record — a full Uzbek name and a +998 number."""
    owner, biz = await _owner_biz(db)
    resp = await client.post(
        f"{API}/businesses/{biz.id}/staff",
        json={
            "name": "Abdurahmonov Abdulaziz Abdurahmon o'g'li",
            "phone": "+998901234567",
            "bio": "Stomatolog, 12 yillik tajriba.",
            "service_ids": [],
        },
        headers=auth_header(owner.id),
    )
    assert resp.status_code == 201, resp.text
