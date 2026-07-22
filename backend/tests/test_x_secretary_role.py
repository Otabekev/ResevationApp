"""
Secretary / desk-manager role — the security-critical tests.

A secretary is a Staff row with can_manage=True, is_provider=False, linked to a
user account (role "staff"). She may manage HER clinic's bookings/schedules/
staff/services, but:
  - must be scoped strictly to clinics she's assigned to (NO cross-tenant access),
  - must NOT change business settings or the storefront photo (owner-only),
  - must NOT appear as a bookable provider,
  - must NOT be able to promote anyone (grant can_manage).
"""
from tests import factories as f

API = "/api/v1"


async def _clinic_with_secretary(db, *, tid_owner, tid_sec, slug):
    """Owner + business + a linked secretary (staff-role user, can_manage)."""
    cat = await f.create_category(db, slug=slug)
    owner = await f.create_user(db, role="business_owner", telegram_id=tid_owner)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="active")
    sec_user = await f.create_user(db, role="staff", telegram_id=tid_sec, name="Secretary")
    await f.create_staff(
        db, business_id=biz.id, user_id=sec_user.id, name="Secretary",
        can_manage=True, is_provider=False,
    )
    return owner, biz, sec_user


# ── The secretary CAN run her own clinic's desk ──────────────────────────────

async def test_secretary_sees_her_clinic_in_mine_as_manager(client, db):
    owner, biz, sec = await _clinic_with_secretary(db, tid_owner=9001, tid_sec=9002, slug="c1")
    resp = await client.get(f"{API}/businesses/mine", headers=f.auth_header(sec.id))
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["id"] == biz.id
    assert items[0]["access_role"] == "manager"


async def test_secretary_can_manage_bookings_services_schedule(client, db):
    owner, biz, sec = await _clinic_with_secretary(db, tid_owner=9003, tid_sec=9004, slug="c2")
    h = f.auth_header(sec.id)

    # bookings list
    assert (await client.get(f"{API}/businesses/{biz.id}/bookings", headers=h)).status_code == 200
    # create a service
    r = await client.post(
        f"{API}/businesses/{biz.id}/services",
        json={"name_uz": "Ko'rik", "name_ru": "Осмотр", "name_en": "Checkup", "duration_minutes": 30},
        headers=h,
    )
    assert r.status_code == 201, r.text
    # set business working hours
    r = await client.put(
        f"{API}/businesses/{biz.id}/working-hours",
        json={"hours": [{"day_of_week": 0, "start_time": "09:00", "end_time": "18:00"}]},
        headers=h,
    )
    assert r.status_code == 200, r.text
    # add a doctor (staff)
    r = await client.post(
        f"{API}/businesses/{biz.id}/staff",
        json={"name": "Dr. Aziz", "service_ids": []},
        headers=h,
    )
    assert r.status_code == 201, r.text


# ── The secretary is BLOCKED from owner-only actions ─────────────────────────

async def test_secretary_cannot_edit_business_settings(client, db):
    owner, biz, sec = await _clinic_with_secretary(db, tid_owner=9005, tid_sec=9006, slug="c3")
    r = await client.patch(
        f"{API}/businesses/{biz.id}", json={"name": "Hacked Clinic"}, headers=f.auth_header(sec.id)
    )
    assert r.status_code == 403


async def test_secretary_cannot_change_photo(client, db):
    owner, biz, sec = await _clinic_with_secretary(db, tid_owner=9007, tid_sec=9008, slug="c4")
    files = {"file": ("x.png", b"\x89PNG\r\n", "image/png")}
    r = await client.put(f"{API}/businesses/{biz.id}/photo", files=files, headers=f.auth_header(sec.id))
    assert r.status_code == 403


async def test_secretary_cannot_add_self_as_provider(client, db):
    owner, biz, sec = await _clinic_with_secretary(db, tid_owner=9009, tid_sec=9010, slug="c5")
    r = await client.post(f"{API}/businesses/{biz.id}/staff/me", json={}, headers=f.auth_header(sec.id))
    assert r.status_code == 403


async def test_secretary_cannot_grant_manager_rights(client, db):
    """A secretary adding a doctor cannot secretly mint another manager."""
    owner, biz, sec = await _clinic_with_secretary(db, tid_owner=9011, tid_sec=9012, slug="c6")
    r = await client.post(
        f"{API}/businesses/{biz.id}/staff",
        json={"name": "Mole", "can_manage": True, "service_ids": []},
        headers=f.auth_header(sec.id),
    )
    assert r.status_code == 201
    assert r.json()["can_manage"] is False  # silently forced off for a non-owner caller


# ── Cross-tenant isolation — the leak the owner fears most ───────────────────

async def test_secretary_of_A_is_blocked_from_B_everywhere(client, db):
    owner_a, biz_a, sec_a = await _clinic_with_secretary(db, tid_owner=9013, tid_sec=9014, slug="cA")
    cat_b = await f.create_category(db, slug="cB")
    owner_b = await f.create_user(db, role="business_owner", telegram_id=9015)
    biz_b = await f.create_business(db, owner_id=owner_b.id, category_id=cat_b.id, status="active")

    h = f.auth_header(sec_a.id)  # secretary of A only
    # Every management surface of B must 403/404 for her.
    probes = [
        ("get", f"{API}/businesses/{biz_b.id}"),
        ("get", f"{API}/businesses/{biz_b.id}/bookings"),
        ("get", f"{API}/businesses/{biz_b.id}/staff"),
        ("get", f"{API}/businesses/{biz_b.id}/services/all"),
        ("get", f"{API}/businesses/{biz_b.id}/working-hours"),
        ("get", f"{API}/businesses/{biz_b.id}/analytics"),
    ]
    for method, url in probes:
        resp = await getattr(client, method)(url, headers=h)
        assert resp.status_code in (403, 404), f"LEAK: {method} {url} -> {resp.status_code}"

    # And she must not be able to WRITE to B either.
    w = await client.post(
        f"{API}/businesses/{biz_b.id}/services",
        json={"name_uz": "x", "name_ru": "x", "name_en": "x", "duration_minutes": 30},
        headers=h,
    )
    assert w.status_code in (403, 404)
    # /mine must not leak B.
    mine = await client.get(f"{API}/businesses/mine", headers=h)
    assert all(b["id"] != biz_b.id for b in mine.json())


async def test_plain_customer_gets_no_dashboard_access(client, db):
    cat = await f.create_category(db, slug="cCust")
    owner = await f.create_user(db, role="business_owner", telegram_id=9016)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="active")
    customer = await f.create_user(db, role="customer", telegram_id=9017, name="Cust")
    r = await client.get(f"{API}/businesses/{biz.id}/bookings", headers=f.auth_header(customer.id))
    assert r.status_code == 403


# ── Secretary is not bookable ────────────────────────────────────────────────

async def test_secretary_absent_from_public_roster(client, db):
    owner, biz, sec = await _clinic_with_secretary(db, tid_owner=9018, tid_sec=9019, slug="cRost")
    # Add a real bookable doctor too.
    await f.create_staff(db, business_id=biz.id, name="Dr. Real", is_provider=True)
    resp = await client.get(f"{API}/public/businesses/{biz.id}/staff")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert "Dr. Real" in names
    assert "Secretary" not in names  # desk-manager never shown to customers


# ── A deactivated secretary loses access ─────────────────────────────────────

async def test_unlink_lets_owner_reissue_invite(client, db):
    """A linked staff blocks a new invite (409). Unlink detaches the account so a
    fresh invite works again — the fix for 'the first link didn't work'."""
    cat = await f.create_category(db, slug="cUnlink")
    owner = await f.create_user(db, role="business_owner", telegram_id=9030)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="active")
    joined_user = await f.create_user(db, role="staff", telegram_id=9031, name="Joined")
    staff = await f.create_staff(db, business_id=biz.id, user_id=joined_user.id, name="Dr. X")
    h = f.auth_header(owner.id)

    # Already linked → invite refused.
    blocked = await client.post(f"{API}/businesses/{biz.id}/staff/{staff.id}/invite", headers=h)
    assert blocked.status_code == 409

    # Unlink, then a fresh invite works.
    un = await client.post(f"{API}/businesses/{biz.id}/staff/{staff.id}/unlink", headers=h)
    assert un.status_code == 200
    assert un.json()["user_id"] is None
    ok = await client.post(f"{API}/businesses/{biz.id}/staff/{staff.id}/invite", headers=h)
    assert ok.status_code == 200
    assert ok.json()["invite_url"]


async def test_secretary_can_reissue_but_cross_tenant_unlink_blocked(client, db):
    owner, biz, sec = await _clinic_with_secretary(db, tid_owner=9032, tid_sec=9033, slug="cUn2")
    doctor = await f.create_staff(db, business_id=biz.id, user_id=None, name="Doc")
    # Secretary (manager) may issue invites for her own clinic's staff.
    r = await client.post(f"{API}/businesses/{biz.id}/staff/{doctor.id}/invite", headers=f.auth_header(sec.id))
    assert r.status_code == 200

    # But a secretary of another clinic cannot unlink here.
    cat_b = await f.create_category(db, slug="cUn2B")
    owner_b = await f.create_user(db, role="business_owner", telegram_id=9034)
    biz_b = await f.create_business(db, owner_id=owner_b.id, category_id=cat_b.id, status="active")
    outsider = await f.create_user(db, role="staff", telegram_id=9035, name="Outsider")
    await f.create_staff(db, business_id=biz_b.id, user_id=outsider.id, can_manage=True, is_provider=False)
    leak = await client.post(f"{API}/businesses/{biz.id}/staff/{doctor.id}/unlink", headers=f.auth_header(outsider.id))
    assert leak.status_code in (403, 404)


async def test_deactivated_secretary_loses_access(client, db):
    owner, biz, sec = await _clinic_with_secretary(db, tid_owner=9020, tid_sec=9021, slug="cDeact")
    # Owner deactivates her staff row.
    from sqlalchemy import select
    from app.models.staff import Staff
    row = (await db.execute(select(Staff).where(Staff.user_id == sec.id))).scalar_one()
    row.is_active = False
    await db.commit()

    r = await client.get(f"{API}/businesses/{biz.id}/bookings", headers=f.auth_header(sec.id))
    assert r.status_code == 403
