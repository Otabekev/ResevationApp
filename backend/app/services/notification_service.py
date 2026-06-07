"""
Notification service — sends Telegram messages via Bot API.
Used by the scheduler for reminders and by booking events for confirmations.
"""
import html

import httpx

from app.config import settings


def _esc(value: str) -> str:
    """Escape user-controlled text before it goes into a parse_mode=HTML message."""
    return html.escape(str(value), quote=False)


BOT_API_BASE = f"https://api.telegram.org/bot{settings.telegram_bot_token}"


async def send_telegram_message(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
) -> bool:
    """Sends a message via Telegram Bot API. Returns True on success."""
    if not settings.telegram_bot_token:
        return False

    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{BOT_API_BASE}/sendMessage", json=payload)
            return resp.status_code == 200
    except Exception:
        return False


def booking_confirmed_message(
    lang: str,
    business_name: str,
    service_name: str,
    staff_name: str,
    date_str: str,
    time_str: str,
) -> str:
    business_name, service_name, staff_name = _esc(business_name), _esc(service_name), _esc(staff_name)
    templates = {
        "uz": (
            f"✅ <b>Bron tasdiqlandi!</b>\n\n"
            f"🏪 {business_name}\n"
            f"💈 Xizmat: {service_name}\n"
            f"👤 Usta: {staff_name}\n"
            f"📅 Sana: {date_str}\n"
            f"🕐 Vaqt: {time_str}\n\n"
            f"Kech qolmang! ⏰"
        ),
        "ru": (
            f"✅ <b>Бронь подтверждена!</b>\n\n"
            f"🏪 {business_name}\n"
            f"💈 Услуга: {service_name}\n"
            f"👤 Мастер: {staff_name}\n"
            f"📅 Дата: {date_str}\n"
            f"🕐 Время: {time_str}\n\n"
            f"Не опаздывайте! ⏰"
        ),
        "en": (
            f"✅ <b>Booking confirmed!</b>\n\n"
            f"🏪 {business_name}\n"
            f"💈 Service: {service_name}\n"
            f"👤 Staff: {staff_name}\n"
            f"📅 Date: {date_str}\n"
            f"🕐 Time: {time_str}\n\n"
            f"Don't be late! ⏰"
        ),
    }
    return templates.get(lang, templates["uz"])


def booking_reminder_message(
    lang: str,
    business_name: str,
    service_name: str,
    time_str: str,
    hours_until: int,
) -> str:
    business_name, service_name = _esc(business_name), _esc(service_name)
    when = {
        "uz": f"{hours_until} soatdan keyin",
        "ru": f"через {hours_until} час(а)",
        "en": f"in {hours_until} hour(s)",
    }.get(lang, f"{hours_until} soatdan keyin")

    templates = {
        "uz": f"⏰ Eslatma: {when} {business_name}da {service_name} uchun broningiz bor. Vaqt: {time_str}",
        "ru": f"⏰ Напоминание: {when} у вас запись на {service_name} в {business_name}. Время: {time_str}",
        "en": f"⏰ Reminder: {when} you have a {service_name} appointment at {business_name}. Time: {time_str}",
    }
    return templates.get(lang, templates["uz"])


def booking_cancelled_message(lang: str, business_name: str, date_str: str, time_str: str) -> str:
    business_name = _esc(business_name)
    templates = {
        "uz": f"❌ {business_name}dagi {date_str} {time_str} dagi broningiz bekor qilindi.",
        "ru": f"❌ Ваша запись в {business_name} на {date_str} в {time_str} отменена.",
        "en": f"❌ Your booking at {business_name} on {date_str} at {time_str} has been cancelled.",
    }
    return templates.get(lang, templates["uz"])


def review_prompt_message(lang: str, business_name: str, service_name: str, booking_id: int) -> str:
    business_name, service_name = _esc(business_name), _esc(service_name)
    templates = {
        "uz": (
            f"⭐ <b>{business_name}</b>da {service_name} xizmatidan foydalandingiz.\n\n"
            f"Xizmatni baholang (1-5 yulduz):\n"
            f"Bron #{booking_id}"
        ),
        "ru": (
            f"⭐ Вы посетили <b>{business_name}</b> — {service_name}.\n\n"
            f"Оцените услугу (1-5 звёзд):\n"
            f"Запись #{booking_id}"
        ),
        "en": (
            f"⭐ You visited <b>{business_name}</b> for {service_name}.\n\n"
            f"Rate your experience (1-5 stars):\n"
            f"Booking #{booking_id}"
        ),
    }
    return templates.get(lang, templates["uz"])


def new_booking_alert_message(
    lang: str,
    customer_name: str,
    service_name: str,
    date_str: str,
    time_str: str,
) -> str:
    """Alert sent to business owner / staff when a new booking arrives."""
    customer_name, service_name = _esc(customer_name), _esc(service_name)
    templates = {
        "uz": (
            f"🔔 <b>Yangi bron!</b>\n"
            f"👤 Mijoz: {customer_name}\n"
            f"💈 Xizmat: {service_name}\n"
            f"📅 {date_str} | 🕐 {time_str}"
        ),
        "ru": (
            f"🔔 <b>Новая запись!</b>\n"
            f"👤 Клиент: {customer_name}\n"
            f"💈 Услуга: {service_name}\n"
            f"📅 {date_str} | 🕐 {time_str}"
        ),
        "en": (
            f"🔔 <b>New booking!</b>\n"
            f"👤 Customer: {customer_name}\n"
            f"💈 Service: {service_name}\n"
            f"📅 {date_str} | 🕐 {time_str}"
        ),
    }
    return templates.get(lang, templates["uz"])
