"""
Broadcast service — resolves recipients and delivers a super-admin announcement
to bot users via the Telegram Bot API.

Sending runs in the background (an immediate task for "send now", or the
scheduler's poller for a future `scheduled_at`). It is paced under Telegram's
~30 msg/sec ceiling and processes each recipient in its own try/except, so one
blocked user never aborts the run. Delivery counters are written back to the
`broadcasts` row as it goes, so the admin sees progress and a final tally.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from app.database import AsyncSessionLocal
from app.models.broadcast import Broadcast
from app.models.user import User
from app.services.notification_service import send_telegram_message

logger = logging.getLogger("rezerv.broadcast")

# Uzbekistan is UTC+5 year-round (no DST). Used to interpret a naive scheduled
# time the admin enters as local Tashkent time.
UZ_TZ = timezone(timedelta(hours=5))

# Which user roles each audience targets. Super-admins are excluded from every
# audience — the founder previews via the dedicated "send test to me" action,
# so they never get blasted by their own "everyone" send.
AUDIENCE_ROLES: dict[str, tuple[str, ...]] = {
    "all": ("business_owner", "staff", "customer"),
    "owners_staff": ("business_owner", "staff"),
    "customers": ("customer",),
}

# Pace ~20 messages/sec — comfortably under Telegram's ~30/sec ceiling so a
# bulk send doesn't trip rate limits.
_SEND_INTERVAL_S = 0.05
# Flush progress counters to the DB every N sends (and once at the end).
_PROGRESS_EVERY = 20


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_scheduled_at(value: datetime | None) -> datetime | None:
    """Treat a naive datetime as Tashkent local time; pass aware ones through."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UZ_TZ)
    return value


def _audience_query(audience: str):
    roles = AUDIENCE_ROLES[audience]
    return (
        User.telegram_id.isnot(None),
        User.is_active == True,  # noqa: E712
        User.role.in_(roles),
    )


async def audience_count(db, audience: str) -> int:
    conds = _audience_query(audience)
    result = await db.execute(select(func.count()).select_from(User).where(*conds))
    return int(result.scalar() or 0)


async def count_audiences(db) -> dict[str, int]:
    """Recipient count for each audience (for the admin's pre-send preview)."""
    return {name: await audience_count(db, name) for name in AUDIENCE_ROLES}


async def _recipient_ids(db, audience: str) -> list[int]:
    conds = _audience_query(audience)
    result = await db.execute(select(User.telegram_id).where(*conds))
    return [tid for (tid,) in result.all() if tid is not None]


async def run_broadcast(broadcast_id: int) -> None:
    """Deliver a broadcast. Idempotent: claims the row (scheduled → sending) and
    bails if it's already sending/done/cancelled, so the immediate task and the
    scheduler poller can never double-send the same row."""
    async with AsyncSessionLocal() as db:
        b = await db.get(Broadcast, broadcast_id)
        if b is None or b.status in ("sending", "done", "cancelled"):
            return
        b.status = "sending"
        b.started_at = b.started_at or _now_utc()
        await db.commit()

        recipients = await _recipient_ids(db, b.audience)
        b.total_recipients = len(recipients)
        b.sent_count = 0
        b.failed_count = 0
        await db.commit()

        text = b.text
        sent = failed = 0
        for i, tid in enumerate(recipients, start=1):
            try:
                ok = await send_telegram_message(tid, text, parse_mode=None)
            except Exception:
                ok = False
            if ok:
                sent += 1
            else:
                failed += 1
            if i % _PROGRESS_EVERY == 0:
                b.sent_count, b.failed_count = sent, failed
                await db.commit()
            await asyncio.sleep(_SEND_INTERVAL_S)

        b.sent_count, b.failed_count = sent, failed
        b.status = "done"
        b.finished_at = _now_utc()
        await db.commit()
        logger.info("Broadcast %s done: %s sent, %s failed", broadcast_id, sent, failed)


async def send_due_broadcasts() -> None:
    """Scheduler hook: run any scheduled broadcast whose time has arrived. Only
    rows with a concrete future `scheduled_at` are picked up here — immediate
    ('send now') rows have a null schedule and are dispatched by their own task."""
    async with AsyncSessionLocal() as db:
        now = _now_utc()
        result = await db.execute(
            select(Broadcast.id).where(
                Broadcast.status == "scheduled",
                Broadcast.scheduled_at.isnot(None),
                Broadcast.scheduled_at <= now,
            )
        )
        due_ids = [row[0] for row in result.all()]

    for bid in due_ids:
        try:
            await run_broadcast(bid)
        except Exception:
            logger.exception("Scheduled broadcast %s failed", bid)


async def send_test(telegram_id: int, text: str) -> bool:
    """Send the message to a single chat (the admin previewing their own send)."""
    if not telegram_id:
        return False
    try:
        return await send_telegram_message(telegram_id, text, parse_mode=None)
    except Exception:
        return False
