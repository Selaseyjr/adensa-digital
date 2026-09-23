# P4 API gap — AI advisory decision brief

## Status

**Resolved** in Checkpoint P4.x.

The gap identified during P4 — the advisory AI decision brief existed in
the backend (`app/ai_support.py`, exposed to planners only through the
Streamlit client) while the `/v1` application boundary had no route for
it — is closed.

## Resolution

`GET /v1/exceptions/{exception_id}/decision-brief` (P4.x) exposes the
existing advisory capability through the versioned boundary:

- backed by `services.get_decision_brief` and the existing ai_support
  provider/validation contract — no second AI implementation;
- the deterministic decision engine remains the sole operational
  authority; the brief is advisory interpretation only;
- a missing exception is 404, distinguished from the structured
  unavailable advisory state (mirrors sustainability/interventions);
- explicit Pydantic response model (`DecisionBrief`); no internal
  objects, credentials or configuration cross the boundary;
- the brief is never persisted and no workflow or database state can
  change (pinned by `test_v1_decision_brief_does_not_mutate_workflow_or_database`).

The Next.js Investigation Workspace consumes the endpoint through the
typed API client (`web/lib/api/client.ts`); the P4 pending placeholder
was replaced by the real advisory section, which keeps its own failure
states without affecting the rest of the workspace.
