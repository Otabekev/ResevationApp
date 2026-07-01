FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Drop root — an app-code escape then lands as an unprivileged user, not root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Migrations are NOT run here. On Railway they run in `preDeployCommand`
# (see railway.toml) so the healthcheck window doesn't race the migration.
# For other platforms (docker-compose, Hetzner), run `alembic upgrade head`
# explicitly before bringing the service up — see RUNBOOK.md.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
