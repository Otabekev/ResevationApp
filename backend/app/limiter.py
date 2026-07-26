"""
Single shared rate limiter. Keying (H2): authenticated requests are limited
per-user (so users behind a shared mobile NAT aren't lumped together), requests
the Telegram bot proxies are limited per END USER, and everything else per client
IP, honoring one trusted proxy's X-Forwarded-For.
"""
import hmac

from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import settings

# A Telegram user id is a positive integer well under this length; the cap just
# stops a caller from making the limiter's key arbitrarily large.
_MAX_TG_ID_LEN = 20


def _is_trusted_bot(request: Request) -> bool:
    """True only for the real bot: the shared BOT_SECRET matched, constant-time.
    Fails closed when the secret is unset."""
    expected = settings.bot_secret
    provided = request.headers.get("x-bot-secret", "")
    return bool(expected) and bool(provided) and hmac.compare_digest(provided, expected)


def rate_limit_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.decode(
                auth[7:], settings.secret_key, algorithms=["HS256"],
                options={"verify_exp": False},
            )
            sub = payload.get("sub")
            if sub and payload.get("type") != "refresh":
                return f"user:{sub}"
        except JWTError:
            pass

    # Bot-proxied traffic. Every Telegram user reaches us through the bot's single
    # egress IP and carries no Bearer token, so an IP key would put the ENTIRE
    # platform in one bucket: one chatty (or hostile) Telegram user exhausts the
    # booking limit for everybody. Key on the end user the bot names instead.
    #
    # X-Bot-User is trusted ONLY behind a valid bot secret. Without that check it
    # would be the opposite of a fix — any anonymous caller could send a fresh
    # value per request and get an unlimited number of buckets, bypassing the
    # anonymous IP limit entirely.
    if _is_trusted_bot(request):
        tg_id = request.headers.get("x-bot-user", "")
        if tg_id.isdigit() and len(tg_id) <= _MAX_TG_ID_LEN:
            return f"tg:{tg_id}"
        # The bot's own calls that aren't on behalf of one user: keep them in a
        # per-path bucket rather than sharing the users' one.
        return f"bot:{request.url.path}"

    # Use the RIGHTMOST X-Forwarded-For entry — the IP the trusted edge proxy
    # (Railway) appended, i.e. the real client peer. The leftmost entries are
    # whatever the client sent and are fully spoofable, so keying off split(",")[0]
    # let an attacker rotate a fake first hop per request and bypass every
    # anonymous rate limit. Fall back to the socket peer when no XFF is present.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return f"ip:{parts[-1]}"
    return f"ip:{get_remote_address(request)}"


# storage_uri=None → in-process memory (single-instance default). Set
# RATE_LIMIT_STORAGE_URL to a Redis URL to make counters durable across
# deploys/restarts and shared across instances.
limiter = Limiter(key_func=rate_limit_key, storage_uri=settings.rate_limit_storage_url or None)
