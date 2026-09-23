# P4 API gap — AI advisory decision brief is not exposed via /v1

## Status

Reported during Checkpoint P4 — not worked around, not implemented ad hoc.

## Gap

```text
Existing endpoint:      (none) — the /v1 boundary has no AI-advisory route
Required information:   the advisory AI decision brief that app/ai_support.py
                        already produces for an exception (situation summary,
                        recommendation explanation, trade-offs, verification
                        points)
Why insufficient:       Checkpoint U's advisory AI layer is reachable only
                        from the Streamlit client through app/services.py /
                        app/main.py; ADR-011 established /v1 as the versioned
                        application boundary, so the Next.js client cannot
                        obtain the brief without bypassing that boundary.
Why not worked around:  the P4 checkpoint forbids ad-hoc frontend
                        implementations of unexposed backend capabilities and
                        forbids new endpoints in this checkpoint; a capability
                        must cross the boundary through a contract, not a
                        side door.
Smallest backend change required: one protected read endpoint
                        GET /v1/exceptions/{exception_id}/decision-brief
                        with an explicit Pydantic response model mirroring
                        the existing structured ai_support.py output,
                        following the ADR-011 response-contract pattern;
                        advisory-only framing (non-authoritative, never the
                        system of record) documented in the ADR that
                        introduces it.
```

## Interim P4 behavior

The workspace renders the AI Advisory section as an explicitly pending
section: advisory briefs are not yet available through the API boundary,
and the deterministic recommendation remains the authoritative decision
support. No fabricated advisory content is displayed.

## Future checkpoint

Expose `/v1/exceptions/{exception_id}/decision-brief` (P2-style response
contract + tests), then render the real brief in the workspace's AI
Advisory section, subordinate to the deterministic recommendation.
