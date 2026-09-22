# ADR-011 — Establish FastAPI as the versioned application boundary

## Status

Accepted

## Context

Adensa's clients — Streamlit (app/main.py), the FastAPI boundary
(app/api.py) and the CLI (app/cli.py) — all consume the same
service layer (ADR-002), and the service layer is the only place
where clients meet operational data. That boundary was already
architecturally sound, but the HTTP surface did not yet reflect
it: FastAPI exposed a narrow machine-to-machine API (metrics,
inbox, review, latest action, three workflow mutations) sized for
the Power Automate integration contract (ADR-007), while the
Streamlit UI reached the service layer directly for everything
else.

The next planned step in the project is a separately hosted web
frontend. A new client can only consume the application through
HTTP, which makes FastAPI — not Streamlit — the future primary
application boundary. Before that client exists, the API surface
must expose the capabilities the workspace actually needs:
control-tower summary, the operational work queue, investigation
context, investigation state, operational history, the recovery
assessment with its rationale, sustainability comparison,
manual-intervention records and the operational mutations.

P1 (the production-architecture graduation audit) identified the
gaps precisely: the versioned surface, explicit response
contracts, a `sqlite3.Row` leak across the service boundary, CORS
for a browser client, and a readiness check.

## Decision

The FastAPI application is extended into the **complete, versioned
application boundary**:

- **New application-facing paths under `/v1`**: control-tower
  summary, exception inbox, exception context, investigation
  state, operational history, recovery assessment (recommendation,
  alternatives, rationale), sustainability comparison, manual
  intervention reads, manual-resolution recording, and the two
  operational pipeline operations (refresh, simulated arrival).
  The API exposes application capabilities, not Streamlit
  widgets; the investigation workflow stays coherent rather than
  fragmenting into per-visual-section endpoints.

- **The existing machine-to-machine paths are retained
  unchanged.** `/health`, `/metrics`, `/exceptions`,
  `/exceptions/{id}/review`, `/exceptions/{id}/actions/latest` and
  the three mutation endpoints are the deployed integration
  contract for external orchestration (ADR-007). Reshaping them
  silently would break that contract, so they coexist with `/v1`
  and remain the compatibility surface. `/v1` is the path where
  the application boundary can evolve without contractual
  collateral damage.

- **Explicit Pydantic response models for operational reads.**
  Each `/v1` read returns a documented schema that mirrors the
  existing service output — the models describe reality, they do
  not invent a new domain model. Nullability follows the database
  schema (an undated field stays nullable in the contract).

- **No `sqlite3.Row` crosses the service boundary.** The two
  service functions that returned raw rows
  (`get_exception_inbox`, `get_latest_action`) now return plain
  dictionaries, fixed once at the service boundary rather than
  converted in every endpoint. The API — like every client — no
  longer needs to know that the persistence layer is SQLite.

- **CORS is environment-driven.** Allowed browser origins are
  read from `ADENSA_CORS_ORIGINS` (comma-separated, empty by
  default). No production origin is hard-coded and the wildcard
  is deliberately never used for an operational API. CORS does
  not affect machine-to-machine callers.

- **Readiness is a first-class contract.** `/health` remains the
  public liveness probe; `/ready` verifies the application can
  open and use the configured database, reporting nothing about
  database internals.

- **Security posture unchanged.** Every operational endpoint —
  `/v1` included — is guarded by the existing `X-API-Key`
  mechanism (ADR-008). P2 introduces no user identity, no OAuth /
  JWT, and no RBAC.

## Rationale

The API is completed *before* the frontend because a boundary
that is designed around real consumer needs is the only way to
build the client without either duplicating orchestration in the
browser or reshaping the backend under it. The service layer
already proved it can carry three clients; `/v1` simply makes the
fourth consumer's path explicit and contract-checked.

Doing this while the persistence layer is still SQLite is
deliberate: the versioned boundary is what makes the later
PostgreSQL migration a behind-the-boundary change instead of an
application-wide one. Migrating storage first would harden the
leak instead of fixing it.

## Consequences

Benefits:

- A future web client can be built against a stable, documented,
  contract-tested HTTP surface without touching Streamlit.
- The service boundary is now type-clean: no client depends on
  the persistence layer's row type.
- OpenAPI documentation for the whole workspace capability set is
  generated from the response models.
- The machine-to-machine integration contract remains untouched,
  so external orchestration keeps working unchanged.

Trade-offs and limitations:

- Two parallel endpoint generations coexist (legacy paths and
  `/v1`), which is intentional compatibility but temporary
  surface duplication.
- API-key authentication remains prototype-grade (ADR-008);
  the versioned boundary does not change that.
- SQLite remains the store: single-writer, local-file
  semantics — acceptable at prototype scale, deferred by design.
- The sustainability models carry the prototype's estimate
  methodology, not measured data (ADR-010).

## Alternatives considered

- **Break the old paths now and serve everything under `/v1`**
  — rejected: it would silently break the existing Power
  Automate integration contract for no functional gain.
- **Serve the new reads on the existing unversioned paths**
  — rejected: it would mix the evolving application contract
  into the frozen integration contract and make both harder to
  reason about.
- **Keep converting rows in each endpoint** — rejected: the leak
  is a boundary problem and is fixed once at the boundary, not
  re-fixed per route.
- **Defer the API work until the frontend is built** — rejected:
  that inverts the dependency; the client would then drive
  boundary design under delivery pressure.

## Current implementation

- `app/api.py` — `/v1` routes, response models, `/ready`, CORS.
- `app/config.py` — `ADENSA_CORS_ORIGINS`.
- `app/services.py` — boundary dict conversion
  (`get_exception_inbox`, `get_latest_action`).
- `tests/test_api.py` — `/v1` contract tests.
