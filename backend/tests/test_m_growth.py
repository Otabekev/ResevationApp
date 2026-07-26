"""
Investor growth feed (GET /admin/growth):
  M1. Secret-gated — wrong/missing secret → 403; disabled when unset.
  M2. Uzbekistan bounds guard — a location shared from abroad is dropped.
  M3. Traction stats block is present.
  M4. The secret never reaches the logs, in either the header or the legacy
      ?secret= form (and neither does a login nonce).
"""
import logging

from app.config import settings
from app.log_redaction import RedactSecretsFilter, redact
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


# ── M4: the secret never reaches the logs ────────────────────────────────────
# The investor site still sends ?secret=… (it's a static page we don't control
# from here), and uvicorn's access log writes the whole request line. Redact at
# the logging layer so the secret — and a live login nonce, which for its TTL is
# the capability that collects a user's tokens — is never written down.

def test_m4_redacts_query_secret_and_login_nonce():
    line = f'GET /api/v1/admin/growth?secret={SECRET}&x=1 HTTP/1.1'
    out = redact(line)
    assert SECRET not in out
    assert "secret=***" in out
    assert "x=1" in out, "unrelated query params must survive"

    nonce = "abc123DEADBEEF"
    out = redact(f"GET /api/v1/auth/tg-login/poll/{nonce} HTTP/1.1")
    assert nonce not in out and "poll/***" in out


def test_m4_filter_scrubs_uvicorn_style_access_record():
    """uvicorn.access puts the request path in record.args, not the message, so
    the filter has to walk the args or the secret still gets emitted."""
    record = logging.LogRecord(
        name="uvicorn.access", level=logging.INFO, pathname=__file__, lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("1.2.3.4:0", "GET", f"/api/v1/admin/growth?secret={SECRET}", "1.1", 200),
        exc_info=None,
    )
    assert RedactSecretsFilter().filter(record) is True
    assert SECRET not in record.getMessage()
    assert "secret=***" in record.getMessage()


async def test_m4_header_secret_still_authorizes(client, db, monkeypatch):
    """The preferred (header) form keeps working — that's the one the investor
    site should move to so the query param can be deleted."""
    monkeypatch.setattr(settings, "growth_secret", SECRET)
    _reset_cache()
    r = await client.get(URL, headers={"X-Growth-Secret": SECRET})
    assert r.status_code == 200, r.text
