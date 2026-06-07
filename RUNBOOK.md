# Rezerv — Operations Runbook

Short, practical procedures for running Rezerv in production. Stack: Neon
(Postgres), Upstash (Redis), Railway (backend + bot), Vercel (frontend).

---

## 1. Deploy

**Backend / Bot (Railway)** — push to `main`; Railway rebuilds from each service's
Dockerfile. The backend container runs `alembic upgrade head` then starts uvicorn
(see `backend/Dockerfile` / `backend/railway.toml`), so migrations apply on every
deploy. Health is checked at `/health` (verifies DB connectivity).

**Frontend (Vercel)** — push to `main`; Vercel runs `npm ci && npm run build`.
Before the first deploy, set the API rewrite target in `frontend/vercel.json`
(replace `https://your-backend.railway.app` with the real Railway URL).

**Required env vars** (Railway, both backend and bot share `.env` keys):
`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, `BOT_SECRET`,
`SUPER_ADMIN_TELEGRAM_IDS`, `ALLOWED_ORIGINS`, `ENVIRONMENT=production`.
The app **refuses to boot** in production if `SECRET_KEY`/`BOT_SECRET`/
`TELEGRAM_BOT_TOKEN`/`DATABASE_URL` are missing or weak (see `validate_runtime_config`).

**First-run seed:** `python -m scripts.seed_categories` (business categories).

---

## 2. Roll back

- **Railway:** Deployments tab → pick the previous green deploy → "Redeploy".
- **Migrations:** if a deploy shipped a bad migration, roll the *code* back first,
  then if the schema must be reverted: `alembic downgrade -1` (every migration here
  has a tested `downgrade()`). Never downgrade across a destructive change without a
  backup (step 4).
- **Frontend (Vercel):** Deployments → previous build → "Promote to Production".

---

## 3. Rotate a secret

1. Generate a new value: `python -c "import secrets; print(secrets.token_hex(32))"`.
2. Update it in Railway (backend **and** bot for `BOT_SECRET` — they must match).
3. Redeploy both services.
4. **Telegram bot token:** revoke in BotFather (`/revoke`), set the new
   `TELEGRAM_BOT_TOKEN` in Railway, redeploy. (Rotating `SECRET_KEY` invalidates all
   existing JWTs — users simply re-open the Mini App to get fresh tokens.)

---

## 4. Backups & restore

- **Backups:** Neon keeps automatic point-in-time backups (history retention is set
  per project — verify it is enabled in the Neon console > Project > Settings).
- **Restore test (do this once before launch, then quarterly):**
  1. Neon console → Branches → create a branch from a past point in time.
  2. Point a throwaway backend at the branch's `DATABASE_URL`.
  3. Confirm `/health` is `ok` and a known business + bookings are present.
  4. Delete the test branch.
- **Manual dump (extra safety):** `pg_dump "$DATABASE_URL" > backup.sql`.

---

## 5. Common incidents

| Symptom | Check |
|---|---|
| 503 from `/health` | DB unreachable — Neon status, `DATABASE_URL`, connection limits. |
| All logins fail | `TELEGRAM_BOT_TOKEN` correct? initData clock skew? `SECRET_KEY` changed? |
| "Invalid bot secret" on bookings | `BOT_SECRET` mismatch between bot and backend. |
| Reminders at wrong time | Confirm server clock is UTC; booking times are Asia/Tashkent (see `app/timeutils.py`). |
| 500s | Logs include a `request_id`; grep server logs for it (clients never see stack traces). |

---

## 6. Useful commands

```bash
# Run the test suite (incl. Postgres concurrency test if TEST_DATABASE_URL is set)
cd backend && pytest -q

# Apply / inspect migrations
alembic upgrade head
alembic history
alembic downgrade -1

# Regenerate PWA icons after changing the SVG
cd frontend && node scripts/generate-icons.js
```
