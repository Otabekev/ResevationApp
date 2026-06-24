FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Migrations are NOT run here. On Railway they run in `preDeployCommand`
# (see railway.toml) so the healthcheck window doesn't race the migration.
# For other platforms (docker-compose, Hetzner), run `alembic upgrade head`
# explicitly before bringing the service up — see RUNBOOK.md.
#
# `::` (IPv6 dual-stack) — not 0.0.0.0 — so Railway's IPv6-only private network
# can reach this service; on Linux it still accepts IPv4 (public + healthcheck).
CMD ["sh", "-c", "uvicorn app.main:app --host :: --port ${PORT:-8000}"]
