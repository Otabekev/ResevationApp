"""
Booking flow FSM:
  book_start → choose category → choose business → choose service
            → choose staff → choose date → choose time
            → enter phone → confirm → done

Navigation notes
----------------
Callback prefixes (cat_/biz_/svc_/staff_/date_/time_) are globally unique, so
the step handlers are registered WITHOUT FSM-state filters. That makes every
"back" button work from any step (a stale tap simply re-runs that step) instead
of dying against a state filter. Only free-text input (phone) stays gated
behind its FSM state.
"""
import re
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import api_client
from i18n import t

router = Router()

PHONE_RE = re.compile(r"^\+998\d{9}$")


class BookingFSM(StatesGroup):
    entering_phone = State()
    confirming = State()


def normalize_phone(raw: str) -> str | None:
    """Accepts '+998901234567', '998901234567', '901234567', with spaces/dashes.
    Returns canonical '+998XXXXXXXXX' or None if it can't be an Uzbek number."""
    digits = re.sub(r"[^\d]", "", raw)
    if len(digits) == 9:  # 901234567
        digits = "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        candidate = "+" + digits
        return candidate if PHONE_RE.match(candidate) else None
    return None


def main_menu_button(lang: str) -> list[list[InlineKeyboardButton]]:
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
        if i == 0:
            label = f"{t('date_today', lang)} · {d.strftime('%d.%m')}"
        elif i == 1:
            label = f"{t('date_tomorrow', lang)} · {d.strftime('%d.%m')}"
        else:
            weekday = t(f"wd_{d.weekday()}", lang)
            label = f"{weekday} · {d.strftime('%d.%m.%Y')}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"date_{d.isoformat()}")])
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data="choose_staff_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _lang(state: FSMContext) -> str:
    return (await state.get_data()).get("lang", "uz")


# ── Start booking ─────────────────────────────────────────────────────────────

async def _categories_view(lang: str):
    """Build the category-selection step. Returns (text, keyboard), or
    (None, None) if the backend is unreachable."""
    try:
        categories = await api_client.get_categories()
    except Exception:
        return None, None
    if not categories:
        return t("no_categories", lang), InlineKeyboardMarkup(inline_keyboard=main_menu_button(lang))

    def cat_label(c):
        icon = c.get("icon", "") or ""
        name = c.get(f"name_{lang}") or c.get("name_uz", "")
        return f"{icon} {name}".strip()

    return t("choose_business_category", lang), paginate_buttons(categories, "cat_", "id", cat_label, lang)


async def start_booking_from_message(message: Message, state: FSMContext) -> None:
    """Begin booking from a plain text message (the always-docked 'Bron qilish'
    button) by sending a fresh message instead of editing an existing one."""
    lang = await _lang(state)
    text, kb = await _categories_view(lang)
    if text is None:
        await message.answer(t("server_error", lang))
        return
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "book_start")
async def book_start(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    text, kb = await _categories_view(lang)
    if text is None:
        await callback.answer(t("server_error", lang), show_alert=True)
        return
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Category chosen → businesses ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("cat_"))
async def category_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    try:
        category_id = int(callback.data.split("_", 1)[1])
    except ValueError:
        await callback.answer()
        return
    await state.update_data(category_id=category_id)

    try:
        businesses = await api_client.get_businesses_by_category(category_id)
    except Exception:
        await callback.answer(t("server_error", lang), show_alert=True)
        return

    if not businesses:
        await callback.message.edit_text(
            t("no_businesses_found", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("back", lang), callback_data="book_start")]
            ]),
        )
        await callback.answer()
        return

    kb = paginate_buttons(businesses, "biz_", "id", lambda b: b["name"], lang, back_cb="book_start")
    await callback.message.edit_text(t("choose_business", lang), reply_markup=kb)
    await callback.answer()


# ── Business chosen → services ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("biz_"))
async def business_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    try:
        business_id = int(callback.data.split("_", 1)[1])
    except ValueError:
        await callback.answer()
        return

    try:
        services = await api_client.get_services(business_id)
        biz = await api_client.get_public_business(business_id)
    except Exception:
        await callback.answer(t("server_error", lang), show_alert=True)
        return

    await state.update_data(business_id=business_id, business_name=biz.get("name", "—"))

    if not services:
        await callback.message.edit_text(
            t("no_businesses_found", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("back", lang), callback_data="book_start")]
            ]),
        )
        await callback.answer()
        return

    def svc_label(s):
        name = s.get(f"name_{lang}") or s.get("name_uz", "")
        duration = s.get("duration_minutes", 0)
        price = s.get("price")
        price_str = f" • {t('price_uzs', lang, amount=f'{int(float(price)):,}')}" if price else ""
        return f"{name} ({duration}′){price_str}"

    data = await state.get_data()
    back_cb = f"cat_{data['category_id']}" if data.get("category_id") else "book_start"
    kb = paginate_buttons(services, "svc_", "id", svc_label, lang, back_cb=back_cb)
    await callback.message.edit_text(t("choose_service", lang), reply_markup=kb)
    await callback.answer()


# ── Service chosen → staff ───────────────────────────────────────────────────

async def _show_staff_step(callback: CallbackQuery, state: FSMContext) -> None:
    """Renders the staff-selection step from state (used by both the forward
    path and the 'back' button on the date/time steps)."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    business_id = data.get("business_id")
    if not business_id:
        await callback.answer()
        return

    try:
        staff_list = await api_client.get_staff(business_id)
    except Exception:
        staff_list = []

    # Map staff id → name so the summary can show a real name later.
    staff_names = {str(s["id"]): s["name"] for s in staff_list}
    await state.update_data(staff_names=staff_names)

    rows = [[InlineKeyboardButton(text=t("any_staff", lang), callback_data="staff_any")]]
    for s in staff_list:
        rows.append([InlineKeyboardButton(text=s["name"], callback_data=f"staff_{s['id']}")])
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data=f"biz_{business_id}")])

    await callback.message.edit_text(
        t("choose_staff", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("svc_"))
async def service_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    try:
        service_id = int(callback.data.split("_", 1)[1])
    except ValueError:
        await callback.answer()
        return

    data = await state.get_data()
    business_id = data.get("business_id")
    if not business_id:
        await callback.answer()
        return

    # Remember the chosen service's display name + price for the summary.
    try:
        services = await api_client.get_services(business_id)
    except Exception:
        services = []
    svc = next((s for s in services if s["id"] == service_id), {})
    await state.update_data(
        service_id=service_id,
        service_name=svc.get(f"name_{lang}") or svc.get("name_uz", "—"),
        service_price=svc.get("price"),
    )

    await _show_staff_step(callback, state)


@router.callback_query(F.data == "choose_staff_back")
async def choose_staff_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Back from the date/time steps to staff selection."""
    await _show_staff_step(callback, state)


# ── Staff chosen → date ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("staff_"))
async def staff_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    raw = callback.data.split("_", 1)[1]
    data = await state.get_data()
    lang = data.get("lang", "uz")

    if raw == "any":
        staff_id = None
        staff_name = t("staff_any", lang)
    else:
        try:
            staff_id = int(raw)
        except ValueError:
            await callback.answer()
            return
        staff_name = data.get("staff_names", {}).get(raw, f"#{raw}")

    await state.update_data(staff_id=staff_id, staff_name=staff_name)
    await callback.message.edit_text(t("choose_date", lang), reply_markup=date_keyboard(lang))
    await callback.answer()


# ── Date chosen → time slots ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("date_"))
async def date_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    date_str = callback.data.split("_", 1)[1]
    await state.update_data(booking_date=date_str)

    data = await state.get_data()
    lang = data.get("lang", "uz")
    business_id = data.get("business_id")
    service_id = data.get("service_id")
    staff_id = data.get("staff_id")
    if not business_id or not service_id:
        await callback.answer()
        return

    try:
        slots = await api_client.get_available_slots(business_id, service_id, date_str, staff_id)
    except Exception:
        await callback.answer(t("server_error", lang), show_alert=True)
        return

    if not slots:
        await callback.message.edit_text(
            t("no_slots", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("back", lang), callback_data="choose_staff_back")]
            ]),
        )
        await callback.answer()
        return

    # 3 slot buttons per row — fewer scrolls on busy days.
    rows, row = [], []
    for slot in slots:
        row.append(InlineKeyboardButton(
            text=slot["start_time"],
            callback_data=f"time_{slot['start_time']}",
        ))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data="choose_staff_back")])

    await callback.message.edit_text(
        t("choose_time", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


# ── Time chosen → ask for phone ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("time_"))
async def time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    start_time = callback.data.split("_", 1)[1]
    await state.update_data(start_time=start_time)

    lang = await _lang(state)
    await callback.message.edit_text(t("enter_phone", lang))
    await state.set_state(BookingFSM.entering_phone)
    await callback.answer()


# ── Phone entered → show summary ─────────────────────────────────────────────

@router.message(BookingFSM.entering_phone)
async def phone_entered(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "uz")

    phone = normalize_phone(message.text or "")
    if phone is None:
        await message.answer(t("invalid_phone", lang))
        return

    await state.update_data(customer_phone=phone, customer_name=message.from_user.full_name)

    price = data.get("service_price")
    price_str = (
        t("price_uzs", lang, amount=f"{int(float(price)):,}") if price else t("price_free", lang)
    )

    summary = t(
        "booking_summary", lang,
        business=data.get("business_name", "—"),
        service=data.get("service_name", "—"),
        staff=data.get("staff_name", t("staff_any", lang)),
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
            "language": lang,
        })
        result_text = t("booking_confirmed", lang)
    except ValueError:
        result_text = t("slot_taken", lang)
    except Exception:
        result_text = t("booking_failed", lang)

    # Keep lang/auth in state but clear the FSM step + booking draft.
    await state.set_state(None)
    await state.update_data(
        booking_date=None, start_time=None, service_id=None, staff_id=None,
        service_name=None, staff_name=None, service_price=None,
    )

    await callback.message.edit_text(
        result_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("main_menu", lang), callback_data="main_menu")]
        ]),
    )
    await callback.answer()
