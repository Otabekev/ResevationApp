import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, ErrorEvent

from config import BOT_TOKEN, REDIS_URL
from handlers import booking, my_bookings, start

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    storage = RedisStorage.from_url(REDIS_URL)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=storage)

    dp.include_router(start.router)
    dp.include_router(booking.router)
    dp.include_router(my_bookings.router)

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

    # Menu button (left of the input field) shows a clear, localized command so
    # users who don't know to type /start still have an obvious one-tap way in.
    await bot.set_my_commands([
        BotCommand(command="start", description="📅 Bron qilish / Boshlash"),
    ])

    logger.info("Bot starting...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
