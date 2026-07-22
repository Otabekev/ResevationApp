"""
Phase 2 — live queue: join/position/ETA, dashboard advance, cross-tenant safety.
"""
from app.config import settings
from tests import factories as f

API = "/api/v1"
BOT = {"X-Bot-Secret": settings.bot_secret}


async def _queue_biz(db, *, tid, avg=15):
    cat = await f.create_category(db, slug=f"q{tid}")
    owner = await f.create_user(db, role="business_owner", telegram_id=tid)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="active")
    doc = await f.create_staff(db, business_id=biz.id, name="Dr. Q")
    doc.scheduling_mode = "queue"
    doc.queue_avg_minutes = avg
    await db.commit()
    return owner, biz, doc


async def test_join_positions_and_eta(client, db):
    owner, biz, doc = await _queue_biz(db, tid=8100, avg=10)
    r1 = await client.post(f"{API}/public/queue/join", headers=BOT, json={
        "business_id": biz.id, "staff_id": doc.id, "customer_name": "A", "telegram_id": 5001, "language": "uz"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["position"] == 1 and r1.json()["eta_minutes"] == 0
    r2 = await client.post(f"{API}/public/queue/join", headers=BOT, json={
        "business_id": biz.id, "staff_id": doc.id, "customer_name": "B", "telegram_id": 5002})
    assert r2.json()["position"] == 2
    assert r2.json()["eta_minutes"] == 10  # 1 ahead × 10 min


async def test_double_join_is_idempotent(client, db):
    owner, biz, doc = await _queue_biz(db, tid=8107)
    a = await client.post(f"{API}/public/queue/join", headers=BOT, json={
        "business_id": biz.id, "staff_id": doc.id, "customer_name": "A", "telegram_id": 5040})
    b = await client.post(f"{API}/public/queue/join", headers=BOT, json={
        "business_id": biz.id, "staff_id": doc.id, "customer_name": "A", "telegram_id": 5040})
    assert a.json()["entry_id"] == b.json()["entry_id"]
    assert b.json()["already"] is True


async def test_join_requires_queue_mode(client, db):
    owner, biz, doc = await _queue_biz(db, tid=8101)
    doc.scheduling_mode = "appointments"
    await db.commit()
    r = await client.post(f"{API}/public/queue/join", headers=BOT, json={
        "business_id": biz.id, "staff_id": doc.id, "customer_name": "A"})
    assert r.status_code == 400


async def test_public_join_requires_bot_secret(client, db):
    owner, biz, doc = await _queue_biz(db, tid=8102)
    r = await client.post(f"{API}/public/queue/join", json={
        "business_id": biz.id, "staff_id": doc.id, "customer_name": "A"})
    assert r.status_code == 403


async def test_dashboard_list_and_advance(client, db):
    owner, biz, doc = await _queue_biz(db, tid=8103)
    j1 = await client.post(f"{API}/public/queue/join", headers=BOT, json={
        "business_id": biz.id, "staff_id": doc.id, "customer_name": "A", "telegram_id": 5010})
    j2 = await client.post(f"{API}/public/queue/join", headers=BOT, json={
        "business_id": biz.id, "staff_id": doc.id, "customer_name": "B", "telegram_id": 5011})
    lst = await client.get(f"{API}/businesses/{biz.id}/queue", headers=f.auth_header(owner.id))
    assert lst.status_code == 200 and len(lst.json()) == 2

    e1 = j1.json()["entry_id"]
    assert (await client.post(f"{API}/businesses/{biz.id}/queue/{e1}/call", headers=f.auth_header(owner.id))).status_code == 200
    assert (await client.post(f"{API}/businesses/{biz.id}/queue/{e1}/done", headers=f.auth_header(owner.id))).status_code == 200
    # B is now #1
    st2 = await client.get(f"{API}/public/queue/status/{j2.json()['entry_id']}", headers=BOT)
    assert st2.json()["position"] == 1


async def test_queue_cross_tenant_blocked(client, db):
    owner_a, biz_a, doc_a = await _queue_biz(db, tid=8104)
    j = await client.post(f"{API}/public/queue/join", headers=BOT, json={
        "business_id": biz_a.id, "staff_id": doc_a.id, "customer_name": "A", "telegram_id": 5020})
    outsider = await f.create_user(db, role="staff", telegram_id=8105)
    assert (await client.get(f"{API}/businesses/{biz_a.id}/queue", headers=f.auth_header(outsider.id))).status_code in (403, 404)
    act = await client.post(f"{API}/businesses/{biz_a.id}/queue/{j.json()['entry_id']}/call", headers=f.auth_header(outsider.id))
    assert act.status_code in (403, 404)


async def test_leave_queue(client, db):
    owner, biz, doc = await _queue_biz(db, tid=8106)
    j = await client.post(f"{API}/public/queue/join", headers=BOT, json={
        "business_id": biz.id, "staff_id": doc.id, "customer_name": "A", "telegram_id": 5030})
    eid = j.json()["entry_id"]
    assert (await client.post(f"{API}/public/queue/leave/{eid}", headers=BOT)).status_code == 200
    st = await client.get(f"{API}/public/queue/status/{eid}", headers=BOT)
    assert st.json()["status"] == "cancelled"
