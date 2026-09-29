# Deploying Adensa Digital

Operational guidance for running the system outside local
development.

> **Status:** Adensa Digital is **not yet deployed** to any
> production environment. This document describes the approved
> production topology the repository is packaged for — the
> containers, configuration boundaries, and sequencing — as
> part of the production-style graduation path. It is not a
> record of a running service.
>
> **P10.3 update:** the application layer is now packaged for
> **Google Cloud Run** — a frontend `web/Dockerfile` joins the
> backend `Dockerfile` (P10.2), and migrations run as an
> explicit Cloud Run Job instead of a platform release hook.
> The Fly.io configuration was retired (P11.3) after the
> Google Cloud deployment was verified in production.

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

## Deployed topology (P10.3 — Google Cloud + Neon)

The approved production topology runs the application layer on
**Google Cloud** and the database on **Neon PostgreSQL** —
a managed PostgreSQL service, keeping the existing persistence
abstraction and ADR-012 migration model unchanged:

```text
Public domain
   ↓
Google Cloud
   ├─ Cloud Run: adensa-web        — Next.js frontend
   ├─ Cloud Run: adensa-api        — FastAPI backend (/v1)
   ├─ Cloud Run Job: adensa-migrations — schema migrations
   ├─ Artifact Registry            — container images
   ├─ Secret Manager               — credentials
   └─ IAM                          — least-privilege service accounts
   ↓
Neon PostgreSQL (managed; DSN injected as DATABASE_URL)
```

Cloud Run region: **`europe-west3` (Frankfurt)** — matching the
Neon project region (`eu-central-1`) so database round-trips
stay local.

### Service responsibilities

| Service | Responsibility |
|---|---|
| `adensa-web` | Serves the Next.js application (server-rendered pages and client islands). Performs all API access server-side against `adensa-api`; the browser never sees the API origin or credentials. Built from `web/Dockerfile`. |
| `adensa-api` | Serves the FastAPI `/v1` application boundary. Stateless, per-request database connections. Built from the root `Dockerfile`. Verifies — never migrates (ADR-012). |
| `adensa-migrations` | A Cloud Run **Job** running the same backend image with the command `python -m app.database`. Applies the migration history idempotently. Run explicitly before each API revision that follows a schema change. |

Artifact Registry stores the images; Cloud Build builds them
(`gcloud builds submit` — the container validation path when no
local Docker exists). Secret Manager holds the credentials;
IAM service accounts grant each service access only to the
secrets it needs.

## Deployment sequence

The ordering below preserves the architecture's invariant:
**migrations run before new API code accepts traffic, and the
API process itself never migrates (ADR-012).**

```text
1. Build image(s)            →  gcloud builds submit (Cloud Build → Artifact Registry)
2. Update migration Job      →  point adensa-migrations at the new image
3. Execute migration Job     →  gcloud run jobs execute adensa-migrations --wait
4. Wait for Job success      →  Job exits 0 (idempotent; a no-op when current)
5. Deploy API revision       →  gcloud run deploy adensa-api (new revision)
6. Verify /ready             →  200 {"status":"ready","database":"ok"}
7. Deploy web                →  gcloud run deploy adensa-web
8. End-to-end verification   →  pages, KPI deep links, one real mutation
```

> **Cloud Run does not automatically execute the migration Job
> before every service revision.** Unlike a platform release
> hook, a Cloud Run Job is invoked only when orchestration
> explicitly runs it. Deployment automation must therefore run
> `gcloud run jobs execute adensa-migrations --wait` between
> "build image" and "deploy API revision" every time the image
> may contain schema changes. Deploying an API revision whose
> schema expectations are ahead of the database is safe by
> design — `/ready` reports `503 schema-outdated` and the old
> revision's traffic is held back — but the correct sequence
> keeps the Job execution in the loop.

## Environments: local ≠ CI ≠ production

| | Local development | CI | Production (target) |
|---|---|---|---|
| Database | SQLite (`data/adensa.db`, default) | Disposable SQLite + a PostgreSQL 16 service container | Neon PostgreSQL, configuration-driven |
| Secrets | None required; synthetic/empty values | None; synthetic test keys inside the test session | Real values in Secret Manager / Cloud Run config — never in source |
| Migrations | `python -m app.database` / bootstrap | Bootstrap of a throwaway dev DB; integration tests migrate temporary databases | The `adensa-migrations` Cloud Run Job (above) |
| API server | `uvicorn app.api:app` (localhost) | TestClient (in-process) | Container CMD binding Cloud Run's `$PORT` |
| Frontend | `npm run dev`, fallback API origin | `npm run build` gate | Container build + `next start` on Cloud Run's `$PORT` |

## Environment variables

Backend (see `.env.example` at the repository root):

| Variable | Purpose | Production requirement |
|---|---|---|
| `DATABASE_URL` | Backend selection: `postgresql://…` = PostgreSQL (requires `requirements-postgres.txt`) | **Secret Manager** — the Neon DSN (pooled endpoint for the service; see migration note below) |
| `ADENSA_API_KEY` | Machine credential for every operational endpoint; unconfigured = fail-closed | **Secret Manager** — high-entropy per-environment value |
| `ADENSA_CORS_ORIGINS` | Browser origins allowed to call the API; comma-separated; empty = none trusted | **Runtime environment variable** — the frontend's Cloud Run URL; never `*` |

Frontend (`web/.env.example`):

| Variable | Purpose | Production requirement |
|---|---|---|
| `API_BASE_URL` | Server-side origin of the FastAPI `/v1` boundary | **Runtime environment variable** — the `adensa-api` Cloud Run URL |
| `API_KEY` | Machine credential the Next server presents to the API | **Runtime-only web-service secret** (Secret Manager reference) — same value the API server receives as `ADENSA_API_KEY` |

Both frontend variables are deliberately **not**
`NEXT_PUBLIC_`-prefixed: they are read only on the Node server
and never ship to the browser.

**Build-time boundary:** `API_KEY` must **never** be baked into
a Docker image, passed as a Docker build ARG, or exposed during
image build. The frontend image intentionally contains no API
configuration at all: the Next.js build executes no API calls
(all fetches are `cache: "no-store"`), so no build ARG exists
for either variable — configuration is injected by Cloud Run
at container start only.

## Secret boundaries

| Secret | Mechanism | Consumer |
|---|---|---|
| `DATABASE_URL` | Secret Manager | `adensa-api`, `adensa-migrations` |
| `ADENSA_API_KEY` | Secret Manager | `adensa-api` |
| `API_KEY` | Secret Manager (same value as `ADENSA_API_KEY`) | `adensa-web` (runtime only — never in the image, never a build ARG) |
| `ADENSA_CORS_ORIGINS` | Plain Cloud Run env var (not secret-sensitive) | `adensa-api` |
| `API_BASE_URL` | Plain Cloud Run env var (not secret-sensitive) | `adensa-web` |

## API health and readiness contract

| Endpoint | Meaning | Auth | Failure behavior |
|---|---|---|---|
| `/health` | Process liveness | Public | — |
| `/ready` | Database reachable **and** schema current | Public, minimal response | `503 {"status": "degraded", "database": "schema-outdated"}` |

On Cloud Run, `/ready` is the **startup probe** target for
`adensa-api`: a revision receives traffic only once the API has
verified its database state. `/health` serves liveness
restarts. Responses never expose database internals,
connection details, or credentials.

## Neon PostgreSQL considerations

The persistence layer (psycopg 3 via `app/pg_compat.py`) talks
to Neon exactly as to any PostgreSQL 16+ server.

- **Pooled endpoint (PgBouncer transaction mode).** The
  `adensa-api` service uses Neon's *pooled* DSN: Cloud Run can
  scale instances up and down without exhausting PostgreSQL
  connections. The application opens short-lived per-request
  connections with no server-side prepared statements, which
  is the access pattern transaction pooling supports.
- **Direct endpoint fallback for the migration Job.** The
  `adensa-migrations` Job runs as a single process; if the
  pooled endpoint ever interferes with migration-session
  semantics, switch the Job's `DATABASE_URL` secret to Neon's
  *direct* (unpooled) endpoint — one connection, full session
  semantics, no pooling benefit lost.
- **Scale-to-zero.** Neon's compute suspends after inactivity
  (tier-dependent). For a demonstration or low-traffic
  deployment, either disable suspension or warm the database
  before the session. Cloud Run `min instances` addresses our
  cold starts, not Neon's.

## Cloud Run instance configuration

**Initial deployment settings subject to verification — not
permanent guarantees.** Size from observed behaviour after
deployment; these are starting points:

| Setting | `adensa-api` | `adensa-web` | `adensa-migrations` |
|---|---|---|---|
| CPU / memory | 1 vCPU / 512Mi | 1 vCPU / 512Mi | 1 vCPU / 512Mi |
| Min instances | **1** | 0 (raise to 1 for demo stability) | — (Job) |
| Max instances | 2 | 3 | — |
| Concurrency | 80 | 80 | — |

**Why `min instances = 1` on the API initially:** the frontend
renders every page server-side through API calls, so a
scale-to-zero API turns the first user request into a double
cold start (instance start + startup verification). One always
warm instance keeps the operational surface responsive and
predictable — the same demo-stability decision the previous
Fly configuration encoded (`min_machines_running = 1`). The API is
stateless (per-request connections), so additional instances
scale safely if traffic demands.

## Custom-domain strategy

The production custom domain terminates at **Google's
recommended global external Application Load Balancer** with a
managed certificate, routing to the two Cloud Run services
(serverless NEG backends). Direct Cloud Run domain mapping is
acceptable for provisional access during bring-up but is **not
the final production architecture** — it does not provide the
global anycast entry point, centralized certificate management,
or the path-based routing an Application Load Balancer offers.

## Why this topology needs no further Google Cloud infrastructure

- **No Cloud SQL** — PostgreSQL is provided by Neon; the
  application reaches it over TLS via its public DSN. Cloud SQL
  would duplicate the database and break the single-source
  persistence contract.
- **No VPC connector / Serverless VPC Access** — Cloud Run
  services connect to Neon over the public internet with TLS
  (`sslmode=require`); there is no private-network resource to
  reach. The frontend→API hop is also public Cloud Run HTTPS
  with the `X-API-Key` boundary.
- **No GKE** — two stateless HTTP services and a one-shot Job
  are exactly Cloud Run's model; Kubernetes would add cluster
  operations with no benefit at this scale.

## Security principles and service accounts

Least privilege, per service:

| Identity | Granted | Not granted |
|---|---|---|
| `adensa-api-sa` | `secretAccessor` on `DATABASE_URL` + `ADENSA_API_KEY` | Access to `API_KEY`, any other project secrets, deployment roles |
| `adensa-web-sa` | `secretAccessor` on `API_KEY` | Access to `DATABASE_URL` or any API-side secret |
| `adensa-migrations` | reuses `adensa-api-sa` | Deployment roles |
| Deployer (human/CI identity) | `run.admin`, `artifactregistry.writer`, `secretManager.admin` on the project scope | — |

The application-layer security model is unchanged: the
prototype `X-API-Key` machine credential (ADR-008) with
fail-closed behaviour and constant-time comparison — machine
authentication, **not** user authentication (see the
limitations section at the end of this document). All API
access from the browser path is server-to-server; the browser
never receives the API origin or the credential.

## Image builds: Cloud Build + Artifact Registry

`gcloud builds submit` builds both images from the repository's
Dockerfiles (no local Docker required) and pushes them to
Artifact Registry. Images are the deployable unit for all three
services: `adensa-web` from `web/Dockerfile`; `adensa-api` and
the `adensa-migrations` Job from the root `Dockerfile` (the Job
overrides the container command). Neither image contains
secrets, credentials, or operational data — packaging is
configuration-shape only.

**Build executor identity (P11.2c).** This project's Cloud
Build default executor is the default Compute Engine service
account (`533810602636-compute@developer.gserviceaccount.com`),
confirmed by build history: the production `adensa/api` and
`adensa/web` images were built under that identity. Its
`roles/cloudbuild.builds.builder` grant is therefore
load-bearing for the manual `gcloud builds submit` workflow and
must **not** be removed — an earlier audit recommendation to
strip it (P11.1) is superseded by this evidence. The Cloud
Build service account also holds the builder role but is not
the configured executor; Cloud Build service-agent roles are
standard and untouched.

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

Treat the key as a deployment secret (Secret Manager, rotated
on schedule, never committed or logged).

## Future authentication path

Human-user authentication — enterprise identity (SSO /
Microsoft Entra ID), OAuth/OIDC tokens at the API boundary,
and role-based authorization — is a deliberate future
checkpoint. The service-layer boundary means it can be added
at the API edge (token validation replacing the shared key for
browser-originated traffic) without changes to engines,
repositories, or the decision authority.
