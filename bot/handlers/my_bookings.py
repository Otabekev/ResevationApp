from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import api_client
from i18n import t

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
    icon = status_icons.get(b.get("status", ""), "📋")
    return (
        f"{icon} <b>#{b['id']}</b>\n"
        f"📅 {b['booking_date']} {b['start_time'][:5]}\n"
        f"Status: {b.get('status', '—')}"
    )


@router.callback_query(F.data == "my_bookings")
async def my_bookings(callback: CallbackQuery, state: FSMContext) -> None:
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
                text=t("cancel_n", lang, id=b["id"]),
                callback_data=f"cancel_booking_{b['id']}",
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


@router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: CallbackQuery, state: FSMContext) -> None:
    booking_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    lang = data.get("lang", "uz")
    access_token = data.get("access_token", "")

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
