# ADR-006 — Separate manual resolution path

## Status

Accepted

## Context

Some exceptions have no feasible system-generated recovery: every
evaluated option fails operational constraints. The situation is
still real, and a planner may well resolve it — by phoning a
carrier, negotiating with a supplier, coordinating internally —
entirely outside Adensa. The system must stay the record of that
outcome without pretending the solution was one of its own
recommendations.

## Decision

Manually resolved exceptions do **not** create fabricated recovery
options or recovery actions. Human-driven recovery is represented
independently:

```text
System path:
  Exception → feasible option → recommendation → approval
            → system execution → outcome

Human path:
  Exception → no feasible system recovery → human intervention
            (outside Adensa) → manual resolution recorded
            → outcome
```

A manual resolution is its own record — intervention type (carrier
call, carrier email, supplier/customer/internal coordination,
other), external party, agreed resolution summary, optional revised
expected delivery, notes, recorder, timestamp — stored in a
dedicated `manual_interventions` table, distinct from
`recovery_options` (system-evaluated candidates) and
`recovery_actions` (system-generated workflow items).

Safeguards, all enforced in the service layer:

- Eligibility: the exception must be open, and no system action may
  be `Pending Approval` or `Approved` — a manual resolution can
  never bypass or collide with the human-approval workflow
  (recording after a rejection is exactly the planner-takeover
  case and is allowed).
- The recorded outcome determines the resulting exception state:
  `Resolved` (guarded status update, stamped `resolved_at`) or
  `Still Open` (no status change — recording an intervention alone
  never resolves anything).
- Validation failures raise before any write; the intervention
  insert and the status update commit atomically.
- The shipment's operational record (its ETA) is intentionally left
  untouched: the recorded revised delivery is an attested plan, not
  a shipment mutation. If Adensa later ingests a carrier's revised
  ETA, that is an explicit operational-data decision, not a
  side effect.

## Rationale

Fabricating a recovery option or action for an externally
negotiated solution would corrupt exactly the data the system
exists to keep honest: option statistics would count solutions the
engine never evaluated, and actions would exist that no approval
workflow ever governed. A separate, auditable record keeps the two
paths conceptually distinct while keeping Adensa the operational
system of record.

## Consequences

Benefits:

- Option/action data reflects only system-evaluated/system-governed
  reality.
- The full externally-negotiated story is auditable: who recorded
  it, with whom, on what terms, and with what outcome.
- The history and control-tower views can present resolution paths
  honestly (system-executed vs manually resolved vs neutral).

Trade-offs:

- Two resolution representations must be kept conceptually separate
  in reporting and UI.
- Externally agreed outcomes are planner-attested rather than
  system-verified; the audit record is the evidence.

## Alternatives considered

- **Fake option/action rows for manual outcomes** — rejected: it
  pollutes engine evaluation data and fabricates workflow history.
- **Free-form notes on the exception** — rejected: unqueryable,
  unauditable structure, and it would blur the resolution-state
  rules.

## Current implementation

`app/repositories/manual_interventions_repo.py`,
`services.record_manual_resolution` and
`services.get_manual_interventions` in `app/services.py`,
`ManualInterventionNotAllowedError` in `app/errors.py`, the Human
Intervention section in `app/main.py`; behavior covered by the
manual-resolution tests and the UI manual-resolution AppTest
scenarios.
