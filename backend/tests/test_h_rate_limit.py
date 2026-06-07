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


def test_key_uses_forwarded_for_when_anonymous():
    key = rate_limit_key(_request({"x-forwarded-for": "9.9.9.9, 10.0.0.1"}, client_ip="172.16.0.1"))
    assert key == "ip:9.9.9.9"


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
