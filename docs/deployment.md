# Deploying Adensa Digital

Operational guidance for running the system outside local
development.

> **Status:** Adensa Digital is **not currently deployed** to
> any production environment. This document describes the
> deployment model the architecture is prepared for — verified
> by the CI pipeline and the local/PostgreSQL test suites — as
> part of the production-style graduation path. It is not a
> record of a running service.

## Architecture

```text
Next.js frontend (server-rendered client)
      ↓ HTTPS (server-to-server fetch, X-API-Key)
FastAPI backend (/v1 application boundary, ADR-011)
      ↓
Application services
      ↓
Engines / domain logic (deterministic decision authority)
      ↓
Repositories
      ↓
PostgreSQL (production target) / SQLite (local default)
```

The frontend performs all API access in Server Components;
the API origin and the machine credential never reach the
browser.

## Environments: local ≠ CI ≠ production

| | Local development | CI | Future production |
|---|---|---|---|
| Database | SQLite (`data/adensa.db`, default) | Disposable SQLite + a PostgreSQL 16 service container | PostgreSQL server, configuration-driven |
| Secrets | None required; synthetic/empty values | None; synthetic test keys inside the test session | Real values injected via the environment/secret store — never in source |
| Migrations | `python -m app.database` / bootstrap | Bootstrap of a throwaway dev DB; integration tests migrate temporary databases | Applied by the operator/bootstrap **before** API startup |
| API server | `uvicorn app.api:app` (localhost) | TestClient (in-process) | A production ASGI server invocation (below) behind TLS |
| Frontend | `npm run dev`, fallback API origin | `npm run build` gate | `npm run build && npm run start` with explicit `API_BASE_URL` |

## Environment variables

Backend (see `.env.example` at the repository root):

| Variable | Purpose | Production requirement |
|---|---|---|
| `DATABASE_URL` | Backend selection: absent = SQLite default; `sqlite:///…` = explicit path; `postgresql://…` = PostgreSQL (requires `requirements-postgres.txt`) | **Required** — set to the PostgreSQL DSN |
| `ADENSA_API_KEY` | Machine credential for every operational endpoint; unconfigured = fail-closed (503) | **Required** — high-entropy per-environment value |
| `ADENSA_CORS_ORIGINS` | Browser origins allowed to call the API; comma-separated; empty = none trusted | Set to the frontend's origin(s); never `*` |

Frontend (`web/.env.example`):

| Variable | Purpose | Production requirement |
|---|---|---|
| `API_BASE_URL` | Server-side origin of the FastAPI `/v1` boundary | **Required** — there is a deliberate localhost fallback for development only; relying on it in production warns loudly at startup and is a configuration error |
| `API_KEY` | Machine credential the Next server presents to the API | **Required** in production — same value the API server receives as `ADENSA_API_KEY` |

Both frontend variables are deliberately **not**
`NEXT_PUBLIC_`-prefixed: they are read only on the Node server
and never ship to the browser.

## Database configuration and migration sequence

One migration history serves both backends (ADR-012); the
PostgreSQL rendering of the same DDL resolves the dialect and
type decisions documented in `app/pg_compat.py`.

```text
1. Provision the database (PostgreSQL server / SQLite file)
2. Apply migrations          →  python -m app.database
   (bootstrap/CLI responsibility — the API never migrates)
3. Start the API             →  startup verification runs
4. /ready reports readiness  →  deploy/route traffic
```

The recorded schema version must equal `CURRENT_VERSION`
before the API accepts traffic.

## API startup verification (P6.2)

At startup the API opens one connection through the
persistence abstraction, verifies the database is reachable
and the schema is current, closes the connection, and fails
fast — with a redacted (credential-free) log line — when the
required state cannot be established. It verifies; it never
migrates.

## Health and readiness

| Endpoint | Meaning | Auth | Failure behavior |
|---|---|---|---|
| `/health` | Process liveness | Public | — |
| `/ready` | Database reachable **and** schema current | Public, minimal response | `503 {"status": "degraded", "database": "schema-outdated"}` |

Probe `/health` for restart decisions and `/ready` for
traffic-routing decisions. Responses never expose database
internals, connection details, or credentials.

## FastAPI production invocation

Development uses `uvicorn app.api:app`. For production-style
invocation, bind explicitly and size workers to the
deployment:

```bash
pip install -r requirements.txt -r requirements-api.txt -r requirements-postgres.txt
export DATABASE_URL="postgresql://…"      # injected, not committed
export ADENSA_API_KEY="…"                 # injected, not committed
export ADENSA_CORS_ORIGINS="https://adensa.example.org"  # illustrative shape, not a real deployment
uvicorn app.api:app --host 0.0.0.0 --port 8000 --workers 2
```

The API is a stateless HTTP service (per-request database
connections); horizontal scale is a matter of running more
processes behind the proxy. No worker/queue infrastructure is
required at this scale.

## Next.js production build and start

```bash
cd web
npm ci
API_BASE_URL="https://api.example.org" API_KEY="…" npm run build
API_BASE_URL="https://api.example.org" API_KEY="…" npm run start
```

The variables must be present in the server process
environment at both build and run time. A production start
without `API_BASE_URL` logs a loud warning and targets the
development fallback — treat that as a deployment failure.

## TLS / reverse-proxy boundary

Terminate TLS at a reverse proxy (for example nginx, Caddy,
or a platform load balancer) and forward to the two services:

```text
Browser ──HTTPS──▶ proxy ──▶ Next.js server (frontend)
                        └──▶ uvicorn (FastAPI API)
```

The browser talks only to the frontend; the frontend's API
calls are server-to-server. CORS on the API remains restricted
to configured origins. TLS details and certificate management
belong to the proxy, not the application.

## API-key security limitation

The current boundary security is the prototype/small-deployment
`X-API-Key` mechanism (ADR-008): one shared machine credential,
constant-time comparison, fail-closed when unconfigured,
generic authentication failures. This is appropriate for a
small professional deployment with a small number of trusted
server-side callers — it is **not** user authentication:

- it identifies machines, not people;
- there are no roles, per-user permissions, or audit trails
  tied to individuals;
- a leaked key grants full operational access until rotated.

Treat the key as a deployment secret (injected via the
environment or a secret store, rotated on schedule, never
committed or logged).

## Future authentication path

Human-user authentication — enterprise identity (SSO /
Microsoft Entra ID), OAuth/OIDC tokens at the API boundary,
and role-based authorization — is a deliberate future
checkpoint. The service-layer boundary means it can be added
at the API edge (token validation replacing the shared key for
browser-originated traffic) without changes to engines,
repositories, or the decision authority.
