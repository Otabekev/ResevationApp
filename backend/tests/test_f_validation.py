"""
Category F — input validation & injection.

F2: user content escaped in Telegram HTML messages.
F3: numeric Pydantic constraints reject engine-breaking values.
F5: working-hours end must be after start.
"""
from tests.factories import auth_header, create_business, create_category, create_user

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
