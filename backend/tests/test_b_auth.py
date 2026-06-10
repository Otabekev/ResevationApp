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
    create_access_token, create_refresh_token,
    verify_telegram_init_data, verify_telegram_login_widget,
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


# ── B9: Telegram Login Widget (web/PWA flow, NOT Mini App) ────────────────────

def make_widget_payload(bot_token: str, user: dict, auth_date: int | None = None) -> dict:
    """Build a Telegram-Login-Widget-shaped payload. Note the different crypto
    from Mini App initData: secret = SHA256(bot_token), not HMAC('WebAppData', ...)."""
    auth_date = auth_date or int(time.time())
    data = {**user, "auth_date": auth_date}
    # Exclude None and the (not-yet-set) `hash` from the data-check string.
    data_check_pairs = {k: v for k, v in data.items() if v is not None}
    data_check = "\n".join(f"{k}={data_check_pairs[k]}" for k in sorted(data_check_pairs))
    secret = hashlib.sha256(bot_token.encode()).digest()
    h = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return {**data, "hash": h}


async def test_widget_payload_accepted(client):
    payload = make_widget_payload(
        settings.telegram_bot_token,
        {"id": 555111555, "first_name": "Otabek", "username": "otabek_web"},
    )
    resp = await client.post(f"{API}/auth/telegram-widget", json=payload)
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.json()


async def test_widget_forged_hash_rejected(client):
    payload = make_widget_payload(
        settings.telegram_bot_token,
        {"id": 555111556, "first_name": "Forged"},
    )
    payload["hash"] = "0" * 64
    resp = await client.post(f"{API}/auth/telegram-widget", json=payload)
    assert resp.status_code == 401, resp.text


def test_widget_expired_rejected_in_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    old = int(time.time()) - 2 * 86400  # 2 days ago
    payload = make_widget_payload(
        settings.telegram_bot_token,
        {"id": 1, "first_name": "Stale"},
        auth_date=old,
    )
    assert verify_telegram_login_widget(payload) is None


def test_widget_rejected_when_token_unset(monkeypatch):
    # Parity with B2: an empty bot token must NOT be a valid signing key.
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    payload = make_widget_payload("", {"id": 1, "first_name": "X"})
    assert verify_telegram_login_widget(payload) is None


# ── B10: web dashboard login via bot (deep-link + poll) ──────────────────────

async def test_web_login_complete_and_poll(client):
    """Full handshake against the REAL in-memory store: poll is pending → bot
    completes → poll returns token ONCE (consumed)."""
    nonce = "abc123nonceXYZ"

    # Before the bot completes → pending
    r1 = await client.get(f"{API}/auth/tg-login/poll/{nonce}")
    assert r1.json()["status"] == "pending"

    # Bot confirms the login
    r2 = await client.post(f"{API}/auth/tg-login/complete", json={
        "nonce": nonce, "telegram_id": 777222777, "name": "Web Owner",
        "username": "owner", "language": "uz", "bot_secret": settings.bot_secret,
    })
    assert r2.status_code == 200, r2.text

    # Browser poll picks up the token
    r3 = await client.get(f"{API}/auth/tg-login/poll/{nonce}")
    body = r3.json()
    assert body["status"] == "ok"
    assert "access_token" in body and body["user_id"] > 0

    # One-time read: a second poll is pending again (token already consumed)
    r4 = await client.get(f"{API}/auth/tg-login/poll/{nonce}")
    assert r4.json()["status"] == "pending"


async def test_web_login_complete_rejects_bad_secret(client):
    """A wrong bot_secret must 403 and never park a token (poll stays pending)."""
    resp = await client.post(f"{API}/auth/tg-login/complete", json={
        "nonce": "badsecretnonce", "telegram_id": 1, "name": "X", "bot_secret": "wrong-secret",
    })
    assert resp.status_code == 403, resp.text
    poll = await client.get(f"{API}/auth/tg-login/poll/badsecretnonce")
    assert poll.json()["status"] == "pending"


# ── B7: password hashing must actually work (passlib/bcrypt compat) ───────────

def test_password_hashing_roundtrip():
    from app.services.auth_service import hash_password, verify_password

    h = hash_password("test-password-123")
    assert verify_password("test-password-123", h)
    assert not verify_password("wrong-password", h)
