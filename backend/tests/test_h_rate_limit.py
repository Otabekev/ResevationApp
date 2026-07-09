"""
Category H — rate-limit keying (H2).

The key must be the authenticated user when a token is present (so users sharing
a mobile NAT IP aren't throttled together), and an X-Forwarded-For-aware IP
otherwise. One shared limiter instance (E6).
"""
from starlette.requests import Request

from app.limiter import limiter, rate_limit_key
from app.services.auth_service import create_access_token


def _request(headers: dict, client_ip: str = "1.2.3.4") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
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


def test_single_shared_limiter_instance():
    # main, auth and availability must all import the SAME limiter object,
    # otherwise the registered limits never enforce.
    from app.main import limiter as main_limiter
    from app.routers.auth import limiter as auth_limiter

    assert main_limiter is limiter
    assert auth_limiter is limiter
