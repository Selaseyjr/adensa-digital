# ADR-005 — Executed does not necessarily mean resolved

## Status

Accepted

## Context

Executing a recovery changes the plan: a new transport mode, a new
estimated arrival. It is tempting to treat execution as success.
Operationally that would be wrong — the recovery only matters if
the resulting delivery outcome actually satisfies the customer's
required delivery date, and the new ETA can still miss it.

## Decision

Execution and resolution are distinct states, evaluated separately:

- **Execution** applies the approved recovery: shipment mode/ETA are
  updated and a recovery shipment event is recorded. The action
  becomes `Executed`.
- **Resolution** is evaluated from the operational outcome: the
  exception becomes `Resolved` (with `resolved_at` stamped) only
  when the post-execution estimated arrival meets the required
  delivery date. Otherwise the action is `Executed` while the
  exception **remains open and monitored**.

The distinction is preserved end to end: the execution outcome
reports the exception status it produced, the UI and API render
"executed — still open" as still open, the exception stays in the
open inbox, and the control tower's Recently Resolved surface only
lists genuinely resolved exceptions. The operational history keeps
the two events separate.

## Rationale

This is the difference between doing something and having done
enough. Conflating them would hide stuck exceptions from planners,
falsely shrink the open-exception population, and make recovery
quality unmeasurable. Keeping them separate makes the "still open
after execution" population visible — which is exactly the set a
planner must keep working on.

## Consequences

Benefits:

- Honest operational reporting: the open inbox means what it says.
- Outcome quality is measurable (how many executions actually
  resolve).
- Manual follow-up has a well-defined entry point: exceptions that
  remain open after execution are candidates for further recovery
  or intervention.

Trade-offs:

- The system carries a state ("executed, still open") that simpler
  designs collapse away; UI and API must render it distinctly.
- Resolution depends on the recorded operational data (new ETA vs
  required delivery); if that data is wrong upstream, resolution is
  wrong with it.

## Alternatives considered

- **Resolve on execution** — rejected: it fabricates operational
  success and hides unresolved work.
- **Separate planner confirmation step to resolve** — considered
  for the system path; rejected there because the delivery-outcome
  rule is already objective, while the human path records outcomes
  explicitly (see ADR-006).

## Current implementation

`app/execution_engine.py` (execution, ETA evaluation, guarded
resolution update), `app/repositories/exceptions_repo.py`
(`mark_exception_resolved`), outcome rendering in `app/main.py` and
`app/api.py`; behavior covered by the execution-branch tests
(`Resolved` vs still-open) and the UI still-open honesty test.
