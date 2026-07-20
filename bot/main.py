import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, ErrorEvent, MenuButtonCommands

from config import BOT_TOKEN, REDIS_URL
from handlers import booking, fallback, my_bookings, start
from i18n import t

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    # Redis holds each user's conversation state (which booking step they're on)
    # and is read/written on EVERY button tap. With no timeout, a single stalled
    # Redis call over a flaky network hangs the whole update forever — the user
    # sees a frozen button that never responds. These settings cap any single
    # call at 5s (so the @dp.errors guard below can release the spinner and ask
    # them to retry instead of an infinite freeze) and keep the link healthy.
    storage = RedisStorage.from_url(
        REDIS_URL,
        connection_kwargs={
            "socket_timeout": 3,           # cap a single op; healthy Singapore ops are tens of ms
            "socket_connect_timeout": 5,   # (re)connecting can take a touch longer
            "socket_keepalive": True,      # keep the TCP link warm at the kernel level between taps
            "health_check_interval": 120,  # only PING-before-use a connection idle >2min, so warm
                                           # taps never pay an extra round-trip (was 30s — too eager)
            "retry_on_timeout": True,      # reconnect+retry once instead of surfacing a transient error
        },
    )
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=storage)

    dp.include_router(start.router)
    dp.include_router(booking.router)
    dp.include_router(my_bookings.router)
    # LAST on purpose: the catch-all that re-docks the persistent keyboard when a
    # user types anything unrecognized (Telegram sometimes drops the keyboard
    # after days of inactivity — typing anything must bring the buttons back).
    dp.include_router(fallback.router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> None:
        """Last-resort guard: log the error and release the callback spinner so
        a single handler crash never leaves a user staring at a frozen button."""
        logger.exception("Unhandled bot error: %s", event.exception)
        update = event.update
        callback = getattr(update, "callback_query", None)
        if callback:
            try:
                await callback.answer("⚠️ Error. Try again / Xatolik. Qayta urinib ko'ring.", show_alert=False)
            except Exception:
                pass

    # Menu button (left of the input field) shows clear, one-tap commands so
    # users who don't know to type /start still have an obvious way in — and a
    # business owner who found the bot via a flyer sees "add your business".
    await bot.set_my_commands([
        BotCommand(command="start", description="📅 Bron qilish / Boshlash"),
        BotCommand(command="biznes", description="🏪 Biznesingizni bepul qo'shish"),
    ])
    # Make the button left of the input field the COMMANDS menu (Boshlash /
    # Biznes qo'shish) instead of a BotFather-configured web-app launcher — a
    # customer whose docked keyboard vanished always has a visible one-tap way
    # to restart the bot. Overrides any BotFather menu-button setting.
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception:
        logger.warning("Could not set chat menu button", exc_info=True)

    # Ambient "what is this + how to use" text shown the moment a user opens the
    # bot (the pre-Start screen) and on its profile — this is the always-there
    # background instruction. Set the default (uz + fallback) plus ru/en. Wrapped
    # so a transient Telegram API hiccup on boot never stops the bot polling.
    try:
        await bot.set_my_description(t("bot_description", "uz"))
        await bot.set_my_short_description(t("bot_short_description", "uz"))
        for lc in ("ru", "en"):
            await bot.set_my_description(t("bot_description", lc), language_code=lc)
            await bot.set_my_short_description(t("bot_short_description", lc), language_code=lc)
    except Exception:
        logger.warning("Could not set bot description/commands metadata", exc_info=True)

    logger.info("Bot starting...")
    # drop_pending_updates: on every restart (each deploy restarts the bot),
    # discard the taps that queued while it was down. Without this, a deploy's
    # ~30s window of queued button taps all replay in a backlog on startup, so
    # every button feels delayed for the first stretch after a deploy. A dropped
    # tap just means the user taps again — far better than a stale backlog.
    await dp.start_polling(
        bot,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
