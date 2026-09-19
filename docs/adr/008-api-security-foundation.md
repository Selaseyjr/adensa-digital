# ADR-008 — API security foundation (prototype API key)

## Status

Accepted

## Context

Once the FastAPI boundary is reachable by an external orchestrator
(see ADR-007), operational reads expose business data and the
mutation endpoints change operational state. The prototype needs a
controlled, explicit security mechanism now, while enterprise
identity infrastructure is out of scope.

## Decision

The API boundary is protected by a static API key sourced from the
environment, applied as one shared FastAPI dependency:

- `GET /health` is public — a liveness probe carrying no
  operational data, kept keyless so "service down" is
  distinguishable from "credentials misconfigured".
- **Every operational endpoint requires `X-API-Key`**: the four
  operational reads (`/metrics`, `/exceptions`,
  `/exceptions/{id}/review`, `/exceptions/{id}/actions/latest`) and
  the three mutations (approve, reject, execute). Reads are
  protected because operational data itself is sensitive once the
  API is externally reachable.
- The key is never hard-coded: it comes from configuration
  (`ADENSA_API_KEY`, environment).
- Key comparison uses a constant-time comparison
  (`secrets.compare_digest`).
- Fail-closed posture: an unconfigured server key yields HTTP 503
  for protected routes — an unprovisioned deployment never silently
  allows access; a missing or wrong header yields HTTP 401 with
  generic messages that leak neither the key nor the configuration
  state.
- Authentication sits at the API boundary, before domain
  validation; services and engines know nothing of it.
- Rejected requests perform no database mutation (covered by
  tests).

This is a **prototype security mechanism**, explicitly not a
production enterprise identity architecture. Deferred: Microsoft
Entra ID / SSO, OAuth/JWT, RBAC, user management, audit of identity
beyond the actor string recorded on workflow actions, and transport
security beyond the deployment's responsibility (the prototype
binds locally / uses a temporary tunnel).

## Rationale

A single environment-sourced key provides the minimum property the
integration actually requires — only holders of the configured
secret can read operational data or mutate state — with a few dozen
lines of standard-library-backed code and no new dependencies. It
keeps the external boundary safe enough for a controlled prototype
without pulling an identity platform into a system whose identity
requirements are not yet defined.

## Consequences

Benefits:

- The mutation surface and operational reads are inaccessible
  without the configured secret, enforced uniformly by one
  dependency.
- Fail-closed behavior means misconfiguration is loud, not silent.
- No coupling to any identity provider; upgrading to enterprise
  identity later replaces one dependency function.

Trade-offs:

- A single shared key has no per-user identity, rotation story or
  scope granularity; the recorded actor on workflow actions is a
  name supplied by the caller, not a verified identity.
- Protecting it in real deployments requires secret management and
  TLS, which are deployment responsibilities outside this
  repository.

## Alternatives considered

- **Unauthenticated API (prototype trust)** — rejected: mutation
  endpoints and operational data exposed anonymously is
  indefensible even for a prototype.
- **OAuth/JWT or Entra ID now** — rejected: enterprise identity is
  a deployment and organizational decision, premature before the
  integration's real users exist; deliberately listed as future
  direction.

## Current implementation

`app/api.py` (`require_api_key` dependency, `APIKeyHeader`,
`secrets.compare_digest`, 401/503 mapping),
`app/config.py` (`ADENSA_API_KEY` from environment),
`docs/api-authentication.md` (the implemented contract);
coverage in `tests/test_api.py` (missing/invalid/unconfigured key,
fail-closed, no-mutation, reads-protected policy).
