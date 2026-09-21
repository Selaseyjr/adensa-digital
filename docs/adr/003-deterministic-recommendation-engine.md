# ADR-003 — Deterministic recommendation engine

## Status

Accepted

## Context

Recovery recommendations must be inspectable and reproducible: an
operations team needs to see why a recommendation was made, and a
workflow system needs identical inputs to produce identical
decisions. The prototype also needs recommendations it can test
exactly.

## Decision

The decision engine is deterministic and configuration-driven. It
scores each feasible recovery option as a weighted sum of four
normalized components — cost, transit time, risk, and priority
alignment — using fixed weights from configuration:

```text
decision_score = cost_score      × w_cost      (0.25)
               + transit_score   × w_transit   (0.30)
               + risk_score      × w_risk      (0.25)
               + priority_score  × w_priority  (0.20)
```

Feasibility is decided earlier, by the recovery-option generator
against operational constraints; the engine only ranks feasible
options. Confidence is derived from the competitive situation: a
sole feasible option yields `High`; otherwise the gap between the
best and second-best score maps to `High` (≥ 15), `Medium` (≥ 7) or
`Low`. Each recommendation carries a human-readable reason stating
that factual basis (score separation), so the label is never
mistaken for a probability of success.

The full rationale is exposed to clients as a structured service
projection: the configured policy weights, each factor's raw fit
and weighted contribution for the recommendation and every
alternative, the factor-level trade-offs where an alternative
genuinely scores higher, and the basis of the confidence label.
The projection consumes the engine's own output and the single
`DECISION_WEIGHTS` source; it never recomputes or duplicates the
scoring model.

There is no LLM, machine-learning model or probabilistic component
anywhere in the recommendation path.

## Rationale

For an operational prototype, determinism is a feature:

- **Inspectability** — every score component is persisted and shown
  in the UI and API; a planner can audit exactly why option A beat
  option B.
- **Reproducibility** — the same option set always produces the
  same ranking, which makes workflow behavior, tests and
  demonstrations stable.
- **Testability** — scoring, confidence and reason are covered by
  exact assertions in the test suite, which would be impossible
  with a non-deterministic component.

Weights live in configuration, so operational priorities can be
tuned without touching engine logic.

## Consequences

Benefits:

- Transparent, auditable decision support that domain stakeholders
  can debate on its own terms (weights, thresholds).
- Exact reproducibility across UI, API and CLI.

Trade-offs:

- The model cannot learn from outcomes or handle relationships too
  subtle for the four components; recommendation quality is bounded
  by the configured weights and the generator's feasibility rules.
- Confidence reflects score separation, not real-world uncertainty.

## Alternatives considered

- **LLM-based or ML-based ranking** — deliberately deferred. It
  would undermine inspectability and exact testability in the
  current stage; AI-assisted decision support is listed as future
  direction, not current capability.
- **Simple rule pick (cheapest or fastest)** — rejected: it would
  discard the multi-criteria trade-off the operational domain
  actually requires.

## Current implementation

`app/decision_engine.py` (scoring, weighted contributions,
confidence, reason),
`app/config.py` (`DECISION_WEIGHTS`, cost benchmarks),
`app/generate_recovery_options.py` (feasibility evaluation upstream),
`app/services.py` (`get_recommendation_rationale` — structured
explainability projection).
