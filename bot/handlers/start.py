import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import api_client
from i18n import t

logger = logging.getLogger(__name__)
router = Router()


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("book_appointment", lang), callback_data="book_start")],
        [InlineKeyboardButton(text=t("my_bookings", lang), callback_data="my_bookings")],
        [InlineKeyboardButton(text=t("settings", lang), callback_data="settings")],
    ])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="setlang_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang_en"),
        ]
    ])


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()

    tg_user = message.from_user
    lang_code = tg_user.language_code or "uz"
    if lang_code not in ("uz", "ru", "en"):
        lang_code = "uz"

    # Authenticate with backend
    try:
        auth_data = await api_client.auth_user(
            telegram_id=tg_user.id,
            name=tg_user.full_name,
            username=tg_user.username,
            language=lang_code,
        )
        lang = auth_data.get("language", lang_code)
        await state.update_data(
            lang=lang,
            access_token=auth_data["access_token"],
            user_id=auth_data["user_id"],
            role=auth_data["role"],
        )
    except Exception:
        lang = lang_code
        await state.update_data(lang=lang)

    # Handle deep links (join invite, direct booking)
    start_param = message.text.split(maxsplit=1)[1] if " " in message.text else ""
    if start_param.startswith("join_"):
        await _handle_join(message, state, start_param[5:])
        return
    if start_param.startswith("book_"):
        # book_{business_id} — direct booking link (Instagram bio, share button).
        # Remember the business, then ask language first; after the user picks,
        # set_language opens this business's booking card.
        raw_id = start_param[5:]
        if raw_id.isdigit():
            try:
                biz = await api_client.get_public_business(int(raw_id))
                await state.update_data(
                    business_id=int(raw_id),
                    business_name=biz.get("name", "—"),
                    business_address=biz.get("address", ""),
                    pending_action="book",
                )
            except Exception:
                pass  # fall through to a plain language pick → main menu
        await message.answer(t("choose_language", lang), reply_markup=language_keyboard())
        return
    if start_param.startswith("login_"):
        # login_{nonce} — web dashboard login. Ask the user to confirm so a
        # drive-by /start can't silently authenticate someone else's browser.
        nonce = start_param[6:]
        await message.answer(
            t("web_login_confirm", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("web_login_yes", lang), callback_data=f"weblogin_{nonce}")]
            ])
        )
        return

    # Every /start asks for language first — older users often share a device
    # and expect to pick their language each time. set_language then routes on.
    await message.answer(t("choose_language", lang), reply_markup=language_keyboard())


async def _handle_join(message: Message, state: FSMContext, token: str) -> None:
    data = await state.get_data()
    lang = data.get("lang", "uz")
    access_token = data.get("access_token")

    if not access_token:
        await message.answer(t("join_invalid", lang))
        return

    try:
        result = await api_client.join_via_invite(token, access_token)
        biz = await api_client.get_public_business(result["business_id"])
        await message.answer(
            t("join_success", lang, business=biz.get("name", "")),
            reply_markup=main_menu_keyboard(lang),
        )
    except Exception:
        await message.answer(t("join_invalid", lang))


@router.callback_query(F.data.startswith("weblogin_"))
async def confirm_web_login(callback: CallbackQuery, state: FSMContext) -> None:
    """User tapped 'Yes, it's me' — tell the backend to release the web token."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    nonce = callback.data[len("weblogin_"):]
    u = callback.from_user
    try:
        await api_client.complete_web_login(nonce, u.id, u.full_name, u.username, lang)
        await callback.message.edit_text(t("web_login_done", lang))
    except Exception as exc:
        logger.exception("web-login failed for tg=%s nonce=%s: %s", u.id, nonce, exc)
        await callback.message.edit_text(t("web_login_failed", lang))
    await callback.answer()


@router.callback_query(F.data == "settings")
async def settings_menu(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await callback.message.edit_text(
        t("choose_language", lang),
        reply_markup=language_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setlang_"))
async def set_language(callback: CallbackQuery, state: FSMContext) -> None:
    new_lang = callback.data.split("_", 1)[1]
    if new_lang not in ("uz", "ru", "en"):
        new_lang = "uz"
    await state.update_data(lang=new_lang)

    # Persist to the backend so reminders/notifications switch language too.
    data = await state.get_data()
    token = data.get("access_token")
    if token:
        try:
            await api_client.update_language(token, new_lang)
        except Exception:
            pass  # cosmetic — the FSM language is already updated

    # If the user arrived via a booking deep-link, continue to that business's
    # card; otherwise drop them on the main menu.
    if data.get("pending_action") == "book" and data.get("business_id"):
        await state.update_data(pending_action=None)
        biz_id = data["business_id"]
        await callback.message.edit_text(
            f"🏪 <b>{data.get('business_name', '')}</b>\n📍 {data.get('business_address', '')}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("book_appointment", new_lang), callback_data=f"biz_{biz_id}")],
                [InlineKeyboardButton(text=t("back", new_lang), callback_data="main_menu")],
            ]),
        )
    else:
        await callback.message.edit_text(
            t("start", new_lang),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(new_lang),
        )
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await callback.message.edit_text(
        t("start", lang),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(lang),
    )
    await callback.answer()
