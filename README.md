# Adensa Digital

### Supply Chain Exception & Recovery Platform

> 🚧 **Work in Progress**

Adensa Digital is a digital supply-chain platform prototype designed to help operations teams **monitor international shipments, detect delivery exceptions, evaluate recovery options, and manage operational responses through structured workflows.**

The current prototype focuses on shipments moving between **Asia and Europe**.

---

## The Problem

When an international shipment is delayed, operations teams need to quickly understand the impact, evaluate alternatives, decide what to do, and execute the response.

Adensa Digital models this process as:

```text
Detect
  ↓
Assess
  ↓
Recommend
  ↓
Approve / Reject
  ↓
Execute
  ↓
Resolve
```

---

## Current Capabilities

The current version provides a functioning exception-to-recovery workflow:

* **Shipment visibility** — shipment status, carrier, transport mode, ETA and delivery requirements
* **Exception detection** — automatically identifies shipments at risk of missing required delivery dates
* **Recovery options** — evaluates alternative transport modes, carriers, cost, transit time, risk and feasibility
* **Decision engine** — ranks feasible recovery options using a weighted decision model
* **Human approval** — recommended actions require approval before execution
* **Recovery execution** — updates shipment information and records recovery events
* **Outcome evaluation** — determines whether the recovery action actually satisfies the delivery requirement
* **Operational interface** — Streamlit interface for monitoring, investigation and workflow management

---

## Architecture

The current system separates the major responsibilities of the platform:

```text
Database
   ↓
Business Logic
   ↓
Decision Engine
   ↓
Workflow Engine
   ↓
Execution Engine
   ↓
Streamlit Interface
```

This creates a foundation for progressively introducing more advanced automation and AI capabilities.

---

## Testing & Validation

The backend includes validation for:

* Database integrity and relationships
* Shipment and event consistency
* Exception generation
* Recovery-option feasibility
* Decision-engine recommendations
* Workflow state transitions
* Idempotency
* Recovery execution
* Backend integration

The current environment uses **synthetic supply-chain data** to simulate an international logistics network.

---

## Technology

`Python` · `SQLite` · `Pandas` · `Streamlit` · `Git` · `GitHub`

---

## What's Next

The current release establishes the **deterministic digital supply-chain foundation**.

The next development stage will introduce:

* AI-assisted decision support
* AI-generated operational reasoning
* Agentic workflow orchestration
* Predictive shipment-risk detection
* Real-time logistics integrations
* ERP / SAP integration
* Carrier and logistics APIs

The longer-term vision is to explore how **data, workflow automation, AI and enterprise systems can work together to improve supply-chain decision-making and execution.**

---

## Project Status

**Active Development**

This is an evolving portfolio project. The current version demonstrates the operational and workflow foundation, while future versions will progressively introduce AI and agentic capabilities.

---

## Author

**Selasey Junior Gbeddy**

Focused on:

**Digital Supply Chain Systems · Supply Chain Planning · ERP / SAP · Workflow Automation · AI & Agentic Systems**

📌**Project Links**

Live Application:
adensa-digital-systems.streamlit.app

Source Code:
GitHub Repository — Selaseyjr/adensa-digital

> **Understand the system. Improve the workflow. Build what comes next.**