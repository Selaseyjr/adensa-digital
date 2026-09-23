# Adensa Digital — Operational Web Client

The production-style Next.js client for Adensa Digital. It consumes the
versioned FastAPI `/v1` application boundary (ADR-011) and contains no
business logic of its own: detection, prioritization, recommendation and
workflow semantics remain authoritative on the server.

```text
Next.js / React
      ↓ HTTPS / REST
FastAPI /v1
      ↓
Services
      ↓
Engines
      ↓
Repositories
      ↓
SQLite
```

## Architecture decisions

**Rendering strategy — Server Components.** All operational data is read
on the Node server (`app/` pages are async Server Components using
`cache: "no-store"`). The browser never sees the API origin, and no
API key can leak into client code. This mirrors the P2 boundary design,
where `X-API-Key` is a machine-to-machine contract, not browser
authentication.

**API client — one module, typed result states.** React components never
call `fetch` and never build URLs. `lib/api/client.ts` is the single
network boundary; every read resolves to one of four deliberate states —
`data`, `empty`, `unavailable` (API down / HTTP error) or `unexpected`
(contract violation) — so components render honest states instead of
guessing, and no raw backend error reaches the UI. The client presents
an optional server-side `X-API-Key` from `API_KEY` — the same
machine-to-machine contract the API already enforces (ADR-008).

**TypeScript contract — hand-maintained, mirrored from the API.**
`lib/types/api.ts` mirrors the Pydantic response models in `app/api.py`;
the API contract is the source of truth and the frontend never invents
operational fields. An OpenAPI code-generation step was deliberately not
introduced at this scale — one small, reviewable contract file with a
structural validation net in the API-client tests is cheaper to maintain
than a generator pipeline. Revisit if the surface grows.

**No business rules in the client.** Metrics populations, inbox ordering,
severity semantics and workflow states are consumed verbatim from the
API. The frontend adds presentation only.

## Surfaces

| Route | Status | Source |
|---|---|---|
| `/` — Control Tower | Implemented | `GET /v1/control-tower/summary` |
| `/exceptions` — Inbox work queue | Implemented | `GET /v1/exceptions/inbox` |
| `/exceptions/[id]` — Investigation Workspace | Implemented | `/v1/exceptions/{id}/context`, `/state`, `/assessment`, `/history`, `/sustainability`, `/interventions`, `/decision-brief` |
| `/operations` | Placeholder | future operational refresh/simulation UI |
| `/administration` | Placeholder | future configuration UI |

### Investigation Workspace

The selected-exception workspace preserves the W4 information hierarchy:

```text
State → Situation & Impact → Decision Support →
Operational History → AI Advisory → Workflow Action
```

Sections compose independently: only a context failure collapses the
workspace; every other section degrades to its own honest failure or
empty panel. The decision support renders the deterministic assessment
verbatim — recommendation, alternatives, evaluated (infeasible) options,
factor scores, weights, weighted contributions, trade-offs, confidence —
with no client-side recalculation. Sustainability stays subordinate and
prototype-framed. The AI Advisory section consumes the advisory decision
brief from `GET /v1/exceptions/{id}/decision-brief` and is explicitly
subordinate to the deterministic recommendation: it renders the
backend's advisory label, disclaimer and verification points verbatim,
and degrades to an honest unavailable state without affecting the rest
of the workspace.

### Workflow actions (P7.2)

The workspace is interactive: approve, reject, execute and manual
resolution are drivable from the Workflow Action section. The mutations
cross one deliberate boundary:

```text
WorkflowAction (the workspace's first client component)
      ↓
web/lib/actions/workflow.ts ("use server" actions)
      ↓
web/lib/api/client.ts (POST twin of the read helpers)
      ↓
existing mutation contracts (legacy paths + /v1 manual-resolution)
```

Server actions run on the Node server, so the API origin and the
machine credential still never reach the browser. UI gating (which
controls render for which persisted state) is UX only: the backend
workflow engine remains authoritative, and its 409 guard messages are
rendered verbatim rather than re-interpreted. Actions render only for
the classifier's literal state names ("Decision required", "Awaiting
execution", "No system recovery available", "Executed — still open");
a successful mutation revalidates the workspace and the list surfaces.

## Configuration

Copy `.env.example` to `.env.local`:

```bash
API_BASE_URL=http://127.0.0.1:8000
API_KEY=<the value the API server receives via ADENSA_API_KEY>
```

Both variables are read **server-side only**. There is deliberately no
`NEXT_PUBLIC_` variable: the API origin and the machine credential must
never ship to the browser. The `http://127.0.0.1:8000` fallback is for
local development only — **production deployments must configure
`API_BASE_URL` explicitly**; starting a production build without it
logs a loud warning at startup (and is a configuration error, not a
supported mode). Deployment guidance for the whole system —
environment separation, migration sequence, health/readiness probes,
production invocation — lives in [`docs/deployment.md`](../docs/deployment.md).
The Next server presents the same
`X-API-Key` a trusted server-side integration (e.g. Power Automate)
presents — this is machine-to-machine configuration, not user
authentication, which remains a future checkpoint. Without `API_KEY`,
the client still functions against an API whose `/v1` reads are
unauthenticated in a fully local setup; against a keyed API the
surfaces render their deliberate "API unavailable" states.

## Development

```bash
# from web/
npm install
npm run dev        # http://localhost:3000

npm run typecheck  # tsc --noEmit
npm run lint       # eslint (next/core-web-vitals + next/typescript)
npm run test       # vitest (54 tests, msw-mocked /v1 boundary)
npm run build      # production build
```

The Python FastAPI server must be running locally for the pages to
render live data; with the API down, surfaces render their deliberate
"API unavailable" states.

## CI

CI runs typecheck, lint, tests and the production build for `web/`
alongside the Python suite. A failing frontend build fails CI.

## Relationship to the Streamlit client

Streamlit (`app/main.py`) remains temporarily available as the existing
reference client during the migration. It is unaffected by this client;
the two coexist against the same service layer.
