# Qulay Navbat — Roadmap / Backlog

Things to tackle later. Newest ideas near the top of **Backlog**.

## ⚠️ Before launch — DO BEFORE 2026-07-20
- **Clear out test bookings.** During pre-launch, owners & staff can use the bot
  to try the full flow (see *Pre-launch gate* below). Every test booking is a
  **real row** with a real "new booking" ping to staff — harmless, but it piles
  up dummy data. **Right before July 20, wipe the test bookings** so launch starts
  clean. Nothing to build; just a cleanup pass.
  _(Claude: surface this reminder in any session as the date nears.)_

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
- **Neon pooler endpoint** — confirm `DATABASE_URL` uses Neon's `-pooler` host
  for cheaper, always-warm connections.
