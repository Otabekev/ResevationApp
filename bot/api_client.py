"""Async HTTP client for talking to the backend API."""
import httpx

from config import BACKEND_URL, BOT_SECRET

# One shared client for the whole bot process. httpx keeps connections to the
# backend alive and pools them, so each call reuses an open TLS connection
# instead of doing a fresh handshake every time — that per-call handshake was
# adding hundreds of ms to every step of the flow.
#
# keepalive_expiry is 300s (not 30s) so the pooled connection survives realistic
# think-time — a user routinely spends >30s reading a screen before tapping the
# next step, and at 30s the pool would go empty and force a fresh TLS handshake on
# that next call. httpx still transparently retries if the server closed the
# socket, and the 10s read timeout bounds the worst case. The structured timeout
# caps connect at 5s and any single call at 10s, so a slow backend surfaces a
# clean error the handlers can show — never a silent hang.
_client = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0, connect=5.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100, keepalive_expiry=300.0),
)


def absolute_media_url(url: str | None) -> str | None:
    """Make a backend-relative media URL (e.g. '/api/v1/businesses/5/photo?v=1')
    absolute so Telegram can fetch it by URL. The backend returns a relative photo
    URL when WEBHOOK_BASE_URL isn't set; the bot always knows BACKEND_URL, so we
    resolve it here. Already-absolute URLs pass through unchanged."""
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    origin = BACKEND_URL.split("/api/v1")[0].rstrip("/")
    return f"{origin}{url}"


async def auth_user(telegram_id: int, name: str, username: str | None, language: str) -> dict:
    resp = await _client.post(
        f"{BACKEND_URL}/auth/bot",
        json={
            "telegram_id": telegram_id,
            "name": name,
            "username": username,
            "language": language,
            "bot_secret": BOT_SECRET,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def complete_location_share(nonce: str, latitude: float, longitude: float) -> dict:
    """Send an owner's shared business location to the backend, keyed by the
    browser's nonce. Protected by BOT_SECRET."""
    resp = await _client.post(
        f"{BACKEND_URL}/businesses/location-share/complete",
        json={
            "nonce": nonce,
            "latitude": latitude,
            "longitude": longitude,
            "bot_secret": BOT_SECRET,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def complete_web_login(
    nonce: str, telegram_id: int, name: str, username: str | None, language: str
) -> dict:
    """Confirm a web-dashboard login: the backend mints tokens and parks them in
    Redis keyed by the browser's nonce. Protected by BOT_SECRET."""
    resp = await _client.post(
        f"{BACKEND_URL}/auth/tg-login/complete",
        json={
            "nonce": nonce,
            "telegram_id": telegram_id,
            "name": name,
            "username": username,
            "language": language,
            "bot_secret": BOT_SECRET,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def update_language(token: str, language: str) -> None:
    """Persist the user's language so backend notifications match the bot."""
    resp = await _client.patch(
        f"{BACKEND_URL}/auth/me/language",
        json={"language": language},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()


async def get_categories() -> list[dict]:
    resp = await _client.get(f"{BACKEND_URL}/businesses/categories")
    resp.raise_for_status()
    return resp.json()


async def get_businesses_by_category(category_id: int) -> list[dict]:
    resp = await _client.get(
        f"{BACKEND_URL}/public/businesses",
        params={"category_id": category_id},
    )
    resp.raise_for_status()
    return resp.json()


async def get_public_business(business_id: int) -> dict:
    resp = await _client.get(f"{BACKEND_URL}/businesses/{business_id}/public")
    resp.raise_for_status()
    return resp.json()


async def get_services(business_id: int) -> list[dict]:
    resp = await _client.get(f"{BACKEND_URL}/businesses/{business_id}/services")
    resp.raise_for_status()
    return resp.json()


async def get_staff(business_id: int) -> list[dict]:
    resp = await _client.get(f"{BACKEND_URL}/public/businesses/{business_id}/staff")
    resp.raise_for_status()
    return resp.json()


async def get_launch_status(telegram_id: int) -> dict:
    """Ask the backend whether the booking flow is open for this user (pre-launch
    gate). Returns {"open": bool, "launched": bool}: owners/staff are always open;
    everyone else only once the launch date has passed."""
    resp = await _client.get(
        f"{BACKEND_URL}/public/launch-status",
        params={"telegram_id": telegram_id},
    )
    resp.raise_for_status()
    return resp.json()


async def get_available_slots(
    business_id: int,
    service_id: int,
    date_str: str,
    staff_id: int | None = None,
    service_ids: list[int] | None = None,
) -> list[dict]:
    params: dict = {"business_id": business_id, "service_id": service_id, "date": date_str}
    if staff_id:
        params["staff_id"] = staff_id
    if service_ids:
        # httpx serializes a list value as repeated query params
        # (?service_ids=1&service_ids=2) → multi-service combined-duration slots.
        params["service_ids"] = service_ids
    resp = await _client.get(f"{BACKEND_URL}/availability", params=params)
    resp.raise_for_status()
    return resp.json()


async def create_booking(payload: dict) -> dict:
    resp = await _client.post(
        f"{BACKEND_URL}/bookings/public",
        json=payload,
        headers={"X-Bot-Secret": BOT_SECRET},
    )
    if resp.status_code == 409:
        raise ValueError(resp.json().get("detail", "Slot unavailable"))
    resp.raise_for_status()
    return resp.json()


# ── Live queue ────────────────────────────────────────────────────────────────

async def join_queue(payload: dict) -> dict:
    resp = await _client.post(
        f"{BACKEND_URL}/public/queue/join", json=payload, headers={"X-Bot-Secret": BOT_SECRET}
    )
    if resp.status_code == 400:
        raise ValueError(resp.json().get("detail", "Cannot join"))
    resp.raise_for_status()
    return resp.json()


async def queue_status(entry_id: int) -> dict:
    resp = await _client.get(
        f"{BACKEND_URL}/public/queue/status/{entry_id}", headers={"X-Bot-Secret": BOT_SECRET}
    )
    resp.raise_for_status()
    return resp.json()


async def queue_leave(entry_id: int) -> dict:
    resp = await _client.post(
        f"{BACKEND_URL}/public/queue/leave/{entry_id}", headers={"X-Bot-Secret": BOT_SECRET}
    )
    resp.raise_for_status()
    return resp.json()


async def queue_confirm(entry_id: int) -> dict:
    resp = await _client.post(
        f"{BACKEND_URL}/public/queue/confirm/{entry_id}", headers={"X-Bot-Secret": BOT_SECRET}
    )
    resp.raise_for_status()
    return resp.json()


async def get_customer_bookings(telegram_id: int, token: str, upcoming_only: bool = False) -> list[dict]:
    resp = await _client.get(
        f"{BACKEND_URL}/customers/{telegram_id}/bookings",
        params={"upcoming_only": upcoming_only},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


async def cancel_booking(booking_id: int, token: str, reason: str | None = None) -> dict:
    resp = await _client.patch(
        f"{BACKEND_URL}/bookings/{booking_id}/cancel",
        json={"reason": reason},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


async def submit_review(telegram_id: int, booking_id: int, rating: int, comment: str | None = None) -> dict:
    resp = await _client.post(
        f"{BACKEND_URL}/reviews",
        json={"booking_id": booking_id, "rating": rating, "comment": comment, "telegram_id": telegram_id},
        headers={"X-Bot-Secret": BOT_SECRET},
    )
    resp.raise_for_status()
    return resp.json()


async def join_via_invite(token: str, access_token: str, phone: str | None = None) -> dict:
    resp = await _client.post(
        f"{BACKEND_URL}/staff/join/{token}",
        json={"phone": phone},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    # 403 = the shared phone doesn't match the staff record — surface it distinctly
    # so the bot can tell the user this invite is for someone else's number.
    if resp.status_code == 403:
        raise ValueError("phone_mismatch")
    resp.raise_for_status()
    return resp.json()
