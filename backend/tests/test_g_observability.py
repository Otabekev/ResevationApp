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


async def test_health_reports_db_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["db"] is True
