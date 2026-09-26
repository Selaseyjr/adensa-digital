# ADR-013 — Retire the Streamlit reference client

## Status

Accepted

## Context

ADR-001 and ADR-002 established a layered architecture in which the original
Streamlit application was decomposed into services, engines and repositories,
with the UI reduced to a pure service consumer. ADR-011 later versioned the
FastAPI boundary as the application contract, and the Next.js operational
client (`web/`) was built against it incrementally (P7–P9). Throughout that
migration Streamlit (`app/main.py`, entry point `streamlit_app.py`) remained
in the repository as the reference client, explicitly "temporarily available"
in both READMEs.

The P9.2 retirement audit compared every user-facing Streamlit capability
against the current Next.js client and found complete parity — in most cases
the Next.js surface exceeds its Streamlit counterpart:

- **Control Tower** — all summary metrics, plus analytical visualizations and
  KPI deep links that Streamlit never had (P8.3, P8.7, P8.8).
- **Exception Inbox** — the bounded work queue plus search, severity/verdict/
  workflow-state filtering, sorting and URL-driven state (P8.2, P8.8), none of
  which existed in Streamlit's selectbox-driven queue.
- **Investigation Workspace** — exception context, investigation state,
  decision support with sustainability comparison, AI decision brief,
  operational history and manual-intervention evidence (P8.4).
- **Workflow actions** — approve (with planner attribution), reject, execute
  and the full manual-resolution path, driven through server actions to the
  same mutation contracts Streamlit called directly.
- **Operations** — simulated shipment arrival and the operational pipeline
  refresh, including the preserved single-new-exception investigation
  affordance (P9.1).

No user-facing capability remained Streamlit-only at the time of this
decision.

## Decision

The Streamlit reference client is **retired and removed** from the repository:

- Deleted: `streamlit_app.py`, `app/main.py`,
  `tests/test_ui_apptest.py`, `tests/ui_entry.py`.
- Removed: the `streamlit` runtime dependency, the Streamlit entry point from
  CI's compile-check target list, and the Streamlit installation/startup
  commands from the devcontainer configuration.
- Updated: only the active documentation (root README, `web/README.md`,
  `docs/demo-walkthrough.md`). Historical ADRs (001, 002, 011, 012) are
  decision records of their time and are deliberately left unchanged; this
  ADR is the record of the retirement.

The FastAPI `/v1` boundary and the CLI remain the non-browser access paths;
the Next.js client is the primary user-facing surface.

## Consequences and trade-offs

- **Loss of the real-backend UI test layer.** The 19 Streamlit AppTest tests
  in `tests/test_ui_apptest.py` executed the real UI against real services,
  engines and repositories on isolated temporary databases. They are removed
  with the client, and nothing equivalent replaces them yet. The frontend
  suite (vitest + MSW) mocks the API boundary by design and is **not**
  equivalent to real-backend UI testing: it verifies component behaviour and
  contract mapping, never the integrated path from rendered UI through to a
  live database.
- **Current mitigation.** Coverage now rests on the existing layers that were
  always underneath the UI tests — repository, service, engine, lifecycle and
  API contract tests against real temporary databases — plus the backend
  SQLite suite and the PostgreSQL 16 integration job in CI, and the
  established practice of disposable live browser verification against a
  production build and a database copy before significant frontend
  checkpoints.
- **Future mitigation is a separate decision.** An automated end-to-end
  browser test layer (for example Playwright) driving the Next.js client
  against a real backend could restore integrated UI coverage. Whether to
  introduce one, and when, is deliberately out of scope for this ADR and
  remains un-decided.
- **Dependency surface shrinks.** The Streamlit runtime dependency and its
  devcontainer installation are gone; the API runtime needs only the standard
  library, keeping the `requirements.txt` contract explicitly minimal.
