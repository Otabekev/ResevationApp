"""Lazy async Redis client. Connection is opened on first use (not at import),
so importing this module never blocks app startup or tests."""
import redis.asyncio as redis

from app.config import settings

_client: "redis.Redis | None" = None


def get_redis() -> "redis.Redis":
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client
