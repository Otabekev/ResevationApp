"""Short-lived store for the web-dashboard bot-login handshake.

The browser generates a nonce, opens the bot deep-link, and polls. When the
user confirms in the bot, the bot calls /auth/tg-login/complete which parks the
freshly-minted tokens here keyed by that nonce. The next poll reads them ONCE
and logs the browser in. Entries expire on their own so an abandoned login
never lingers.

In-process store: the API is a single uvicorn worker that owns BOTH the
/complete (write) and /poll (read) endpoints, so a module-level dict is shared
across the requests that matter and needs no external service. The bot reaches
it over HTTP, not shared memory. If the API is ever scaled to multiple workers
or instances, move this to Redis (see git history for a Redis-backed version).
"""
import time

_TTL_SECONDS = 120
# nonce -> (expires_at_epoch, payload)
_store: dict[str, tuple[float, dict]] = {}


def _prune(now: float) -> None:
    for key in [k for k, (exp, _) in _store.items() if exp <= now]:
        _store.pop(key, None)


async def save(nonce: str, payload: dict) -> None:
    now = time.time()
    _prune(now)
    _store[nonce] = (now + _TTL_SECONDS, payload)


async def take(nonce: str) -> dict | None:
    """One-time read: pop so a token is consumed once, honouring TTL."""
    entry = _store.pop(nonce, None)
    if not entry:
        return None
    expires_at, payload = entry
    if expires_at <= time.time():
        return None
    return payload
