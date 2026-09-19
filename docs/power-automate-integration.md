# Power Automate Integration (First Slice)

This documents the implemented closed-loop integration between
Adensa Digital and Microsoft Power Automate.

> **Prototype scope.** This is a controlled prototype
> integration. API-key authentication is prototype-grade (see
> [api-authentication.md](api-authentication.md)), the flow runs
> on a single controlled exception at a time, and connectivity
> relies on a temporary tunnel. It is not a production
> deployment architecture.

## Architecture

```text
Adensa (source of truth)
    Detect → Assess → Recommend → Approve/Reject → Execute → Outcome
        │
        FastAPI boundary  (X-API-Key protected)
        │
Power Automate (external orchestrator — the only clock)
        ├─ Poll Adensa for new actionable exceptions
        ├─ Notify / request human approval (Teams)
        ├─ Call Adensa back with the human decision
        ├─ Execute approved recoveries
        └─ Report the outcome Adensa reports
```

Division of responsibility — the boundary is strict:

| Adensa owns | Power Automate owns |
|---|---|
| exception state, recovery options | polling schedule (the clock) |
| recommendation scoring & confidence | notification content |
| workflow transition validation | delivery of the approval request |
| approval / rejection recording | calling the API with the decision |
| execution validation & shipment mutation | outcome notification |
| operational outcome, audit & history | retry behavior on transport failures |

Power Automate never decides what is operationally valid: it
sends a request, and Adensa's state validation either accepts it
or refuses it with a domain error. Power Automate reports the
state Adensa returns — it never computes outcomes itself.

## API endpoints used (all validated in `tests/test_power_automate_flow.py`)

| Step | Call | Notes |
|---|---|---|
| precondition | `GET /health` | public; distinguishes "Adensa down" from "key misconfigured" |
| poll | `GET /exceptions` | open exceptions with `severity`, `feasible_option_count` |
| select | (flow logic) | first row with `feasible_option_count > 0`; one at a time |
| review | `GET /exceptions/{id}/review` | recommendation: mode, carrier, cost, transit, risk, `decision_score`, `confidence`, `reason` + ranked alternatives |
| decide | `POST /exceptions/{id}/approve` / `reject` | body `{"approved_by": "<human name>"}` / `{"rejected_by": …}` |
| execute | `POST /recovery-actions/{action_id}/execute` | only for approved actions |
| read back | `GET /exceptions/{id}/actions/latest`, `GET /exceptions` | ground truth for the notification |

Every protected call sends the header `X-API-Key`; the key comes
from Power Automate's secure mechanism (never from flow JSON,
screenshots, documentation or notification content).

## Approval flow

1. **Recurrence trigger** (prototype cadence: every 15 minutes)
   runs the poll.
2. A new actionable exception produces a Teams adaptive card:
   exception ID, shipment, severity, priority, dates, delay,
   recommendation summary with score/confidence/reason, and the
   alternatives table.
3. The planner uses **Approve** / **Reject** actions on the card.
   The card records the human decision; the actor sent to Adensa
   is the planner's name.
4. Power Automate calls the matching mutation endpoint. Adensa
   validates the transition (identity, state, allowed transition,
   actor) and records the decision with its own audit fields.

## Execution flow

- After a **200 approval**, the flow executes the returned
  `action_id`.
- A **409** from Adensa is treated as authoritative: the state
  has moved on (already approved, already executed, conflicting
  decision, closed exception). The flow re-reads state and
  reports that state instead of retrying the mutation.
- A **404** means the addressed resource does not exist (e.g. a
  stale exception reference); the flow stops for that exception.

## Outcome handling

The notification is built from Adensa's read-back, never from
the flow's assumptions:

| Adensa state | Notification |
|---|---|
| `Executed` + exception `Resolved` | "Executed — Resolved" (new ETA) |
| `Executed` + exception still `Open` | "Executed — Still Open" (new ETA still misses the required date) |
| action `Rejected` | "Rejected — no execution performed" |

The executed-but-still-open case is explicitly tested: it is
never reported as resolved.

## Retry / idempotency approach

- **Duplicate notifications** — polling reads state; the flow
  tracks the exceptions it has already presented in flow state.
- **Approval repeated** — the flow re-reads
  `GET /exceptions/{id}/actions/latest` before any re-send. If
  the status already reflects the decision, no second mutation
  is sent. If a blind repeat happens anyway (or a mutation timed
  out after Adensa committed it), Adensa's optimistic state guard
  refuses it with `409` and no duplicate business action exists.
- **Execution repeated** — same rule: only `Approved` actions
  execute, exactly once; a repeat returns `409`.
- **Adensa unavailable** — the recurrence trigger retries; the
  next successful poll re-reads current state (state-based, so
  no event is lost while the service was down).
- **Power Automate unavailable** — Adensa functions normally;
  approvals simply happen through the Streamlit UI or CLI.

## Connectivity (prototype limitation)

Power Automate is a cloud service and cannot reach a local
development machine directly. For the prototype, Adensa is
exposed through a **temporary developer tunnel** (for example
`cloudflared` or VS Code port forwarding) bound to a locally
running uvicorn instance:

```text
uvicorn app.api:app          # localhost, X-API-Key required
cloudflared tunnel --url http://localhost:8000   # temporary URL
```

Limitations, stated plainly:

- the tunnel URL is ephemeral and must be updated in the flow
  when it changes;
- the tunnel terminates TLS but grants no identity to callers —
  the API key is the only authentication;
- the tunnel must be closed when the demonstration ends; the
  service is never left exposed.

No production cloud infrastructure, static endpoints or gateway
configuration is introduced in this checkpoint.

## What Power Automate does NOT do

- No second workflow engine: every transition rule lives in
  Adensa's workflow/execution engines.
- No duplicated scoring: confidence/scores are read from
  Adensa's review payload, never recomputed.
- No direct database access: the API is the only door.
- No event infrastructure: no webhooks, queues, outbox tables or
  background workers on either side.

## Prototype limitations

- One actionable exception is presented per cycle by design
  (controlled demonstration scale).
- The polling model has cadence-scale latency by definition.
- The adaptive-card actor is the name typed in Teams; Adensa
  records it verbatim (identity verification is out of scope).
- API-key authentication is prototype-grade; production exposure
  would require the organization's identity stack and network
  security boundary (see api-authentication.md).
