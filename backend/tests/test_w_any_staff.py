"""
allow_any_staff toggle — clinics hide "Any available" so patients pick a
specific specialist (never auto-assigned across specialties).
"""
from tests import factories as f

API = "/api/v1"


async def test_default_is_true_and_exposed_publicly(client, db):
    cat = await f.create_category(db, slug="clinic")
    owner = await f.create_user(db, role="business_owner", telegram_id=8100)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="active")

    pub = await client.get(f"{API}/businesses/{biz.id}/public")
    assert pub.status_code == 200
    assert pub.json()["allow_any_staff"] is True  # default on (barbers)


async def test_owner_can_turn_it_off_and_bot_sees_it(client, db):
    cat = await f.create_category(db, slug="clinic2")
    owner = await f.create_user(db, role="business_owner", telegram_id=8101)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="active")

    resp = await client.patch(
        f"{API}/businesses/{biz.id}",
        json={"allow_any_staff": False},
        headers=f.auth_header(owner.id),
    )
    assert resp.status_code == 200
    assert resp.json()["allow_any_staff"] is False

    # The bot reads the public profile to decide whether to offer "Any available".
    pub = await client.get(f"{API}/businesses/{biz.id}/public")
    assert pub.json()["allow_any_staff"] is False
