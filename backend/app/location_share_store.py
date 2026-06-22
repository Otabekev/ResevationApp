"""Short-lived store for the Telegram "share business location" handshake.

Mirrors web_login_store: the browser generates a nonce, opens the bot deep-link
t.me/<bot>?start=setloc_<nonce>, and polls. When the owner shares their location
in the bot, the bot calls /businesses/location-share/complete which parks the
coordinates here keyed by the nonce. The next poll reads them ONCE and drops
them into the setup form. Entries expire on their own so an abandoned attempt
never lingers.

In-process store: the API is a single uvicorn worker that owns BOTH the
/complete (write) and /poll (read) endpoints, so a module-level dict is shared
across the requests that matter and needs no external service. The bot reaches
it over HTTP, not shared memory. If the API is ever scaled to multiple workers
or instances, move this to Redis (see web_login_store for the same note).
"""
import time

_TTL_SECONDS = 300
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
    """One-time read: pop so coordinates are consumed once, honouring TTL."""
    entry = _store.pop(nonce, None)
    if not entry:
        return None
    expires_at, payload = entry
    if expires_at <= time.time():
        return None
    return payload
