# Rezerv — Hardening Changelog

Maps every hardening change to the `AUDIT.md` finding it closes. Grouped so each
block can become one isolated commit once a git identity is provided.

Legend: ✅ done & test-proven · 🟡 done, needs Postgres to prove · ⬜ pending

---

## Test harness (Phase 2 pre-step)

- ✅ Added `requirements-dev.txt` (pytest, pytest-asyncio, aiosqlite); isolated `backend/.venv`.
- ✅ `pytest.ini` + `tests/conftest.py`: runs the real FastAPI app against in-memory SQLite, overrides `get_db`, stubs Telegram calls. `tests/factories.py` for seeding.
- ✅ Postgres-only behaviour is marked `@pytest.mark.postgres` and skipped until `TEST_DATABASE_URL` is set.

---

## A. Multi-tenant isolation & authorization

| Finding | Fix | Files | Proof |
|---|---|---|---|
| **A1** customer bookings world-readable by `telegram_id` | Endpoint now requires JWT; caller's `telegram_id` must match the path (or super-admin). Bot sends its token. | `routers/bookings.py`, `bot/api_client.py`, `bot/handlers/my_bookings.py` | `test_customer_bookings_requires_auth`, `test_customer_cannot_read_another_customers_bookings` |
| **A2** public booking endpoint unauthenticated | Added `require_bot_secret` choke point (`X-Bot-Secret` header, constant-time, fails closed if secret unset). Bot sends it. | `deps.py`, `routers/bookings.py`, `bot/api_client.py` | `test_public_booking_rejected_without_bot_secret`, `..._with_wrong_bot_secret` |
| **A3** review submission unauthenticated | Same `require_bot_secret` gate. Bot sends it. | `routers/reviews.py`, `bot/api_client.py` | `test_review_rejected_without_bot_secret` |
| **A4** `GET /admin/users` leaked `hashed_password` | Added `AdminUserOut` response_model that omits the hash. | `routers/admin.py` | `test_admin_users_does_not_leak_password_hash` |
| **A5** `GET /businesses/{id}` returned full record unauthenticated | Now requires JWT + ownership (or super-admin); customers use `/{id}/public`. | `routers/businesses.py` | `test_get_business_requires_auth`, `test_get_business_forbidden_cross_tenant` |
| **A6** no single tenant choke point | Introduced `require_bot_secret` dependency; cross-tenant matrix locked in by regression tests. | `deps.py` | 4 `test_cross_tenant_*` tests |
| **A7** no Postgres Row-Level Security | ⬜ Pending — will ship in the Postgres migration alongside D2 (needs a real Postgres to verify). | — | — |

**Status:** A1–A6 ✅ (12/12 tests). A7 🟡 pending Postgres.

---

## B. Authentication & Telegram initData

| Finding | Fix | Files | Proof |
|---|---|---|---|
| **B1** `/auth/bot` fail-open when `BOT_SECRET` empty (→ mint super-admin token) | Reject when `bot_secret` unset; constant-time compare retained. | `routers/auth.py` | `test_auth_bot_rejects_when_secret_unset` |
| **B2** initData validator usable with empty bot token (forgery) | Fail closed if `telegram_bot_token` unset. | `services/auth_service.py` | `test_initdata_rejected_when_token_unset` |
| **B3** refresh token accepted as access token | `get_current_user` rejects `type=refresh`; added rotating `POST /auth/refresh`. | `deps.py`, `routers/auth.py` | `test_refresh_token_rejected_as_access`, `test_access_token_accepted` |
| **B4** no fail-fast on weak/missing prod secrets | `validate_runtime_config()` raises at startup in production. | `config.py`, `main.py` | `test_validate_config_rejects_weak_secret_in_production` |
| **B5** replay window | Confirmed enforced (10 min in prod); locked by test. | `services/auth_service.py` | `test_expired_initdata_rejected_in_production` |
| **B6** Mini App SDK never loaded (`window.Telegram` undefined) | Added `telegram-web-app.js` to `index.html`. | `frontend/index.html` | manual (frontend) |
| **B7** password hashing **broken** under bcrypt 5.0.0 (passlib 1.7.4 raises) — upgraded Low→High | Pinned `bcrypt==4.0.1`. | `requirements.txt` | `test_password_hashing_roundtrip` |
| **B8** *(new, found via tests)* initData never URL-decoded → **all real logins rejected** | Decode values before building the data-check-string. | `services/auth_service.py`, `routers/auth.py` | `test_valid_initdata_accepted`, `test_forged_initdata_rejected` |

**Status:** ✅ all proven (13 B tests). Total suite: 25 passing.

---

## C. Secrets & configuration

| Finding | Fix | Files | Proof |
|---|---|---|---|
| **C1 / K1** all Alembic migrations git-ignored (deploys get no schema) | Stopped ignoring `backend/alembic/versions/*.py`; migrations are now tracked. | `.gitignore` | inspection |
| **C2** no committed secrets | Verified clean (no change needed). | — | grep |
| **C3** no startup env validation | Covered by `validate_runtime_config()` (see B4). | `config.py`, `main.py` | B4 test |

**Status:** ✅

---

## D. Double-booking & timezones

| Finding | Fix | Files | Proof |
|---|---|---|---|
| **D1** first-booking race (FOR UPDATE locks zero rows) | App: validate via single source of truth + final overlap check; convert DB constraint violation to clean 409. DB: exclusion constraint (below). | `services/booking_engine.py`, migration `0002` | `test_sequential_double_book_rejected` (app); `test_concurrent_booking_single_winner` 🟡 (Postgres) |
| **D2** no DB-level overlap guard | `btree_gist` EXCLUDE constraint on `(staff_id, tsrange(start,end))` for active bookings. | `alembic/versions/0002_*` | 🟡 needs Postgres |
| **D3** scheduler treats local time as UTC (reminders ~5h off) | `app/timeutils.py` (Asia/Tashkent → UTC); scheduler uses it. | `timeutils.py`, `services/scheduler.py` (pending wire-in) | `test_to_utc_tashkent_offset` |
| **D4** min/max advance + past times never enforced | Enforced in `get_available_slots` (window + past filter) and at confirm. | `services/booking_engine.py` | `test_availability_excludes_past_dates`, `..._beyond_max_advance`, `test_create_booking_rejects_past_date` |
| **D5** confirm-time skipped working hours/breaks/blocked | `create_booking` re-validates the slot via `get_available_slots`. | `services/booking_engine.py` | `test_create_booking_rejects_outside_working_hours` |
| **D7** duplicate `staff_services` links | Unique constraint `(staff_id, service_id)`. | migration `0002` | 🟡 needs Postgres |

**Status:** D1(app)/D3/D4/D5 ✅ (7 tests). D1(DB)/D2/D7 🟡 migration written, pending Postgres run. D6 (partial blocked-times) ⬜ deferred to F.
**Note:** `timeutils.to_utc` is now wired into `scheduler.py` (D3 applied). ✅

---

## F. Input validation & injection

| Finding | Fix | Files | Proof |
|---|---|---|---|
| **F2** stored-XSS / HTML injection in Telegram notifications | `html.escape()` all user-controlled values in every message builder. | `services/notification_service.py` | `test_notification_escapes_user_html` |
| **F3** no numeric/length constraints (0/negative duration breaks engine) | `Field(gt=0/ge=0/max_length=…)` on service schemas. (Skipped `extra=forbid` — the Services page posts `id`/`business_id`/`is_active`, so it would break editing.) | `routers/services.py` | `test_service_create_rejects_zero_duration`, `..._negative_price` |
| **F5** working hours with `end <= start` accepted | `model_validator` rejects inverted intervals + bad day_of_week. | `routers/schedules.py` | `test_working_hours_rejects_end_before_start` |
| **F1** SQL injection / React XSS | Verified none (parameterized + auto-escape). | — | grep |

**Status:** F2/F3/F5 ✅ (5 tests). F4 (admin dict body) / F6 / D6 ⬜ deferred (Medium/Low).

---

## H. Rate limiting & abuse

| Finding | Fix | Files | Proof |
|---|---|---|---|
| **H1/H3** public booking/review spam, availability scraping | Booking/review now bot-secret-gated (A2/A3); added `60/min` on availability. | `routers/availability.py` | covered by A tests + manual |
| **H2** limits keyed by IP only (NAT over/under-blocks) | Custom key: per-user when authenticated, X-Forwarded-For-aware IP otherwise. | `limiter.py` | `test_key_prefers_authenticated_user`, `..._forwarded_for`, `..._client_ip` |
| **E6** two `Limiter` instances → auth limits silently not enforced | One shared limiter in `app/limiter.py`, imported by main/auth/availability. | `limiter.py`, `main.py`, `routers/auth.py` | `test_single_shared_limiter_instance` |

**Status:** ✅ (4 tests). Redis-backed storage for multi-replica deferred (needs running Redis; in-memory fine for single instance).

---

## E. Performance

| Finding | Fix | Files | Proof |
|---|---|---|---|
| **E1** N+1: one Service query per existing booking on the availability hot path | Batch-load services in `_get_booking_intervals` and the confirm overlap loop. | `services/booking_engine.py` | `test_availability_no_n_plus_one_on_services` (6→2 queries) |
| **E3** missing composite indexes | `(staff_id, booking_date, status)` + `(business_id, booking_date)`. | migration `0002` | 🟡 needs Postgres |
| **E4** unbounded bookings list | `limit`/`offset` (default 200, max 500); non-breaking. | `routers/bookings.py` | `test_bookings_list_respects_limit` |
| **E6** duplicate limiter | Single shared limiter (see H). | `limiter.py` | H test |

**Status:** E1/E4/E6 ✅. E3 🟡 (migration). E5 (Redis cache) / E2 / E7 ⬜ deferred (need Redis / Lower value).

---

## G. Error handling, logging & observability

| Finding | Fix | Files | Proof |
|---|---|---|---|
| **G1** no global handler (leaks tracebacks/SQL) | Global exception handler → clean JSON + `request_id`; request-id middleware; structured logging. | `main.py` | `test_unhandled_error_returns_clean_json`, `test_response_has_request_id_header` |
| **G2** no React error boundary (white screen) | `ErrorBoundary` with localized fallback, wraps `<App>`. | `frontend/src/components/ErrorBoundary.jsx`, `main.jsx` | frontend build ✓ |
| **G3** `/health` didn't check DB | `/health` runs `SELECT 1`, returns 503 if DB down. | `main.py` | `test_health_reports_db_ok` |

**Status:** G1/G2/G3 ✅. G4 (Sentry) hookable in ErrorBoundary/logger; G6 (scheduler single-runner) ⬜ deferred.

---

## I. UI — full design-system rebrand

| Finding | Fix | Files | Proof |
|---|---|---|---|
| **I1** generic default-blue / stock-SaaS look | Distinctive **deep teal-green** brand on warm **paper** neutrals; new icon (gradient mark), `theme-color`, manifest colors. | `index.css`, `index.html`, `vite.config.js`, `public/icons/*` | bundle grep ✓ (no `#2563eb`) |
| **I2** no real token layer; ad-hoc styles | Full token system: brand ramp, warm neutrals, semantic, **type scale, spacing, radius, shadow, motion**. Redefined legacy token *values* so all 10 pages re-skin at once; refined every component class (btn/card/badge/input/nav/table/stat/modal/toggle). | `frontend/src/index.css` | build ✓ |
| typeface with character | **Manrope** variable, self-hosted (offline PWA), Latin + Cyrillic (uz/ru/en). | `main.jsx`, bundle | 5 woff2 subsets shipped ✓ |
| micro-interactions | 120–320ms transitions, button press, focus rings, sheet/pop modal animations, **skeleton loaders**, `prefers-reduced-motion`. | `index.css`, `components/Skeleton.jsx`, `Bookings.jsx` | build ✓ |
| **I4** viewport blocked pinch-zoom | Removed `maximum-scale`/`user-scalable=no`; added `viewport-fit=cover` + safe-area insets. | `index.html`, `index.css` | build ✓ |
| **I5** missing PWA icons | Generated PNGs + favicon from rebranded SVG. | `public/icons/*` | 9 precache entries ✓ |
| **I3** sub-44px tap targets | 44px min on buttons/nav/inputs, 58px bottom-nav. | `index.css` | build ✓ |
| polished surfaces | Rebuilt Login (brand mark), sidebar lockup, empty states; **Dashboard** flagship polish — skeleton loading, resolved service names (was raw `#id`), localized strings, brand-accented stat. | `Login.jsx`, `Layout.jsx`, `Dashboard.jsx`, `i18n/index.js` | build ✓ |

**Verified live via `preview_inspect`:** primary button `rgb(12,110,86)` (brand teal), body `rgb(247,245,241)` (warm paper), font `Manrope Variable`, 44px tap targets — rendering exactly as designed.

**Status:** ✅ build-verified + bundle-inspected + computed-style-verified. (Live screenshot blocked: the preview launcher can't handle spaces in Windows paths — `C:\Program Files`, `Nitro 5`. Run `npm run dev` in `frontend/` to see it.) Per-page fine-polish of remaining inline styles can follow, but every page already inherits the new system.

---

## J. Testing & CI

| Finding | Fix | Files | Proof |
|---|---|---|---|
| **J1** zero tests, no CI | 46-test suite across A/B/D/E/F/G/H; GitHub Actions runs backend (with a Postgres service → the concurrency test runs green in CI) + frontend build. | `tests/*`, `.github/workflows/ci.yml` | suite green |

**Status:** ✅ (CI runs the Postgres-only tests that are skipped locally).

---

## K. Ops, data safety & deploy

| Finding | Fix | Files | Proof |
|---|---|---|---|
| **K1** migrations git-ignored | Fixed (see C1). | `.gitignore` | — |
| **K2** base compose ran `--reload`, no migration | Removed override (Dockerfile CMD migrates); `--reload` + bind-mount moved to dev overlay. | `docker-compose.yml`, `docker-compose.dev.yml` | inspection |
| **K3** `npm ci` build break (no lockfile) | Generated `package-lock.json`; build verified. | `frontend/package-lock.json` | `npm run build` ✓ |
| **K4** no security headers | Added to nginx + Vercel (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, HSTS, Permissions-Policy). | `nginx.conf`, `vercel.json` | inspection |
| **K7** no runbook | `RUNBOOK.md` (deploy / rollback / rotate / restore / incidents). | `RUNBOOK.md` | — |
| **K8** docs off in prod | Verified already correct. | — | — |

**Status:** K1/K2/K3/K4/K7 ✅. K5 (tighten CORS methods) / K6 (set real Vercel API URL) ⬜ need your prod URLs.

---

## SUITE STATUS: **46 passing locally (1 Postgres test skipped); full suite GREEN in CI.**

### ✅ Proven on real Postgres in GitHub Actions (run #3, branch `hardening`):
- **D1/D2** — migration applies the `btree_gist` exclusion constraint; concurrency test: 8 parallel bookings → exactly 1 winner.
- **D7** — `staff_services` unique constraint applies.
- **E3** — composite indexes apply.
- **K** — migrations `upgrade head` → `downgrade base` cleanly (reversible).
- CI fixes en route: `0001` enum double-creation (DuplicateObjectError) and `0002` exclusion-constraint parenthesization.

### ⬜ Still open:
- **A7 (RLS)** — NOT implemented (documented only). App-level tenant isolation is proven (12 A tests); RLS is defense-in-depth and remains the one unbuilt audit item.
- Deferred (your call / infra): E5 Redis cache, I1/I2 remaining per-page UI polish, K6 real prod URLs, G4 Sentry.

