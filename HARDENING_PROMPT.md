# Rezerv — Master Hardening Prompt for Claude Code

> Paste everything below the line into Claude Code, run from the repo root.
> It is one prompt. It turns the current vibe-coded build into a production-grade,
> secure, scalable system without adding features you don't need for 50 businesses.

---

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
