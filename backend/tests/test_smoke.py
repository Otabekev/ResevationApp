"""Harness smoke tests — prove the app boots and the test DB wiring works."""


async def test_health_ok(client, monkeypatch):
    # Tests don't start the scheduler; simulate a healthy one so /health reflects
    # DB liveness (scheduler-down behaviour is covered in test_g_observability).
    monkeypatch.setattr(
        "app.services.scheduler.scheduler_health",
        lambda: {"running": True, "last_reminder_run": "2026-07-01T00:00:00+00:00", "healthy": True},
    )
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
