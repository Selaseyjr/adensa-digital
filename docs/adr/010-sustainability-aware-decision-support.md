# ADR-010 — Sustainability-aware decision support

## Status

Accepted

## Context

Adensa's recovery comparison ranks options by operational fit
(cost, transit, risk, priority — ADR-003), but transport decisions
also have environmental consequences a planner cannot currently
see. Choosing between an air and a rail recovery is materially
different in emissions terms, yet the investigation view is silent
on this dimension.

The checkpoint constraint is explicit: sustainability must become
a **decision-support dimension**, not a fifth decision factor.
The deterministic recommendation, weights, confidence and workflow
remain exactly as they were; the system must answer *"what is the
environmental trade-off of this operational decision?"* without
yet answering *"which option should the system choose because it
is greener?"*

## Decision

Adensa adds a pure, offline, deterministic sustainability layer
that estimates **transport CO₂e** for the recommendation and each
feasible alternative using the transparent formula:

```text
estimated CO₂e (kg) = shipment tonnes
                    × route kilometres
                    × mode emissions factor
```

- **Physical inputs are persisted facts**: `shipments.weight_kg`
  (converted kg → tonnes, 1000 kg = 1 t) and
  `shipments.distance_km` — the route distance Adensa already
  records. No coordinates, distance mapping or routing service is
  introduced; no external routing or emissions API is called.
- **Emissions factors are explicit prototype assumptions**, not
  measured data: `TRANSPORT_EMISSIONS_FACTORS` in `app/config.py`
  (kg CO₂e per tonne-kilometre; Air 0.60, Road 0.10, Rail 0.028,
  Sea 0.015), centralized beside `DECISION_WEIGHTS` and labelled
  in the UI as `Prototype sustainability estimate`. Only the four
  transport modes Adensa actually operates are listed; an
  unsupported mode raises instead of silently estimating zero.
- **Invalid inputs fail safely**: missing/zero/negative weight or
  distance produce an honest unavailable state, never a
  misleading estimate.
- **Nothing is persisted**: estimates are recomputed on demand
  (deterministic, so recomputation equals storage); no emissions
  table, no schema change.
- **The comparison is factual, not moralizing**: per-alternative
  `Higher`/`Lower`/`Similar` relative to the recommendation with
  the numeric `difference_kg` in CO₂e, plus the lowest-emission
  feasible option. No "green"/"dirty" language.

## Rationale

The same persisted data that drives cost and transit assessment
(weight, distance, mode) is sufficient for a transparent
emissions estimate, so the feature requires no new data
collection, no external service, and no trust in black-box
numbers — every figure in the UI can be traced to
`tonnes × km × configured factor`.

Keeping the layer out of the decision engine preserves the
properties ADR-003 was built on: identical inputs still produce
identical recommendations, and the operational policy remains
the single, auditable authority while the sustainability
evidence matures.

## Consequences

Benefits:

- Planners see the environmental trade-off of each recovery
  option next to the operational trade-off, in the same
  investigation view.
- The projection is structured evidence, ready to feed the
  advisory AI layer (already wired additively into the Checkpoint
  U evidence builder) or a future decision-weight revision.

Trade-offs / limitations:

- The factors are prototype magnitudes reflecting the correct
  modal ordering, not measured emission rates; absolute values
  are indicative and must not be read as carbon accounting.
- The estimate covers transport only (no warehousing, no
  well-to-wheel nuances, no modal-shifting second-order effects).
- Because the recommendation does not yet weigh emissions, the
  lowest-emission option may not be the recommended one — this
  is surfaced factually as a trade-off, not corrected silently.

## Alternatives considered

- **Fifth decision factor now** — rejected for this checkpoint:
  weights and confidence semantics would change without a
  validated measurement foundation; explicitly deferred.
- **External routing/emissions APIs** — rejected: breaks the
  deterministic, offline, cheap-to-run prototype constraints.
- **Persisting calculated emissions** — rejected: deterministic
  recomputation is always equivalent; a stored value would risk
  drifting from its inputs.

## Current implementation

`app/sustainability.py` (pure calculation + comparison),
`app/config.py` (`TRANSPORT_EMISSIONS_FACTORS`, unit and
methodology strings),
`app/repositories/shipments_repo.py`
(`get_shipment_emissions_inputs` — read-only projection),
`app/services.py` (`get_sustainability_comparison`; additive
`sustainability` key in the AI evidence builder),
`app/main.py` ("Sustainability Impact" section).
