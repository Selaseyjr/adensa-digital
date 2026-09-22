# Adensa Digital

Adensa Digital is a digital supply-chain exception-management prototype: a control tower that turns shipment exceptions into structured operational decisions and recorded outcomes. It models the full lifecycle an operations team actually works through — detect, assess, recommend, decide, execute or intervene, and record what happened — on top of a layered Python service architecture with a Streamlit operations UI, a secured FastAPI boundary, and a CLI.

```text
Detect → Assess → Recommend → Execute / Intervene → Outcome
```

## Overview

When an international shipment is going to miss its required delivery date, an operations team has to answer several questions quickly: how bad is it, what are the realistic recovery options, which option best balances cost, transit time and risk, who decides, and did the recovery actually work?

Adensa Digital models that process end to end:

- **Shipment exceptions** are detected from operational shipment and event data (for example, a projected arrival later than the customer's required delivery date).
- **Recovery options** are evaluated against operational constraints — alternative transport modes, carriers, cost, transit time and risk — and each option is marked feasible or infeasible.
- A **decision engine** ranks the feasible options with a weighted scoring model and expresses a recommendation with a score, confidence level and reason.
- A **human planner** approves or rejects the recommendation; Adensa records who decided and when.
- The recovery is either **executed by the system** (updating shipment state and recording recovery events) or **resolved by a human** outside the system when no feasible system option exists — in which case the planner records the intervention and outcome in Adensa.
- Everything is **persisted**: exceptions, options, actions, decisions, executions, interventions, and the resulting exception state.

The prototype runs on a synthetic Asia–Europe logistics dataset (orders, shipments, carriers, customs and transit events) so the whole journey is reproducible from a clean database.

## Key capabilities

Verified functionality in the current repository:

- **Exception detection** — rule-based detection of delivery-delay exceptions with a severity ladder (Low/Medium/High/Critical), impact estimation and duplicate-detection guards.
- **Recovery assessment** — evaluates candidate recovery options (Air/Road/Rail/Sea alternatives) with cost, transit time, carrier and risk; options that fail operational constraints are recorded as evaluated-but-infeasible rather than silently dropped.
- **Recommendation engine** — weighted multi-criteria scoring of feasible options, producing a ranked recommendation with decision score, confidence band and a human-readable reason, plus ranked alternatives.
- **Human approval workflow** — explicit Pending Approval → Approved/Rejected transitions with actor attribution, timestamps and optimistic state guards that reject invalid or duplicate transitions.
- **System execution** — executes an approved recovery: updates the shipment's mode/ETA, records a shipment event, and evaluates the operational outcome.
- **Manual resolution** — when no system-generated option is feasible, a planner can record an externally negotiated intervention (method, external party, agreed resolution, optional revised delivery, outcome) as a distinct, auditable resolution path.
- **Operational history** — a chronological, evidence-based timeline per exception: detection, option evaluation, decisions (with actor), executions, interventions and the current outcome.
- **Control tower** — an at-a-glance operational summary: open exceptions split into actionable vs monitoring, pending decisions, actions awaiting execution, critical exceptions, and recently resolved outcomes with their resolution path.
- **Three clients, one boundary** — Streamlit UI, FastAPI API and CLI all consume the same application service layer; no client contains SQL or business rules.
- **Controlled data-arrival simulation** — a deterministic development mechanism that creates a new shipment arrival so the full pipeline (detect → recommend → decide → execute) can be demonstrated on demand.
- **Automated testing** — 178 tests covering repositories, services, engines, workflow lifecycles, the API contract, the Streamlit UI (Streamlit AppTest) and the external integration contract, all on isolated temporary databases.
- **CI** — GitHub Actions runs compile checks and the full test suite on every push.

## Architecture

Adensa is a strictly layered application. The service layer is the application boundary: every client (UI, API, CLI) delegates to it, and it delegates to engines and repositories. Repositories own all SQL and data access; engines own the business rules.

```mermaid
flowchart TD
    UI["Streamlit UI<br/>app/main.py"] --> SVC
    API["FastAPI API<br/>app/api.py"] --> SVC
    CLI["CLI<br/>app/cli.py"] --> SVC
    SVC["Application services<br/>app/services.py"] --> ENG["Business engines<br/>detect / options / decision /<br/>workflow / execution / simulation"]
    SVC --> REPO["Repositories<br/>app/repositories/*"]
    ENG --> REPO
    REPO[("SQLite<br/>data/adensa.db")]
```

| Layer | Responsibility |
|---|---|
| Presentation (Streamlit / FastAPI / CLI) | Rendering, request handling, input validation. No SQL, no business rules. |
| Application services | Orchestration, application-level projections (control tower, operational history), transaction boundaries for service-owned operations, typed error translation. |
| Business engines | Domain rules: detection, option generation, decision scoring, workflow transitions, execution, simulation. |
| Repositories | All SQL and data access. Read/write functions per aggregate; no business logic. |
| Database | SQLite with foreign-key enforcement; schema created idempotently by the production initializer. |

Workflow state is a small explicit state machine on recovery actions: `Pending Approval → Approved → Executed`, plus `Rejected` as a terminal alternative. Domain failures are typed (`RecoveryWorkflowError` and subtypes) and mapped to HTTP 409/404 at the API boundary.

## Operational workflow

There are two legitimate resolution paths, and Adensa keeps them conceptually distinct.

**System-driven recovery** — when at least one feasible recovery option exists:

```text
Exception detected
  → Recovery options evaluated
  → Recommendation (score · confidence · reason)
  → Human approval or rejection
  → System execution (shipment update + recovery event)
  → Outcome evaluation
```

**Human-driven recovery** — when every evaluated option is infeasible:

```text
Exception detected
  → Recovery options evaluated, none feasible
  → Human intervention outside Adensa (carrier call, negotiation, coordination)
  → Manual resolution recorded in Adensa (method, party, outcome, actor)
  → Outcome recorded
```

An important operational honesty rule: **executed does not necessarily mean resolved.** A system-executed recovery produces a new estimated arrival; only when that arrival satisfies the required delivery date does the exception become `Resolved`. Otherwise the action is `Executed` while the exception remains open and monitored — and the UI reports it that way. Resolution through the human path happens only when the planner explicitly records a `Resolved` outcome; recording an intervention with a `Still Open` outcome never resolves anything.

## API

The FastAPI boundary (`app/api.py`) exposes the service layer over HTTP. All operational endpoints require an `X-API-Key` header; only the health probe is public. Keys are sourced from the environment (`ADENSA_API_KEY`); an unconfigured key fails closed.

**Machine-to-machine integration API** (the Power Automate contract, kept unchanged):

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness (public) |
| GET | `/ready` | Readiness — verifies the configured database is reachable (public) |
| GET | `/metrics` | Operational KPI counts |
| GET | `/exceptions` | Open-exception inbox with severity and actionability |
| GET | `/exceptions/{exception_id}/review` | Decision-engine review: recommendation, alternatives, infeasible-option assessment |
| GET | `/exceptions/{exception_id}/actions/latest` | Latest workflow action and its state |
| POST | `/exceptions/{exception_id}/approve` | Record a planner approval |
| POST | `/exceptions/{exception_id}/reject` | Record a planner rejection |
| POST | `/recovery-actions/{action_id}/execute` | Execute an approved recovery |

**Versioned application boundary** (`/v1` — the workspace capability surface, ADR-011):

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/control-tower/summary` | Control-tower projection: bounded-queue and full-population metrics, follow-up and resolved queues |
| GET | `/v1/exceptions/inbox` | The operational work queue (actionable first, then newest detected) |
| GET | `/v1/exceptions/{exception_id}/context` | Investigation context (Situation & Impact) |
| GET | `/v1/exceptions/{exception_id}/state` | Persisted-evidence investigation state |
| GET | `/v1/exceptions/{exception_id}/history` | Chronological operational history |
| GET | `/v1/exceptions/{exception_id}/assessment` | Recovery assessment: recommendation, alternatives, rationale — or evaluated options explaining why none exists |
| GET | `/v1/exceptions/{exception_id}/sustainability` | Informational emissions comparison (or the structured unavailable state) |
| GET | `/v1/exceptions/{exception_id}/interventions` | Recorded manual interventions |
| POST | `/v1/exceptions/{exception_id}/manual-resolution` | Record a planner-performed manual resolution |
| POST | `/v1/operations/refresh` | Run the operational pipeline (detect → options → actions) |
| POST | `/v1/operations/simulate-arrival` | Create one controlled simulated shipment arrival |

Every operational read under `/v1` returns an explicit Pydantic schema mirroring the service output, so the whole workspace capability set is documented in the generated OpenAPI. Service results are ordinary JSON-compatible structures — no persistence-layer types cross the boundary. Domain errors map to HTTP semantics: missing resources to 404, invalid workflow transitions and domain-rule violations to 409, with the engine's message preserved. See `docs/api-authentication.md` for the authentication contract.

## CLI

The CLI (`app/cli.py`) provides terminal access to the same services:

```text
python -m app.cli workflow    # workflow summary and recent recovery actions (default)
python -m app.cli decision    # run the decision engine across all open exceptions
python -m app.cli execution   # execution-engine load check (no action executed)
```

## Testing and engineering

The test suite (178 tests) runs entirely on isolated temporary databases built with the production schema initializer and deterministic fixtures; the development database is never touched by tests.

- **Repository tests** — data-access contracts for every repository read/write.
- **Service tests** — orchestration contracts: review, approval, rejection, execution outcomes, manual resolution, operational refresh, history.
- **Engine and lifecycle tests** — detection rules, decision scoring, workflow transitions and idempotency, execution branches (resolved vs still open), bootstrap idempotence.
- **API contract tests** — endpoint behavior, error mapping, and the `X-API-Key` security boundary (missing/invalid/unconfigured key, fail-closed behavior, no mutation on rejected requests).
- **Streamlit AppTest tests** — the real UI executed headlessly: control-tower render, exception investigation, approval → execution, still-open honesty, rejection, manual resolution paths, resolved visibility, history, and the quiet-database state.
- **Integration contract tests** — the exact request sequence an external orchestrator performs against the API (poll → select → review → decide → execute → read back → outcome), including timeout/re-read and duplicate-mutation protection.
- **Database validation** — schema, foreign keys, referential integrity and shipment/event consistency validators.

CI (GitHub Actions, Linux, Python 3.14) installs both dependency sets, byte-compiles the codebase and runs the full suite on every push.

## Power Automate integration

Adensa exposes the API boundary required for a Microsoft Power Automate orchestration flow, and the repository contains the integration contract, executable request-sequence tests and build documentation (`docs/power-automate-integration.md`).

The intended relationship:

- **Adensa** is the operational source of truth: exception state, recovery options, recommendation, workflow validation, execution, outcomes, audit and history.
- **Power Automate** (external) is the polling, notification, human-approval and follow-up layer: it reads Adensa's API, presents approval requests, calls the mutation endpoints with the human decision, and reports the outcome Adensa returns.

Adensa itself does not send emails or Teams messages, and Power Automate never decides what is operationally valid — every decision it submits is revalidated by Adensa's workflow guards.

**Status:** the Adensa-side boundary, contract tests and documentation are complete and CI-verified. The actual Microsoft 365 / Power Automate tenant flow is **not yet deployed**; assembling and running it requires tenant access and is documented as an operator step.

## Project structure

```text
streamlit_app.py            # Streamlit entry point (initializes, then runs the UI)
app/
  main.py                   # Streamlit operations UI
  api.py                    # FastAPI boundary
  cli.py                    # CLI (workflow / decision / execution)
  services.py               # Application service layer (the application boundary)
  errors.py                 # Typed domain errors
  bootstrap.py              # Environment initialization (idempotent)
  database.py               # Connection factory and schema DDL
  config.py                 # Configuration (paths, API key)
  detect_exceptions.py      # Exception detection engine
  generate_recovery_options.py  # Recovery-option evaluation engine
  decision_engine.py        # Recommendation scoring engine
  workflow_engine.py        # Approval/rejection state machine
  execution_engine.py       # Recovery execution and outcome evaluation
  simulation.py             # Deterministic data-arrival simulation
  generate_data.py          # Synthetic dataset generator (master + operational data)
  repositories/             # All SQL and data access
    exceptions_repo.py · recovery_options_repo.py ·
    recovery_actions_repo.py · manual_interventions_repo.py ·
    shipments_repo.py
docs/
  api-authentication.md     # API-key authentication contract
  power-automate-integration.md  # External orchestration integration contract
tests/                      # 178 automated tests (pytest + Streamlit AppTest)
```

## Getting started

Requirements: Python 3.14.

```bash
# 1. Install dependencies
pip install -r requirements.txt
pip install -r requirements-api.txt   # only needed to run the API

# 2. Run the Streamlit application
streamlit run streamlit_app.py
```

On first run the application initializes its SQLite database automatically: schema, synthetic master data, the operational dataset (orders, shipments, events), then exception detection, recovery-option generation and workflow actions. Subsequent starts reuse the existing database without regenerating it.

```bash
# Run the API locally
uvicorn app.api:app

# Run the CLI
python -m app.cli workflow

# Run the test suite
pytest

# (Optional) regenerate the synthetic dataset from scratch
python -m app.generate_data
```

## Configuration

| Variable | Purpose |
|---|---|
| `ADENSA_API_KEY` | API key required by all operational FastAPI endpoints. Supplied through the environment; never hard-coded or committed. If unset, the API fails closed for protected routes while `/health` and `/ready` stay available. |
| `ADENSA_CORS_ORIGINS` | Comma-separated list of browser origins allowed to call the API from a separately hosted frontend (CORS). Empty by default — no browser origin is trusted unless the deployment configures one; machine-to-machine callers are unaffected. |

No secrets are stored in the repository.

## Current status and future direction

**Implemented today:** everything described above — the full two-path exception lifecycle, control-tower visibility, three clients over one service boundary, the secured machine-to-machine API plus the versioned `/v1` application boundary with explicit response contracts, the external integration contract, and a CI-gated test suite.

**Architecture progression:**

```text
Streamlit prototype
        ↓
service / domain architecture
        ↓
versioned FastAPI application boundary   ← current (ADR-011)
        ↓
Next.js operational frontend             ← future
        ↓
PostgreSQL + migrations                  ← future
        ↓
authentication / deployment hardening    ← future
```

**Not implemented (future direction):** deployment of the actual Power Automate tenant flow, Teams/email notification delivery, enterprise identity (SSO / Microsoft Entra ID, OAuth/JWT, RBAC), the dedicated web frontend, PostgreSQL with schema migrations, production cloud deployment and hardening, event-driven integrations at scale, and a real AI provider behind the advisory boundary. These are directions for future development, not current capabilities.

## Author

**Selasey Junior Gbeddy** — digital supply-chain systems, supply-chain planning, ERP/SAP, workflow automation and integration engineering.

Source code: [github.com/Selaseyjr/adensa-digital](https://github.com/Selaseyjr/adensa-digital)
