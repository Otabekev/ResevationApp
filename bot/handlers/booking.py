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
import asyncio
import re
from datetime import date, datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import api_client
from i18n import t
from textutils import esc

router = Router()

PHONE_RE = re.compile(r"^\+998\d{9}$")


class BookingFSM(StatesGroup):
    entering_name = State()
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


def _entry_nav_kb(lang: str, with_back: bool = False) -> InlineKeyboardMarkup:
    """Nav buttons for the free-text entry steps (name / phone) so a customer who
    mistyped isn't stuck: Back returns to the name step, Cancel aborts the flow."""
    rows = []
    if with_back:
        rows.append([InlineKeyboardButton(text=t("back", lang), callback_data="entry_back_name")])
    rows.append([InlineKeyboardButton(text=t("cancel", lang), callback_data="book_abort")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def _numbered_picker(items, cb_prefix, id_key, name_fn, lang, intro, back_cb, per_row=4):
    """Pick from a list whose labels can be LONG (business names) without ever
    clipping them. Telegram hard-truncates long button text, so instead we put the
    FULL names in the message body — which wraps and is always readable — as a
    numbered list, and use small numbered buttons (several per row) that map to
    each item. Returns (text, keyboard)."""
    lines = [intro, ""]
    rows, row = [], []
    for i, item in enumerate(items, 1):
        lines.append(f"<b>{i}.</b> {esc(name_fn(item))}")
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"{cb_prefix}{item[id_key]}"))
        if len(row) == per_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data=back_cb)])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


# Asia/Tashkent is a fixed UTC+5 (no DST, ever). Compute "today" in business-local
# time so the picker's Today/Tomorrow labels and the first bookable day match the
# backend (which uses Asia/Tashkent). Plain date.today() uses the server's UTC and
# is a day behind between local midnight and 05:00 — the "Today" button then points
# at yesterday and the backend returns no slots.
_TASHKENT_OFFSET = timedelta(hours=5)


def _today_local() -> date:
    return (datetime.now(timezone.utc) + _TASHKENT_OFFSET).date()


def date_keyboard(lang: str) -> InlineKeyboardMarkup:
    today = _today_local()
    rows = []
    for i in range(7):
        d = today + timedelta(days=i)
        if i == 0:
            label = f"{t('date_today', lang)} · {d.strftime('%d.%m')}"
        elif i == 1:
            label = f"{t('date_tomorrow', lang)} · {d.strftime('%d.%m')}"
        else:
            weekday = t(f"wd_{d.weekday()}", lang)
            label = f"{weekday} · {d.strftime('%d.%m')}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"date_{d.isoformat()}")])
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data="choose_staff_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _lang(state: FSMContext) -> str:
    return (await state.get_data()).get("lang", "uz")


# ── Progressive "booking card" header ────────────────────────────────────────
# Each step keeps the choices made so far visible (one per line) above its
# question, so the flow reads as one growing card instead of a series of bare,
# context-free prompts. `show` lists which choices THIS step should include — we
# render only up to the current step so a stale value left in state by an
# abandoned earlier attempt (state survives back-navigation) can never leak in.
def _booking_header(data: dict, lang: str, show: tuple = ()) -> str:
    lines = []
    if "business" in show and data.get("business_name"):
        lines.append(f"🏪 {esc(data['business_name'])}")
    svc = data.get("service_name")
    if "service" in show and svc and svc != "—":
        lines.append(f"💈 {esc(svc)}")
    if "staff" in show and data.get("staff_name"):
        lines.append(f"👤 {esc(data['staff_name'])}")
    if "date" in show and data.get("booking_date"):
        try:
            bd = date.fromisoformat(data["booking_date"]).strftime("%d.%m")
        except (ValueError, TypeError):
            bd = str(data["booking_date"])
        line = f"📅 {bd}"
        if "time" in show and data.get("start_time"):
            line += f" · 🕐 {data['start_time']}"
        lines.append(line)
    # Neutral 📋 (not a barber-specific icon) — the platform serves every business
    # type, and it matches the final booking-summary screen's header.
    title = f"📋 <b>{t('booking_title', lang)}</b>"
    if lines:
        return title + "\n" + "\n".join(lines) + "\n──────────"
    return title


def _step(data: dict, lang: str, show: tuple, question_key: str) -> str:
    """Progressive header + the step's question. Rendered as HTML (bold title +
    HTML-escaped business/service/staff names), so every caller sends it with
    parse_mode='HTML'."""
    return f"{_booking_header(data, lang, show)}\n\n{t(question_key, lang)}"


# ── Service-button label (protect the price) ─────────────────────────────────
# Telegram renders an inline button on ONE line and ellipsizes from the RIGHT to
# the button's pixel width (~20-34 visible chars on a mid-range Android). The
# PRICE is the element customers need, so we place it on the LEFT — the edge
# Telegram never clips — and truncate ONLY the name. Duration is intentionally
# left off the button (it reappears on the slot picker, the confirmation screen,
# and the multi-select running total), which frees room for the name.
_SVC_NAME_BUDGET = 26   # max name chars before we truncate (generous; name is 2nd)
_ELLIPSIS = "…"         # single code point (not "...") to spend the least width


def _clip_name(name: str, budget: int = _SVC_NAME_BUDGET) -> str:
    """Trim a service name to `budget` chars with a single-glyph ellipsis.
    Strips the trailing space before the ellipsis so we never get 'Name …'."""
    name = (name or "").strip()
    if len(name) <= budget:
        return name
    return name[: budget - 1].rstrip() + _ELLIPSIS


def _price_str(price, lang: str) -> str:
    """Localized price, or '' when there is no usable price. Guards None / '' /
    0 / non-numeric junk so one bad row degrades to name-only, never crashes the
    keyboard build. Same int(float(...)):, formatting as the rest of the flow."""
    if price in (None, "", 0, "0"):
        return ""
    try:
        amount = int(float(price))
    except (TypeError, ValueError):
        return ""
    return t("price_uzs", lang, amount=f"{amount:,}")


def _svc_button_label(name: str, price, lang: str, mark: str = "") -> str:
    """One inline-button label where the PRICE can never be the cut element.

    Layout (left → right):  [mark ]PRICE · NAME
      - price is on the protected LEFT edge (Telegram ellipsizes from the right),
      - the ✅/⬜ `mark` (multi-select only) sits ahead of even the price,
      - NAME is the only element ever truncated (single '…').
    With no price we fall back to '[mark ]NAME' (no dangling ' · ').
    Used by BOTH the single-service list and the multi-service checklist.
    """
    prefix = f"{mark} " if mark else ""
    price_seg = _price_str(price, lang)
    if not price_seg:
        return f"{prefix}{_clip_name(name)}"
    return f"{prefix}{price_seg} · {_clip_name(name)}"


def _multiselect_kb(
    ms_list: list[dict], selected: list[int], lang: str, back_cb: str,
    business_id: int, has_location: bool = False,
) -> InlineKeyboardMarkup:
    """Checklist of services (✅/⬜) + a Continue button with a running total.
    Used when a business allows booking several services in one appointment."""
    sel = set(selected)
    rows = []
    for s in ms_list:
        mark = "✅" if s["id"] in sel else "⬜"
        rows.append([InlineKeyboardButton(
            text=_svc_button_label(s["name"], s.get("price"), lang, mark=mark),
            callback_data=f"msvc_{s['id']}",
        )])
    # Continue row shows count + summed duration once something is picked.
    cont = t("svc_continue", lang)
    if sel:
        total = sum(s["dur"] for s in ms_list if s["id"] in sel)
        cont += f" · {len(sel)} · {total} {t('min_suffix', lang)}"
    rows.append([InlineKeyboardButton(text=cont, callback_data="svcdone")])
    if has_location:
        rows.append([InlineKeyboardButton(text=t("view_location", lang), callback_data=f"loc_{business_id}")])
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Pre-launch gate ───────────────────────────────────────────────────────────
# Until launch day the booking flow is closed to the public: business owners and
# staff can test freely (so they get the feel of it during onboarding), everyone
# else sees a friendly "opening soon" notice. The backend is the single source of
# truth (LAUNCH_DATE + an owner/staff lookup) — we don't trust the bot's cached
# role, which can be stale for an owner who just registered. Once the backend
# reports the platform has launched we remember it for the whole process, so the
# gate becomes a true no-op (zero backend calls per tap) from launch day on.
_launched = False


async def _booking_open(telegram_id: int) -> bool:
    """True if this user may enter the booking flow. Owners/staff always pass;
    everyone else passes only once the launch date has arrived. Fails OPEN on any
    backend error so a transient blip never blocks a real owner mid-demo."""
    global _launched
    if _launched:
        return True
    try:
        status = await api_client.get_launch_status(telegram_id)
    except Exception:
        return True  # best-effort gate — never hard-block on a network hiccup
    if status.get("launched"):
        _launched = True  # platform is public now → stop calling for everyone
        return True
    return bool(status.get("open"))


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

    return _step({}, lang, (), "choose_business_category"), paginate_buttons(categories, "cat_", "id", cat_label, lang)


async def start_booking_from_message(message: Message, state: FSMContext) -> None:
    """Begin booking from a plain text message (the always-docked 'Bron qilish'
    button) by sending a fresh message instead of editing an existing one."""
    lang = await _lang(state)
    text, kb = await _categories_view(lang)
    if text is None:
        await message.answer(t("server_error", lang))
        return
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "book_start")
async def book_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()  # clear the Telegram spinner up front so the button never looks frozen
    lang = await _lang(state)
    if not await _booking_open(callback.from_user.id):
        await callback.message.edit_text(t("prelaunch_wait", lang))
        return
    text, kb = await _categories_view(lang)
    if text is None:
        await callback.message.answer(t("server_error", lang))
        return
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ── Category chosen → businesses ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("cat_"))
async def category_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    lang = await _lang(state)
    try:
        category_id = int(callback.data.split("_", 1)[1])
    except ValueError:
        return
    await state.update_data(category_id=category_id)

    try:
        businesses = await api_client.get_businesses_by_category(category_id)
    except Exception:
        await callback.message.answer(t("server_error", lang))
        return

    if not businesses:
        await callback.message.edit_text(
            t("no_businesses_found", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("back", lang), callback_data="book_start")]
            ]),
        )
        return

    # Full names go in the message body (numbered, always readable) with small
    # numbered buttons — long business names never get clipped the way a per-name
    # button would. The header title sits above the "choose a business" prompt.
    intro = _step({}, lang, (), "choose_business")
    text, kb = _numbered_picker(businesses, "biz_", "id", lambda b: b["name"], lang, intro, back_cb="book_start")
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ── Business chosen → services ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("biz_"))
async def business_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    lang = await _lang(state)
    # Backstop gate — covers any path that reaches a concrete business (incl. the
    # deep-link card) even if an entry point above is ever missed. No-op after launch.
    if not await _booking_open(callback.from_user.id):
        await callback.message.edit_text(t("prelaunch_wait", lang))
        return
    try:
        business_id = int(callback.data.split("_", 1)[1])
    except ValueError:
        return

    # These two calls are independent — fetch them concurrently instead of one
    # after the other (halves this step's backend wait).
    try:
        services, biz = await asyncio.gather(
            api_client.get_services(business_id),
            api_client.get_public_business(business_id),
        )
    except Exception:
        await callback.message.answer(t("server_error", lang))
        return

    # Stash each service's display name + price + duration so later steps read
    # them from state instead of re-fetching. Reset staff cache + any multi-select
    # draft carried over from a previously-viewed business.
    has_location = biz.get("latitude") is not None and biz.get("longitude") is not None
    allow_multi = bool(biz.get("allow_multi_service"))
    services_meta = {
        str(s["id"]): {
            "name": s.get(f"name_{lang}") or s.get("name_uz", ""),
            "price": s.get("price"),
            "duration": s.get("duration_minutes", 0),
        }
        for s in services
    }
    await state.update_data(
        business_id=business_id,
        business_name=biz.get("name", "—"),
        services_meta=services_meta,
        allow_multi=allow_multi,
        biz_has_location=has_location,
        selected_services=[],
        service_ids=None,
        ms_list=None,
        staff_cache=None,
        staff_names=None,
    )

    if not services:
        await callback.message.edit_text(
            t("no_businesses_found", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("back", lang), callback_data="book_start")]
            ]),
        )
        return

    data = await state.get_data()
    back_cb = f"cat_{data['category_id']}" if data.get("category_id") else "book_start"

    # Multi-service businesses get a ✅/⬜ checklist (pick several, book one block);
    # everyone else keeps the classic one-tap service list.
    if allow_multi:
        ms_list = [
            {
                "id": s["id"],
                "name": s.get(f"name_{lang}") or s.get("name_uz", ""),
                "dur": s.get("duration_minutes", 0),
                "price": s.get("price"),
            }
            for s in services
        ]
        await state.update_data(ms_list=ms_list)
        await callback.message.edit_text(
            _step(data, lang, ("business",), "choose_services_multi"),
            parse_mode="HTML",
            reply_markup=_multiselect_kb(ms_list, [], lang, back_cb, business_id, has_location),
        )
        return

    def svc_label(s):
        name = s.get(f"name_{lang}") or s.get("name_uz", "")
        return _svc_button_label(name, s.get("price"), lang)

    kb = paginate_buttons(services, "svc_", "id", svc_label, lang, back_cb=back_cb)
    # If this business has a location set, offer a "📍 view location" button (above
    # the Back row) so the customer can check directions before booking.
    if has_location:
        kb.inline_keyboard.insert(
            len(kb.inline_keyboard) - 1,
            [InlineKeyboardButton(text=t("view_location", lang), callback_data=f"loc_{business_id}")],
        )
    await callback.message.edit_text(_step(data, lang, ("business",), "choose_service"), parse_mode="HTML", reply_markup=kb)


# ── Service chosen → staff ───────────────────────────────────────────────────

async def _show_staff_step(callback: CallbackQuery, state: FSMContext, data: dict | None = None) -> None:
    """Renders the staff-selection step from state (used by both the forward
    path and the 'back' button on the date/time steps). Callers that already
    have the FSM data pass it in to save a Redis read. Callers must have already
    answered the callback (cleared the spinner)."""
    if data is None:
        data = await state.get_data()
    lang = data.get("lang", "uz")
    business_id = data.get("business_id")
    if not business_id:
        return

    # Reuse the staff list across forward + back navigation instead of re-fetching
    # it from the backend on every visit (it's cleared when the business changes).
    staff_list = data.get("staff_cache")
    if staff_list is None:
        try:
            staff_list = await api_client.get_staff(business_id)
        except Exception:
            staff_list = []  # render empty this time, but don't cache a failure → retry on next visit
        else:
            await state.update_data(
                staff_cache=staff_list,
                staff_names={str(s["id"]): s["name"] for s in staff_list},
            )

    # For a multi-service selection, only offer staff who can do EVERY chosen
    # service (the backend enforces this too; this just keeps the list honest).
    selected = data.get("selected_services")
    if selected:
        need = set(selected)
        staff_list = [s for s in staff_list if need.issubset(set(s.get("service_ids") or []))]

    rows = [[InlineKeyboardButton(text=t("any_staff", lang), callback_data="staff_any")]]
    for s in staff_list:
        rows.append([InlineKeyboardButton(text=s["name"], callback_data=f"staff_{s['id']}")])
    rows.append([InlineKeyboardButton(text=t("back", lang), callback_data=f"biz_{business_id}")])

    await callback.message.edit_text(
        _step(data, lang, ("business", "service"), "choose_staff"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("svc_"))
async def service_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    lang = await _lang(state)
    try:
        service_id = int(callback.data.split("_", 1)[1])
    except ValueError:
        return

    data = await state.get_data()
    business_id = data.get("business_id")
    if not business_id:
        return

    # Name + price were already fetched in business_chosen and stashed in state —
    # no need to re-pull the whole services list from the backend here.
    meta = (data.get("services_meta") or {}).get(str(service_id), {})
    await state.update_data(
        service_id=service_id,
        service_name=meta.get("name") or "—",
        service_price=meta.get("price"),
    )

    await _show_staff_step(callback, state, data=data)


# ── Multi-service: toggle a service in/out of the selection ──────────────────

@router.callback_query(F.data.startswith("msvc_"))
async def multi_service_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        sid = int(callback.data.split("_", 1)[1])
    except ValueError:
        return
    data = await state.get_data()
    lang = data.get("lang", "uz")
    ms_list = data.get("ms_list") or []
    selected = list(data.get("selected_services") or [])
    if sid in selected:
        selected.remove(sid)
    elif any(s["id"] == sid for s in ms_list):
        selected.append(sid)
    await state.update_data(selected_services=selected)

    back_cb = f"cat_{data['category_id']}" if data.get("category_id") else "book_start"
    kb = _multiselect_kb(
        ms_list, selected, lang, back_cb, data.get("business_id"), data.get("biz_has_location", False)
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass  # "message is not modified" / transient — ignore


@router.callback_query(F.data == "svcdone")
async def multi_service_done(callback: CallbackQuery, state: FSMContext) -> None:
    """Finish the multi-select → set the combined booking draft and go to staff."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    selected = list(data.get("selected_services") or [])
    if not selected:
        await callback.answer(t("pick_at_least_one", lang), show_alert=True)
        return
    await callback.answer()

    by_id = {s["id"]: s for s in (data.get("ms_list") or [])}
    names = [by_id[sid]["name"] for sid in selected if sid in by_id]
    prices = [float(by_id[sid]["price"]) for sid in selected if sid in by_id and by_id[sid].get("price")]
    await state.update_data(
        service_id=selected[0],          # primary service (back-compat)
        service_ids=selected,            # full back-to-back set
        service_name=", ".join(names) if names else "—",
        service_price=sum(prices) if prices else None,
    )
    await _show_staff_step(callback, state)


@router.callback_query(F.data == "choose_staff_back")
async def choose_staff_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Back from the date/time steps to staff selection."""
    await callback.answer()
    await _show_staff_step(callback, state)


# ── Staff chosen → date ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("staff_"))
async def staff_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
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
            return
        staff_name = (data.get("staff_names") or {}).get(raw, f"#{raw}")

    await state.update_data(staff_id=staff_id, staff_name=staff_name)
    data["staff_name"] = staff_name  # data was read before this write — reflect it in the header
    await callback.message.edit_text(
        _step(data, lang, ("business", "service", "staff"), "choose_date"),
        parse_mode="HTML",
        reply_markup=date_keyboard(lang),
    )


# ── Date chosen → time slots ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("date_"))
async def date_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    date_str = callback.data.split("_", 1)[1]
    await state.update_data(booking_date=date_str)

    data = await state.get_data()
    lang = data.get("lang", "uz")
    business_id = data.get("business_id")
    service_id = data.get("service_id")
    service_ids = data.get("service_ids")
    staff_id = data.get("staff_id")
    if not business_id or not service_id:
        return

    try:
        slots = await api_client.get_available_slots(
            business_id, service_id, date_str, staff_id, service_ids=service_ids
        )
    except Exception:
        await callback.message.answer(t("server_error", lang))
        return

    if not slots:
        await callback.message.edit_text(
            t("no_slots", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("back", lang), callback_data="choose_staff_back")]
            ]),
        )
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
        _step(data, lang, ("business", "service", "staff", "date"), "choose_time"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


# ── Time chosen → ask for phone ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("time_"))
async def time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    start_time = callback.data.split("_", 1)[1]
    await state.update_data(start_time=start_time)

    data = await state.get_data()
    lang = data.get("lang", "uz")
    await callback.message.edit_text(
        _step(data, lang, ("business", "service", "staff", "date", "time"), "enter_name"),
        parse_mode="HTML",
        reply_markup=_entry_nav_kb(lang),
    )
    await state.set_state(BookingFSM.entering_name)


# ── Name entered → ask for phone ─────────────────────────────────────────────

@router.message(BookingFSM.entering_name)
async def name_entered(message: Message, state: FSMContext) -> None:
    """Take the name the customer types (not their Telegram display name, which
    is often a nickname) so the business sees a real name."""
    data = await state.get_data()
    lang = data.get("lang", "uz")
    name = (message.text or "").strip()
    if not (2 <= len(name) <= 100):
        await message.answer(t("invalid_name", lang), reply_markup=_entry_nav_kb(lang))
        return
    await state.update_data(customer_name=name)
    await message.answer(
        _step(data, lang, ("business", "service", "staff", "date", "time"), "enter_phone"),
        parse_mode="HTML",
        reply_markup=_entry_nav_kb(lang, with_back=True),
    )
    await state.set_state(BookingFSM.entering_phone)


@router.callback_query(F.data == "entry_back_name")
async def entry_back_name(callback: CallbackQuery, state: FSMContext) -> None:
    """Customer tapped Back on the phone step → re-ask the name."""
    await callback.answer()
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await callback.message.edit_text(
        _step(data, lang, ("business", "service", "staff", "date", "time"), "enter_name"),
        parse_mode="HTML",
        reply_markup=_entry_nav_kb(lang),
    )
    await state.set_state(BookingFSM.entering_name)


@router.callback_query(F.data == "book_abort")
async def book_abort(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel the in-progress booking from a name/phone step and return to the
    main menu (nothing was created yet — just clears the draft)."""
    await callback.answer()
    lang = await _lang(state)
    await state.set_state(None)
    await state.update_data(
        booking_date=None, start_time=None, service_id=None, staff_id=None,
        service_name=None, staff_name=None, service_price=None,
        service_ids=None, selected_services=[], customer_name=None,
    )
    from handlers.start import main_menu_keyboard
    await callback.message.edit_text(
        t("start", lang), parse_mode="HTML", reply_markup=main_menu_keyboard(lang),
    )


# ── Phone entered → show summary ─────────────────────────────────────────────

@router.message(BookingFSM.entering_phone)
async def phone_entered(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "uz")

    phone = normalize_phone(message.text or "")
    if phone is None:
        await message.answer(t("invalid_phone", lang), reply_markup=_entry_nav_kb(lang, with_back=True))
        return

    # Name was collected in the previous step; only fall back to the Telegram
    # display name if it's somehow missing.
    customer_name = data.get("customer_name") or message.from_user.full_name
    await state.update_data(customer_phone=phone, customer_name=customer_name)

    price = data.get("service_price")
    price_str = (
        t("price_uzs", lang, amount=f"{int(float(price)):,}") if price else t("price_free", lang)
    )

    # Show the date the same friendly way the picker did (DD.MM.YYYY), not the
    # raw ISO string the API uses internally.
    bd = data.get("booking_date")
    try:
        date_disp = date.fromisoformat(bd).strftime("%d.%m.%Y") if bd else "—"
    except ValueError:
        date_disp = bd or "—"

    # Escape user-controlled values (business/service/staff/customer names) — the
    # message is HTML-parsed, so a raw & or < would break the send.
    summary = t(
        "booking_summary", lang,
        business=esc(data.get("business_name", "—")),
        service=esc(data.get("service_name", "—")),
        staff=esc(data.get("staff_name", t("staff_any", lang))),
        date=date_disp,
        time=data.get("start_time", "—"),
        price=price_str,
        name=esc(customer_name),
        phone=phone,
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
    await callback.answer()
    data = await state.get_data()
    lang = data.get("lang", "uz")

    # Guard against a double-tap on a slow backend (Neon cold-start can take
    # seconds): leave the confirming state NOW so a second tap no longer matches
    # this handler, and strip the keyboard so there's nothing left to tap. Without
    # this the second tap fired a duplicate create — the server dedup then bounced
    # it back as a confusing "slot taken (by yourself)".
    await state.set_state(None)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    try:
        await api_client.create_booking({
            "business_id": data["business_id"],
            "service_id": data["service_id"],
            "service_ids": data.get("service_ids"),
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
        booking_ok = True
    except ValueError:
        result_text = t("slot_taken", lang)
        booking_ok = False
    except Exception:
        result_text = t("booking_failed", lang)
        booking_ok = False

    # Keep lang/auth in state but clear the booking draft (FSM step already exited
    # above to block a double-tap).
    await state.update_data(
        booking_date=None, start_time=None, service_id=None, staff_id=None,
        service_name=None, staff_name=None, service_price=None,
        service_ids=None, selected_services=[],
    )

    # On failure (slot just taken / error) offer a one-tap way to start over,
    # not just a dead-end main-menu button.
    rows = []
    if not booking_ok:
        rows.append([InlineKeyboardButton(text=t("book_again", lang), callback_data="book_start")])
    rows.append([InlineKeyboardButton(text=t("main_menu", lang), callback_data="main_menu")])
    await callback.message.edit_text(
        result_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
