"""
Business photo upload/serve/delete.

  V1. Owner uploads any image -> it's recompressed to a downscaled JPEG, stored,
      and served publicly with immutable caching; photo_url appears on the record.
  V2. A non-owner cannot upload to someone else's business (403).
  V3. Delete removes the photo (photo_url -> None, serve -> 404).
  V4. Non-image bytes are rejected with a clean 400 (not a 500).
  V5. The public profile (what the Telegram bot reads) carries photo_url.
  V6. The anti-abuse byte ceiling returns 413.
  V7. Conditional GET (If-None-Match) returns 304 for an unchanged photo.
"""
import io

from PIL import Image

import app.routers.businesses as biz_router
from tests import factories as f

API = "/api/v1"


def _img_bytes(w=1600, h=1200, fmt="PNG", color=(120, 40, 200)):
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


async def _make_owned_business(db, *, tid=7001):
    cat = await f.create_category(db, slug=f"cat{tid}")
    owner = await f.create_user(db, role="business_owner", telegram_id=tid)
    biz = await f.create_business(db, owner_id=owner.id, category_id=cat.id, status="active")
    return owner, biz


async def test_v1_upload_recompresses_and_serves(client, db):
    owner, biz = await _make_owned_business(db, tid=7001)

    files = {"file": ("store.png", _img_bytes(1600, 1200, "PNG"), "image/png")}
    resp = await client.put(f"{API}/businesses/{biz.id}/photo", files=files, headers=f.auth_header(owner.id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["photo_url"], "upload response should carry a photo_url"

    # Owner record now advertises the photo.
    got = await client.get(f"{API}/businesses/{biz.id}", headers=f.auth_header(owner.id))
    assert got.json()["photo_url"]

    # Public serve endpoint needs NO auth and returns a cached JPEG.
    photo = await client.get(f"{API}/businesses/{biz.id}/photo")
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/jpeg"
    assert "immutable" in photo.headers.get("cache-control", "")
    assert photo.content[:2] == b"\xff\xd8", "served bytes should be a JPEG"

    # It was downscaled to <= the max edge, and is much smaller than a raw 1600x1200.
    served = Image.open(io.BytesIO(photo.content))
    assert max(served.size) <= biz_router._PHOTO_MAX_DIM


async def test_v2_non_owner_cannot_upload(client, db):
    _owner, biz = await _make_owned_business(db, tid=7002)
    attacker = await f.create_user(db, role="business_owner", telegram_id=7092)

    files = {"file": ("x.png", _img_bytes(400, 300), "image/png")}
    resp = await client.put(f"{API}/businesses/{biz.id}/photo", files=files, headers=f.auth_header(attacker.id))
    assert resp.status_code == 403


async def test_v3_delete_clears_photo(client, db):
    owner, biz = await _make_owned_business(db, tid=7003)
    files = {"file": ("s.png", _img_bytes(500, 500), "image/png")}
    await client.put(f"{API}/businesses/{biz.id}/photo", files=files, headers=f.auth_header(owner.id))

    resp = await client.delete(f"{API}/businesses/{biz.id}/photo", headers=f.auth_header(owner.id))
    assert resp.status_code == 200
    assert resp.json()["photo_url"] is None

    gone = await client.get(f"{API}/businesses/{biz.id}/photo")
    assert gone.status_code == 404


async def test_v4_non_image_rejected(client, db):
    owner, biz = await _make_owned_business(db, tid=7004)
    files = {"file": ("evil.png", b"this is definitely not an image", "image/png")}
    resp = await client.put(f"{API}/businesses/{biz.id}/photo", files=files, headers=f.auth_header(owner.id))
    assert resp.status_code == 400


async def test_v5_public_profile_carries_photo_url(client, db):
    owner, biz = await _make_owned_business(db, tid=7005)
    files = {"file": ("s.jpg", _img_bytes(800, 600, "JPEG"), "image/jpeg")}
    await client.put(f"{API}/businesses/{biz.id}/photo", files=files, headers=f.auth_header(owner.id))

    pub = await client.get(f"{API}/businesses/{biz.id}/public")
    assert pub.status_code == 200
    assert pub.json()["photo_url"], "the bot-facing public profile must expose photo_url"


async def test_v6_oversized_rejected(client, db, monkeypatch):
    owner, biz = await _make_owned_business(db, tid=7006)
    # Shrink the ceiling so a tiny image trips it — cheaper than crafting 25MB.
    monkeypatch.setattr(biz_router, "_PHOTO_MAX_UPLOAD_BYTES", 10)
    files = {"file": ("big.png", _img_bytes(400, 300), "image/png")}
    resp = await client.put(f"{API}/businesses/{biz.id}/photo", files=files, headers=f.auth_header(owner.id))
    assert resp.status_code == 413


async def test_v7_conditional_get_returns_304(client, db):
    owner, biz = await _make_owned_business(db, tid=7007)
    files = {"file": ("s.png", _img_bytes(500, 500), "image/png")}
    await client.put(f"{API}/businesses/{biz.id}/photo", files=files, headers=f.auth_header(owner.id))

    first = await client.get(f"{API}/businesses/{biz.id}/photo")
    etag = first.headers["etag"]
    again = await client.get(f"{API}/businesses/{biz.id}/photo", headers={"If-None-Match": etag})
    assert again.status_code == 304


async def test_v8_heic_iphone_photo_accepted(client, db):
    """iPhones shoot HEIC by default — the server must decode it (pillow-heif)
    and store the usual JPEG, or every iPhone owner's upload bounces."""
    import pytest

    pytest.importorskip("pillow_heif")
    import pillow_heif

    owner, biz = await _make_owned_business(db, tid=7008)
    heif = pillow_heif.from_pillow(Image.new("RGB", (900, 700), (10, 120, 90)))
    buf = io.BytesIO()
    heif.save(buf, quality=80)

    files = {"file": ("IMG_0001.HEIC", buf.getvalue(), "image/heic")}
    resp = await client.put(f"{API}/businesses/{biz.id}/photo", files=files, headers=f.auth_header(owner.id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["photo_url"]

    served = await client.get(f"{API}/businesses/{biz.id}/photo")
    assert served.status_code == 200
    assert served.content[:2] == b"\xff\xd8", "HEIC should be stored re-encoded as JPEG"
