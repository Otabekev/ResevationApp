# Production-readiness pass — 2026-06-11

Full-stack pass: security, correctness, and a complete UI redesign.
Every fix below maps to a verified issue found in the audit.

## Critical functional fixes

| # | Issue | Fix |
|---|-------|-----|
| F1 | **Staff invite links never worked** — URL was built from the bot *token's* numeric prefix (`t.me/123456?start=…`), which is a dead link AND leaks part of the token | New `TELEGRAM_BOT_USERNAME` setting; links are now `t.me/<username>?start=join_…`. Production boot fails fast if unset. (`backend/app/routers/staff.py`, `config.py`) |
| F2 | **Second manual booking always crashed (500)** — every walk-in customer was inserted with `telegram_id=0`, violating the unique constraint | `customers.telegram_id` is now nullable (migration `0003_walkin_customers`); walk-ins are found-or-created by phone so repeat customers keep history. (`routers/bookings.py`, `models/booking.py`) |
| F3 | **Dead "Back" buttons in the bot** — `choose_staff_back` had no handler; service-list "back" died against FSM state filters | Step handlers are state-independent (unique callback prefixes), `choose_staff_back` implemented; every back path works from any step. (`bot/handlers/booking.py`) |
| F4 | **Blocked-times API broken** — partial-day ranges were silently dropped, the response schema 500-ed (`date` vs `str`), and there was **no list endpoint**, so blocks could never be viewed or deleted from the UI | Full CRUD: list endpoint added, ranges stored tz-aware, schema fixed, Schedule page now lists/creates/deletes blocks. |
| F5 | **Customers got notifications in the wrong language** — the bot never sent the customer's language; records defaulted to `uz` | `language` flows through `POST /bookings/public` onto the customer record; bot language changes also persist via `PATCH /auth/me/language`. |
| F6 | **No logout anywhere in the web app** | User menu (avatar → menu) with logout + language switcher in the new Layout. |
| F7 | Pending → confirmed transition never notified the customer | Confirmation message sent on owner approval. (`routers/bookings.py`) |
| F8 | Bot booking summary showed staff as `#3`, English weekday names in uz/ru, phone input rejected local formats | Staff names resolved from state; localized weekday keys (`wd_0…wd_6` ×3 langs); phone normalizer accepts `90 123 45 67` / `998…` / `+998…`. |
| F9 | Assigned staff member was never notified of new bookings (only the owner) | Staff with a linked Telegram account now get the new-booking alert too. |
| F10 | Double-cancel allowed re-cancelling finished bookings | `409` guard: only `pending/confirmed` can be cancelled; customer-cancel now notifies the owner. |

## Security hardening

| # | Issue | Fix |
|---|-------|-----|
| S1 | No security headers on API responses (Railway is reachable directly, bypassing the Vercel proxy headers) | Middleware: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store`, HSTS in production. (`main.py`) |
| S2 | CORS allowed all methods/headers | Locked to the methods/headers the app actually uses. |
| S3 | Mass assignment in `PATCH /admin/categories/{id}` (raw `dict` + `setattr`) | Explicit `CategoryUpdate` allow-list schema. |
| S4 | Timezone confusion: tz-aware `timestamptz` columns compared against naive datetimes (5-hour skew window on blocked ranges) | All comparisons/boundaries built tz-aware in `Asia/Tashkent`; stored datetimes normalized via `_as_local`. (`booking_engine.py`, `schedules.py`) |
| S5 | Missing rate limits on public booking + review submission | `60/min` and `30/min` (slowapi, per-user/IP key). |
| S6 | `GET /staff/{id}/working-hours` ignored business scoping | 404 unless the staff belongs to the path business. |
| S7 | Input validation gaps (name/phone/notes/reason lengths) | Pydantic `Field` constraints on booking, review, schedule payloads. |
| S8 | Access token expiry forced silent logouts after 24 h | Frontend now stores the refresh token and rotates on 401 (single-flight, replay of failed request). (`frontend/src/api/client.js`) |

## Reliability

- Reminder scheduler: bounded date window (no full-table scans), per-booking `try/except` (one Telegram failure can't kill the sweep), `coalesce/max_instances=1`, walk-ins skipped-and-flagged. (`services/scheduler.py`)
- Bot: global error handler releases the callback spinner on any handler crash. (`bot/main.py`)
- Bookings list API now returns service names (uz/ru/en) + staff name — clients render names without N+1 fetches.

## UI — complete redesign (frontend/src)

- **Design system v2** (`index.css`): warm-paper background washes, refined teal sidebar, sticky blurred topbar, segmented controls, date-strip, chips, stat cards with icon tiles, pure-CSS bar/donut charts, bottom-sheet modals, toast stack, staggered page reveals, `prefers-reduced-motion` support.
- **Hand-drawn SVG icon set** (`components/icons.jsx`, 34 icons) — no emojis anywhere in the chrome.
- **New shell** (`Layout.jsx`): desktop sidebar + topbar with business switcher and user menu (logout, language); mobile app bar + bottom nav.
- **Every page rebuilt**: Login (split brand panel, spinner states), Dashboard (greeting, today timeline, quick links), Bookings (14-day date strip, live slot picker fed by `/availability`, two-tap cancel), Services (chips, descriptions, manual-confirm hint), Staff (avatars, invite modal with Telegram share, per-staff hours editor), Schedule (copy-Mon-to-all, breaks + blocked days CRUD), Analytics (scaled bars, status donut, success rate), Settings (booking-link share card for Instagram bio, sticky save bar), Setup (3-step wizard with category cards), Admin (filterable table).
- **i18n**: ~240 keys complete in uz/ru/en with `{param}` interpolation; weekday families documented (`wd_*` = dayjs order, `wdm_*` = DB order).

## Tests & ops

- New regression suite `backend/tests/test_i_fixes.py` (walk-in collision, invite-URL shape, blocked-time lifecycle incl. availability impact, customer language, double-cancel guard). Runs in the existing GitHub Actions CI.
- `.env.example` / `DEPLOYMENT.md` updated with `TELEGRAM_BOT_USERNAME`.
- **Action required when deploying:** set `TELEGRAM_BOT_USERNAME` in Railway variables and run `alembic upgrade head` (Railway pre-deploy does this automatically).
