import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
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
    queue,
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
    title="Qulay Navbat API",
    description="Universal appointment booking platform for Uzbekistan",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    # Also close the raw schema in prod — /docs/redoc render it, so leaving
    # /openapi.json open would still expose the full API surface.
    openapi_url="/openapi.json" if not settings.is_production else None,
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


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Defense-in-depth headers on every API response (the frontend proxy adds
    its own, but the Railway API is also reachable directly)."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Cache-Control", "no-store")
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
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


# Compress JSON/text responses above ~500 bytes (browsers always send
# Accept-Encoding: gzip). Shrinks transfer size on slow mobile networks; small
# responses skip it so we don't spend CPU compressing for no real gain.
app.add_middleware(GZipMiddleware, minimum_size=500)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Bot-Secret"],
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
app.include_router(queue.router,        prefix="/api/v1")
app.include_router(queue.public_router, prefix="/api/v1")


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Liveness + DB connectivity + reminder-scheduler heartbeat. Returns 503 if
    the DB is unreachable OR the scheduler has silently died (no reminders)."""
    from app.services.scheduler import scheduler_health

    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    sched = scheduler_health()
    healthy = db_ok and sched["healthy"]
    body = {
        "status": "ok" if healthy else "degraded",
        "db": db_ok,
        "scheduler": sched,
        "platform": settings.platform_name,
    }
    return body if healthy else JSONResponse(status_code=503, content=body)
