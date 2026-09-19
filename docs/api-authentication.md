# API Authentication (Prototype)

This documents the implemented authentication contract of the
Adensa Digital API (`app/api.py`).

> **Security scope.** API-key authentication here is a
> **prototype security mechanism** for a controlled integration
> boundary. It is **not** equivalent to a production enterprise
> identity architecture: there is no OAuth, no user management,
> no JWT, no identity provider and no per-user authorization.
> Production exposure would additionally require TLS termination
> and the organization's standard identity stack.

## Mechanism

- Mutation endpoints require the standard header:

  ```
  X-API-Key: <key>
  ```

- The key is sourced exclusively from the environment variable
  `ADENSA_API_KEY` (read once into `app.config.ADENSA_API_KEY`).
- The key is never hard-coded, never committed, never returned in
  any response and never logged.
- Comparison is constant-time (`secrets.compare_digest`).

## Policy: which endpoints require the key

| Surface | Endpoints | Policy |
|---|---|---|
| Liveness | `GET /health` | **Public** — a health probe carrying no operational data |
| Operational reads | `GET /metrics`, `GET /exceptions`, `GET /exceptions/{id}/review`, `GET /exceptions/{id}/actions/latest` | **API key required** — they expose operational data |
| Mutations | `POST /exceptions/{id}/approve`, `POST /exceptions/{id}/reject`, `POST /recovery-actions/{action_id}/execute` | **API key required** — they change operational state |

In short: `/health` is public; **every other API endpoint requires the API key.**

## Error behavior

| Situation | Response |
|---|---|
| Header missing | `401 {"detail": "Missing API key."}` |
| Wrong key | `401 {"detail": "Invalid API key."}` — generic; leaks neither the key nor the configuration state |
| `ADENSA_API_KEY` unset (fail-closed) | `503 {"detail": "Mutation API is not configured for external access."}` — whether or not a header is supplied |

Authentication runs as a FastAPI dependency **in front of**
routing and domain validation, so a rejected request can never
touch the database. Authorized API behavior remains unchanged;
authentication is additive at the API boundary. The existing
domain error mapping (404 missing action/exception, 409
workflow violations, 422 request validation) applies unchanged
to correctly authenticated callers.

## Operating notes

- Run the API with the variable set, e.g.:

  ```
  set ADENSA_API_KEY=<generated-key>
  uvicorn app.api:app
  ```

- Generate keys with a proper secret generator (for example
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`);
  store them only in your local environment or a secrets vault —
  never in Git, never in flow definitions.
- The OpenAPI schema at `/docs` advertises the `X-API-Key`
  security requirement on the mutation routes; it never contains
  the key value.
