# Qulay Navbat — Roadmap / Backlog

Things to tackle later. Newest ideas near the top of **Backlog**.

## 🔜 In progress
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
