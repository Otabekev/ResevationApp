"""
APScheduler-based reminder scheduler.
Runs every 15 minutes and sends:
  - 24-hour reminders
  - 1-hour reminders

Hardening notes:
  - The candidate query is bounded to [today, today + 2 days] so the job never
    scans the whole future bookings table.
  - Each booking is processed inside its own try/except — one failed send
    (Telegram hiccup, deleted customer) can never abort the whole sweep.
"""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import and_, select

from app.database import AsyncSessionLocal
from app.models.booking import Booking, Customer, Notification
from app.models.business import Business
from app.models.service import Service
from app.services.notification_service import (
    booking_reminder_message,
    send_telegram_location,
    send_telegram_message,
)
from app.timeutils import to_utc

logger = logging.getLogger("rezerv.scheduler")

scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")

# Heartbeat: updated after every reminder sweep (success OR handled error). If it
# stops advancing, the scheduler has silently died — reminders would stop with no
# other symptom, so /health watches it.
last_reminder_run: datetime | None = None


def scheduler_health() -> dict:
    """Reminder-scheduler liveness for /health. Stale = the 15-min sweep hasn't
    run in 20 min (dead scheduler / stuck loop). last_reminder_run is seeded at
    start so a freshly-started scheduler isn't flagged before its first sweep."""
    now = datetime.now(timezone.utc)
    running = scheduler.running
    stale = last_reminder_run is None or (now - last_reminder_run) > timedelta(minutes=20)
    return {
        "running": running,
        "last_reminder_run": last_reminder_run.isoformat() if last_reminder_run else None,
        "healthy": bool(running and not stale),
    }


async def _send_reminders() -> None:
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        today = now.date()

        for hours_until, flag_col, flag_name in [
            (24, Booking.reminder_24h_sent, "reminder_24h_sent"),
            (1, Booking.reminder_1h_sent, "reminder_1h_sent"),
        ]:
            window_start = now + timedelta(hours=hours_until - 0.25)
            window_end = now + timedelta(hours=hours_until + 0.25)

            # Pending bookings (a service with requires_confirmation=True is
            # created pending, booking_engine.py) hold their slot exactly like
            # confirmed ones — every other live-booking filter in the codebase
            # treats pending+confirmed together. Reminding them is what stops the
            # no-shows the reviewer flagged.
            stmt = select(Booking).where(
                and_(
                    flag_col == False,  # noqa: E712
                    Booking.status.in_(["pending", "confirmed"]),
                    Booking.booking_date >= today,
                    Booking.booking_date <= today + timedelta(days=2),
                )
            )
            result = await db.execute(stmt)
            bookings = result.scalars().all()

            for booking in bookings:
                try:
                    # Booking times are stored in business-local time (Asia/Tashkent);
                    # convert to UTC before comparing against the UTC reminder window.
                    apt_datetime = to_utc(booking.booking_date, booking.start_time)
                    if not (window_start <= apt_datetime <= window_end):
                        continue

                    customer = (
                        await db.execute(
                            select(Customer).where(Customer.id == booking.customer_id)
                        )
                    ).scalar_one_or_none()
                    # Walk-in customers have no Telegram — skip but mark sent so
                    # the row isn't rescanned forever.
                    if not customer or not customer.telegram_id:
                        setattr(booking, flag_name, True)
                        continue

                    business = (
                        await db.execute(
                            select(Business).where(Business.id == booking.business_id)
                        )
                    ).scalar_one_or_none()
                    service = (
                        await db.execute(
                            select(Service).where(Service.id == booking.service_id)
                        )
                    ).scalar_one_or_none()
                    if not business or not service:
                        setattr(booking, flag_name, True)
                        continue

                    lang = customer.language
                    svc_name = getattr(service, f"name_{lang}", service.name_uz)
                    time_str = booking.start_time.strftime("%H:%M")

                    text = booking_reminder_message(
                        lang=lang,
                        business_name=business.name,
                        service_name=svc_name,
                        time_str=time_str,
                        hours_until=hours_until,
                    )

                    # A one-tap Cancel button on the reminder — a customer who
                    # can't make it frees the slot instead of no-showing. Routes
                    # to the bot's existing cancel_ask handler.
                    cancel_label = {
                        "uz": "❌ Bekor qilish", "ru": "❌ Отменить", "en": "❌ Cancel",
                    }.get(lang, "❌ Bekor qilish")
                    reminder_kb = {
                        "inline_keyboard": [
                            [{"text": cancel_label, "callback_data": f"cancel_ask_{booking.id}"}]
                        ]
                    }
                    success = await send_telegram_message(
                        customer.telegram_id, text, reply_markup=reminder_kb
                    )

                    # On the 1-hour reminder (read right before heading out), also
                    # drop the business map pin for one-tap directions.
                    if (
                        hours_until == 1
                        and business.latitude is not None
                        and business.longitude is not None
                    ):
                        await send_telegram_location(
                            customer.telegram_id, business.latitude, business.longitude
                        )

                    db.add(
                        Notification(
                            telegram_id=customer.telegram_id,
                            notification_type=flag_name,
                            booking_id=booking.id,
                            message=text,
                            status="sent" if success else "failed",
                        )
                    )
                    # Only mark the reminder as sent when it actually went out. A
                    # transient Telegram failure leaves the flag False so the next
                    # 15-min sweep retries (bounded — the booking drops out once it
                    # leaves the ±15-min window). Permanent skips above (no
                    # telegram_id / missing business) still set the flag, since
                    # retrying those never helps.
                    if success:
                        setattr(booking, flag_name, True)
                except Exception:
                    logger.exception("Reminder failed for booking %s", booking.id)

            await db.commit()


async def _send_reminders_safe() -> None:
    global last_reminder_run
    try:
        await _send_reminders()
    except Exception:
        logger.exception("Reminder sweep failed")
    finally:
        last_reminder_run = datetime.now(timezone.utc)


async def _send_due_broadcasts_safe() -> None:
    try:
        from app.services.broadcast_service import send_due_broadcasts
        await send_due_broadcasts()
    except Exception:
        logger.exception("Broadcast poll failed")


def start_scheduler() -> None:
    global last_reminder_run
    last_reminder_run = datetime.now(timezone.utc)  # grace before the first sweep
    scheduler.add_job(
        _send_reminders_safe,
        "interval",
        minutes=15,
        id="reminders",
        coalesce=True,        # collapse missed runs into one
        max_instances=1,      # never overlap two sweeps
        misfire_grace_time=300,
    )
    # Poll for due scheduled broadcasts (near-minute precision). Cheap query;
    # only does work when a broadcast's scheduled_at has arrived.
    scheduler.add_job(
        _send_due_broadcasts_safe,
        "interval",
        seconds=60,
        id="broadcasts",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
