# Rezerv — Production-Readiness Hardening Audit

> **Status:** Audit only. No code changed. Awaiting approval before any fixes.
> **Scope:** Whole repo (backend, bot, frontend, infra) against categories A–K of the hardening prompt.
> **Date:** 2026-06-07
> **Reviewer hat:** staff-level security + backend + frontend. Goal = "50 paying businesses trust this with their bookings and customer data."

---

## How to read this

Each finding has an ID (e.g. `A1`), a **severity**, the **file:line**, the concrete problem, and a one-line fix. IDs are stable so the eventual `CHANGELOG_HARDENING.md` can map fix ↔ issue. Acceptance tests called out in the prompt are noted where relevant.

### Severity tally

| Severity | Count | IDs |
|---|---|---|
| 🔴 Critical | 7 | A1, A2, B1, B2, D1, C1/K1, B6 |
| 🟠 High | 18 | A3, A4, A7, B3, B4, C3, D2, D3, D4, E1, E3, F2, G1, G2, H1, H2, J1, K2, K3 |
| 🟡 Medium | 21 | A5, A6, A8, B5, C4, D5, D6, E2, E4, E5, E6, F3, F4, F5, G3, G4, G5, H3, I1–I5, K4–K7 |
| ⚪ Low | 9 | A9, B7, C2, D7, E7, F6, G6, I6, K8 |

### The one-paragraph summary

The build is structurally sound (clean SQLAlchemy, parameterized queries, React auto-escaping, a real attempt at `FOR UPDATE`, i18n parity, `.env` ignored, docs off in prod). But it is **not safe for real customer data yet**. Three things must be fixed before anyone touches it in production: (1) the public booking/customer/review endpoints have **no authentication and trust `telegram_id` from the request body/path** — anyone on the internet can read any customer's phone + booking history and create/spoof bookings (A1–A3); (2) the bot-auth shared secret and the Telegram initData validator **fail open when their secret env var is empty**, allowing anyone to mint a token for any user, including super-admin (B1, B2); (3) **all Alembic migrations are git-ignored** (`.gitignore:44`), so every Railway/Docker deploy runs `alembic upgrade head` against an empty migration set and comes up with **no database schema** (C1/K1). Separately, the Telegram Mini App login is silently broken because `index.html` never loads the Telegram SDK (B6), and the double-booking guard has a real race on the first booking of the day (D1).

---

## A. Multi-tenant isolation & authorization — CRITICAL category

The existing owner-scoped routers (`services.py`, `staff.py`, `analytics.py`, `schedules.py`) mostly do this right via a local `_get_owned_business` helper. The danger is the **unauthenticated "public" surface** that trusts client-supplied identity.

| ID | Sev | Location | Problem | Fix |
|---|---|---|---|---|
| **A1** | 🔴 Critical | `backend/app/routers/bookings.py:336` `get_customer_bookings` | No auth at all. `telegram_id` taken from the URL path; returns any customer's bookings including `customer_phone` (PII). Telegram IDs are not secret → mass PII enumeration. | Require identity (Mini App JWT, or bot shared-secret header); derive the customer from the token, never the path. |
| **A2** | 🔴 Critical | `backend/app/routers/bookings.py:81` `create_public_booking` | No auth. `telegram_id` trusted from request body. Anyone can create bookings as any customer / flood any business. | Authenticate the caller (bot secret header or initData); derive `telegram_id` server-side. |
| **A3** | 🟠 High | `backend/app/routers/reviews.py:29` `create_review` | No auth; `telegram_id` from body. Ownership check exists but only compares to the same attacker-supplied id → anyone who knows a victim's telegram_id + a completed `booking_id` (sequential) can post reviews as them. | Require auth; derive customer from token. |
| **A4** | 🟠 High | `backend/app/routers/admin.py:149` `list_users` | Returns raw `User` ORM rows with **no `response_model`** → serializes `hashed_password` to the client. | Add a response schema that omits `hashed_password`. |
| **A5** | 🟡 Medium | `backend/app/routers/businesses.py:144` `get_business` | No auth; returns full internal config (booking rules, custom messages) for **any** business id, including `suspended`/`blocked`/`pending` (the `/public` route filters these; this one doesn't). | Gate to owner/admin, or return only public fields. |
| **A6** | 🟡 Medium | `businesses.py:162`, `bookings.py:175,201,251,305`, `schedules.py:95,142,180,213`, `analytics.py:26` | Tenant ownership is re-implemented inline in ~10 places (`business.owner_id != user.id and role != "super_admin"`). Easy to forget one; no single choke point. | One `get_owned_business(business_id)` FastAPI dependency + tenant-scoped query helper; reuse everywhere. |
| **A7** | 🟠 High | DB-wide (migration `0001`) | No Postgres **Row-Level Security** on any tenant table — no defense-in-depth if an app filter is ever missed. | RLS migration on tenant-owned tables, tenant id set per-transaction (GUC); verify a wrong-tenant query returns 0 rows. |
| **A8** | 🟡 Medium | `availability.py:19`, `public.py:43` | Internal `staff_id`s and a business's full open-slot map are exposed unauthenticated and unthrottled → staff enumeration + scraping. | Acceptable as semi-public, but throttle (see H) and consider opaque ids. |
| **A9** | ⚪ Low | `bookings.py:306` `cancel_booking` | `is_customer` relies on `hasattr(user, "telegram_id")`; manual bookings use `customer.telegram_id = 0`, so a user with a null/0 telegram_id could match. | Explicit `is not None` and `!= 0` checks. |

**Acceptance (prompt):** an automated IDOR matrix proving user B gets 403/404 (never data) on business A's object ids. None exists today → see J1.

---

## B. Authentication & Telegram initData

The initData validator (`auth_service.py:40`) is actually well-written — correct HMAC-SHA256 with `WebAppData`, sorted data-check-string, `hmac.compare_digest`, and an `auth_date` window. The failures are around **empty-secret fail-open**, **token type**, and a **broken Mini App bootstrap**.

| ID | Sev | Location | Problem | Fix |
|---|---|---|---|---|
| **B1** | 🔴 Critical | `auth.py:91` `auth_bot` + `config.py:42` (`bot_secret: str = ""`) | `hmac.compare_digest(body.bot_secret, settings.bot_secret)`. If `BOT_SECRET` is unset, both sides are `""` and the check passes for anyone sending `bot_secret=""`. They can then mint a token for **any** `telegram_id`, and `auth_service.py:80` auto-grants `super_admin` to configured admin ids → **privilege escalation to platform admin**. | Fail closed: refuse `/auth/bot` if `bot_secret` is empty or < 32 chars; validate at startup (C3). |
| **B2** | 🔴 Critical | `auth_service.py:52` + `config.py:27` (`telegram_bot_token: str = ""`) | initData secret key = HMAC(`WebAppData`, bot_token). If the token is empty, the key is known → initData forgery is trivial. | Refuse initData validation when the bot token is unset. |
| **B6** | 🔴 Critical | `frontend/index.html` | The Telegram WebApp SDK (`telegram-web-app.js`) is **never loaded**, so `window.Telegram?.WebApp` is `undefined` (`App.jsx:27`). The Mini App auth branch never runs → in production the app falls through to "Open via Telegram" and is unusable as built. | Add `<script src="https://telegram.org/js/telegram-web-app.js"></script>` to `index.html`. |
| **B3** | 🟠 High | `deps.py:16` `decode_token` | Doesn't verify the token `type`. A 30-day **refresh** token (`auth_service.py:23`) is accepted as an access token on every protected route. No `/auth/refresh` endpoint exists to rotate, either. | In `get_current_user`, reject tokens where `payload.get("type") == "refresh"`; add a rotating `/auth/refresh`. |
| **B4** | 🟠 High | `config.py:22` + `.env.example:15` | `SECRET_KEY` is required (good — no default) but the app will happily boot with the literal placeholder `change-this-to-a-long-random-string...`. | At startup in production, reject empty / placeholder / `< 32 char` secrets. |
| **B5** | 🟡 Medium | `auth_service.py:60` | `auth_date` freshness only enforced when `is_production`; fine, but document the 600 s window; no nonce store (window-only is acceptable at this scope). | Keep window; document it. |
| **B7** | ⚪ Low | `requirements.txt:10` | `passlib[bcrypt]==1.7.4` is known to raise on bcrypt ≥ 4.1 (`__about__` removed). No web-password signup path exists yet, so impact is low. | Pin `bcrypt<4.1` or move to `bcrypt`/`argon2` directly. |

**Acceptance (prompt):** forged + expired initData both rejected; protected routes 401 without a token. Tests needed (J1).

---

## C. Secrets & configuration

Good news first: **no real secret is committed anywhere** (full-repo grep clean), `.env.example` is placeholders only, `.gitignore:15` covers `.env`, and this isn't a git repo yet so there's no history to leak.

| ID | Sev | Location | Problem | Fix |
|---|---|---|---|---|
| **C1** | 🔴 Critical | `.gitignore:44` | `backend/alembic/versions/*.py` ignores **all** migrations. They won't be committed; `alembic upgrade head` on deploy runs against nothing → empty schema in prod. (Cross-listed K1.) | Replace with a rule that only ignores scratch files; ensure `0001_initial_schema.py` is tracked. |
| **C2** | ⚪ Low (✅) | repo-wide | No hardcoded secrets/tokens/connection strings found. | None — keep it that way; add CI secret scan. |
| **C3** | 🟡 Medium | `config.py` | No startup validation that `DATABASE_URL`, `SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, `BOT_SECRET` are present and non-placeholder. Missing ones surface as confusing runtime errors. | Validate in `Settings`/lifespan; fail fast with a clear message in production. |
| **C4** | ⚪ Low | `config.py:13-14` | `postgres_password` defaults to `"changeme"` (local-compose only; prod uses `DATABASE_URL`). | Document; ensure prod never relies on the default. |

---

## D. Booking concurrency & timezones — the heart of the product

`create_booking` (`booking_engine.py:348`) makes a genuine attempt with `SELECT ... FOR UPDATE`, but it has a classic gap, and the whole system is timezone-naive.

| ID | Sev | Location | Problem | Fix |
|---|---|---|---|---|
| **D1** | 🔴 Critical | `booking_engine.py:400-413` | `FOR UPDATE` locks only **existing** booking rows for `(staff, date)`. When the staff has **zero** bookings that day, the lock set is empty and locks nothing → two concurrent "first booking" requests both pass the in-Python overlap check and both insert. Check-then-insert is not safe under concurrency. | Add a Postgres **`EXCLUSION` constraint** (`btree_gist`) on `(staff_id, tstzrange(start,end))` — declarative, race-proof — and/or lock the parent `staff`/`business` row. Return a clean 409 on conflict (already does). |
| **D2** | 🟠 High | migration `0001` (bookings) | No DB-level overlap/unique constraint exists at all. | Ship the exclusion-constraint migration (needs `CREATE EXTENSION btree_gist`). |
| **D3** | 🟠 High | `booking.py:42-44`, `scheduler.py:45` | Times stored as **naive** `Date`+`Time`. The scheduler does `datetime.combine(date, time, tzinfo=utc)`, treating Asia/Tashkent (UTC+5) local time as UTC → **24h/1h reminders fire ~5 hours off**. Availability math is also tz-naive. | Do availability/reminder math in the business tz (Asia/Tashkent), store/compare in UTC; audit every naive `datetime`. |
| **D4** | 🟠 High | `booking_engine.py` (slots + confirm) | `min_advance_booking_minutes` and `max_advance_booking_days` (defined on `Business`) are **never enforced**. Customers can book in the past or years ahead; for "today" already-passed times are still offered. | Enforce both windows in `get_available_slots` and again in `create_booking`; drop past times. |
| **D5** | 🟡 Medium | `booking_engine.py:421-434` | Confirm-time validation only checks overlap with other bookings — **not** working hours, breaks, or blocked times. A crafted POST can book outside hours / during lunch. | Re-validate the requested slot against full availability at confirm; never trust the client slot. |
| **D6** | 🟡 Medium | `booking_engine.py:174-181` + `schedules.py:205-227` | Blocked-time handling is inconsistent: `add_blocked_time` silently ignores `start_datetime`/`end_datetime` (partial blocks never persist), and the engine's `blocked_date == target_date` branch forces a full-day block even for partial ranges. | Persist partial ranges; make the engine honor them. |
| **D7** | ⚪ Low | migration `0001` (staff_services) | No unique constraint on `(staff_id, service_id)` → duplicate links inflate auto-assign load counts and availability. | Add unique constraint. |

**Acceptance (prompt):** N concurrent requests for one slot → exactly one booking. Needs a concurrency test (J1) — it will currently **fail** on D1.

---

## E. Performance & scalability

Passes with 5 rows; the cliffs are N+1s, missing composite indexes, and no caching.

| ID | Sev | Location | Problem | Fix |
|---|---|---|---|---|
| **E1** | 🟠 High | `booking_engine.py:208-209`, `:422-423` | N+1: per existing booking, a separate `SELECT` for its `Service` (in both availability and the confirm overlap loop). This is the hot path. | Eager-load services (join/`selectinload`) or cache service buffers in one fetch. |
| **E3** | 🟠 High | migration `0001` | Only single-column indexes. The hot availability/list queries filter on `(staff_id, booking_date, status)` and `(business_id, booking_date)` — no composite index. | Add composite indexes. |
| **E2** | 🟡 Medium | `staff.py:92` (`_staff_with_services` per staff), other list endpoints | N+1 on staff→services. | `selectinload`. |
| **E4** | 🟡 Medium | `bookings.py:165`, `staff.py:262`, `public.py:16` | No pagination — unbounded result sets (a busy business returns every booking). | Add limit/offset or keyset pagination. |
| **E5** | 🟡 Medium | backend-wide | `redis` is a dependency but **unused** (grep clean) — no caching of categories/services/business profile. | Add tenant-scoped Redis cache + TTL + invalidate-on-write; **do not** cache availability. |
| **E6** | 🟡 Medium | `main.py:27`, `auth.py:22` | slowapi uses default **in-memory** storage and there are **two** `Limiter` instances → limits are per-process, reset on restart, and inconsistent across replicas. | Single limiter backed by Redis `storage_uri`. |
| **E7** | ⚪ Low | `scheduler.py:34` | Loads all future confirmed unsent bookings every 15 min, filters in Python. | Add a SQL time-window bound. |

---

## F. Input validation & injection

| ID | Sev | Location | Problem | Fix |
|---|---|---|---|---|
| **F1** | ✅ | repo-wide | **No raw/string-built SQL** (grep) — SQLAlchemy parameterized throughout. **No `dangerouslySetInnerHTML`** — React escapes. Good. | Keep. |
| **F2** | 🟠 High | `notification_service.py:35-154` | User-controlled `customer_name`, `service_name`, `business_name`, `staff_name` are interpolated into `parse_mode="HTML"` Telegram messages **unescaped**. A customer named `<b>x` (or with `&`/`<`) forges formatting or makes Telegram reject the message (notification DoS to the owner). | `html.escape()` every interpolated value before sending. |
| **F3** | 🟡 Medium | `services.py`, `businesses.py`, `bookings.py` schemas | Pydantic models lack constraints: `duration_minutes`/`buffer_*` no `gt=0` (0/negative breaks slot math), `price` no `ge=0`, strings no `max_length`, no `extra="forbid"` (unknown fields silently accepted), phone/Instagram/Telegram URLs unvalidated. | Add `Field(...)` constraints + `model_config = {"extra": "forbid"}`; validate phone/URL formats. |
| **F4** | 🟡 Medium | `admin.py:130` `update_category` | Body typed as `dict`; `setattr`s arbitrary attributes (mass assignment, super-admin only but still). | Typed Pydantic schema. |
| **F5** | 🟡 Medium | `schedules.py` (working hours/breaks) | No check that `end_time > start_time` → inverted intervals silently corrupt availability. | Validate ordering. |
| **F6** | ⚪ Low | `businesses.py` `BusinessUpdate` | `min_advance`, `max_advance`, `slot_step` accept negative/huge values. | Bound them. |

---

## G. Error handling, logging & observability

| ID | Sev | Location | Problem | Fix |
|---|---|---|---|---|
| **G1** | 🟠 High | `main.py` (none) | No global exception handler. Unhandled errors leak FastAPI's default 500; with `database.py:11` `echo=not is_production`, SQL (incl. params) is logged in dev. | Global handler → clean JSON + request id; structured logging server-side with tenant id. |
| **G2** | 🟠 High | `frontend/src/App.jsx` | No React **error boundary** → any render error is a white screen. | Add an `ErrorBoundary` with a localized fallback. |
| **G3** | 🟡 Medium | `main.py:72` `/health` | Returns a static OK; doesn't check DB/Redis. | Add a DB ping (and Redis once used). |
| **G4** | 🟡 Medium | backend-wide | No error tracker (Sentry), no structured logging of auth failures / authz denials / booking conflicts / scheduler errors. | Add leveled logging + optional Sentry free tier (no PII/secrets). |
| **G5** | 🟡 Medium | `database.py:11` | `echo=True` in dev logs customer phones (PII). Off in prod (correct) — flag so it stays off. | Keep prod off; scrub if ever enabled. |
| **G6** | ⚪ Low | `main.py:31` + `scheduler.py` | Scheduler runs inside the API process; with >1 replica → **duplicate reminders**; a job exception loop could affect the API. | Single-runner guard or a separate worker process. |

---

## H. Rate limiting & abuse

| ID | Sev | Location | Problem | Fix |
|---|---|---|---|---|
| **H1** | 🟠 High | `bookings.py:81`, `availability.py`, `reviews.py:29`, `public.py` | Public, unauthenticated, **unthrottled** → booking spam, availability scraping, review spam. | Apply slowapi limits + require identity (ties to A1–A3). |
| **H2** | 🟠 High | `main.py:27` | Limits keyed by `get_remote_address` only. Behind nginx/Vercel that's the proxy IP (global throttle/bypass); Uzbek mobile NAT means per-IP both over- and under-blocks. | Honor `X-Forwarded-For` from trusted proxy + key per-user / per-tenant. |
| **H3** | 🟡 Medium | routers | Decorators only on `/auth/*`; booking/review/availability have none. | Add per-endpoint limits to sensitive routes. |

**Acceptance (prompt):** public booking link guarded against spam — currently open.

---

## I. Make the UI not look like every other AI app

There's a partial token layer, a working mobile bottom-nav, and full i18n parity (`frontend/src/i18n/index.js`, all three langs match) — a decent base. But it reads as the default-blue SaaS template the goal explicitly warns against.

| ID | Sev | Location | Problem | Fix |
|---|---|---|---|---|
| **I1** | 🟡 Medium | `index.css:4`, `vite.config.js:17`, `index.html:6` | Primary `#2563eb` is the exact generic SaaS blue. | Pick a distinctive, restrained brand color + a typeface with character. |
| **I2** | 🟡 Medium | `index.css` + pages | Token layer is colors-only; no type scale, spacing scale, radius/shadow/motion tokens. Components use ad-hoc inline styles (`Bookings.jsx`, `Login.jsx`). | Complete the token system; refactor components onto it. |
| **I3** | 🟡 Medium | `index.css:40` `.btn-sm`, bottom-nav, icon buttons | Tap targets below 44px (HIG). | Enforce ≥44px touch targets. |
| **I4** | 🟡 Medium | `index.html:5` | `maximum-scale=1.0, user-scalable=no` blocks pinch-zoom (a11y). | Allow user scaling. |
| **I5** | 🟡 Medium | `vite.config.js:19-23` vs `public/icons/` | Manifest references `icon-192.png` / `icon-512.png`, but only `icon.svg` exists → PWA install/icon failures. | Generate the PNGs (`scripts/generate-icons.js` exists) and ensure they ship. |
| **I6** | ⚪ Low | pages | No skeletons / optimistic UI / success states; long ru/uz strings vs fixed inline widths untested. | Add restrained micro-interactions; test long-string layouts. |

---

## J. Testing & CI

| ID | Sev | Location | Problem | Fix |
|---|---|---|---|---|
| **J1** | 🟠 High | repo-wide | **Zero tests.** `pytest`/`pytest-asyncio` not in `requirements.txt` (plan pre-step). No `.github/` CI. | Add test deps; write critical-flow tests — forged/expired initData (B), IDOR matrix (A), double-booking concurrency (D1), availability edge cases, status transitions, role perms; add a GitHub Actions lint+test gate. Per the prompt's "Final Rule", each fix lands with a failing→passing test. |

---

## K. Ops, data safety & deploy

| ID | Sev | Location | Problem | Fix |
|---|---|---|---|---|
| **K1** | 🔴 Critical | `.gitignore:44` | (= C1) Migrations git-ignored → deploys come up with no schema. | Track migrations. |
| **K2** | 🟠 High | `docker-compose.yml:45` | Backend command is `uvicorn --reload` with **no** `alembic upgrade head` (the prod `railway.toml`/`Dockerfile` do run it; base compose doesn't), and `--reload` is wrong for the base/prod compose. | Run migrations on start; drop `--reload` from the base compose (keep it only in `.dev`). |
| **K3** | 🟠 High | `frontend/Dockerfile:12` | `npm ci` requires `package-lock.json`, which is **absent** → production image build fails. | Commit a lockfile, or use `npm install` in the build stage. |
| **K4** | 🟡 Medium | `nginx.conf`, `vercel.json` | No security headers (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP); nginx listens on 80 only though compose maps 443; no HTTPS enforcement. | Add headers; enforce HTTPS/redirect. |
| **K5** | 🟡 Medium | `main.py:49-55` | CORS: `allow_methods=["*"]`, `allow_headers=["*"]` with `allow_credentials=True` is broad (origins are locked, which is good). | Tighten methods/headers to what's used. |
| **K6** | 🟡 Medium | `vercel.json:3` | API rewrite destination is the placeholder `https://your-backend.railway.app` → prod API 404s until replaced. | Set the real backend URL (or env). |
| **K7** | 🟡 Medium | docs (none) | No backup/restore verification, no `RUNBOOK.md`. | Document Neon backups + a tested restore; write the runbook (deploy/rollback/rotate-secret/restore). |
| **K8** | ⚪ Low | `main.py:42-43` (✅), Dockerfiles | `/docs` + `/redoc` correctly disabled in prod. Containers run as root (minor). | Keep docs gated; add a non-root user. |

---

## Notable things already done right (so we don't regress them)

- Parameterized SQL everywhere; no string-built queries (F1).
- React auto-escaping; no `dangerouslySetInnerHTML` (F1).
- initData validator uses correct HMAC + `compare_digest` + freshness window (B, minus the empty-token fail-open).
- A real `SELECT FOR UPDATE` attempt and clean 409-on-conflict (D — minus the first-booking race).
- Owner-scoped routers use a consistent `_get_owned_business` ownership check (A — the gap is the public surface).
- Full uz/ru/en i18n parity in both frontend and bot.
- `.env` git-ignored; no committed secrets; `/docs` off in prod; reversible migration `downgrade()`; healthcheck path wired.

---

## Recommended execution order (per the prompt)

1. **Data-breach stoppers first (do not deploy until these land):** A1, A2, A3, A4 · B1, B2, B6, B3 · C1/K1. These are small, high-leverage fixes.
2. **Booking integrity:** D1+D2 (exclusion constraint), D3 (timezone), D4/D5 (window + confirm-time validation).
3. **Input validation & abuse:** F2, F3, F4, F5 · H1, H2.
4. **Scale & resilience:** E1, E3 (then E2/E4/E5/E6) · G1, G2, G3, G4.
5. **Testing + CI:** J1 — and per the Final Rule, retro-fit a failing→passing test for each A/B/D fix above.
6. **Ops:** K2, K3, K4, K6, K7.
7. **UI (parallel, frontend-isolated):** I1–I6.

---

## Proposed deliverables once approved

- Fixes as small, single-concern commits, each leaving the app runnable (committed as `ismoiljon1101 / ismoiljonedu@gmail.com` per repo convention — please confirm that author convention applies here too, or give me the right one).
- New Alembic migrations: composite indexes (E3), `btree_gist` + exclusion constraint (D2), RLS (A7), `staff_services` unique (D7).
- A `pytest` suite covering the critical flows + a GitHub Actions workflow (J1).
- `CHANGELOG_HARDENING.md` mapping every fix to the IDs above.
- `RUNBOOK.md` (deploy / rollback / rotate-secret / restore).

---

### Questions before I start fixing (need your call)

1. **Git:** this folder isn't a git repo. Phase 2 is built on "small isolated commits." Want me to `git init` here first?
2. **Commit author:** the MedAccess CLAUDE.md says commit as `ismoiljon1101 / ismoiljonedu@gmail.com`. Does that apply to this repo too, or a different author?
3. **Approval granularity:** approve the whole audit and I work top-to-bottom, or approve category-by-category (A → B → C …) with a checkpoint after each?
4. **Secrets to rotate:** I found no committed secrets, so nothing to rotate. If you have a real `.env` outside the repo, keep it out — I won't read it.

**No code will change until you approve.**
