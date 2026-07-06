"""
Single shared rate limiter. Keying (H2): authenticated requests are limited
per-user (so users behind a shared mobile NAT aren't lumped together), and
anonymous requests per client IP, honoring one trusted proxy's X-Forwarded-For.
"""
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import settings


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

    xff = request.headers.get("x-forwarded-for")
    if xff:
        return f"ip:{xff.split(',')[0].strip()}"
    return f"ip:{get_remote_address(request)}"


# storage_uri=None → in-process memory (single-instance default). Set
# RATE_LIMIT_STORAGE_URL to a Redis URL to make counters durable across
# deploys/restarts and shared across instances.
limiter = Limiter(key_func=rate_limit_key, storage_uri=settings.rate_limit_storage_url or None)
