# ADR-001 — Layered application architecture

## Status

Accepted

## Context

Adensa started as a single Streamlit script in which data access,
business rules and presentation lived together. As operational
capability grew — detection, option evaluation, recommendation,
workflow, execution, manual resolution, history — that shape could
not keep responsibilities separated: UI code accumulated SQL, and
business rules had no home that clients other than the UI could
reach.

## Decision

The application is strictly layered:

```text
Streamlit / FastAPI / CLI        (presentation clients)
        ↓
Application Services             (app/services.py)
        ↓
Business Engines                 (detection, options, decision,
                                  workflow, execution, simulation)
        ↓
Repositories                     (app/repositories/*)
        ↓
SQLite                           (data/adensa.db)
```

Responsibilities are fixed:

- **Presentation clients** render and handle input. They contain no
  SQL and no business rules.
- **Application services** orchestrate engine and repository calls
  and expose application operations.
- **Engines** own the domain rules (what makes an exception, what is
  feasible, which transitions are allowed, what execution does).
- **Repositories** own all SQL and data access, one module per
  aggregate.

The layering is enforced by review and by the test suite: the UI is
verified to contain no SQL, no repository calls and no engine logic,
and every client is tested through the public service contracts.

## Rationale

Layered separation keeps each concern independently testable and
replaceable. Because repositories own SQL, the storage schema can
evolve without touching clients. Because engines own rules, those
rules can be exercised without any UI. Because services form the
boundary, new clients attach without duplicating orchestration.

## Consequences

Benefits:

- New clients (the FastAPI boundary, the CLI) attached to the same
  behavior with almost no new logic.
- Every layer is tested in isolation against explicit contracts;
  the repository, service, engine and UI test files each target one
  layer.
- The dependency direction is acyclic and easy to audit by grep.

Trade-offs:

- Cross-layer changes (for example, adding one operational field)
  can touch a repository, a service and a presentation client.
- Deliberate thinness at the boundary means some orchestration code
  exists in services that a less disciplined codebase would inline
  into the UI.

## Alternatives considered

- **Single-script application** — how the project began; rejected
  once multiple clients and a test strategy were needed.
- **Client-per-layer duplication** — each client querying SQLite
  directly; rejected because it multiplies SQL and makes behavior
  drift between UI, API and CLI inevitable.

## Current implementation

`app/services.py`, `app/repositories/`, the engine modules
(`detect_exceptions.py`, `generate_recovery_options.py`,
`decision_engine.py`, `workflow_engine.py`, `execution_engine.py`,
`simulation.py`), `app/main.py`, `app/api.py`, `app/cli.py`,
`app/database.py`.
