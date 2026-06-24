"""Async HTTP client for talking to the backend API."""
import httpx

from config import BACKEND_URL, BOT_SECRET

# One shared client for the whole bot process. httpx keeps connections to the
# backend alive and pools them, so each call reuses an open TLS connection
# instead of doing a fresh handshake every time — that per-call handshake was
# adding hundreds of ms to every step of the flow.
_client = httpx.AsyncClient(timeout=10)


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


async def get_available_slots(
    business_id: int, service_id: int, date_str: str, staff_id: int | None = None
) -> list[dict]:
    params = {"business_id": business_id, "service_id": service_id, "date": date_str}
    if staff_id:
        params["staff_id"] = staff_id
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


async def join_via_invite(token: str, access_token: str) -> dict:
    resp = await _client.post(
        f"{BACKEND_URL}/staff/join/{token}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    resp.raise_for_status()
    return resp.json()
