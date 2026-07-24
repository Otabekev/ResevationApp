# Qulay Navbat — Roadmap / Backlog

Things to tackle later. Newest ideas near the top of **Backlog**.

## ⚠️ Before launch — DO BEFORE 2026-07-20
- **Clear out test bookings.** During pre-launch, owners & staff can use the bot
  to try the full flow (see *Pre-launch gate* below). Every test booking is a
  **real row** with a real "new booking" ping to staff — harmless, but it piles
  up dummy data. **Right before July 20, wipe the test bookings** so launch starts
  clean. Nothing to build; just a cleanup pass.
  _(Claude: surface this reminder in any session as the date nears.)_
- **Move Upstash Redis to a paid tier.** The bot's FSM state lives in Upstash, and
  every tap reads/writes it. The free tier's daily command cap (~10k/day) gets
  eaten by a few hundred *active* daily users — long before our 15k user target —
  and a maxed-out Redis means **frozen buttons**, the worst possible launch look.
  It's a cheap (~$10/mo) tier bump, not a rewrite. Do it before the launch push.
  _(Claude: surface this with the test-bookings reminder as the date nears.)_
- **Stay on ONE backend instance.** The scheduler, booking reminders, and the
  broadcast poller all assume a single process — running two Railway instances
  would double-fire reminders/broadcasts. One instance comfortably serves 15k
  users; making it multi-instance-safe is a *post-launch / proper-dev* task (see
  *Deferred performance / infra*). Until then: keep the backend at 1 instance.

### Security hardening (from the 8-tip audit — fix A shipped; B + D queued here)
- **B — Rate-limit the broadcast + secret endpoints.** `POST /admin/broadcast` and
  `/admin/broadcast/test` fan out Telegram sends with NO rate limit (the
  "unexpected bills" vector); `/admin/growth` is secret-gated by a query param with
  no limit (brute-forceable). Add `@limiter.limit` (e.g. broadcast 5/min, test
  10/min, growth 10/min). Super-admin-only today, so do it before broadcasting to a
  real audience.
- **D — Active crash monitoring (Sentry) + uptime ping.** Logs exist but nothing
  *alerts* you on a crash. Add `sentry-sdk[fastapi]` to backend AND bot, gated on a
  `SENTRY_DSN` env var (no-op in dev/tests), `send_default_pii=False`, capture
  scheduler/broadcast job failures too; point a free uptime monitor (UptimeRobot)
  at `/health`. ~30 min + 2 free accounts. Turn on before the soft launch so the
  first real crash reaches you, not a customer.
- _(Optional, low severity — C):_ three schedule-read GETs in `schedules.py`
  (get_business_hours/get_staff_hours/get_breaks) have no auth (leak working hours);
  and `admin.py` growth_map compares its secret with `!=` not `hmac.compare_digest`.
  Bundle whenever convenient.

## 🔜 In progress
- **Pre-launch gate** — until 2026-07-20 the bot's customer booking flow is gated:
  business **owners & staff pass through and can test freely**; everyone else sees
  a "we open July 20th" message. Auto-opens on the launch date (date-based, no
  redeploy). Web dashboard stays fully open so owners can set up.
- **Investor growth map** (separate `QN_Investor` project) — interactive map of
  Uzbekistan with a week-by-week growth timeline. Phase 1 (real data feed via
  `GET /admin/growth`) is wired up.

## 🚀 Launch & growth tactics

### Soft-launch dinner (launch day)
A free dinner for **20 restaurant owners** on launch day — show the app, let them
play with it, win them over in person.

- **Goal: 10 of the 20 sign up by the end of the night** (50% conversion).
- Show the app live, then let them **play with it hands-on** at the table.
- **Onboard on the spot** — help each interested owner set up their business +
  first service + working hours right there, so they leave already live.
- **A reason to act tonight** — a launch-night perk (extended free trial,
  featured placement, "founding business" badge) so they sign up now, not "later."
- Prep: confirmed guest list of 20, venue + dinner, a tight 5-min demo, a couple
  of helpers for on-the-spot onboarding, and printed copies of the sales guide.

## 📋 Backlog — tackle later

### Reduce churn: let us schedule calls with business owners
**Why:** the single biggest lever against churn is *talking to owners* —
onboarding check-ins, "how's it going," catching problems before they leave.
Today there's no streamlined way; arranging a call is manual back-and-forth.

**What we want:** a "request a call" flow —
1. We (the team) flag a business owner for a call.
2. The owner picks a time slot from a calendar (their availability).
3. We call them at that time. No phone tag.

**Possible approaches:**
- **Dogfood our own booking engine** *(cleanest, on-brand)* — treat "QN Support"
  as a provider; the owner books a call slot through our own bot/app. Reuses
  everything we already built (slots, reminders, no-double-book).
- **In-dashboard "Book a call"** — a banner/button in the owner dashboard → owner
  picks a slot → the call lands in a team view, with a reminder.
- **Stopgap:** a Calendly-style external link from the dashboard while the native
  version is built.

**Payoff:** retention. Reaching owners early is what stops churn.

### Broadcast tool — later upgrades
The super-admin broadcast (now/scheduled; everyone / owners+staff / customers)
ships v1 as a background sender with delivery counters. Revisit when volume grows:
- **Resumable outbox** — per-recipient rows so a mid-send restart resumes, instead
  of relying on one background task (fine while sends are hundreds, not thousands).
- **Customer opt-out** — a way for customers to stop marketing messages (Telegram
  can ban a bot if mass messages get reported). Owner/staff + launch news is fine;
  add opt-out before frequent customer promos.
- **Per-language variants** — currently one message for all; add uz/ru/en versions
  delivered by each user's language if customer marketing needs it.

### Investor growth map — later phases
- **Phase 2:** growth-curve chart + bookings traction (total + per week) +
  momentum % (week-over-week) + retention (active vs churned).
- **Phase 3:** cinematic polish — auto-play intro, pins pulse on join, count-up
  numbers, milestone markers on the timeline.
- **Phase 4:** deploy behind a password + custom URL + record the animation as a
  GIF/video for the pitch deck.

### Deferred performance / infra
- **Bot ↔ backend private networking** — move off the public `.up.railway.app`
  edge (failed once on Railway's healthcheck; revisit as its own carefully-
  verified task). ~80–200ms per call.
- **Availability endpoint batching** — the booking-engine availability query
  does per-staff round-trips (N+1); batch them. Measure after the SQL-echo fix
  before investing.
- **Neon idle-suspend latency (the "schedule save felt slow" cause).** Neon's free
  tier suspends compute after ~5 min idle; the first request after the owner has
  been editing for a while eats the wake (a few seconds). The *failure* half (save
  not landing → "try a few times") is fixed in code now (idempotent setup writes
  auto-retry through blips — `client.js`). The *latency* half is operational:
  **disable Neon scale-to-zero (always-on compute, paid)** and confirm
  `DATABASE_URL` uses Neon's `-pooler` host for warm connections. Do before launch
  so onboarding feels instant.
- **Multi-instance-safe scheduler** *(proper-dev task, enables horizontal scale)* —
  today the scheduler / reminders / broadcast poller assume a single backend
  process; two instances would double-fire them. Add a DB lock or move these to a
  dedicated worker so the API can scale out past one instance. Not needed until
  well beyond 15k users — but it's the gate to horizontal scaling.
- **Resumable broadcast outbox** — see *Broadcast tool → later upgrades* above;
  per-recipient rows so a mid-send restart resumes instead of truncating.
