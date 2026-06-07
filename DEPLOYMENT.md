# Rezerv — Deployment Guide

## Free Development Stack

| Service | Provider | URL |
|---------|----------|-----|
| PostgreSQL | Neon | neon.tech |
| Redis | Upstash | upstash.com |
| Backend (FastAPI) | Railway | railway.app |
| Bot (aiogram) | Railway | railway.app |
| Frontend (React PWA) | Vercel | vercel.com |

---

## Step 1: Database — Neon (PostgreSQL)

1. Go to [neon.tech](https://neon.tech) → Create account → New project
2. Name it `rezerv-db`, region: Europe (Frankfurt is closest to UZ)
3. Copy the **connection string** — it looks like:
   ```
   postgresql://user:pass@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require
   ```
4. Save it as `DATABASE_URL` in your `.env`

---

## Step 2: Redis — Upstash

1. Go to [upstash.com](https://upstash.com) → Create account → New Database
2. Name: `rezerv-redis`, region: `eu-west-1` (Ireland)
3. Copy the **Redis URL** — it looks like:
   ```
   rediss://default:xxxxx@eu1-xxx.upstash.io:6379
   ```
4. Save it as `REDIS_URL` in your `.env`

---

## Step 3: Telegram Bot Token

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. `/newbot` → set name and username
3. Copy the token → save as `TELEGRAM_BOT_TOKEN`
4. Set `WEBHOOK_BASE_URL` to your Railway backend URL (filled in step 5)

---

## Step 4: Environment variables

Copy `.env.example` to `.env` and fill in:

```env
DATABASE_URL=postgresql+asyncpg://user:pass@...neon.tech/neondb?ssl=require
REDIS_URL=rediss://default:xxx@eu1-xxx.upstash.io:6379
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
TELEGRAM_BOT_TOKEN=123456:ABCDEF...
TELEGRAM_WEBHOOK_SECRET=<another random hex>
WEBHOOK_BASE_URL=https://your-backend.railway.app
BOT_SECRET=<another random hex>
SUPER_ADMIN_TELEGRAM_IDS=your_telegram_id
ALLOWED_ORIGINS=https://your-frontend.vercel.app
ENVIRONMENT=production
```

**Important:** For Neon, the DATABASE_URL must use `asyncpg` driver and include `?ssl=require`.

---

## Step 5: Backend — Railway

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Select your repo, set **Root Directory** to `backend`
3. Railway auto-detects the `Dockerfile` and `railway.toml`
4. Add all environment variables from Step 4 in Railway's Variables tab
5. Deploy — Railway runs `alembic upgrade head` then starts uvicorn
6. Copy the generated URL (e.g. `https://rezerv-backend.railway.app`)
7. Set it as `WEBHOOK_BASE_URL` in Railway variables

**After first deploy**, seed the categories:
```bash
# In Railway shell (from the backend service)
python -m scripts.seed_categories
```

---

## Step 6: Bot — Railway

1. New service in same Railway project → Deploy from GitHub
2. Root Directory: `bot`
3. Add environment variables: `BOT_TOKEN`, `BOT_SECRET`, `BACKEND_URL`, `REDIS_URL`
   - `BACKEND_URL` = `https://your-backend.railway.app/api/v1`
4. Deploy

---

## Step 7: Frontend — Vercel

1. Go to [vercel.com](https://vercel.com) → New Project → Import from GitHub
2. Root Directory: `frontend`
3. Framework: Vite
4. Update `frontend/vercel.json` — replace `your-backend.railway.app` with your real Railway URL
5. Add environment variable: `VITE_DEV_BYPASS_TELEGRAM=false`
6. Deploy

---

## Step 8: Set Telegram Webhook

After deploying backend and bot, set the webhook:

```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -d "url=https://your-backend.railway.app/api/v1/bot/webhook" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

> Note: The bot currently uses polling (`main.py`). To switch to webhook mode for Railway, see the bot README.

---

## Production (Hetzner VPS)

When ready to launch, migrate to Hetzner CX22 (~€4/month):

1. Install Docker + docker-compose on the VPS
2. Clone repo, fill `.env`
3. `docker-compose up -d`
4. Point your domain DNS to the VPS IP
5. Nginx handles HTTPS (via Certbot) and serves the frontend

```bash
# Certbot for HTTPS
apt install certbot python3-certbot-nginx
certbot --nginx -d yourdomain.com
```

---

## Local Development

```bash
# 1. Start DB + Redis locally
docker-compose -f docker-compose.dev.yml up db redis -d

# 2. Backend
cd backend
pip install -r requirements.txt
alembic upgrade head
python -m scripts.seed_categories
uvicorn app.main:app --reload

# 3. Bot (separate terminal)
cd bot
pip install -r requirements.txt
python main.py

# 4. Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Access the app at `http://localhost:5173`
