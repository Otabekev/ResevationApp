"""
Booking flow FSM:
  book_start → choose category → choose business → choose service
            → choose staff → choose date → choose time
            → enter phone → confirm → done
"""
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import api_client
from i18n import t

router = Router()


class BookingFSM(StatesGroup):
    choosing_category = State()
    choosing_business = State()
    choosing_service = State()
    choosing_staff = State()
    choosing_date = State()
    choosing_time = State()
    entering_phone = State()
    confirming = State()


def back_button(lang: str) -> list[list[InlineKeyboardButton]]:
    return [[InlineKeyboardButton(text=t("back", lang), callback_data="main_menu")]]


def paginate_buttons(
    items: list[dict],
    cb_prefix: str,
    id_key: str,
    label_fn,
    lang: str,
    back_cb: str = "main_menu",
) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        rows.append([InlineKeyboardButton(
            text=label_fn(item),
            callback_data=f"{cb_prefix}{item[id_key]}",
        )])
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def date_keyboard(lang: str) -> InlineKeyboardMarkup:
    today = date.today()
    rows = []
    for i in range(7):
        d = today + timedelta(days=i)
        label = t("date_today", lang) if i == 0 else (t("date_tomorrow", lang) if i == 1 else d.strftime("%d.%m.%Y (%A)"))
        rows.append([InlineKeyboardButton(text=label, callback_data=f"date_{d.isoformat()}")])
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data="choose_staff_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Start booking ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "book_start")
async def book_start(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "uz")

    try:
        categories = await api_client.get_categories()
    except Exception:
        await callback.answer("Server error", show_alert=True)
        return

    if not categories:
        await callback.message.edit_text("No categories available.")
        return

    def cat_label(c):
        icon = c.get("icon", "") or ""
        name = c.get(f"name_{lang}") or c.get("name_uz", "")
        return f"{icon} {name}".strip()

    kb = paginate_buttons(categories, "cat_", "id", cat_label, lang)
    await callback.message.edit_text(t("choose_business_category", lang), reply_markup=kb)
    await state.set_state(BookingFSM.choosing_category)
    await callback.answer()


# ── Category chosen ───────────────────────────────────────────────────────────

@router.callback_query(BookingFSM.choosing_category, F.data.startswith("cat_"))
async def category_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    category_id = int(callback.data.split("_", 1)[1])
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await state.update_data(category_id=category_id)

    try:
        businesses = await api_client.get_businesses_by_category(category_id)
    except Exception:
        await callback.answer("Server error", show_alert=True)
        return

    if not businesses:
        await callback.message.edit_text(
            "No businesses found in this category.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=back_button(lang)),
        )
        return

    kb = paginate_buttons(businesses, "biz_", "id", lambda b: b["name"], lang, back_cb="book_start")
    await callback.message.edit_text(t("choose_business", lang), reply_markup=kb)
    await state.set_state(BookingFSM.choosing_business)
    await callback.answer()


# ── Business chosen ───────────────────────────────────────────────────────────

@router.callback_query(BookingFSM.choosing_business, F.data.startswith("biz_"))
async def business_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    business_id = int(callback.data.split("_", 1)[1])
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await state.update_data(business_id=business_id)

    try:
        services = await api_client.get_services(business_id)
    except Exception:
        await callback.answer("Server error", show_alert=True)
        return

    def svc_label(s):
        name = s.get(f"name_{lang}") or s.get("name_uz", "")
        duration = s.get("duration_minutes", 0)
        price = s.get("price")
        price_str = f" • {int(price):,} so'm" if price else ""
        return f"{name} ({duration} min){price_str}"

    kb = paginate_buttons(services, "svc_", "id", svc_label, lang, back_cb="book_start")
    await callback.message.edit_text(t("choose_service", lang), reply_markup=kb)
    await state.set_state(BookingFSM.choosing_service)
    await callback.answer()


# ── Service chosen ────────────────────────────────────────────────────────────

@router.callback_query(BookingFSM.choosing_service, F.data.startswith("svc_"))
async def service_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    service_id = int(callback.data.split("_", 1)[1])
    data = await state.get_data()
    lang = data.get("lang", "uz")
    business_id = data.get("business_id")
    await state.update_data(service_id=service_id)

    try:
        staff_list = await api_client.get_staff(business_id)
    except Exception:
        staff_list = []

    rows = [[InlineKeyboardButton(text=t("any_staff", lang), callback_data="staff_any")]]
    for s in staff_list:
        rows.append([InlineKeyboardButton(text=s["name"], callback_data=f"staff_{s['id']}")])
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data=f"biz_{business_id}")])

    await callback.message.edit_text(
        t("choose_staff", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await state.set_state(BookingFSM.choosing_staff)
    await callback.answer()


# ── Staff chosen ──────────────────────────────────────────────────────────────

@router.callback_query(BookingFSM.choosing_staff, F.data.startswith("staff_"))
async def staff_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    raw = callback.data.split("_", 1)[1]
    staff_id = None if raw == "any" else int(raw)
    await state.update_data(staff_id=staff_id)

    data = await state.get_data()
    lang = data.get("lang", "uz")

    await callback.message.edit_text(t("choose_date", lang), reply_markup=date_keyboard(lang))
    await state.set_state(BookingFSM.choosing_date)
    await callback.answer()


# ── Date chosen ───────────────────────────────────────────────────────────────

@router.callback_query(BookingFSM.choosing_date, F.data.startswith("date_"))
async def date_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    date_str = callback.data.split("_", 1)[1]
    await state.update_data(booking_date=date_str)

    data = await state.get_data()
    lang = data.get("lang", "uz")
    business_id = data.get("business_id")
    service_id = data.get("service_id")
    staff_id = data.get("staff_id")

    try:
        slots = await api_client.get_available_slots(business_id, service_id, date_str, staff_id)
    except Exception:
        slots = []

    if not slots:
        await callback.message.edit_text(
            t("no_slots", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("back", lang), callback_data="choose_staff_back")]
            ]),
        )
        return

    rows = []
    for slot in slots:
        rows.append([InlineKeyboardButton(
            text=slot["start_time"],
            callback_data=f"time_{slot['start_time']}",
        )])
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data="choose_staff_back")])

    await callback.message.edit_text(
        t("choose_time", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await state.set_state(BookingFSM.choosing_time)
    await callback.answer()


# ── Time chosen → ask for phone ───────────────────────────────────────────────

@router.callback_query(BookingFSM.choosing_time, F.data.startswith("time_"))
async def time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    start_time = callback.data.split("_", 1)[1]
    await state.update_data(start_time=start_time)

    data = await state.get_data()
    lang = data.get("lang", "uz")

    await callback.message.edit_text(t("enter_phone", lang))
    await state.set_state(BookingFSM.entering_phone)
    await callback.answer()


# ── Phone entered → show summary ─────────────────────────────────────────────

@router.message(BookingFSM.entering_phone)
async def phone_entered(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    data = await state.get_data()
    lang = data.get("lang", "uz")

    if not (phone.startswith("+") and len(phone) >= 10):
        await message.answer(t("invalid_phone", lang))
        return

    await state.update_data(customer_phone=phone, customer_name=message.from_user.full_name)

    # Load service details for summary
    try:
        services = await api_client.get_services(data["business_id"])
        service = next((s for s in services if s["id"] == data["service_id"]), {})
        biz = await api_client.get_public_business(data["business_id"])
    except Exception:
        service = {}
        biz = {}

    svc_name = service.get(f"name_{lang}") or service.get("name_uz", "—")
    price = service.get("price")
    price_str = t("price_uzs", lang, amount=f"{int(price):,}") if price else t("price_free", lang)
    staff_id = data.get("staff_id")
    staff_name = t("staff_any", lang) if not staff_id else f"#{staff_id}"

    summary = t(
        "booking_summary", lang,
        business=biz.get("name", "—"),
        service=svc_name,
        staff=staff_name,
        date=data.get("booking_date", "—"),
        time=data.get("start_time", "—"),
        price=price_str,
    )

    await message.answer(
        summary,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("confirm", lang), callback_data="booking_confirm")],
            [InlineKeyboardButton(text=t("cancel", lang), callback_data="main_menu")],
        ]),
    )
    await state.set_state(BookingFSM.confirming)


# ── Confirm booking ───────────────────────────────────────────────────────────

@router.callback_query(BookingFSM.confirming, F.data == "booking_confirm")
async def booking_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "uz")

    try:
        await api_client.create_booking({
            "business_id": data["business_id"],
            "service_id": data["service_id"],
            "staff_id": data.get("staff_id"),
            "booking_date": data["booking_date"],
            "start_time": data["start_time"] + ":00",
            "customer_name": data.get("customer_name", callback.from_user.full_name),
            "customer_phone": data.get("customer_phone", ""),
            "notes": None,
            "telegram_id": callback.from_user.id,
        })
        await callback.message.edit_text(t("booking_confirmed", lang))
    except ValueError:
        await callback.message.edit_text(t("booking_failed", lang))
    except Exception:
        await callback.message.edit_text(t("booking_failed", lang))

    await state.clear()
    # Return to main menu after short delay would require scheduler; just show menu button
    await callback.message.answer(
        t("main_menu", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("main_menu", lang), callback_data="main_menu")]
        ]),
    )
    await callback.answer()
