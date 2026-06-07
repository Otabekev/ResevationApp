"""
APScheduler-based reminder scheduler.
Runs every 15 minutes and sends:
  - 24-hour reminders
  - 1-hour reminders
"""
from datetime import date, datetime, time, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import and_, select

from app.database import AsyncSessionLocal
from app.models.booking import Booking, Customer, Notification
from app.models.business import Business
from app.models.service import Service
from app.models.staff import Staff
from app.services.notification_service import booking_reminder_message, send_telegram_message
from app.timeutils import to_utc

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
                    flag_col == False,
                    Booking.status == "confirmed",
                    Booking.booking_date >= today,
                )
            )
            result = await db.execute(stmt)
            bookings = result.scalars().all()

            for booking in bookings:
                # Booking times are stored in business-local time (Asia/Tashkent);
                # convert to UTC before comparing against the UTC reminder window.
                apt_datetime = to_utc(booking.booking_date, booking.start_time)
                if not (window_start <= apt_datetime <= window_end):
                    continue

                # Load related objects
                cust_result = await db.execute(select(Customer).where(Customer.id == booking.customer_id))
                customer = cust_result.scalar_one_or_none()
                if not customer:
                    continue

                biz_result = await db.execute(select(Business).where(Business.id == booking.business_id))
                business = biz_result.scalar_one_or_none()

                svc_result = await db.execute(select(Service).where(Service.id == booking.service_id))
                service = svc_result.scalar_one_or_none()

                if not business or not service:
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

                # Log notification
                notif = Notification(
                    telegram_id=customer.telegram_id,
                    notification_type=flag_name,
                    booking_id=booking.id,
                    message=text,
                    status="sent" if success else "failed",
                )
                db.add(notif)

                # Mark flag
                setattr(booking, flag_name, True)

            await db.commit()


def start_scheduler() -> None:
    scheduler.add_job(_send_reminders, "interval", minutes=15, id="reminders")
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
