# Adensa Digital — FastAPI backend image (P10.2).
#
# Production packaging for the /v1 application boundary:
# a slim Python image running `uvicorn app.api:app` on the
# platform-provided $PORT against the configured database
# (DATABASE_URL — PostgreSQL in the managed topology).
#
# The image contains no secrets, no credentials and no
# operational data: all configuration is injected at runtime
# via the environment (docs/deployment.md). Startup
# verification (lifespan) fails fast unless the database is
# reachable and the schema is current; migrations are applied
# by the Cloud Run migration Job (`python -m app.database`),
# never by the API process itself (ADR-012).

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependency layer first so code changes do not bust the pip
# cache. The API runtime needs the application/API set plus
# the PostgreSQL driver for the deployed backend.
COPY requirements.txt requirements-api.txt requirements-postgres.txt ./
RUN pip install -r requirements.txt -r requirements-api.txt -r requirements-postgres.txt

# Application code only — data/, tests/, docs/ and the
# frontend are not part of the runtime image.
COPY app/ ./app/

EXPOSE 8000

# Bind the platform-provided $PORT (8000 when unset, e.g.
# locally). Migrations run in the Cloud Run migration Job
# before this process starts — the API verifies and never
# migrates.
CMD ["sh", "-c", "uvicorn app.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
