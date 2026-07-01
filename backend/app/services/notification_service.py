"""
Notification service — sends Telegram messages via Bot API.
Used by the scheduler for reminders and by booking events for confirmations.
"""
import html
import logging

import httpx

from app.config import settings

logger = logging.getLogger("rezerv.notify")


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
    """Sends a message via Telegram Bot API. Returns True on success.

    On failure it logs the reason (Telegram's error description) instead of
    swallowing it silently, so a broadcast that reports "N failed" is always
    diagnosable from the server logs (e.g. "bot was blocked by the user",
    "chat not found")."""
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured — cannot message chat %s", chat_id)
        return False

    # Only send parse_mode when set. Broadcasts pass parse_mode=None (plain text);
    # omitting the key entirely is cleaner than sending JSON null, so a null can
    # never be a factor in a rejected send.
    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{BOT_API_BASE}/sendMessage", json=payload)
            if resp.status_code != 200:
                logger.warning(
                    "Telegram sendMessage failed: chat=%s status=%s body=%s",
                    chat_id, resp.status_code, resp.text[:300],
                )
                return False
            return True
    except Exception as exc:
        logger.warning("Telegram sendMessage error: chat=%s err=%r", chat_id, exc)
        return False


async def send_telegram_location(chat_id: int, latitude: float, longitude: float) -> bool:
    """Sends a native Telegram map pin (tap it → directions in the user's maps
    app). Best-effort: returns True on success, never raises. Callers should only
    invoke this when the business actually has coordinates."""
    if not settings.telegram_bot_token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BOT_API_BASE}/sendLocation",
                json={"chat_id": chat_id, "latitude": latitude, "longitude": longitude},
            )
            return resp.status_code == 200
    except Exception:
        return False


_CONFIRM_LABELS = {
    "uz": {"title": "✅ <b>Bron tasdiqlandi!</b>", "svc": "Xizmat", "staff": "Usta",
           "addr": "Manzil", "phone": "Tel", "price": "Narx", "date": "Sana",
           "time": "Vaqt", "unit": "so'm", "foot": "Kech qolmang! ⏰"},
    "ru": {"title": "✅ <b>Бронь подтверждена!</b>", "svc": "Услуга", "staff": "Мастер",
           "addr": "Адрес", "phone": "Тел", "price": "Цена", "date": "Дата",
           "time": "Время", "unit": "сум", "foot": "Не опаздывайте! ⏰"},
    "en": {"title": "✅ <b>Booking confirmed!</b>", "svc": "Service", "staff": "Staff",
           "addr": "Address", "phone": "Phone", "price": "Price", "date": "Date",
           "time": "Time", "unit": "UZS", "foot": "Don't be late! ⏰"},
}


def booking_confirmed_message(
    lang: str,
    business_name: str,
    service_name: str,
    staff_name: str,
    date_str: str,
    time_str: str,
    address: str | None = None,
    phone: str | None = None,
    price: float | None = None,
) -> str:
    """Customer confirmation. Includes address, phone and price when available so
    the customer knows where to go, how to reach the business, and what it costs
    (a native map pin is sent separately when the business has coordinates)."""
    L = _CONFIRM_LABELS.get(lang, _CONFIRM_LABELS["uz"])
    business_name, service_name, staff_name = _esc(business_name), _esc(service_name), _esc(staff_name)

    lines = [
        L["title"], "",
        f"🏪 {business_name}",
        f"💈 {L['svc']}: {service_name}",
        f"👤 {L['staff']}: {staff_name}",
    ]
    if address:
        lines.append(f"📍 {L['addr']}: {_esc(address)}")
    if phone:
        lines.append(f"📞 {L['phone']}: {_esc(phone)}")
    if price:
        lines.append(f"💰 {L['price']}: {int(price):,} {L['unit']}")
    lines += [
        f"📅 {L['date']}: {date_str}",
        f"🕐 {L['time']}: {time_str}",
        "", L["foot"],
    ]
    return "\n".join(lines)


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


def customer_cancelled_alert_message(
    lang: str,
    customer_name: str,
    date_str: str,
    time_str: str,
    late_policy_hours: int | None = None,
) -> str:
    """Owner alert when a CUSTOMER cancels. If late_policy_hours is set, the
    cancellation landed inside the business's cancellation window — flag it so the
    owner knows the slot freed up late and may not get rebooked in time."""
    customer_name = _esc(customer_name)
    templates = {
        "uz": (
            f"❌ <b>Mijoz bronni bekor qildi</b>\n"
            f"👤 {customer_name}\n"
            f"📅 {date_str}  🕐 {time_str}"
        ),
        "ru": (
            f"❌ <b>Клиент отменил запись</b>\n"
            f"👤 {customer_name}\n"
            f"📅 {date_str}  🕐 {time_str}"
        ),
        "en": (
            f"❌ <b>Customer cancelled the booking</b>\n"
            f"👤 {customer_name}\n"
            f"📅 {date_str}  🕐 {time_str}"
        ),
    }
    msg = templates.get(lang, templates["uz"])
    if late_policy_hours is not None:
        late_note = {
            "uz": f"\n⚠️ Kech bekor qilindi (siyosatingiz: {late_policy_hours} soat).",
            "ru": f"\n⚠️ Поздняя отмена (ваше правило: {late_policy_hours} ч).",
            "en": f"\n⚠️ Late cancellation (your policy: {late_policy_hours}h).",
        }.get(lang, f"\n⚠️ Kech bekor qilindi (siyosatingiz: {late_policy_hours} soat).")
        msg += late_note
    return msg


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
