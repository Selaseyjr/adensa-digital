# Adensa Digital — Operational Demo Walkthrough

This walkthrough shows how Adensa handles a shipment exception from
detection through to a recorded operational outcome, using the
application's own controlled simulation and the real user interface.
It takes about five minutes to follow.

Two scenarios are shown:

- **Scenario A — System-assisted recovery:** an exception with a
  feasible recovery option is recommended, approved by a planner,
  executed by the system — and **still stays open**, because the
  executed recovery does not fully fix the delivery problem.
- **Scenario B — Human intervention:** an exception with no feasible
  system recovery is resolved through a recorded manual intervention
  instead.

Together they demonstrate the most important rule in the product:

> **Executed does not mean resolved.** Adensa evaluates the recovery
> action and the delivery outcome separately, and never marks an
> operational problem as resolved just because an action was taken.

---

## 1. The operational lifecycle

Adensa models the lifecycle an operations team actually works through:

```text
Detect → Assess → Recommend → Approve / Reject → Execute / Intervene → Outcome
```

- **Detect** — the operational pipeline compares shipment arrival
  estimates against customer-required delivery dates and records
  exceptions with a severity.
- **Assess** — the recovery engine generates and evaluates recovery
  options (alternative transport mode, carrier, cost, transit time,
  risk) and marks each feasible or infeasible.
- **Recommend** — the decision engine scores the feasible options
  with a weighted model and produces a recommendation with a score,
  a confidence level and a reason.
- **Approve / Reject** — a named planner makes the decision. The
  recommendation engine never executes anything itself.
- **Execute / Intervene** — the system executes an approved recovery
  action; or, when no feasible system recovery exists, a planner
  records a manual intervention.
- **Outcome** — the resulting shipment state is evaluated against the
  required delivery date, and the exception becomes **Resolved** or
  **remains Open** accordingly. The full sequence is recorded in the
  exception's operational history.

---

## 2. Scenario A — System-assisted recovery (Executed → Still Open)

The values below were all produced by a validated run of the current
application. A fresh database will show different shipment and
exception identifiers, but the same journey and the same behaviour.

### Start the application

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

On first run the application initializes its SQLite database
automatically (schema, master data, the operational dataset, then
exception detection, recovery options and workflow actions). Later
starts reuse the existing database.

### Simulate a shipment arrival

In the sidebar, under **Simulation**, press
**Simulate Shipment Arrival**.

This is a controlled data-arrival mechanism, not a random demo effect:
it records one new shipment — with its shipment events — whose
estimated arrival is deliberately later than the customer's required
delivery date. Everything else (the exception, the recovery options,
the recommendation) is produced afterwards by the real operational
pipeline. A success banner confirms the arrival, for example:

```text
SHP-SIM-0001 arrived · 2 events recorded
```

### Refresh the operational pipeline

In the sidebar, under **Operations**, press
**Refresh Operations Pipeline**.

This runs the real detection → options → actions pipeline over the
new data and reports what it created, for example:

```text
Detected 1 new exceptions · 3 new recovery options · 1 new workflow actions
New exceptions: EXC-001529
```

When a single new exception is detected, the app focuses it
automatically in the inbox.

### Discover the exception in the inbox

The **Exception Inbox** lists open exceptions as triage rows of the
form:

```text
EXC-001529 — High · Delivery Delay · Actionable
```

The queue is ordered so the newest **actionable** work (exceptions
with at least one feasible recovery option) surfaces first; rows
without a feasible option are labelled **No feasible recovery** and
queued behind the actionable work. The inbox is bounded to 100 rows
so the control tower stays usable at scale.

### Investigate

Selecting the exception opens **Exception Details**: route, shipment,
order, customer, priority, current transport mode, estimated arrival,
required delivery date and estimated impact. For a newly simulated
shipment this shows the delivery problem at a glance — the estimated
arrival is 6 days past the required delivery date.

### Review the recovery assessment and recommendation

The **Decision Engine** section shows the assessment. Where feasible
options exist, Adensa presents:

- **Recommended Recovery** — transport mode, carrier, estimated cost,
  transit time, risk score, decision score, confidence and the
  reason for the confidence level. These values are produced by a
  deterministic, config-driven scoring model (cost, transit, risk and
  priority-alignment weights) — this is decision support, not AI.
- **Recovery Options Comparison** — every feasible option as a
  comparable row in the engine's own ranking.

A planner can see exactly why an option was recommended and what the
alternatives cost. Adensa recommends; the planner decides.

### Approve the recovery

Under **Workflow Action**, enter an approver name and press
**Approve Recovery**. The action is a controlled workflow transition
(`Pending Approval → Approved`) recorded with the actor and the
timestamp, and the action's status is shown on screen.

Approval is a decision, not a promise: it does not itself change the
shipment or resolve the exception.

### Execute the recovery

Once approved, the workflow panel offers **Execute Recovery**. The
system performs the recovery — updating the shipment, switching the
transport mode and carrier — and records a recovery event.

### The outcome: executed, but still open

The **Latest Workflow Outcome** panel reports the result, and this is
the key moment of the demo. In the validated run, the exception had
exactly one feasible option (Road, 4 days transit). Executing it
moved the shipment's estimated arrival from 2026-08-27 to 2026-08-26 —
but the required delivery date was 2026-08-25, so the outcome panel
shows:

```text
Action: ACT-000819   Shipment: SHP-04891   Exception Status: Open
New ETA: 2026-08-26          Required Delivery: 2026-08-25
"The recovery action was executed, but the shipment still requires
 further recovery."
```

The exception is **not** marked resolved. It stays in the inbox, the
control tower does not count it under Recently Resolved, and the
workflow panel states that the action has already been executed. The
system separated two questions on purpose:

1. *Did the recovery action execute?* — yes.
2. *Does the shipment now meet the required delivery date?* — no.

When an executed recovery does satisfy the required date, the same
panel shows `Exception Status: Resolved` with the opposite message —
the evaluation, not the action, decides.

### Review the operational history

The **Operational History** section reconstructs the lifecycle from
real persisted records — no invented events. The validated run shows,
in sequence: exception detection (with the delivery arithmetic),
recovery-option evaluation (how many options were assessed and how
many were feasible), the recommendation (with cost, transit and risk),
the approval (with the planner's name), the execution, and the
current status — *open and monitored until recovery is recorded*.

---

## 3. Scenario B — Human intervention (no feasible system recovery)

Many open exceptions have no recovery option that satisfies the
operational constraints — for example, no alternative transport is
fast enough to make the required delivery date. For these, Adensa
never fabricates a recovery option or a fake execution. It offers a
separate, auditable human path.

Selecting such an exception in the inbox shows it labelled
**No feasible recovery**. The Decision Engine section reports:

```text
No recovery recommendation is currently available.
```

together with any options the engine evaluated and rejected, and:

```text
This exception remains open and is monitored.
```

Under **Human Intervention**, the planner records what actually
happened outside the system:

- **Intervention method** — carrier call, carrier email, supplier,
  customer or internal coordination, or other.
- **External party** and the **agreed resolution**, in factual text.
- An optional **new expected delivery** date.
- The **Outcome** — `Resolved` or `Still Open`.
- Who recorded it.

Saving records the intervention with an identifier, the recorder and
the timestamp — for example:

```text
INT-000001 recorded · Carrier call · Resolved
```

The exception's status follows the recorded outcome: `Resolved` moves
it out of the inbox and into **Recently Resolved** (marked *Manually
resolved*), while `Still Open` keeps it under monitoring. No recovery
options, actions or executions are created for this path — the
manual intervention is its own auditable record, visible in the
exception's Operational History.

---

## 4. What the demo demonstrates

- **Deterministic recommendation.** The decision engine is
  config-driven and reproducible: the same options always produce the
  same score, confidence and reason. It is inspectable decision
  support, not an opaque or AI-based ranker.
- **Human approval before system execution.** Recommendations never
  execute themselves; only an approved action can be executed, and
  the approving actor is recorded.
- **Executed does not mean resolved.** Execution and resolution are
  evaluated separately against the required delivery date, and a
  still-late shipment is shown as still open — including in the
  control tower's counts.
- **Manual resolution is a separate path.** Externally negotiated
  outcomes are recorded as manual interventions with their own audit
  trail; no fake recovery data is created.
- **Factual operational history.** Every lifecycle step shown is
  reconstructed from persisted records, with actors and timestamps.
- **Adensa is the operational source of truth.** All state —
  exceptions, options, decisions, executions, interventions,
  outcomes — lives in Adensa's own database behind its service layer.

---

## 5. Demo reproduction

1. Install dependencies and start the UI:
   `pip install -r requirements.txt` then `streamlit run streamlit_app.py`.
2. Press **Simulate Shipment Arrival**.
3. Press **Refresh Operations Pipeline**.
4. Select the newly detected exception (auto-focused) in the
   **Exception Inbox**.
5. Review the recommendation, approve as a named planner, execute.
6. Observe the outcome panel: on the fresh bootstrap dataset the
   simulated shipment's recommended recovery is fast enough to
   satisfy the required delivery date, so this journey ends
   **Resolved** — the still-open outcome shown in Scenario A above
   occurs whenever the feasible options cannot beat the required
   date. Several of the exceptions already in the operational
   dataset behave exactly this way: execution moves the ETA
   forward, but past the required delivery date.
7. For the human path, select an exception labelled
   **No feasible recovery** and record a manual resolution.

Notes on what this demo is and is not:

- The shipment-arrival simulation is controlled application data
  within Adensa's own database. It does not represent real external
  carrier integrations.
- The journeys above were validated against an isolated database
  initialized through the application's real bootstrap, and the
  UI-level lifecycle is covered by the automated Streamlit AppTest
  suite; nothing in this document requires modifying production data.

---

## 6. Architecture boundary

The demo is the layered architecture, visible end to end:

```text
Streamlit / FastAPI / CLI
        ↓
Application Services      (app/services.py — the application boundary)
        ↓
Business Engines          (detection, recovery, decision, workflow, execution)
        ↓
Repositories              (all SQL / data access)
        ↓
SQLite
```

The Streamlit UI is a pure service consumer: it contains no SQL, no
repository access and no business rules. The FastAPI service and the
CLI are sibling clients of the same service layer, and the API is the
boundary used by external orchestration:

```text
Adensa API (X-API-Key)
        ↓
Power Automate (external orchestration layer)
        → notifications, approvals, follow-ups, escalations
```

Adensa owns operational truth throughout; Power Automate would only
orchestrate communication and human interaction around the API. The
integration contract and its executable tests exist in this
repository (`docs/power-automate-integration.md`); the actual
Microsoft 365 / Power Automate tenant flow is **not yet deployed**.

---

## 7. Current limitations

- The Power Automate tenant flow is not yet deployed; only the
  Adensa-side API boundary and integration contract exist.
- Enterprise identity (SSO / Entra ID / OAuth / JWT / RBAC) is not
  implemented; the API is protected by a prototype API-key mechanism.
- The recommendation engine is deterministic and rule-based, not
  AI/ML-based.
- The application is a prototype: it runs locally against SQLite and
  is not a production cloud deployment.

---

## 8. A note on the control-tower counts

The control tower's **Open**, **Pending Decisions**, **Awaiting
Execution**, **Critical Open** and **Recently Resolved** figures are
full-population counts. The **Actionable** and **Monitoring** figures
describe the bounded inbox work-queue surface (the first 100 rows the
planner can actually see and act on), not the entire open population
— on a large dataset the total actionable population is larger than
the inbox can display. The distinction is deliberate and documented in
the service layer; reconciling those two counts is a known future
improvement.
