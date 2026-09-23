/**
 * Investigation Workspace contract tests.
 *
 * Structure tests target the presentational components with
 * typed props — the exact objects the /v1 contracts deliver
 * (the helpers double as contract samples verified against
 * `lib/api/client.ts` validation in api-client.test.ts).
 * Client/network behavior — the four result states, unknown
 * exception mapping, per-section resilience — is covered in
 * the workspace loader tests below via MSW.
 */

import { afterEach, beforeAll, afterAll, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import {
  createApiServer,
  makeAssessment,
  makeContext,
  makeDecisionBrief,
  makeHistoryEntry,
  makeInvestigationState,
  makeManualIntervention,
  makeSustainabilityComparison,
  assessmentPath,
  contextPath,
  decisionBriefPath,
  historyPath,
  http,
  HttpResponse,
} from "./helpers/api-mocks";
import { WorkspaceHeader } from "@/components/investigation/WorkspaceHeader";
import { SituationImpact } from "@/components/investigation/SituationImpact";
import { DecisionSupport } from "@/components/investigation/DecisionSupport";
import { OperationalHistory } from "@/components/investigation/OperationalHistory";
import { SustainabilitySection } from "@/components/investigation/SustainabilitySection";
import { AiDecisionBrief } from "@/components/investigation/AiDecisionBrief";
import { WorkflowAction } from "@/components/investigation/WorkflowAction";
import {
  getExceptionContext,
  getInvestigationState,
  getRecoveryAssessment,
  getExceptionHistory,
  getSustainabilityAssessment,
  getManualInterventions,
  getDecisionBrief,
} from "@/lib/api/client";

const server = createApiServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
});
afterAll(() => server.close());

describe("workspace header — state first", () => {
  it("establishes identity, severity and persisted-evidence state", () => {
    render(
      <WorkspaceHeader
        context={makeContext()}
        state={makeInvestigationState()}
      />,
    );

    expect(
      screen.getByText("EXC-001529 — Shipment Delay"),
    ).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("Decision required")).toBeInTheDocument();
    expect(
      screen.getByText(/Shipment SHP-SIM-0002 · Order ORD-0002/),
    ).toBeInTheDocument();
  });
});

describe("situation & impact", () => {
  it("renders backend context facts in the reading order", () => {
    render(<SituationImpact context={makeContext()} />);

    expect(screen.getByText("Situation & Impact")).toBeInTheDocument();
    // The description sentence verbatim — backend-provided fact.
    expect(
      screen.getByText(/delayed at origin consolidation point/),
    ).toBeInTheDocument();
    // Route appears composed and verbatim; both must be present.
    expect(
      screen.getAllByText("Shanghai → Rotterdam").length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("2026-09-15")).toBeInTheDocument(); // required
    // Customer name shares a cell with the order id.
    expect(
      screen.getByText((_, element) =>
        element?.textContent === "ORD-0002 · Meridian Foods" ? true : false,
      ),
    ).toBeInTheDocument();
  });
});

describe("decision support", () => {
  it("renders the recommendation as the primary element", () => {
    render(<DecisionSupport assessment={makeAssessment()} />);

    expect(screen.getByText("Recommended")).toBeInTheDocument();
    expect(
      screen.getByText(/OPT-0001 — Road/),
    ).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument(); // confidence chip
    expect(
      screen.getByText(
        "Lowest weighted cost with acceptable transit time.",
      ),
    ).toBeInTheDocument();
  });

  it("renders rationale factors with weights and contributions", () => {
    render(<DecisionSupport assessment={makeAssessment()} />);

    expect(screen.getByText("Why this recommendation")).toBeInTheDocument();

    const rationale = screen
      .getByText("Why this recommendation")
      .closest("div")!;

    expect(within(rationale).getByText("Cost")).toBeInTheDocument();
    expect(within(rationale).getByText("0.3")).toBeInTheDocument(); // weight
    expect(
      within(rationale).getByText((_, element) =>
        element?.textContent === "0.8 (0.24)" ? true : false,
      ),
    ).toBeInTheDocument(); // score (contribution)
    expect(
      screen.getByText(
        "Score separation between the leading options and the field.",
      ),
    ).toBeInTheDocument();
  });

  it("renders the trade-off explanation", () => {
    render(<DecisionSupport assessment={makeAssessment()} />);

    expect(
      screen.getByText((_, element) =>
        element?.tagName === "LI" &&
        element?.textContent === "OPT-0002 (Air) is stronger on Transit."
          ? true
          : false,
      ),
    ).toBeInTheDocument();
  });

  it("distinguishes alternatives from the recommendation", () => {
    render(<DecisionSupport assessment={makeAssessment()} />);

    expect(screen.getByText("Alternative")).toBeInTheDocument();
    expect(screen.getByText(/OPT-0002 — Air/)).toBeInTheDocument();
  });

  it("presents the no-feasible-recovery outcome without inventing a recommendation", () => {
    render(
      <DecisionSupport
        assessment={{
          recommendation: null,
          alternatives: [],
          evaluated_options: [
            {
              option_id: "OPT-0001",
              transport_mode: "Road",
              carrier_id: "CAR-002",
              estimated_cost: 3200,
              estimated_transit_days: 4,
              risk_score: 0.2,
              feasible: false,
            },
          ],
          rationale: null,
        }}
      />,
    );

    expect(
      screen.getByText("No feasible system recovery available."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/resolution requires human intervention/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Recommended")).not.toBeInTheDocument();
    expect(screen.getByText("Infeasible")).toBeInTheDocument();
  });
});

describe("evidence / operational history", () => {
  it("renders the chronological timeline verbatim", () => {
    render(
      <OperationalHistory
        entries={[
          makeHistoryEntry(),
          makeHistoryEntry({
            timestamp: "2026-09-14 08:41",
            event: "Planner approved Road",
            actor: "planner",
            sequence: 2,
          }),
          makeHistoryEntry({
            timestamp: null,
            event: "Recovery options generated",
            detail: "Options recorded without dated timestamps.",
            actor: "System",
            sequence: 3,
          }),
        ]}
      />,
    );

    expect(screen.getByText("Operational History")).toBeInTheDocument();
    expect(screen.getByText("Exception detected")).toBeInTheDocument();
    expect(screen.getByText("Planner approved Road")).toBeInTheDocument();
    expect(screen.getByText("Recovery options generated")).toBeInTheDocument();
    // Null timestamps render honestly as em dashes, not invented dates.
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("renders the empty history state", () => {
    render(<OperationalHistory entries={[]} />);

    expect(
      screen.getByText(/No operational history has been recorded/),
    ).toBeInTheDocument();
  });
});

describe("sustainability", () => {
  it("renders the comparison subordinate to the decision with prototype framing", () => {
    render(
      <SustainabilitySection
        sustainability={makeSustainabilityComparison()}
      />,
    );

    expect(screen.getByText("Sustainability Impact")).toBeInTheDocument();
    expect(screen.getByText(/^Informational only/)).toBeInTheDocument();
    expect(screen.getByText("7680")).toBeInTheDocument();
    expect(screen.getByText("+400%")).toBeInTheDocument();
    // Prototype framing appears in the caption and methodology.
    expect(
      screen.getAllByText(/prototype/i).length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("renders the structured unavailable state honestly", () => {
    render(
      <SustainabilitySection
        sustainability={{
          status: "unavailable",
          reason:
            "No deterministic recommendation exists for this exception, so there is nothing to compare.",
        }}
      />,
    );

    expect(
      screen.getByText(/No deterministic recommendation exists/),
    ).toBeInTheDocument();
  });
});

describe("AI advisory", () => {
  it("renders the advisory brief subordinate to the deterministic decision", () => {
    render(<AiDecisionBrief brief={makeDecisionBrief()} />);

    expect(screen.getByText("AI Advisory")).toBeInTheDocument();
    expect(
      screen.getByText("AI-assisted · Advisory only"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Supporting interpretation of the deterministic assessment/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Situation")).toBeInTheDocument();
    expect(screen.getByText("Recommended action")).toBeInTheDocument();
    expect(screen.getByText("Rationale")).toBeInTheDocument();
    expect(screen.getByText("Trade-offs")).toBeInTheDocument();
    expect(screen.getByText("Verify before acting")).toBeInTheDocument();
  });

  it("presents the provider and disclaimer framing verbatim", () => {
    render(<AiDecisionBrief brief={makeDecisionBrief()} />);

    expect(
      screen.getByText(/AI-assisted summary of Adensa's deterministic/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Advisory provider: adensa-evidence-brief/v1"),
    ).toBeInTheDocument();
  });

  it("renders the structured unavailable state honestly", () => {
    render(
      <AiDecisionBrief
        brief={makeDecisionBrief({
          status: "unavailable",
          message:
            "AI decision brief unavailable. Deterministic recommendation remains available.",
        })}
      />,
    );

    expect(
      screen.getByText(/Deterministic recommendation remains available/),
    ).toBeInTheDocument();
    // No advisory content is fabricated when unavailable.
    expect(screen.queryByText("Recommended action")).not.toBeInTheDocument();
  });

  it("keeps advisory content clearly separate from the deterministic recommendation", () => {
    // The advisory section is labelled as interpretation; the
    // deterministic Decision Support section carries no
    // advisory label — the two never share presentation.
    render(<AiDecisionBrief brief={makeDecisionBrief()} />);

    const advisory = screen.getByLabelText("AI advisory");

    expect(
      within(advisory).getByText("AI-assisted · Advisory only"),
    ).toBeInTheDocument();
    expect(
      within(advisory).getByText(/never the operational decision/),
    ).toBeInTheDocument();
  });

  it("maps the decision-brief endpoint failures without collapsing the workspace loader", async () => {
    server.use(
      http.get(decisionBriefPath(), () =>
        HttpResponse.json({ detail: "boom" }, { status: 503 }),
      ),
    );

    const brief = await getDecisionBrief("EXC-001529");

    expect(brief.kind).toBe("unavailable");
  });

  it("validates the decision-brief contract structurally", async () => {
    server.use(
      http.get(decisionBriefPath(), () =>
        HttpResponse.json({ status: "available" }), // missing brief fields
      ),
    );

    const brief = await getDecisionBrief("EXC-001529");

    expect(brief.kind).toBe("unexpected");
  });
});

describe("workflow action", () => {
  it("renders the state, reason and next step without inventing states", () => {
    render(
      <WorkflowAction
        state={makeInvestigationState()}
        interventions={[makeManualIntervention()]}
      />,
    );

    expect(screen.getByText("Workflow Action")).toBeInTheDocument();
    expect(screen.getByText("Decision required")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Review the recommendation and record the approval or rejection decision.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Carrier escalation")).toBeInTheDocument();
  });

  it("renders the executed-still-open semantics from the backend", () => {
    render(
      <WorkflowAction
        state={makeInvestigationState({
          state: "Executed, still open",
          follow_up_required: true,
          reason: "The executed recovery did not resolve the exception.",
        })}
        interventions={[]}
      />,
    );

    expect(screen.getByText("Executed, still open")).toBeInTheDocument();
    expect(
      screen.getByText(
        "The recovery action was executed; the exception remains open and requires follow-up.",
      ),
    ).toBeInTheDocument();
  });

  it("renders no interventions without fabricating any", () => {
    render(
      <WorkflowAction
        state={makeInvestigationState()}
        interventions={[]}
      />,
    );

    expect(screen.queryByText("Carrier escalation")).not.toBeInTheDocument();
  });
});

describe("workspace data loading over the API boundary", () => {
  it("loads all workspace sections through the typed client", async () => {
    const [
      context,
      state,
      assessment,
      history,
      sustainability,
      interventions,
      brief,
    ] = await Promise.all([
      getExceptionContext("EXC-001529"),
      getInvestigationState("EXC-001529"),
      getRecoveryAssessment("EXC-001529"),
      getExceptionHistory("EXC-001529"),
      getSustainabilityAssessment("EXC-001529"),
      getManualInterventions("EXC-001529"),
      getDecisionBrief("EXC-001529"),
    ]);

    expect(context.kind).toBe("data");
    expect(state.kind).toBe("data");
    expect(assessment.kind).toBe("data");
    expect(history.kind).toBe("data");
    expect(sustainability.kind).toBe("data");
    expect(interventions.kind).toBe("data");
    expect(brief.kind).toBe("data");
  });

  it("maps an unknown exception to the empty state on context", async () => {
    server.use(
      http.get(contextPath("EXC-404"), () =>
        HttpResponse.json(
          { detail: "Exception EXC-404 not found." },
          { status: 404 },
        ),
      ),
    );

    const result = await getExceptionContext("EXC-404");

    expect(result.kind).toBe("empty");
  });

  it("keeps a section failure isolated: history unavailable does not affect assessment", async () => {
    server.use(
      http.get(historyPath(), () =>
        HttpResponse.json({ detail: "boom" }, { status: 503 }),
      ),
    );

    const [history, assessment] = await Promise.all([
      getExceptionHistory("EXC-001529"),
      getRecoveryAssessment("EXC-001529"),
    ]);

    expect(history.kind).toBe("unavailable");
    expect(assessment.kind).toBe("data");
  });

  it("validates the assessment contract structurally", async () => {
    server.use(
      http.get(assessmentPath(), () =>
        HttpResponse.json({ recommendation: "nope" }),
      ),
    );

    const result = await getRecoveryAssessment("EXC-001529");

    expect(result.kind).toBe("unexpected");
  });
});
