import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

import api_client
from i18n import t
from textutils import esc

logger = logging.getLogger(__name__)
router = Router()

# Hold strong refs to in-flight fire-and-forget tasks. asyncio only keeps a weak
# reference to a bare create_task(), so without this a background task can be
# garbage-collected mid-flight and silently cancelled.
_bg_tasks: set = set()


def _fire_and_forget(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _persist_language(token: str, language: str) -> None:
    """Best-effort, off the critical path: tell the backend the user's language
    so notifications match. Cosmetic — the FSM language is already set and every
    /start re-syncs it via /auth/bot. A stale token (entering via the docked
    button long after /start) makes this 401; firing it in the background means
    that never costs the user a wasted round-trip before their screen loads."""
    try:
        await api_client.update_language(token, language)
    except Exception:
        pass


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


# Always-docked menu. Constant Uzbek text so it reads the same before a language
# is chosen, and `is_persistent` keeps it pinned above the input field across the
# whole chat — so older users can book, see their reservations, or read the guide
# anytime with one tap, never needing to type /start. Each button asks for the
# language first (just like /start), then routes on — see on_*_cta + set_language.
BOOK_CTA_TEXT = "📅 Bron qilish"
BOOKINGS_CTA_TEXT = "📋 Mening bronlarim"
HELP_CTA_TEXT = "ℹ️ Yo'riqnoma"


def booking_cta_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BOOK_CTA_TEXT)],
            [KeyboardButton(text=BOOKINGS_CTA_TEXT)],
            [KeyboardButton(text=HELP_CTA_TEXT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=BOOK_CTA_TEXT,
    )


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
                    business_has_location=biz.get("latitude") is not None and biz.get("longitude") is not None,
                    business_photo_url=api_client.absolute_media_url(biz.get("photo_url")),
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
    if start_param.startswith("setloc_"):
        # setloc_{nonce} — owner is setting their business location from the
        # dashboard. Show Telegram's native location-share button; the result
        # is posted back to the backend keyed by the browser's nonce.
        await _handle_setloc_prompt(message, state, start_param[7:])
        return

    # Dock the always-on "Bron qilish" launch button (constant Uzbek — language
    # is chosen next) so older users never have to type /start to begin again.
    await message.answer(t("welcome_book_cta", lang), reply_markup=booking_cta_keyboard())

    # Every /start asks for language first — older users often share a device
    # and expect to pick their language each time. set_language then routes on.
    await message.answer(t("choose_language", lang), reply_markup=language_keyboard())


async def _handle_join(message: Message, state: FSMContext, token: str) -> None:
    """A staff invite link was tapped. Don't link the account yet — first have the
    user share their Telegram phone (a verified number) so the backend can check it
    matches the phone the owner put on the staff record. That stops a forwarded
    link from being redeemed by the wrong person."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    access_token = data.get("access_token")

    if not access_token:
        await message.answer(t("join_invalid", lang))
        return

    await state.update_data(join_token=token)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("share_phone_button", lang), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(t("join_share_phone", lang), reply_markup=kb)


@router.message(F.contact)
async def on_contact_shared(message: Message, state: FSMContext) -> None:
    """The user shared their phone to complete a staff invite. Stray contacts (no
    pending join) are ignored so this never interferes with other flows."""
    data = await state.get_data()
    token = data.get("join_token")
    if not token:
        return
    lang = data.get("lang", "uz")
    access_token = data.get("access_token")
    contact = message.contact

    # Only accept the sender's OWN verified number (the request_contact button),
    # never a forwarded contact card for someone else.
    if contact.user_id != message.from_user.id:
        await message.answer(t("join_share_own_phone", lang))
        return

    await state.update_data(join_token=None)
    try:
        result = await api_client.join_via_invite(token, access_token, phone=contact.phone_number)
        biz = await api_client.get_public_business(result["business_id"])
        await message.answer(
            t("join_success", lang, business=esc(biz.get("name", ""))),
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(t("main_menu", lang), reply_markup=main_menu_keyboard(lang))
    except ValueError:
        # Phone didn't match the staff record — the link is for a different number.
        await message.answer(t("join_phone_mismatch", lang), reply_markup=ReplyKeyboardRemove())
    except Exception:
        await message.answer(t("join_invalid", lang), reply_markup=ReplyKeyboardRemove())


async def _handle_setloc_prompt(message: Message, state: FSMContext, nonce: str) -> None:
    """Stash the browser's nonce and show Telegram's native location-share
    button. Tapping it (or 📎 → Location) sends a location message we forward
    to the backend in on_location_shared."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    nonce = (nonce or "").strip()
    if not nonce or len(nonce) > 64 or not all(c.isalnum() or c in "-_" for c in nonce):
        await message.answer(t("setloc_invalid", lang))
        return
    await state.update_data(setloc_nonce=nonce)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("setloc_button", lang), request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(t("setloc_prompt", lang), reply_markup=kb)


@router.message(F.location)
async def on_location_shared(message: Message, state: FSMContext) -> None:
    """Owner shared a location after a setloc_ deep-link → forward it to the
    backend keyed by the browser's nonce. Stray locations (no pending nonce)
    are ignored so this never interferes with other flows."""
    data = await state.get_data()
    nonce = data.get("setloc_nonce")
    if not nonce:
        return
    lang = data.get("lang", "uz")
    loc = message.location
    try:
        await api_client.complete_location_share(nonce, loc.latitude, loc.longitude)
        await state.update_data(setloc_nonce=None)
        await message.answer(t("setloc_success", lang), reply_markup=ReplyKeyboardRemove())
    except Exception:
        await message.answer(t("setloc_failed", lang), reply_markup=ReplyKeyboardRemove())


@router.message(F.text == BOOK_CTA_TEXT)
async def on_booking_cta(message: Message, state: FSMContext) -> None:
    """The always-docked 'Bron qilish' button → ask the language first (every
    time, just like /start), then route into the booking flow once it's picked."""
    lang = (await state.get_data()).get("lang", "uz")
    await state.update_data(pending_action="book_flow")
    await message.answer(t("choose_language", lang), reply_markup=language_keyboard())


@router.message(F.text == BOOKINGS_CTA_TEXT)
async def on_bookings_cta(message: Message, state: FSMContext) -> None:
    """Docked 'Mening bronlarim' button → ask language, then show the user's
    bookings (set_language refreshes auth first so the list never comes back
    empty on a stale token)."""
    lang = (await state.get_data()).get("lang", "uz")
    await state.update_data(pending_action="my_bookings_flow")
    await message.answer(t("choose_language", lang), reply_markup=language_keyboard())


@router.message(F.text == HELP_CTA_TEXT)
async def on_help_cta(message: Message, state: FSMContext) -> None:
    """Docked 'Yo'riqnoma' button → ask language, then show the how-to-book guide."""
    lang = (await state.get_data()).get("lang", "uz")
    await state.update_data(pending_action="help_flow")
    await message.answer(t("choose_language", lang), reply_markup=language_keyboard())


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
    # Title + a Back button so it reads as a real Settings screen, not a reset.
    kb = language_keyboard()
    kb.inline_keyboard.append([InlineKeyboardButton(text=t("back", lang), callback_data="main_menu")])
    await callback.message.edit_text(
        t("settings_title", lang),
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setlang_"))
async def set_language(callback: CallbackQuery, state: FSMContext) -> None:
    new_lang = callback.data.split("_", 1)[1]
    if new_lang not in ("uz", "ru", "en"):
        new_lang = "uz"
    await state.update_data(lang=new_lang)

    # Persist to the backend so reminders/notifications switch language too —
    # in the background, so the user's next screen never waits on this call.
    data = await state.get_data()
    token = data.get("access_token")
    if token:
        _fire_and_forget(_persist_language(token, new_lang))

    # Route on after the language pick: launch button → category list; booking
    # deep-link → that business's card; otherwise → the main menu.
    if data.get("pending_action") == "book_flow":
        await state.update_data(pending_action=None)
        from handlers import booking
        if not await booking._booking_open(callback.from_user.id):
            await callback.message.edit_text(t("prelaunch_wait", new_lang))
            await callback.answer()
            return
        text, kb = await booking._categories_view(new_lang)
        # On a backend blip _categories_view returns (None, None); without a
        # fallback keyboard the error screen would have NO buttons, stranding the
        # user. Give them the main menu so there's always a way forward.
        await callback.message.edit_text(
            text if text is not None else t("server_error", new_lang),
            reply_markup=kb if kb is not None else main_menu_keyboard(new_lang),
        )
    elif data.get("pending_action") == "book" and data.get("business_id"):
        await state.update_data(pending_action=None)
        from handlers import booking
        if not await booking._booking_open(callback.from_user.id):
            await callback.message.edit_text(t("prelaunch_wait", new_lang))
            await callback.answer()
            return
        biz_id = data["business_id"]
        rows = [[InlineKeyboardButton(text=t("book_appointment", new_lang), callback_data=f"biz_{biz_id}")]]
        if data.get("business_has_location"):
            rows.append([InlineKeyboardButton(text=t("view_location", new_lang), callback_data=f"loc_{biz_id}")])
        rows.append([InlineKeyboardButton(text=t("back", new_lang), callback_data="main_menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        card_text = f"🏪 <b>{esc(data.get('business_name', ''))}</b>\n📍 {esc(data.get('business_address', ''))}"
        photo_url = data.get("business_photo_url")
        # With a photo, show the storefront as a real photo card (image + caption +
        # the same buttons). A text message can't be edited into a photo, so send a
        # fresh photo message and drop the old text. If Telegram can't fetch the
        # image, fall back to the plain text card so the flow never breaks.
        sent_photo = False
        if photo_url:
            try:
                await callback.message.answer_photo(
                    photo=photo_url, caption=card_text, parse_mode="HTML", reply_markup=kb,
                )
                sent_photo = True
                try:
                    await callback.message.delete()
                except Exception:
                    pass
            except Exception:
                sent_photo = False
        if not sent_photo:
            await callback.message.edit_text(card_text, parse_mode="HTML", reply_markup=kb)
    elif data.get("pending_action") == "my_bookings_flow":
        await state.update_data(pending_action=None)
        # Refresh auth so the bookings fetch has a valid token — the one from
        # /start may have expired during think-time, which would otherwise show
        # an empty list.
        u = callback.from_user
        try:
            auth_data = await api_client.auth_user(u.id, u.full_name, u.username, new_lang)
            await state.update_data(
                access_token=auth_data["access_token"],
                user_id=auth_data["user_id"],
                role=auth_data["role"],
            )
        except Exception:
            pass
        from handlers.my_bookings import show_my_bookings
        await show_my_bookings(callback, state)
        return
    elif data.get("pending_action") == "help_flow":
        await state.update_data(pending_action=None)
        await callback.message.edit_text(
            t("instructions", new_lang),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(new_lang),
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


@router.callback_query(F.data.startswith("loc_"))
async def send_business_location(callback: CallbackQuery, state: FSMContext) -> None:
    """Send the business location as a native Telegram pin — tap it for
    directions. Reachable from the business card and from a saved reservation,
    so older customers always have a one-tap way to find the place."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    try:
        biz_id = int(callback.data.split("_", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    try:
        biz = await api_client.get_public_business(biz_id)
        lat, lng = biz.get("latitude"), biz.get("longitude")
        if lat is None or lng is None:
            await callback.answer(t("no_location", lang), show_alert=True)
            return
        await callback.message.answer_location(latitude=lat, longitude=lng)
        await callback.message.answer(
            f"🏪 <b>{esc(biz.get('name', ''))}</b>\n📍 {esc(biz.get('address', ''))}",
            parse_mode="HTML",
        )
    except Exception:
        await callback.answer(t("server_error", lang), show_alert=True)
        return
    await callback.answer()
