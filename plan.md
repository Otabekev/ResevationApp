# Rezerv — Reservation App Plan

> This is the full product plan, transcribed word-for-word from `Reservation App Plan.pdf`.
> The hardening prompt for Claude Code is appended at the end of this file.

---

## PROJECT CHECKLIST

> Update this as you go. Legend: ✅ done & verified · 🟡 built (code exists, NOT yet verified or hardened) · ⬜ not started
> Last updated: 2026-06-30
>
> **⚠️ STATUS UPDATE (2026-06-30):** The Phase 2 hardening pass below was **completed on 2026-06-08** (commit `e4d1e09`) and is **test-proven** — the backend suite runs **`91 passed, 1 skipped`** locally and the full suite (incl. the Postgres double-booking concurrency test) is **green in CI**. See **[CHANGELOG_HARDENING.md](CHANGELOG_HARDENING.md)** for the fix-by-fix mapping to every `AUDIT.md` finding. The per-line ⬜/🟡 marks in this checklist were simply never updated after the fixes landed — the ✅ marks below now reflect reality. The only genuinely-unbuilt audit item is **A7 (Postgres RLS)**, which is defense-in-depth on top of already-proven app-level tenant isolation, not a launch blocker.

### Phase 1 — Core build (MVP features)

- [x] ✅ Backend scaffolding (FastAPI, async SQLAlchemy, Alembic, config, deps)
- [x] ✅ Database models (users, businesses, services, staff, schedule, bookings, subscriptions)
- [x] ✅ Auth (JWT, password hashing, Telegram initData validation) — hardened + tested (17 auth tests)
- [x] ✅ Smart booking engine (`booking_engine.py`) + availability endpoint — hardened + tested (14 booking tests)
- [x] ✅ Routers: auth, businesses, services, staff, schedules, availability, bookings, reviews, analytics, admin, public
- [x] ✅ Notifications service + APScheduler (reminders)
- [x] ✅ Telegram bot (aiogram): start, booking, my_bookings handlers
- [x] ✅ Bot i18n: Uzbek / Russian / English locale files
- [x] ✅ Frontend pages: Login, Dashboard, BusinessSetup, Services, Staff, Schedule, Bookings, Analytics, Settings, AdminPanel
- [x] ✅ Frontend PWA setup (Vite, Zustand, router, API client)
- [x] ✅ Deploy config (Docker, docker-compose, Railway, Vercel, Neon, Upstash) — live in production
- [x] ✅ End-to-end booking flow live in production (customer → bot → DB → owner notification)
- [x] ✅ Pilot business live (Pop / Namangan); growth feed reads real bookings

### Phase 2 — Hardening (run the prompt at the end of this file)

- [x] ✅ Pre-step: `pytest`/`pytest-asyncio`/`aiosqlite` added (`requirements-dev.txt`); CSS design-token system chosen over Tailwind
- [x] ✅ Written AUDIT produced and reviewed ([AUDIT.md](AUDIT.md)), then fixed ([CHANGELOG_HARDENING.md](CHANGELOG_HARDENING.md))
- [x] ✅ **A. Multi-tenant isolation & authorization** — IDOR fixes done + 12 tests. (A7 Postgres RLS = the one deferred item, defense-in-depth.)
- [x] ✅ **B. Auth & Telegram initData** — server-side HMAC, replay window, fail-closed on empty secrets; 17 tests
- [x] ✅ **C. Secrets & config** — repo scanned clean, migrations un-ignored, fail-fast env validation at startup
- [x] ✅ **D. Double-booking** — `btree_gist` EXCLUDE constraint + app-level overlap check + tz handling; concurrency test green in CI
- [x] ✅ **E. Performance & scale** — composite indexes, N+1 batch-load, pagination. (Redis cache deferred — not needed at current scale.)
- [x] ✅ **F. Input validation & injection** — strict Pydantic constraints, no raw SQL, bot HTML escaping
- [x] ✅ **G. Error handling, logging & observability** — global handler + request id, React error boundary, DB-checking `/health`. (Sentry deferred.)
- [x] ✅ **H. Rate limiting & abuse** — single shared limiter, per-user/per-tenant keying, public booking/review bot-secret-gated
- [x] ✅ **I. Distinctive UI** — full design-token system, teal-on-paper rebrand, Manrope, micro-interactions, ≥44px targets
- [x] ✅ **J. Testing** — 91-test suite across A/B/D/E/F/G/H + GitHub Actions CI (runs the Postgres concurrency test)
- [x] ✅ **K. Ops & data safety** — reversible migrations, Neon backups, security headers, locked CORS, [RUNBOOK.md](RUNBOOK.md)

### Phase 3 — Launch readiness (first paying businesses)

- [ ] ⬜ Subscription / trial / payment flow working (plan tracks "payments later")
- [ ] ⬜ Super-admin dashboard verified (businesses, status, analytics by town)
- [ ] ⬜ Onboarding flow smooth enough for a non-technical owner
- [ ] ⬜ Backups verified with a real restore test
- [ ] ⬜ Production deploy on real domain + HTTPS
- [ ] ⬜ Pilot with first 1–3 businesses, collect feedback
- [ ] ⬜ Reach 50 paying businesses 🎯

---

## Overview

We are building a Telegram-based appointment/booking management platform for local service businesses in Uzbekistan.

**IMPORTANT:**
This is NOT just a barber reservation bot.
This should become a universal appointment infrastructure for one town first, then expand town by town.

**Current direction:**
so business is manages from app, and customers use telegram bot/miniapp to make reservations, it is for uzbkistan, and I need uzb, eng, Russian languages.

- Customers book through Telegram bot / Telegram Mini App.
- Business owners manage their business from app that works both in android and iphone from admin panel.
- Staff can manage their own schedule/bookings.
- Platform admin manages all businesses, users, plans, and system settings.

**Goal:**
Create a full product plan and architecture for a smart booking system that can work for many business types: barbershops, beauty salons, nail studios, dentists, clinics, football fields, and other appointment-based businesses. Maybe we can create a category for businesses and if some other business wants to register, they can pick their catarory and fit out easaily.

**MAIN PROBLEM:**
Different businesses have different scheduling logic.
Barbers may use simple 30–60 min slots.
Dentists may have services with different durations: consultation 20 min, cleaning 45 min, filling 60 min, root canal 120 min.
Spas may need staff + room + equipment.
Tutors may need recurring lessons.
Clinics may need doctor-specific schedules and appointment types.

I need you to help design a universal smart booking engine. Maybe each business can add their own cervise and time one by one, and smart booking logic hands the rest.

---

## ROLES

### 1. Platform Admin / Super Admin

This is me, the platform owner.

**Functions:**

- View all registered businesses
- Add/edit/delete businesses
- Approve or suspend businesses
- See business status: active, trial, paid, unpaid, blocked
- See total bookings across platform
- See active users/customers
- See active staff
- See failed bookings or errors
- Manage business categories/templates
- Manage Telegram bot settings
- Manage system-wide notifications
- Manage support tickets/issues
- See analytics by town/city
- Track which town is growing fastest
- Export business/customer data
- Manually extend trial
- View logs for debugging
- Manage announcements to all businesses
- Manage multi-language content: Uzbek, Russian, English

### 2. Business Owner / Manager

This is the owner of a barbershop, clinic, salon, etc.

**Functions:**

- Register business
- Set business name
- Set business category/type
- Set location/address
- Set phone number
- Set Telegram username/contact
- Set Instagram link
- Set business working days/hours
- Add breaks/lunch time
- Add holidays/closed days
- Add services
- Set service duration
- Set service price
- Set service buffer time
- Set service description
- Enable/disable services
- Add staff members
- Invite staff through link
- Approve/remove staff
- Assign services to staff
- Set staff working hours
- Override staff schedule
- View all bookings
- Create manual booking
- Cancel booking
- Reschedule booking
- Mark customer arrived
- Mark no-show
- View customer history
- View daily/weekly/monthly calendar
- See today's appointments
- Receive booking notifications
- Receive cancellation notifications
- Receive reminder before appointment
- Set cancellation rules
- Set minimum advance booking time
- Set maximum future booking window
- View basic analytics:
  - bookings per day
  - no-shows
  - busiest services
  - busiest staff
  - repeat customers
- Generate booking link for Instagram bio
- Share booking link
- Manage business profile shown to customers
- Turn online booking on/off
- Block private time
- Add emergency closure
- Set custom message for customers
- Set language preference

### 3. Staff Member

This is barber, dentist, nail master, doctor, massage therapist, tutor, etc.

**Functions:**

- Join business through invite link
- Accept/decline staff invitation
- View own schedule
- View own bookings
- Receive notification for new booking
- Receive notification for cancellation
- Receive daily appointment summary
- Mark appointment completed
- Mark customer no-show
- Block personal unavailable time
- Set own working hours if allowed by owner
- See customer name/contact for their own bookings
- See service type and duration
- See notes from customer
- Confirm booking if manual approval is needed
- Request reschedule
- Contact customer through Telegram if needed
- View own performance:
  - number of bookings
  - completed appointments
  - no-shows
  - most booked services

### 4. Customer

This is the person booking an appointment.

**Functions:**

- Open business booking link
- Choose language
- See business info
- See address/location
- See available services
- See service price/duration
- Choose service
- Choose staff member or "any available staff"
- Choose date
- See available time slots
- Book appointment
- Confirm appointment
- Receive confirmation message
- Receive reminder before appointment
- Cancel appointment
- Reschedule appointment
- See own upcoming bookings
- See past bookings
- Leave review/rating
- Rebook same service
- Get directions/location
- Contact business
- Receive business announcements/promos if allowed

---

## SMART BOOKING ENGINE REQUIREMENTS

**Core logic:**

- Do not create only fixed barber-style slots.
- Build service-duration-based booking.
- Each service has duration_minutes.
- Each service can have buffer_before and buffer_after.
- Each staff member can perform specific services.
- Each staff member has working hours.
- Each staff member can have breaks, holidays, blocked time.
- Existing bookings block availability.
- System dynamically calculates available slots.

**Availability calculation:**

Given:

- business_id
- service_id
- optional staff_id
- date

System should:

1. Get service duration + buffers
2. Find staff who can perform that service
3. Get staff working hours for that date
4. Remove breaks/blocked times/existing bookings
5. Generate valid start times where full service duration fits
6. Return available times to customer

**Important:**

- Support "choose specific staff"
- Support "any available staff"
- Prevent double-booking
- Use database transactions/locking when confirming bookings
- Handle timezone correctly

---

## Business Type Templates

### 1. Barbershop

- Staff-based
- Customer chooses barber
- Main features: reminders, no-show reduction, Instagram booking link

### 2. Beauty Salon

- Staff-based
- Many services
- Different durations
- Customer may choose master
- Some services may require longer buffers

### 3. Nail Studio

- Staff-based
- Important: duration and staff skill matching

### 4. Dentist / Clinic

- Provider-based
- Appointment types with different durations
- Doctor-specific schedules
- Some bookings may require manual confirmation
- Some services should be "consultation first" only
- Patient notes needed
- Later: medical privacy/security considerations
- Group classes later
- Student history

---

## DATABASE ENTITIES TO CONSIDER

- users
- businesses
- business_categories
- business_settings
- staff
- staff_invites
- services
- staff_services
- working_hours
- breaks
- blocked_times
- bookings
- booking_statuses
- customers
- customer_notes
- reviews
- notifications
- subscriptions
- payments later
- audit_logs

---

## BOOKING STATUSES

- pending
- confirmed
- completed
- cancelled_by_customer
- cancelled_by_business
- no_show
- rescheduled

---

## KEY PRODUCT PRINCIPLE

The platform must be simple enough for small-town businesses.
Do not overbuild enterprise features first.
Build one universal scheduling engine with business templates on top.

---

## TASK

Create a full product plan with:

1. Role-based feature list
2. Smart booking engine logic
3. Database schema recommendation
4. API endpoint structure
5. Telegram bot flow
6. Business owner admin flow
7. Staff flow
8. Customer flow
9. Business templates by industry
10. MVP version
11. Version 2 roadmap
12. Risks and edge cases
13. Recommended implementation order

Also explain how to avoid double-booking and how to handle services with different durations.

---
---

# APPENDIX — Master Hardening Prompt for Claude Code

> Paste everything below into Claude Code, run from the repo root.
> It is one prompt. It turns the current vibe-coded build into a production-grade,
> secure, scalable system without adding features you don't need for 50 businesses.

## ROLE

You are a staff-level engineer (security + backend + frontend) doing a production-readiness
hardening pass on an existing codebase. You are NOT adding new features. You are closing the
gap between "demo that works" and "SaaS that 50 paying businesses trust with their bookings
and customer data." Correctness, security, and data isolation outrank speed and cleverness.

## PROJECT CONTEXT (read before touching anything)

- **Product:** "Rezerv" — a multi-tenant appointment/booking platform for local service
  businesses in Uzbekistan (barbershops, salons, nail studios, dentists, clinics, sports fields).
- **Architecture:**
  - Backend: FastAPI (async), SQLAlchemy 2.0 async, Alembic, Pydantic v2, slowapi, JWT (python-jose), passlib/bcrypt.
  - DB: PostgreSQL (Neon). Cache/queue: Redis (Upstash). Scheduler: APScheduler.
  - Bot: aiogram Telegram bot + Telegram Mini App (initData auth).
  - Frontend: React 18 + Vite PWA, Zustand, React Router, Axios, dayjs.
  - Deploy: Railway (backend+bot), Vercel (frontend), later Hetzner VPS + docker-compose.
- **Tenancy model:** every business is a tenant. Owners, staff, services, schedules, bookings,
  customers, reviews all belong to a `business_id`. A user must NEVER see or mutate another
  business's data. This is the single most important invariant in the system.
- **Languages:** UI and bot must work in Uzbek, Russian, English.
- **Scope discipline:** the goal is 50 paying businesses, then scale. Do NOT build enterprise
  features, microservices, multi-region, or speculative abstractions. Make the existing scope
  flawless. If you're tempted to add a feature, stop and instead make what exists bulletproof.

## HOW YOU MUST WORK (non-negotiable process)

1. **Audit before editing.** First produce a written audit: read the code and list every concrete
   issue you find, grouped by the categories below, each with file:line, severity
   (Critical / High / Medium / Low), and a one-line fix. Do not edit yet. Show me the audit.
2. **Plan, then small commits.** After I approve, fix in small, isolated commits — one concern per
   commit, each with a clear message. Each commit must leave the app runnable.
3. **Separate the fixing from the verifying.** After implementing a category, switch hats and
   adversarially try to break it (write a failing test that proves the vulnerability existed, then
   show it passing after the fix). Do not mark anything done on vibes.
4. **No secrets, ever, in code or logs.** If you find one, rotate-by-removing it from code, move it
   to env, and tell me which credential to regenerate.
5. **Don't break the three languages.** Any user-facing string you touch must exist in uz/ru/en.
6. **Ask before destructive changes** (schema drops, data migrations, auth model changes).
7. **Output a CHANGELOG** mapping every fix to the issue it closes.

---

## THE HARDENING WORK (by category, in priority order)

### A. Multi-tenant isolation & authorization — TREAT AS CRITICAL
This is where vibe-coded SaaS leaks customer data. The pattern: an endpoint fetches a row by id
(`/bookings/{id}`) and returns/edits it without checking it belongs to the caller's business — a
classic IDOR. Real 2025–26 breaches (Moltbook, the Tea app, 170+ Lovable apps) were exactly this:
endpoints returning data without an ownership check, or DBs with no row-level security.

Do this:
- Audit **every** router endpoint. For each one, confirm the query is scoped by the authenticated
  user's `business_id` (and role), not just by primary key. Any `get(id)` that doesn't also filter
  by tenant is a bug. Fix all of them.
- Introduce a single enforced choke point: a FastAPI dependency that resolves
  `current_user -> business_id -> role`, and tenant-scoped query helpers so a developer cannot
  forget the filter. Never read `business_id` from the request body or query string for scoping —
  derive it server-side from the token.
- Add **PostgreSQL Row-Level Security** as defense-in-depth on every tenant-owned table, with the
  tenant id set per-connection/transaction. App code still filters by tenant; RLS is the net that
  catches any missed filter. Verify it actually engages (test that a wrong-tenant query returns 0 rows).
- Enforce role checks (super-admin vs owner vs staff vs customer) at the API layer, not the UI.
  Staff can only see their own bookings; owners only their business; super-admin gated by an
  allow-list of Telegram IDs, not a client flag.
- Make sure tenant scoping also applies to: Redis cache keys, background/scheduler jobs,
  notification sending, analytics queries, and any export endpoint.
- Watch for the async footgun: never store `business_id`/tenant context in a module-level global or
  poorly-scoped singleton — under concurrency that bleeds identity between requests. Keep it in
  request scope (dependency / contextvar).

**Acceptance:** for every tenant-owned resource there is an automated test proving that user from
business B gets 403/404 (never data) when accessing business A's object id.

### B. Authentication & Telegram initData
- **initData must be validated server-side, every request, with HMAC-SHA256** against the bot token
  (secret key = HMAC-SHA256 of bot token with constant `WebAppData`), rebuilding the data-check-string
  by sorting fields alphabetically and joining with `\n`. Reject if hash mismatches.
- **Enforce an `auth_date` freshness window** (e.g. reject initData older than ~1 hour) to stop replay
  attacks. Use constant-time comparison (`hmac.compare_digest`) — never `==` on the hash.
- Confirm there is no dev bypass (`VITE_DEV_BYPASS_TELEGRAM`, etc.) reachable in production. Gate any
  bypass behind an explicit non-production env check and fail closed.
- JWT: verify expiry, signature, and `type` (access vs refresh) on every protected route; short access
  token lifetime + refresh rotation; reject refresh tokens used as access tokens. Ensure `SECRET_KEY`
  is strong and env-sourced, and the app refuses to boot with a default/empty secret in production.
- Passwords: bcrypt (already present) — confirm no plaintext logging, enforce a minimum strength.

**Acceptance:** a forged initData string and an expired one are both rejected by a test; protected
routes 401 without a valid token.

### C. Secrets & configuration
- Scan the whole repo (incl. `.env.example`, Docker files, frontend bundle, CI config, README,
  migration files) for any real secret, token, connection string, or key. AI-built apps leak secrets
  at ~2x the normal rate — assume something is exposed until proven otherwise.
- Nothing secret in frontend code or the built bundle (anything in `VITE_*` ships to the browser —
  only public values belong there).
- Confirm `.gitignore` covers `.env`; verify git history isn't carrying a committed secret (if it is,
  tell me — I'll rotate).
- App should validate required env vars at startup and fail fast with a clear message if missing.

### D. Booking concurrency — no double-booking, ever
The smart-booking engine is the heart of the product; a race that double-books a slot is a
trust-killer. App-level "check then insert" is not safe under concurrency.
- Make double-booking **structurally impossible at the database level**, not just in app logic. Two
  proven options for Postgres — implement one and back it with the other where it fits:
  - **`SELECT ... FOR UPDATE`** to lock the relevant staff/slot rows inside the booking transaction
    before checking availability and inserting (lock rows in a consistent order, e.g. `ORDER BY id`,
    to avoid deadlocks; consider `NOWAIT`/`SKIP LOCKED` semantics deliberately).
  - **A Postgres `EXCLUSION` constraint (GiST, `btree_gist`)** on `(staff_id, tstzrange(start, end))`
    so overlapping bookings for the same staff are rejected by the DB declaratively — the strongest net.
- All of this runs inside one transaction with correct isolation; on conflict, return a clean
  "slot just taken" response, not a 500.
- **Timezones:** store timestamps as UTC (`timestamptz`), do all availability math in the business's
  local timezone (Asia/Tashkent), render localized. Audit for naive `datetime` usage.
- Respect service `duration_minutes`, `buffer_before/after`, staff working hours, breaks, blocked
  times, holidays, min-advance and max-future windows in slot generation — and in the final
  server-side validation at confirm time (never trust the slot the client sends).

**Acceptance:** a concurrency test that fires N simultaneous requests for the same slot results in
exactly one booking; all others get a clean rejection.

### E. Performance & scalability (for real data, not 5 test rows)
Vibe-coded apps pass with 5 rows and collapse at 50,000. Fix the usual suspects:
- **N+1 queries:** audit list endpoints (bookings, services, staff, analytics). Use eager loading
  (`selectinload`/`joinedload`) or explicit joins. No query-in-a-loop.
- **Indexes:** add indexes on every column used in WHERE / JOIN / ORDER BY — at minimum
  `business_id`, `staff_id`, `service_id`, booking `start_time`, `status`, and all FKs. Composite
  indexes for the hot availability query (e.g. `(staff_id, start_time)`). Deliver these as Alembic
  migrations.
- **Pagination everywhere** a list can grow (bookings, customers, analytics). No unbounded `SELECT *`.
- **Caching:** cache cheap-to-stale, expensive-to-compute reads in Redis with tenant-scoped keys and
  sane TTLs (e.g. business profile, service list, category templates). Invalidate on write. Do NOT
  cache availability in a way that can serve a stale "free" slot.
- **Connection pooling** sized for Neon/Upstash limits; async DB calls never block the event loop.
- Keep it proportionate — 50 businesses don't need sharding. Just remove the cliffs.

**Acceptance:** seed ~50k bookings and show the main list + availability endpoints stay fast
(measure, report query counts and timings before/after).

### F. Input validation & injection
- Strict Pydantic schemas on every endpoint (types, ranges, string lengths, enums for status/role).
  Reject unknown fields. Validate phone, language code, URLs (Instagram/Telegram links).
- Use SQLAlchemy parameterized queries only — no string-built SQL. Audit for any raw SQL/f-strings.
- Sanitize/escape any user content rendered in the bot, the admin UI, and notifications (prevent
  stored XSS in business name, service description, customer notes, reviews).
- Validate file/image uploads if any (type, size).

### G. Error handling, logging & observability
- Backend: a global exception handler that returns clean JSON errors (no stack traces, no SQL, no
  internal paths to clients) while logging full detail server-side with request id + tenant id.
- Frontend: a React **error boundary** so a render error shows a friendly localized message, not a
  white screen.
- All external calls (Telegram API, DB, Redis, notifications) wrapped with timeouts and graceful
  failure + retry where safe. A failed reminder must not crash the scheduler.
- Structured logging with levels; log auth failures, authorization denials, booking conflicts, and
  scheduler errors. Add a `/health` endpoint. Wire one lightweight error tracker (e.g. Sentry) —
  free tier is fine. No secrets or PII (customer phones) in logs.

### H. Rate limiting & abuse
- slowapi is present — confirm it's actually applied to sensitive endpoints (auth, booking create,
  public booking link, review submit), and make limits **per-tenant / per-user**, not only per-IP
  (many Uzbek users share NAT/mobile IPs, so pure IP limits both over- and under-block).
- Protect the public booking link from spam bookings (e.g. require valid Telegram identity, throttle
  per customer). Add basic guard against no-show/spam booking floods.

### I. Make the UI NOT look like every other AI app
AI defaults to the most generic, average-looking UI — that's why vibe-coded apps are visually
interchangeable. Fix it deliberately:
- **Design from a feeling and an audience first.** This is for busy small-business owners in Uzbek
  towns on mid-range Android phones, often on slow connections, who are not tech people. The feeling:
  fast, calm, trustworthy, effortless — "this respects my time." Every UI decision serves that.
- **Build a real design system / token layer** (colors, type scale, spacing, radius, shadows,
  motion) and use it everywhere — not ad-hoc Tailwind classes per component. One source of truth so
  the app feels coherent and ownable.
- **Pick a distinctive but restrained brand identity:** a real primary color (not default indigo/blue),
  a typeface with character, consistent iconography, generous spacing. Avoid the stock
  "purple gradient SaaS" look.
- **Micro-interactions, restrained:** 100–300ms purposeful transitions, loading skeletons, success
  states, optimistic UI on booking actions. No gratuitous animation.
- **Mobile-first and PWA-real:** test on a small, slow Android profile; offline-friendly shell,
  installable, fast first paint. The booking flow must be thumb-reachable and 3-taps-or-fewer.
- **Accessibility & i18n:** real contrast, focus states, tap targets ≥44px, and layouts that don't
  break when Russian/Uzbek strings are longer than English. Right-pad nothing with hardcoded widths.
- Keep it simple and consistent over flashy — the goal is that an owner trusts it in 5 seconds.

### J. Testing (the part vibe coding skips)
- Add automated tests for the **critical flows**: auth (incl. forged/expired initData), tenant
  isolation (the IDOR matrix), booking creation + double-booking concurrency, availability
  calculation edge cases, cancellation/reschedule/no-show transitions, role permissions.
- A minimal CI pipeline (GitHub Actions) that runs lint + tests on every push and blocks merge on red.
- Don't chase 100% coverage — cover the flows where a bug loses money or leaks data.

### K. Ops, data safety & deploy
- Confirm DB migrations are clean and reversible; no destructive migration without a backup step.
- Verify **automated Postgres backups** are on (Neon) and document a restore test.
- CORS locked to the real frontend origin(s), not `*`. Security headers (HSTS, X-Content-Type-Options,
  etc.) and HTTPS enforced.
- Disable interactive API docs (`/docs`, `/redoc`) in production (already conditional — verify).
- A short runbook: how to deploy, roll back, rotate a secret, restore a backup.

---

## EXECUTION ORDER
1. Audit (all categories, written, no edits) → show me.
2. A (tenant isolation) → B (auth/initData) → C (secrets). These are the data-breach risks; do first.
3. D (double-booking) → F (input validation) → H (rate limiting).
4. E (performance/indexes) → G (errors/logging) → J (tests) → K (ops).
5. I (UI distinctiveness) can proceed in parallel since it's frontend-isolated.

## DELIVERABLES
- `AUDIT.md` — every issue found, severity, file:line, fix.
- The fixes as small reviewed commits, each leaving the app runnable.
- New Alembic migrations for indexes + RLS + exclusion constraint.
- A test suite covering the critical flows + a CI workflow.
- `CHANGELOG_HARDENING.md` — fix ↔ issue mapping.
- `RUNBOOK.md` — deploy/rollback/secret-rotation/restore.

## FINAL RULE
Before you say "done" on any category, you must show the failing test that proved the problem and
the same test passing after the fix. Working-in-the-demo is not done. Done is provable.

**START NOW with the AUDIT only. Do not edit code until I approve the audit.**
