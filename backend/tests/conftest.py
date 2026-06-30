"""
Shared test fixtures.

Strategy: the bulk of the suite runs the REAL FastAPI app against an in-memory
SQLite database (no Docker needed). Postgres-only behaviour (the double-booking
exclusion constraint) is covered by tests marked `@pytest.mark.postgres`, which
run only when TEST_DATABASE_URL points at a real Postgres.

Test env vars are set BEFORE importing any app module so pydantic-settings reads
them from the environment instead of the repo's real .env.
"""
import os

# ── Test configuration (must be set before importing app.config) ──────────────
# A localhost Postgres URL keeps app.database.create_async_engine happy at import
# time (no ssl appended, never actually connected — tests override get_db).
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long-000000")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST-BOT-TOKEN-FOR-HMAC")
os.environ.setdefault("TELEGRAM_BOT_USERNAME", "TestRezerv_bot")
os.environ.setdefault("BOT_SECRET", "test-bot-secret-shared-32-characters-minimum-000")
os.environ.setdefault("SUPER_ADMIN_TELEGRAM_IDS", "999000999")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")
os.environ.setdefault("ENVIRONMENT", "development")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register all mappers on Base.metadata
from app.database import Base, get_db
from app.main import app as fastapi_app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    """Fresh in-memory SQLite, schema built from the ORM metadata, per test."""
    eng = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection so :memory: persists across sessions
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker_(engine):
    # Mirror production's session semantics exactly (app/database.py): autoflush
    # OFF. With autoflush ON (the default), a pending DELETE gets flushed before a
    # later INSERT on the same unique key, hiding delete-then-reinsert bugs that
    # 500 in prod. Keep these in sync so tests reproduce real behaviour.
    return async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


@pytest_asyncio.fixture
async def db(sessionmaker_):
    """Direct DB session for seeding/asserting inside a test."""
    async with sessionmaker_() as session:
        yield session


@pytest_asyncio.fixture
async def client(sessionmaker_):
    """HTTP client hitting the real app, with get_db pointed at the test DB."""
    async def _override_get_db():
        async with sessionmaker_() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    fastapi_app.state.limiter.enabled = False  # don't rate-limit across tests
    # raise_app_exceptions=False so the global 500 handler's response is returned
    # to the client (as in production) instead of being re-raised into the test.
    transport = ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _no_telegram(monkeypatch):
    """Never hit the real Telegram API during tests."""
    async def _noop(*args, **kwargs):
        return True

    for target in (
        "app.services.notification_service.send_telegram_message",
        "app.routers.bookings.send_telegram_message",
    ):
        monkeypatch.setattr(target, _noop, raising=False)
