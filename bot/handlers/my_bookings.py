from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import api_client
from i18n import t
from textutils import esc

router = Router()


def format_booking(b: dict, lang: str) -> str:
    status_icons = {
        "pending": "⏳",
        "confirmed": "✅",
        "completed": "✔️",
        "cancelled_by_customer": "❌",
        "cancelled_by_business": "❌",
        "no_show": "🚫",
        "rescheduled": "🔄",
    }
    status = b.get("status", "")
    icon = status_icons.get(status, "📋")
    biz = b.get("business_name") or "—"
    svc = b.get(f"service_name_{lang}") or b.get("service_name_uz") or ""
    bd = b.get("booking_date")
    try:
        date_disp = date.fromisoformat(bd).strftime("%d.%m.%Y") if bd else "—"
    except (ValueError, TypeError):
        date_disp = bd or "—"
    time_disp = (b.get("start_time") or "")[:5]
    status_word = t(f"bstatus_{status}", lang) if status else "—"

    lines = [f"{icon} <b>{esc(biz)}</b>"]
    if svc:
        lines.append(f"💈 {esc(svc)}")
    lines.append(f"📅 {date_disp}  🕐 {time_disp}")
    lines.append(f"{t('status_label', lang)}: {status_word}")
    return "\n".join(lines)


@router.callback_query(F.data == "my_bookings")
async def my_bookings(callback: CallbackQuery, state: FSMContext) -> None:
    await show_my_bookings(callback, state)


async def show_my_bookings(callback: CallbackQuery, state: FSMContext) -> None:
    """Render the user's upcoming bookings on the current message. Shared by the
    inline 'my_bookings' button and the docked 'Mening bronlarim' menu button."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    access_token = data.get("access_token", "")

    try:
        bookings = await api_client.get_customer_bookings(
            telegram_id=callback.from_user.id,
            token=access_token,
            upcoming_only=True,
        )
    except Exception:
        bookings = []

    if not bookings:
        await callback.message.edit_text(
            t("no_bookings", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("back", lang), callback_data="main_menu")]
            ]),
        )
        await callback.answer()
        return

    text = t("upcoming_bookings", lang) + "\n\n"
    rows = []
    for b in bookings[:10]:
        text += format_booking(b, lang) + "\n\n"
        btn_row = []
        if b.get("business_id"):
            btn_row.append(InlineKeyboardButton(
                text=t("view_location", lang),
                callback_data=f"loc_{b['business_id']}",
            ))
        if b.get("status") in ("pending", "confirmed"):
            btn_row.append(InlineKeyboardButton(
                text=t("cancel_n", lang),
                callback_data=f"cancel_ask_{b['id']}",
            ))
        if btn_row:
            rows.append(btn_row)

    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data="main_menu")])

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_ask_"))
async def cancel_ask(callback: CallbackQuery, state: FSMContext) -> None:
    """Confirm before cancelling — a single accidental tap must not irreversibly
    cancel a real reservation."""
    booking_id = int(callback.data.split("_")[-1])
    lang = (await state.get_data()).get("lang", "uz")
    await callback.message.edit_text(
        t("cancel_confirm_q", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("cancel_yes", lang), callback_data=f"cancel_booking_{booking_id}")],
            [InlineKeyboardButton(text=t("cancel_no", lang), callback_data="my_bookings")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: CallbackQuery, state: FSMContext) -> None:
    booking_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    lang = data.get("lang", "uz")
    access_token = data.get("access_token", "")

    # Refresh the token first — this can be reached from a 24h/1h reminder long
    # after /start, when the token in state has expired. Without this the cancel
    # would 401 and the customer couldn't free the slot.
    u = callback.from_user
    try:
        auth = await api_client.auth_user(u.id, u.full_name, u.username, lang)
        access_token = auth["access_token"]
        await state.update_data(access_token=access_token, user_id=auth["user_id"], role=auth["role"])
    except Exception:
        pass  # fall back to whatever token we had

    try:
        await api_client.cancel_booking(booking_id, access_token)
        await callback.message.edit_text(
            t("booking_cancelled", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("back", lang), callback_data="main_menu")]
            ]),
        )
    except Exception:
        await callback.answer(t("cancel_failed", lang), show_alert=True)

    await callback.answer()


@router.callback_query(F.data.startswith("review_rate_"))
async def handle_review_rating(callback: CallbackQuery, state: FSMContext) -> None:
    # callback_data: review_rate_{booking_id}_{rating}
    parts = callback.data.split("_")
    booking_id = int(parts[2])
    rating = int(parts[3])
    data = await state.get_data()
    lang = data.get("lang", "uz")

    try:
        await api_client.submit_review(
            telegram_id=callback.from_user.id,
            booking_id=booking_id,
            rating=rating,
        )
        await callback.message.edit_text(
            t("review_thanks", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("back", lang), callback_data="main_menu")]
            ]),
        )
    except Exception:
        await callback.answer(t("review_failed", lang), show_alert=True)

    await callback.answer()
