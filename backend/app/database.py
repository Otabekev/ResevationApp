from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url_async,
    pool_pre_ping=True,
    # Refresh connections before Neon idles/closes them (Neon drops idle conns
    # fairly aggressively); keeps pre_ping reconnects rare.
    pool_recycle=300,
    pool_size=10,
    max_overflow=20,
    # OFF by default — see Settings.sql_echo. Logging every statement to stdout
    # synchronously is real per-query overhead and was running in prod.
    echo=settings.sql_echo,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
