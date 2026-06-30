"""
Investor growth feed (GET /admin/growth):
  M1. Secret-gated — wrong/missing secret → 403; disabled when unset.
  M2. Uzbekistan bounds guard — a location shared from abroad is dropped.
  M3. Traction stats block is present.
"""
from app.config import settings
from app.routers import admin
from tests import factories as f

URL = "/api/v1/admin/growth"
SECRET = "test-growth-secret-value"


def _reset_cache():
    # The endpoint caches in a module global — clear it so each test computes fresh.
    admin._growth_cache["data"] = None
    admin._growth_cache["at"] = 0.0


async def test_m1_requires_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "growth_secret", SECRET)
    _reset_cache()
    assert (await client.get(URL)).status_code == 403
    assert (await client.get(URL, params={"secret": "wrong"})).status_code == 403


async def test_m1b_disabled_when_secret_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "growth_secret", "")
    _reset_cache()
    assert (await client.get(URL, params={"secret": "anything"})).status_code == 403


async def test_m2_bounds_guard_drops_abroad(client, db, monkeypatch):
    monkeypatch.setattr(settings, "growth_secret", SECRET)
    _reset_cache()
    cat = await f.create_category(db)
    owner = await f.create_user(db, role="business_owner", telegram_id=1)

    in_uz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, name="Pop Barber")
    in_uz.latitude, in_uz.longitude = 40.86, 71.16          # Pop, Uzbekistan ✓
    abroad = await f.create_business(db, owner_id=owner.id, category_id=cat.id, name="Seoul Test")
    abroad.latitude, abroad.longitude = 37.59, 127.07       # Seoul — must be dropped
    await db.commit()

    body = (await client.get(URL, params={"secret": SECRET})).json()
    names = [b["name"] for b in body["businesses"]]
    assert "Pop Barber" in names
    assert "Seoul Test" not in names
    assert body["stats"]["located_businesses"] == 1
    assert body["stats"]["total_businesses"] == 2  # both exist; only one is mappable


async def test_m3_stats_block_shape(client, db, monkeypatch):
    monkeypatch.setattr(settings, "growth_secret", SECRET)
    _reset_cache()
    cat = await f.create_category(db)
    owner = await f.create_user(db, role="business_owner", telegram_id=2)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, name="Pop Barber")
    biz.latitude, biz.longitude = 40.86, 71.16
    await db.commit()

    stats = (await client.get(URL, params={"secret": SECRET})).json()["stats"]
    for key in (
        "total_businesses", "located_businesses", "active_businesses", "total_bookings",
        "avg_bookings_per_business", "top_categories", "regions_with_businesses",
        "first_booking_date", "top_performer_bookings", "weekly",
    ):
        assert key in stats, key
    assert isinstance(stats["weekly"], list) and stats["weekly"]
    assert {"week", "new_businesses", "cum_businesses", "bookings", "cum_bookings"} <= set(stats["weekly"][0])
    # Investor signals derive correctly from the seeded business (no bookings yet).
    assert stats["regions_with_businesses"] == ["Namangan"]
    assert stats["top_categories"] and stats["top_categories"][0]["count"] == 1
    assert stats["first_booking_date"] is None
    assert stats["avg_bookings_per_business"] == 0.0
    assert stats["top_performer_bookings"] == 0
