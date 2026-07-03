# Before-Deployment Fixes — Scale Readiness Plan

**Source:** Verified multi-agent readiness audit, 2026-07-03 (target: 300 businesses / 50,000 users, single district).
**Method:** every issue below was found by reading the actual code, then independently re-verified. Severities are the *verified* ones.
**Rule:** UI design stays as-is. These are logic / correctness / security / scale fixes only.

**Bottom line:** the core is solid — no data-corruption bombs, double-booking is prevented, HTML/emoji escaping is handled, hot-path indexes exist, health/migrations/secret-validation are good, and multi-tenant isolation holds. The items below are real but bounded, and most bite *early* (first suspension, day-15 trial, nightly at midnight, first forwarded staff link, first investor-map share).

We ship in three focused deploys: **A → B → C**, plus a **Polish backlog (D)**. Each deploy is independently shippable and testable.

---

## DEPLOY A — "the leaks & the money" (start here)

Money-losing or credibility-losing issues. Mostly backend logic.

### A1. Investor map secret is public 🔴
- **Problem:** `GROWTH_SECRET` is hardcoded in the static site `QN_Investor/config.js:23` and `PASSCODE:""` disables the gate. Anyone with the "unlisted" link can view-source, read the secret, and call `GET /admin/growth` to scrape the entire traction dataset + every business name & exact GPS. (No customer PII in the feed.)
- **Locations:** `QN_Investor/config.js:23,27`, `QN_Investor/growth-source.js:8`, `backend/app/routers/admin.py:377` (`growth_map`).
- **Fix — code (I do):**
  - Move the secret out of the URL query string into a request header (`X-Growth-Secret`) in both `growth-source.js` and the backend endpoint (query string is logged by proxies/CDN + browser history).
  - Add rate limiting to `/admin/growth` (see C4 — pull it forward into A).
  - Scaffold a non-empty `PASSCODE` in `config.js` (value chosen by you).
- **Fix — ops (you do):**
  - **Rotate** `GROWTH_SECRET` to a fresh value in the backend Railway env (the current one is burned).
  - **Enable Vercel password protection** (or equivalent) on the investor site so the static bundle isn't world-readable.
- **Tests:** endpoint returns 403 without/with wrong secret; 200 with correct secret via header.

### A2. Trial / subscription enforcement doesn't exist 🔴
- **Problem:** `Subscription` model + `trial_ends_at` are written but never read. After the 14-day trial a business books free forever. Manual-payment model has no teeth. Bites ~day 15 (early August for the launch cohort).
- **Locations:** `backend/app/models/subscription.py`, `backend/app/routers/businesses.py:177` (`trial_ends_at`), `backend/app/services/scheduler.py` (jobs), approval flow in `backend/app/routers/admin.py`.
- **Fix (I do):**
  - Add a daily scheduler job `_expire_trials`: flip `status='trial' AND trial_ends_at < now()` → `status='suspended'` (atomic UPDATE). Registered like the existing reminder/broadcast jobs.
  - Confirm approved businesses land in `trial` (not straight `active`) so the timer means something; adjust approval if needed.
  - Add an admin endpoint to **record a payment** → set `status='active'` (+ optionally extend `trial_ends_at`), and write a `Subscription` row so payments are auditable.
  - Works together with A3: once expired trials become `suspended`, A3's booking-path gate stops them.
- **Tests:** expired trial flips to suspended; active/paid business unaffected; admin mark-paid sets active + creates Subscription row.

### A3. Suspended / blocked / pending businesses stay bookable 🔴
- **Problem:** `get_available_slots` checks only `is_online_booking_enabled`, never `Business.status`. A suspended (non-payment), blocked (abuse), or still-pending business keeps serving slots and accepting bookings for anyone with its id.
- **Locations:** `backend/app/services/booking_engine.py:335` (`get_available_slots`), public create `backend/app/routers/bookings.py` (~238), manual create (~396).
- **Fix (I do):** require `business.status in ('active','trial')` — return `[]` from availability, raise `409` on create — mirroring the listing filter at `public.py:69` / `businesses.py:256`. Applied to availability + public create + manual create (an owner must be approved/active to take any bookings).
- **Tests:** availability returns [] for suspended/blocked/pending; public create → 409; active/trial still works.

### A4. Booking status endpoint has no state-machine guard 🔴
- **Problem:** `update_booking_status` validates only the *target* status, never the *current* one. A completed/cancelled/no_show booking can be flipped back to confirmed → re-fires the review-prompt Telegram message and corrupts the no-show/analytics counts owners read. Bites week 1 on a fat-fingered dropdown.
- **Location:** `backend/app/routers/bookings.py:447-517`.
- **Fix (I do):** add an allowed-transitions map keyed on current status:
  - `pending → {confirmed, completed, no_show, cancelled_by_business}`
  - `confirmed → {completed, no_show, cancelled_by_business}`
  - terminal (`completed`, `cancelled_by_customer`, `cancelled_by_business`, `no_show`, `rescheduled`) → `{}` (blocked, 409)
  - `target == current` → idempotent no-op (return unchanged, **no** side effects re-fired).
  - Mirrors the guard `cancel_booking` already has (`bookings.py:533`).
- **Tests:** terminal→anything = 409; illegal jump = 409; idempotent same-status doesn't re-send review; legal forward transitions still fire their notifications once.

---

## DEPLOY B — "the daily embarrassments"

Things customers/owners hit in normal use.

### B5. Bot date picker uses UTC `date.today()` 🔴
- **Problem:** the only remaining naive date in the code. Between 00:00–05:00 Asia/Tashkent the "Today" button is actually yesterday → backend returns "no slots", and every day label is shifted by one.
- **Location:** `bot/handlers/booking.py:84` (`date_keyboard`).
- **Fix:** compute today from Tashkent wall time (`ZoneInfo("Asia/Tashkent")` / a `now_local()` helper mirrored from the backend).
- **Tests:** bot unit test that day-0 label maps to the Tashkent date at a simulated 23:00 UTC.

### B6. Staff-invite links leak customer PII 🔴
- **Problem:** invite links aren't bound to a person. Whoever opens a *forwarded* `t.me` link becomes that staff member and can read that provider's customers' names + phone numbers. Token is strong (256-bit, single-use) — the risk is link forwarding, not brute force.
- **Locations:** `backend/app/routers/staff.py:333` (`join_via_invite`), `backend/app/models/staff.py:52` (`StaffInvite`), `backend/app/routers/staff.py:387-419` (`get_my_bookings` returns `customer_phone`).
- **Fix:** bind the invite to an expected identity (owner supplies staff phone/telegram_id at invite creation; join verifies the redeemer matches), reject join if `staff.user_id` is already set, and one-time-invalidate on first successful redemption.
- **Tests:** mismatched identity → rejected; already-linked staff → rejected; correct identity → linked once.

### B7. Reminders double-send (no per-row claim) 🔴
- **Problem:** the "sent" flag commits only at the end of the whole sweep. Two instances (deploy overlap) → every reminder sent twice; a mid-sweep restart also re-sends. `broadcast_service.py:151` already has the claim pattern.
- **Location:** `backend/app/services/scheduler.py:168-173`.
- **Fix:** claim each row atomically before sending (`UPDATE ... SET reminder_Xh_sent=true WHERE id=:id AND reminder_Xh_sent=false RETURNING id`), send only claimed ids, reset flag on send failure. Optionally add a unique constraint on `Notification(booking_id, notification_type)`.
- **Tests:** a second concurrent sweep claims zero rows; a send failure leaves the flag re-settable.

### B8. Buffer/turnaround overlaps escape the DB constraint 🔴
- **Problem:** the `btree_gist` EXCLUDE ranges only raw appointment times; service buffers live only in the app check, which under READ COMMITTED can't see a concurrent insert. Two back-to-back bookings can both commit with zero turnaround gap. Only affects businesses with non-zero `buffer_before/after`.
- **Locations:** `backend/alembic/versions/0002_booking_constraints_indexes.py:24-37`, `backend/app/services/booking_engine.py:510-548`.
- **Fix:** serialize same-staff+date inserts with a Postgres advisory lock (`pg_advisory_xact_lock(hash(staff_id, date))`) around the overlap check so the app-level buffer check becomes authoritative; OR bake buffers into the EXCLUDE range. Advisory lock is the lower-risk change.
- **Tests:** two concurrent buffer-only-overlapping inserts → exactly one succeeds.

---

## DEPLOY C — "scale hardening"

Performance & robustness at volume. Not embarrassing at launch; bites as data/traffic grows.

- **C1. Availability fan-out.** `get_available_slots` does ~5 sequential DB round-trips *per staff*, and is re-run inside `create_booking`. Batch into set-based queries keyed by `staff_id IN (...)`; reuse the validated slot in create instead of recomputing. *(booking_engine.py:390-405, 483-508)* — biggest single perf win under Neon cold-start.
- **C2. Booking lists cap at 200 with no pagination.** Day view + dashboard pending list silently drop rows past 200. Add pagination / "load more" + a truncation indicator; bound the dashboard pending query with a date window. *(Bookings.jsx, Dashboard.jsx:77, bookings.py:312)*
- **C3. Rate limiter is in-memory + on only 9 endpoints.** Point slowapi at the existing Upstash Redis (`storage_uri`) so counts survive deploys; add limits to booking status/cancel + manual-booking. *(limiter.py:34)* — DoS-hardening, not a data-leak.
- **C4. `/admin/growth` full-table scan.** Replace the Python week-bucket loop with a SQL `date_trunc('week', created_at)` GROUP BY; guard the cache rebuild with an `asyncio.Lock`. *(admin.py:437)* — (header/rate-limit part folded into A1.)
- **C5. In-process handshake stores.** `web_login_store` + `location_share_store` are process-local dicts — a load-bearing reason the backend must stay single-instance (auth + location, not just the scheduler). Move both to Upstash Redis before ever scaling out. *(web_login_store.py:19, location_share_store.py:20)*
- **C6. N+1 in `list_staff` / `get_my_staff_profiles`.** Batch the per-staff `StaffService` query with a single `.in_()` (mirror `public.list_public_staff`). *(staff.py:100, 384)*
- **C7. `/public/businesses` no pagination / composite index.** Add limit/offset + a `(district, status)` / `(category_id, status)` index; keep the district filter enforced. *(public.py:62-86)*
- **C8. Public-booking phone not normalized.** Apply the same `_normalize_uz_phone` validator the manual path uses to `BookingCreatePublic.customer_phone`. *(bookings.py:72)*
- **C9. Money truncation.** `int(price)` floors the `Numeric(10,2)`; either enforce integer UZS at the `Service.price` validator or format with `Decimal` rounding. *(notification_service.py:121, booking.py:131,666)*
- **C10. Bot confirm has no in-flight guard.** Double-tap on a slow backend shows "slot taken (by yourself)". Disable the confirm keyboard before the API call; map the self-collision 409 to a friendly "already booked". *(bot/handlers/booking.py:704-739)*

---

## DEPLOY D — Polish backlog (low stakes, do when convenient)

- **D1.** Staff & Schedule unreachable from the mobile bottom nav — add a "More" overflow. *(Layout.jsx:14-22, 261-273)*
- **D2.** Booking modal (`Bookings.jsx:89-108`) + Settings (`Settings.jsx:23-49`) swallow load errors into an empty/blank UI — show an error + retry (mirror Analytics/Staff).
- **D3.** Analytics "Last 7 days" omits zero-booking days → sparse chart; zero-fill the 7 calendar days. *(Analytics.jsx:143-158, analytics.py:72-83)*
- **D4.** Untranslated `owner` i18n key renders raw on admin business detail — add `owner` to uz/ru/en. *(AdminBusinessDetail.jsx:157, i18n/index.js)*
- **D5.** Login reads `window.innerWidth` once (no resize handling) → wrong layout after rotate; drive via CSS media query. *(Login.jsx:176,217)*
- **D6.** Genuinely-free (0 UZS) booking stores `total_price_at_booking = NULL` (indistinguishable from unknown) — store the numeric sum. *(booking_engine.py:553-567)*
- **D7.** Manual-booking phone reuse merges two walk-ins under one Customer — match on (phone AND name) or don't overwrite the stored name. *(bookings.py:402-423)*
- **D8.** Unauthenticated reads of working-hours / breaks / staff roster are enumerable (incl. pending shops) — add status filter / owner guard. *(schedules.py:123,161,226, public.py:89)*
- **D9.** Explicit `staff_id` in availability isn't scoped to `business_id` (defense-in-depth). *(booking_engine.py:352)*
- **D10.** `_from_minutes` clamps to 23:59 instead of rejecting past-midnight math (latent). *(booking_engine.py:71-73)*
- **D11.** No Sentry/error-tracker or documented DB backups; `last_reminder_run` reseeds on every start (a fast crash-loop stays "healthy"). Track successful-sweep separately. *(main.py:18-22, scheduler.py:196)*
- **D12.** Admin business-detail shows no coordinates/map — no way to audit which businesses have valid pins. *(AdminBusinessDetail.jsx:103-106)*
- **D13.** Investor map depends on 3 third-party CDNs with no fallback for the map engine/basemap — self-host maplibre + basemap for demo resilience. *(QN_Investor/index.html:104, config.js:4)*

---

## Verified-solid (checked, no action needed)
Double-booking prevention · emoji/`&`/`<` escaping (bot + backend) · phone normalization on the main flow · backend timezone handling · analytics divide-by-zero guards · hot-path indexes · price snapshot at booking · `/health` (DB + scheduler heartbeat) · safe migrations · docs closed in prod · **multi-tenant isolation** (no cross-business data access via ID swapping).

---

## Progress tracker

### Deploy A
- [x] A1 — investor map secret: backend now rate-limits `/admin/growth` + accepts `X-Growth-Secret` header; QN_Investor site sends header not query. **OPS still needed (owner):** rotate `GROWTH_SECRET` in Railway + password-protect the investor host.
- [x] A2 — trial expiry job (`_expire_trials`, every 6h) + `POST /admin/businesses/{id}/record-payment` + approve-to-trial restarts the 14-day window
- [x] A3 — business-status gate in availability + public + manual booking (suspended/blocked rejected; pending stays bookable for owner testing)
- [x] A4 — booking status state-machine (terminal locked, same-status no-op, forward transitions only)
- [x] A — tests green (13 new, full suite 125 passed / 2 skipped)
- [ ] A — merged to main + deployed  ← **awaiting owner go-ahead (see trial-expiry warning + A1 ops steps)**

### Deploy B
- [x] B5 — bot date picker now computes "today" in Asia/Tashkent (fixed UTC+5, no tzdata dependency); no more dead "Today" button / shifted labels overnight
- [x] B6 — staff-invite hardening: can't invite or join an already-linked slot (409) or the owner slot (400); a new invite invalidates the prior one; expiry cut to 48h. (Bonus: made the `expires_at` check timezone-safe — was a latent naive/aware crash.) **Residual (noted):** a link forwarded before the intended staff redeems it can still claim an *unclaimed* slot — fully closing that needs a bot contact-share step (matched to `staff.phone`), deferred so we don't alter the bot join UX without your OK.
- [x] B7 — reminder sweep claims each row atomically before sending + commits per-booking; a repeat/overlapping sweep sends nothing (no duplicate reminders), and a mid-sweep crash can't roll back sent flags
- [x] B8 — advisory lock (`pg_advisory_xact_lock`) serializes same-staff+date inserts so buffer-only overlaps can't both commit (Postgres-only; no-op on SQLite)
- [x] B — tests green (7 new + tz-fix, full suite 132 passed / 2 skipped)
- [ ] B — merged to main + deployed  ← **awaiting owner go-ahead**

### Deploy C
- [ ] C1–C10 scale hardening
- [ ] C — tests green, merged, deployed

### Deploy D
- [ ] D1–D13 polish backlog
