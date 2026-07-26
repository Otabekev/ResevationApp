"""
Category H — rate-limit keying (H2).

The key must be the authenticated user when a token is present (so users sharing
a mobile NAT IP aren't throttled together), the END USER for traffic the Telegram
bot proxies (every one of those arrives from the bot's single egress IP), and an
X-Forwarded-For-aware IP otherwise. One shared limiter instance (E6).
"""
from starlette.requests import Request

from app.config import settings
from app.limiter import limiter, rate_limit_key
from app.services.auth_service import create_access_token

BOT_SECRET = "test-bot-secret-shared-32-characters-minimum-000"


def _request(headers: dict, client_ip: str = "1.2.3.4", path: str = "/") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_ip, 0),
    }
    return Request(scope)


def test_key_prefers_authenticated_user():
    token = create_access_token(42)
    key = rate_limit_key(_request({"authorization": f"Bearer {token}"}))
    assert key == "user:42"


def test_key_uses_trusted_rightmost_forwarded_for_when_anonymous():
    # The RIGHTMOST XFF entry is the IP the trusted edge proxy appended (the real
    # client peer). The leftmost entries are client-supplied and spoofable, so the
    # key must NOT be derived from them — otherwise an attacker rotates a fake first
    # hop per request and bypasses every anonymous rate limit.
    key = rate_limit_key(_request({"x-forwarded-for": "9.9.9.9, 10.0.0.1"}, client_ip="172.16.0.1"))
    assert key == "ip:10.0.0.1"


def test_key_ignores_spoofed_leftmost_forwarded_for():
    # Two requests from the same real client (same rightmost hop) but different
    # attacker-supplied leftmost hops must map to the SAME key.
    k1 = rate_limit_key(_request({"x-forwarded-for": "1.1.1.1, 203.0.113.7"}))
    k2 = rate_limit_key(_request({"x-forwarded-for": "2.2.2.2, 203.0.113.7"}))
    assert k1 == k2 == "ip:203.0.113.7"


def test_key_falls_back_to_client_ip():
    key = rate_limit_key(_request({}, client_ip="5.6.7.8"))
    assert key == "ip:5.6.7.8"


# ── H3: bot-proxied traffic is keyed per Telegram user ───────────────────────

def test_bot_traffic_keys_on_the_end_user(monkeypatch):
    """Two Telegram users coming through the bot must land in DIFFERENT buckets.
    Sharing one (the bot's egress IP) meant a single user could 429 the whole
    platform's booking flow."""
    monkeypatch.setattr(settings, "bot_secret", BOT_SECRET)
    k1 = rate_limit_key(_request({"x-bot-secret": BOT_SECRET, "x-bot-user": "111"}))
    k2 = rate_limit_key(_request({"x-bot-secret": BOT_SECRET, "x-bot-user": "222"}))
    assert k1 == "tg:111" and k2 == "tg:222"


def test_same_bot_user_shares_one_bucket(monkeypatch):
    """...while the SAME user still gets throttled, from whatever IP the bot
    happens to egress from."""
    monkeypatch.setattr(settings, "bot_secret", BOT_SECRET)
    k1 = rate_limit_key(_request({"x-bot-secret": BOT_SECRET, "x-bot-user": "111"}, client_ip="1.1.1.1"))
    k2 = rate_limit_key(_request({"x-bot-secret": BOT_SECRET, "x-bot-user": "111"}, client_ip="2.2.2.2"))
    assert k1 == k2 == "tg:111"


def test_bot_user_header_is_ignored_without_the_secret(monkeypatch):
    """THE security property. If X-Bot-User were trusted unauthenticated, any
    caller could send a fresh value per request, mint unlimited buckets, and
    bypass the anonymous IP limit completely — worse than the bug it fixes."""
    monkeypatch.setattr(settings, "bot_secret", BOT_SECRET)
    for headers in (
        {"x-bot-user": "111"},                                  # no secret at all
        {"x-bot-secret": "wrong-secret", "x-bot-user": "111"},  # bad secret
    ):
        key = rate_limit_key(_request(headers, client_ip="5.6.7.8"))
        assert key == "ip:5.6.7.8", f"{headers} escaped IP keying via {key}"


def test_bot_user_header_must_be_a_plain_id(monkeypatch):
    """A non-numeric or oversized value falls back to the bot's per-path bucket
    instead of becoming part of the key."""
    monkeypatch.setattr(settings, "bot_secret", BOT_SECRET)
    for bad in ("abc", "1; DROP", "", "9" * 40):
        key = rate_limit_key(
            _request({"x-bot-secret": BOT_SECRET, "x-bot-user": bad}, path="/api/v1/availability")
        )
        assert key == "bot:/api/v1/availability", f"{bad!r} produced {key}"


def test_bot_secret_unset_fails_closed(monkeypatch):
    """With no configured secret, nothing is a trusted bot — back to IP keying."""
    monkeypatch.setattr(settings, "bot_secret", "")
    key = rate_limit_key(_request({"x-bot-secret": "", "x-bot-user": "111"}, client_ip="5.6.7.8"))
    assert key == "ip:5.6.7.8"


def test_single_shared_limiter_instance():
    # main, auth and availability must all import the SAME limiter object,
    # otherwise the registered limits never enforce.
    from app.main import limiter as main_limiter
    from app.routers.auth import limiter as auth_limiter

    assert main_limiter is limiter
    assert auth_limiter is limiter
