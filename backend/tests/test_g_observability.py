"""
Category G — error handling & observability.

G1: unhandled errors return clean JSON (no stack trace / SQL) + a request id.
G3: /health verifies DB connectivity.
"""
from app.main import app as fastapi_app


# Register a route that blows up, to exercise the global handler.
@fastapi_app.get("/__boom_test")
async def _boom():
    raise RuntimeError("kaboom secret internals 0xDEADBEEF")


async def test_unhandled_error_returns_clean_json(client):
    resp = await client.get("/__boom_test")
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Internal server error"
    assert "request_id" in body
    # No internal detail leaks to the client.
    assert "kaboom" not in resp.text
    assert "Traceback" not in resp.text


async def test_response_has_request_id_header(client):
    resp = await client.get("/health")
    assert resp.headers.get("X-Request-ID")


async def test_health_reports_db_ok(client, monkeypatch):
    # Tests don't start the scheduler, so simulate a healthy running one.
    monkeypatch.setattr(
        "app.services.scheduler.scheduler_health",
        lambda: {"running": True, "last_reminder_run": "2026-07-01T00:00:00+00:00", "healthy": True},
    )
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["db"] is True
    assert resp.json()["scheduler"]["healthy"] is True


async def test_health_503_when_scheduler_dead(client, monkeypatch):
    """DB fine but a silently-dead scheduler → 503, so an uptime pinger catches it
    (dead scheduler = no reminders = otherwise invisible failure)."""
    monkeypatch.setattr(
        "app.services.scheduler.scheduler_health",
        lambda: {"running": False, "last_reminder_run": None, "healthy": False},
    )
    resp = await client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["db"] is True
    assert resp.json()["scheduler"]["healthy"] is False


# ── G4: the frontend CSP config keeps its teeth ─────────────────────────────
# vercel.json ships the SPA's Content-Security-Policy. It's easy to loosen or
# drop a directive by accident during a frontend edit, so pin the load-bearing
# ones: script-src must stay locked to 'self' (the whole point — no inline/eval),
# and the Telegram frame-ancestors embed must survive.

def test_frontend_csp_keeps_script_src_locked_and_telegram_embed():
    import json
    import os

    vercel = os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "vercel.json"
    )
    with open(vercel, encoding="utf-8") as fh:
        config = json.load(fh)

    csps = [
        h["value"]
        for group in config["headers"]
        for h in group["headers"]
        if h["key"] == "Content-Security-Policy"
    ]
    assert len(csps) == 1, "exactly one CSP header, or the browser picks the strictest and breaks things"
    csp = csps[0]
    assert "script-src 'self'" in csp, "script-src must stay 'self' — no inline/eval slipping back in"
    assert "'unsafe-eval'" not in csp and "'unsafe-inline'" not in csp.split("style-src")[0], \
        "no unsafe-* on script-src"
    assert "object-src 'none'" in csp
    # The map preview iframe and the Telegram web embed must remain allowed. Both
    # OSM hosts (www + apex) so a host redirect on their side can't blank the map.
    assert "https://www.openstreetmap.org" in csp and "https://openstreetmap.org" in csp
    assert "frame-ancestors 'self' https://web.telegram.org" in csp


def test_html_shell_has_no_inline_script_so_script_src_self_holds():
    """The one regression that would white-screen production under script-src
    'self': an inline <script> added to the shell (an analytics pixel, a
    theme-flash guard). The build succeeds, CI stays green, and the page dies on
    deploy. Guard the code against the policy, not just the policy against the code."""
    import os
    import re

    index_html = os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "index.html"
    )
    with open(index_html, encoding="utf-8") as fh:
        html = fh.read()
    # A <script> tag with no src= attribute is an inline script.
    inline = re.search(r"<script(?![^>]*\ssrc=)[^>]*>", html)
    assert inline is None, f"inline <script> in the shell breaks script-src 'self': {inline.group(0) if inline else ''}"
    # And the precache-bump marker must survive: it's what makes a header-only CSP
    # change reach already-installed PWA clients (see the comment in index.html).
    assert "csp-precache-bump" in html
