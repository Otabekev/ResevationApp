"""Harness smoke tests — prove the app boots and the test DB wiring works."""


async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_db_schema_built(db):
    from sqlalchemy import text

    # The customers table should exist in the in-memory SQLite schema.
    result = await db.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='customers'")
    )
    assert result.scalar_one_or_none() == "customers"
