# ADR-002 — Service layer as the shared application boundary

## Status

Accepted

## Context

Once Streamlit, FastAPI and a CLI all needed the same operational
behavior, something had to own orchestration. Two shapes were
possible: each client implementing its own orchestration against
engines/repositories, or one application boundary that every client
consumes. A related question: should the Streamlit UI call the
FastAPI application over HTTP?

## Decision

`app/services.py` is the application boundary. Streamlit, FastAPI
and the CLI are **sibling clients** of the service layer:

```text
Streamlit ──┐
FastAPI ────┼→ services → engines/repositories → SQLite
CLI ────────┘
```

Streamlit is deliberately **not** an HTTP client of the FastAPI
application. All three first-party clients import and call the
service functions directly in-process; the API exists as a genuine
external boundary for integrations (see ADR-007).

## Rationale

Sibling clients avoid self-consumption: the UI and the API would run
in the same process against the same SQLite file, so routing UI
calls through HTTP would add network and serialization overhead,
duplicated error handling and a second failure mode, while changing
no behavior. Keeping the API free of first-party traffic also keeps
it clean as the external integration contract: its consumers are
external by design, and its contract (including authentication) is
shaped for them rather than for the project's own UI.

A shared service boundary means an application operation is
implemented once: approval validation, outcome construction and
error translation behave identically no matter which client invoked
them.

## Consequences

Benefits:

- One implementation per application operation; clients cannot
  drift apart behaviorally.
- The external API stays a genuine integration boundary rather than
  doubling as the UI's transport.
- Service-level tests prove behavior once, for every client.

Trade-offs:

- If the UI and the data tier are ever deployed apart, the UI would
  need a transport (its own API client or the FastAPI boundary);
  that is a deliberate future change, not present today.
- Services must stay free of client-specific concerns (no Streamlit
  types, no HTTP concepts inside `app/services.py`).

## Alternatives considered

- **Streamlit over HTTP to FastAPI** — rejected for this prototype:
  same-process, same-database deployment makes the hop pure
  overhead and muddies the API's role as the external boundary.
- **Per-client orchestration** — rejected: duplicates every
  operation's validation and outcome assembly across three clients.

## Current implementation

`app/services.py`; clients: `app/main.py` (Streamlit),
`app/api.py` (FastAPI), `app/cli.py` (CLI).
