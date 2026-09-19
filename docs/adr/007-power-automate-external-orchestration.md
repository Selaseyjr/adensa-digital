# ADR-007 — Power Automate as an external orchestration layer

## Status

Accepted

## Context

Adensa's workflow needs human decisions to reach planners wherever
they work, and operational events (a new actionable exception, an
approval, an execution outcome) create follow-up work that spans
communication channels. Adensa itself should not grow messaging,
reminder or escalation machinery — that is orchestration around the
operational system, not part of it.

## Decision

External orchestration is delegated to Microsoft Power Automate,
which sits **outside** Adensa and interacts only through the
secured API:

```text
Adensa:     Detect → Assess → Recommend → Execute / Intervene → Outcome
                │
            Adensa API (X-API-Key protected)
                │
Power Automate (external orchestrator)
                ├─ polling / notification
                ├─ human approval requests
                ├─ follow-up and escalation
                └─ calling the Adensa API with decisions
```

The division of authority is strict:

- **Adensa owns operational truth**: exception state, recovery
  options, recommendation, workflow-transition validation,
  execution, shipment mutation, outcomes, audit and history.
- **Power Automate owns external communication and timing**: the
  polling schedule, notification delivery, approval presentation
  and follow-ups.
- **Adensa never calls Power Automate.** There are no webhooks,
  outbound pushes, event tables or queues in Adensa; Power
  Automate polls the API on its own clock. If Power Automate is
  unavailable, Adensa operates normally through its first-party
  clients.
- Power Automate never decides what is operationally valid: every
  approval, rejection or execution it submits is revalidated by
  Adensa's workflow guards, whose optimistic state checks also make
  retries and duplicate submissions safe (see ADR-004).

**Status:** the Adensa-side boundary is complete — the API
contract, executable request-sequence tests and build documentation
exist in the repository (`docs/power-automate-integration.md`,
`tests/test_power_automate_flow.py`). The actual Microsoft 365 /
Power Automate tenant flow is **not yet deployed**; assembling and
running it is an operator step requiring tenant access.

## Rationale

The orchestration lifecycle (notify, remind, escalate) is a solved
problem with good enterprise tooling; rebuilding it inside Adensa
would add notification infrastructure, scheduling and channel
integrations that are not the project's substance. Delegating it
keeps Adensa's engine focused on operational truth while still
demonstrating a complete human-in-the-loop loop across systems —
and the API-first design means any other orchestrator could take
Power Automate's place without an Adensa change.

## Consequences

Benefits:

- Full closed-loop integration with zero Adensa production-code
  changes: the existing API already supports the entire flow.
- Poll-based integration is state-based: nothing is lost while
  either side is down, and retries are guarded by Adensa's state
  machine.
- Clear failure boundaries — Adensa does not depend on Power
  Automate's availability.

Trade-offs:

- The integration's latency is bounded by the polling cadence.
- The prototype exposure path relies on a temporary developer
  tunnel; production use would need durable, secured connectivity
  and the organization's identity stack.
- The live flow exists only as documentation and contract tests
  until a tenant deployment is performed.

## Alternatives considered

- **Adensa-native notifications/schedulers** — rejected: out of the
  project's domain substance and duplicates enterprise tooling.
- **Adensa calling Power Automate webhooks (push)** — rejected for
  the prototype: it couples availability in the wrong direction and
  adds outbound-event infrastructure (webhooks/outbox) that the
  polling model does not need.
- **n8n / custom orchestrator** — functionally possible via the
  same API; Power Automate was chosen for the target organization's
  ecosystem.

## Current implementation

`app/api.py` (the boundary consumed by the flow),
`docs/power-automate-integration.md` (architecture, flow
specification, retry/idempotency approach, connectivity
limitations), `tests/test_power_automate_flow.py` (executable
request-sequence contract); no Adensa-side scheduling, webhook or
queue infrastructure exists.
