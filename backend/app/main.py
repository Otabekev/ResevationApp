import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings, validate_runtime_config
from app.database import get_db
from app.limiter import limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("rezerv")
from app.routers import (
    admin,
    analytics,
    auth,
    availability,
    bookings,
    businesses,
    public,
    reviews,
    schedules,
    services,
    staff,
)
from app.routers.staff import invite_router
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_runtime_config(settings)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Rezerv API",
    description="Universal appointment booking platform for Uzbekistan",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach a short request id for log correlation; expose it on the response."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Never leak stack traces / SQL to clients. Log full detail server-side."""
    request_id = getattr(request.state, "request_id", "-")
    logger.exception(
        "Unhandled error [req=%s] %s %s", request_id, request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth.router,         prefix="/api/v1")
app.include_router(businesses.router,   prefix="/api/v1")
app.include_router(services.router,     prefix="/api/v1")
app.include_router(staff.router,        prefix="/api/v1")
app.include_router(schedules.router,    prefix="/api/v1")
app.include_router(availability.router, prefix="/api/v1")
app.include_router(bookings.router,     prefix="/api/v1")
app.include_router(reviews.router,      prefix="/api/v1")
app.include_router(analytics.router,    prefix="/api/v1")
app.include_router(public.router,       prefix="/api/v1")
app.include_router(admin.router,        prefix="/api/v1")
app.include_router(invite_router,       prefix="/api/v1")


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Liveness + DB connectivity check."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": False, "platform": settings.platform_name},
        )
    return {"status": "ok", "db": True, "platform": settings.platform_name}
