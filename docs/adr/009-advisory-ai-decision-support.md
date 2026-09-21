# ADR-009 — Advisory AI decision-support layer

## Status

Accepted

## Context

The recommendation path is deterministic and configuration-driven
(ADR-003): every score, weight, confidence band and trade-off is
inspectable and exactly testable. What the deterministic system
does not do is help a planner *read* an assessment quickly —
situations, factor interactions and verification points currently
have to be assembled mentally from the structured rationale.

Language models are appropriate for exactly this interpretation
work, but an LLM must never become a second decision engine:
autonomous option selection would destroy the inspectability,
reproducibility and testability that ADR-003 establishes, and no
model output may change operational state.

## Decision

Adensa adds a **strictly advisory** AI layer that sits above the
deterministic decision model, never inside it:

```text
Operational data
      ↓
Deterministic decision engine        ← sole decision authority
      ↓
Structured recommendation + rationale
      ↓
AI decision-support layer            ← advisory interpretation
      ↓
Planner-facing decision brief
      ↓
Human planner → existing workflow / execution
```

The boundary is enforced structurally:

- The AI provider is a callable that **receives structured
  evidence** (exception facts, the deterministic assessment, the
  rationale, the persisted history) and **returns a decision-brief
  dictionary**. It receives no connection, no repositories and no
  engines, so it cannot read or write the database and cannot
  transition any workflow state. Briefs are never persisted.
- Every provider output is validated before a planner sees it:
  required fields, string types, length bounds, the advisory
  disclaimer, no language claiming an action was approved,
  executed or resolved, and no operational identifier that does
  not exist in the supplied evidence. Invalid output degrades to
  an honest `unavailable` state — never silently trusted.
- The layer is **optional and failure-tolerant**: with no provider
  configured, a provider outage, a timeout or malformed output,
  the application reports
  "AI decision brief unavailable. Deterministic recommendation
  remains available." and every workflow function continues.
- Briefs are **planner-triggered** — one explicit button for one
  exception at a time. No automatic, periodic or per-page-render
  model calls.
- The shipped provider is a deterministic evidence summariser
  (no network, no credentials). A real external model provider
  can later implement the same callable interface; its credentials
  would come exclusively from the environment and its failures
  must surface as `AiProviderError`.

The model's role is fixed: **explain and contextualize an existing
deterministic decision** — never make, approve, execute or resolve
one. Approval, rejection and execution remain human actions
through the existing workflow state machine (ADR-004).

## Rationale

Separating *decision authority* from *decision explanation* lets
Adensa adopt AI assistance without giving up the properties that
make the recommendation path trustworthy: identical inputs still
produce identical decisions, tests still assert exact behaviour,
and the planner can always audit the deterministic rationale
independently of any AI narrative.

The evidence-in/evidence-out contract also makes fact-grounding
mechanical: the validator can prove that the brief introduces no
identifier the deterministic system never established, so
hallucinated options, carriers or events are rejected rather than
displayed.

## Consequences

Benefits:

- Planners get a fast, natural-language reading of a deterministic
  assessment, including verification points where evidence is
  incomplete.
- The advisory layer is swappable (built-in summariser today, an
  external model tomorrow) with no change to engines, services'
  contracts, workflow or schema.
- Failure of the AI layer can never degrade the operational core.

Trade-offs:

- The current built-in provider is deliberately not a language
  model, so its prose adds no interpretive ability beyond the
  structured evidence until a real provider is configured.
- Grounding validation is pattern-based: it guarantees identifier
  fidelity and forbids action claims, but nuanced factual errors
  in a future external provider's prose still require planner
  judgement — hence the permanent advisory labelling.

## Alternatives considered

- **LLM-as-decision-maker** — rejected: it would create a second,
  non-reproducible decision engine and undermine ADR-003.
- **Chat interface over operational data** — rejected as scope
  creep and an unbounded prompt-injection surface; the product
  need is a bounded brief, not conversation.
- **Storing generated briefs** — rejected: briefs are advisory
  renderings of evidence that already lives in the database;
  persisting them would create a second source of operational
  truth.

## Current implementation

`app/ai_support.py` (provider contract, brief validation,
deterministic built-in provider),
`app/services.py` (`build_decision_brief_evidence`,
`get_decision_brief` — injectable provider, graceful
unavailable state),
`app/main.py` ("AI Decision Brief" section, planner-triggered).
No external provider is configured yet; none is required for any
existing test.
