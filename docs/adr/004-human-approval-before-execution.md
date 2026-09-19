# ADR-004 — Human approval before system execution

## Status

Accepted

## Context

A recommendation is advice, not authority. If the system could
execute recoveries on its own — mutating shipments and recording
events — a scoring defect or bad feasibility rule would translate
directly into operational change with no human checkpoint, and no
attribution of the decision.

## Decision

System execution is gated by an explicit human decision. Recovery
actions move through a small explicit state machine:

```text
Pending Approval → Approved → Executed
                       ↘ Rejected (terminal)
```

- The recommendation engine produces advice only; it never executes
  anything and holds no authority over workflow state.
- Approval and rejection record **who** decided and **when**
  (actor, timestamp) on the action.
- Every transition is validated: only a `Pending Approval` action
  can be approved or rejected, and only an `Approved` action can be
  executed — exactly once. Invalid, out-of-order or duplicate
  transitions are refused with typed domain errors
  (`InvalidTransitionError`, `RecoveryWorkflowError` subtypes),
  surfaced as HTTP 409 at the API boundary.
- This optimistic state validation is also the concurrency guard:
  if two clients decide against each other, the first valid
  transition wins and the conflicting one is refused; a client
  retrying after a lost response cannot create a duplicate business
  action, because the re-submission hits the state guard.

## Rationale

Human-in-the-loop is the product's core operational premise:
recommendation supports the decision, the planner owns it. The
state machine keeps that premise enforceable in code rather than by
convention, and doubles as the idempotency mechanism external
integrations rely on (see ADR-007).

## Consequences

Benefits:

- Attribution and audit for every operational decision.
- Duplicate and conflicting submissions are structurally
  impossible, not just discouraged.
- Execution remains a distinct, separately validated step — the
  system cannot silently skip approval.

Trade-offs:

- Every recovery requires a human actor; there is no auto-approval
  path for low-impact cases (a deliberate scope boundary, revisitable).
- State-transition rules must be maintained as the workflow grows.

## Alternatives considered

- **Auto-execution of high-confidence recommendations** — rejected:
  it removes the human checkpoint that defines the product and
  complicates attribution.
- **Enforcing transitions only in the UI** — rejected: guards belong
  in the engine so every client (and any external integration)
  inherits them.

## Current implementation

`app/workflow_engine.py` (state machine, transition validation,
status constants), consumed via `services.approve_recovery` /
`services.reject_recovery` / `services.execute_approved_recovery`
in `app/services.py`; error types in `app/errors.py`.
