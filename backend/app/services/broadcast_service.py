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

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.booking import Customer
from app.models.broadcast import Broadcast
from app.models.user import User
from app.services.notification_service import send_telegram_message

logger = logging.getLogger("rezerv.broadcast")

# Uzbekistan is UTC+5 year-round (no DST). Used to interpret a naive scheduled
# time the admin enters as local Tashkent time.
UZ_TZ = timezone(timedelta(hours=5))

# Audience → set of Telegram chat ids, resolved at send time.
#
# IMPORTANT: the people who book through the bot are rows in the `customers`
# table, NOT `users`. Only owners, staff and the founder are `users`. So the
# customer audience is resolved from `customers` (plus any legacy User row
# explicitly flagged role=customer), and owners/staff from `users`. This is the
# bug that made every "customers"/"all" broadcast report 0 sent — it was querying
# `users` for role=customer, where real customers never appear.
#
# Super-admins are excluded from every audience — the founder previews via the
# dedicated "send test to me" action and never gets blasted by their own
# "everyone" send, even if they also booked once and have a customer record.

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


def _clean(ids) -> set[int]:
    """Keep only real, messageable chat ids — drop NULL and 0 (walk-in
    customers created by an owner have no Telegram chat)."""
    return {tid for tid in ids if tid}


async def _owner_staff_ids(db) -> set[int]:
    result = await db.execute(
        select(User.telegram_id).where(
            User.telegram_id.isnot(None),
            User.is_active == True,  # noqa: E712
            User.role.in_(("business_owner", "staff")),
        )
    )
    return _clean(tid for (tid,) in result.all())


async def _customer_ids(db) -> set[int]:
    ids: set[int] = set()
    # Real customers: everyone who has booked through the bot.
    cust = await db.execute(
        select(Customer.telegram_id).where(Customer.telegram_id.isnot(None))
    )
    ids |= _clean(tid for (tid,) in cust.all())
    # Legacy / explicitly-flagged User rows with role=customer (rare).
    urows = await db.execute(
        select(User.telegram_id).where(
            User.telegram_id.isnot(None),
            User.is_active == True,  # noqa: E712
            User.role == "customer",
        )
    )
    ids |= _clean(tid for (tid,) in urows.all())
    return ids


async def _superadmin_ids(db) -> set[int]:
    result = await db.execute(
        select(User.telegram_id).where(
            User.telegram_id.isnot(None),
            User.role == "super_admin",
        )
    )
    return _clean(tid for (tid,) in result.all())


async def _resolve_sets(db) -> tuple[set[int], set[int]]:
    """Return (owners_staff, customers) chat-id sets with super-admins removed
    from both, so a founder who also has a customer record is never targeted."""
    admins = await _superadmin_ids(db)
    owners_staff = await _owner_staff_ids(db) - admins
    customers = await _customer_ids(db) - admins
    return owners_staff, customers


def _select_audience(audience: str, owners_staff: set[int], customers: set[int]) -> set[int]:
    if audience == "owners_staff":
        return set(owners_staff)
    if audience == "customers":
        return set(customers)
    return owners_staff | customers  # "all" — deduped across both groups


async def audience_count(db, audience: str) -> int:
    owners_staff, customers = await _resolve_sets(db)
    return len(_select_audience(audience, owners_staff, customers))


async def count_audiences(db) -> dict[str, int]:
    """Recipient count for each audience (for the admin's pre-send preview)."""
    owners_staff, customers = await _resolve_sets(db)
    return {
        "all": len(owners_staff | customers),
        "owners_staff": len(owners_staff),
        "customers": len(customers),
    }


async def _recipient_ids(db, audience: str) -> list[int]:
    owners_staff, customers = await _resolve_sets(db)
    return list(_select_audience(audience, owners_staff, customers))


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
