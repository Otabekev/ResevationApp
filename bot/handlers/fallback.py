"""Catch-all for unrecognized text — the docked-keyboard self-heal.

Telegram clients sometimes collapse or drop the persistent reply keyboard after
days of inactivity or a cache clean. Older users then face an empty chat with no
buttons and no idea that typing /start fixes it. This router is included LAST in
the dispatcher, so every state-filtered flow handler (name/phone entry, contact,
location, CTA buttons, commands) runs first — anything that falls through to
here is a user typing into the void. Answer by re-docking the keyboard with the
welcome text, so typing literally anything brings the buttons back.
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from handlers.start import booking_cta_keyboard
from i18n import t

router = Router()


@router.message(F.text)
async def redock_keyboard(message: Message, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "uz")
    await message.answer(t("welcome_book_cta", lang), reply_markup=booking_cta_keyboard())
