"""Short-lived store for the web-dashboard bot-login handshake.

The browser generates a nonce, opens the bot deep-link, and polls. When the
user confirms in the bot, the bot calls /auth/tg-login/complete which parks the
freshly-minted tokens here keyed by that nonce. The next poll reads them ONCE
(atomic get-and-delete) and logs the browser in. Entries expire on their own so
an abandoned login never lingers.

Backed by Redis because the bot and the API are separate processes (and the API
may run multiple workers) — an in-process dict would not be shared between them.
"""
import json

from app.redis_client import get_redis

_PREFIX = "weblogin:"
_TTL_SECONDS = 120


async def save(nonce: str, payload: dict) -> None:
    await get_redis().set(f"{_PREFIX}{nonce}", json.dumps(payload), ex=_TTL_SECONDS)


async def take(nonce: str) -> dict | None:
    """One-time read: atomically fetch and delete so a token is consumed once."""
    raw = await get_redis().getdel(f"{_PREFIX}{nonce}")
    return json.loads(raw) if raw else None
