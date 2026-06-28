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

            stmt = select(Booking).where(
                and_(
                    flag_col == False,  # noqa: E712
                    Booking.status == "confirmed",
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

                    success = await send_telegram_message(customer.telegram_id, text)

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
                    setattr(booking, flag_name, True)
                except Exception:
                    logger.exception("Reminder failed for booking %s", booking.id)

            await db.commit()


async def _send_reminders_safe() -> None:
    try:
        await _send_reminders()
    except Exception:
        logger.exception("Reminder sweep failed")


def start_scheduler() -> None:
    scheduler.add_job(
        _send_reminders_safe,
        "interval",
        minutes=15,
        id="reminders",
        coalesce=True,        # collapse missed runs into one
        max_instances=1,      # never overlap two sweeps
        misfire_grace_time=300,
    )
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
