"""
Category B — authentication & Telegram initData.

Asserts secure behaviour; expected to FAIL against current code, PASS after fixes.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import quote

import pytest

from app.config import settings
from app.services.auth_service import (
    create_access_token, create_refresh_token, verify_telegram_init_data,
)
from tests.factories import create_user

API = "/api/v1"


def make_init_data(bot_token: str, user: dict, auth_date: int | None = None) -> str:
    """Build a realistic Telegram initData string the way Telegram actually does:
    HMAC is computed over URL-DECODED values, but values are URL-ENCODED on the wire."""
    auth_date = auth_date or int(time.time())
    user_json = json.dumps(user, separators=(",", ":"))
    fields = {"auth_date": str(auth_date), "user": user_json}
    data_check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return f"user={quote(user_json)}&auth_date={auth_date}&hash={h}"


# ── B1: /auth/bot must fail closed when BOT_SECRET is unset ───────────────────

async def test_auth_bot_rejects_when_secret_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "bot_secret", "")
    body = {"telegram_id": 999000999, "name": "Attacker", "bot_secret": ""}
    resp = await client.post(f"{API}/auth/bot", json=body)
    assert resp.status_code == 403, resp.text


async def test_auth_bot_accepts_with_correct_secret(client):
    body = {"telegram_id": 12345, "name": "Bot User", "bot_secret": settings.bot_secret}
    resp = await client.post(f"{API}/auth/bot", json=body)
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.json()


# ── B2: initData must fail closed when the bot token is unset ─────────────────

def test_initdata_rejected_when_token_unset(monkeypatch):
    # With an empty bot token an attacker could forge a *validly signed* initData
    # (they know the secret is derived from ""). The validator must fail closed.
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    init = make_init_data("", {"id": 1, "first_name": "X"})  # correctly signed under empty token
    assert verify_telegram_init_data(init) is None


# ── B8: genuine (URL-encoded) initData must be accepted ──────────────────────

def test_valid_initdata_accepted():
    init = make_init_data(settings.telegram_bot_token, {"id": 123, "first_name": "Ali"})
    params = verify_telegram_init_data(init)
    assert params is not None
    assert "user" in params


def test_forged_initdata_rejected():
    init = make_init_data(settings.telegram_bot_token, {"id": 123, "first_name": "Ali"})
    tampered = init.rsplit("hash=", 1)[0] + "hash=" + "0" * 64
    assert verify_telegram_init_data(tampered) is None


# ── B5: expired initData rejected in production ──────────────────────────────

def test_expired_initdata_rejected_in_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    old = int(time.time()) - 7200  # 2 hours ago
    init = make_init_data(settings.telegram_bot_token, {"id": 123}, auth_date=old)
    assert verify_telegram_init_data(init) is None


# ── B3: a refresh token must not work as an access token ─────────────────────

async def test_refresh_token_rejected_as_access(client, db):
    user = await create_user(db, role="business_owner", telegram_id=321, name="U")
    refresh = create_refresh_token(user.id)
    resp = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert resp.status_code == 401, resp.text


async def test_access_token_accepted(client, db):
    user = await create_user(db, role="business_owner", telegram_id=321, name="U")
    access = create_access_token(user.id)
    resp = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert resp.status_code == 200, resp.text


# ── B4: production config must fail fast on weak/missing secrets ──────────────

def test_validate_config_rejects_weak_secret_in_production(monkeypatch):
    from app.config import validate_runtime_config

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", "short")
    with pytest.raises(RuntimeError):
        validate_runtime_config(settings)


def test_validate_config_ok_in_development():
    from app.config import validate_runtime_config

    # Default test env is development → must not raise regardless of secrets.
    validate_runtime_config(settings)


# ── B7: password hashing must actually work (passlib/bcrypt compat) ───────────

def test_password_hashing_roundtrip():
    from app.services.auth_service import hash_password, verify_password

    h = hash_password("test-password-123")
    assert verify_password("test-password-123", h)
    assert not verify_password("wrong-password", h)
