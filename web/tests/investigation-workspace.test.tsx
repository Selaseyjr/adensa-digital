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
import { WorkspaceSectionIndex } from "@/components/investigation/WorkspaceSectionIndex";
import { WorkflowProgression } from "@/components/investigation/WorkflowProgression";
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

  // --------------------------------------------------
  // P12.5 — REASONING CHAIN: WHY IT MATTERS
  // --------------------------------------------------

  it("frames the deadline facts as operational impact from existing fields", () => {
    const { container } = render(<SituationImpact context={makeContext()} />);

    const frame = container.querySelector(".impact-frame");

    expect(frame).not.toBeNull();
    // Verbatim contract fields, one statement: required vs
    // estimated arrival plus current shipment status.
    expect(frame!.textContent).toContain("Delivery is required by 2026-09-15.");
    expect(frame!.textContent).toContain("Estimated arrival is 2026-09-21.");
    expect(frame!.textContent).toContain("Shipment status: In Transit.");
  });

  it("omits the arrival clause honestly when no estimated arrival exists", () => {
    const { container } = render(
      <SituationImpact context={makeContext({ estimated_arrival: null })} />,
    );

    const frame = container.querySelector(".impact-frame");

    expect(frame).not.toBeNull();
    expect(frame!.textContent).toContain("Delivery is required by 2026-09-15.");
    expect(frame!.textContent).not.toContain("Estimated arrival is");
    expect(frame!.textContent).toContain("Shipment status: In Transit.");
  });

  it("carries the facts stage class for the reasoning chain", () => {
    const { container } = render(<SituationImpact context={makeContext()} />);

    expect(container.querySelector("section.section--facts")).not.toBeNull();
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

    expect(screen.getByText("Factor breakdown & weights")).toBeInTheDocument();

    // P12.5: the factor table remains a native disclosure —
    // the at-a-glance reasoning block now carries the
    // confidence basis and trade-offs outside it.
    const rationale = screen
      .getByText("Factor breakdown & weights")
      .closest("details")!;

    expect(within(rationale).getByText("Cost")).toBeInTheDocument();
    expect(within(rationale).getByText("0.3")).toBeInTheDocument(); // weight
    expect(
      within(rationale).getByText((_, element) =>
        element?.textContent === "0.8 (0.24)" ? true : false,
      ),
    ).toBeInTheDocument(); // score (contribution)
  });

  it("renders the confidence basis verbatim", () => {
    render(<DecisionSupport assessment={makeAssessment()} />);

    // P8.4 promotion of the confidence basis into the
    // disclosure itself (P12.5 keeps this verbatim inside the
    // at-a-glance reasoning block).
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

  // --------------------------------------------------
  // P12.5 — REASONING CHAIN: OPTIONS → RECOMMENDATION
  // --------------------------------------------------

  it("promotes the recommendation reasoning outside the factor disclosure", () => {
    render(<DecisionSupport assessment={makeAssessment()} />);

    const whyBlock = document.querySelector(".recommendation-why");

    expect(whyBlock).not.toBeNull();
    expect(within(whyBlock as HTMLElement).getByText("Why this recommendation")).toBeInTheDocument();
    // The confidence basis reads at a glance — verbatim, not summarized.
    expect(
      within(whyBlock as HTMLElement).getByText(
        "Score separation between the leading options and the field.",
      ),
    ).toBeInTheDocument();
    // The trade-off sentence is likewise visible without opening anything.
    expect(
      within(whyBlock as HTMLElement).getByText((_, element) =>
        element?.tagName === "LI" &&
        element?.textContent === "OPT-0002 (Air) is stronger on Transit."
          ? true
          : false,
      ),
    ).toBeInTheDocument();
    // The detailed factor table stays disclosed behind its own summary.
    expect(
      screen.getByText("Factor breakdown & weights").closest("details"),
    ).not.toBeNull();
  });

  it("renders no reasoning block when the rationale is absent", () => {
    render(
      <DecisionSupport
        assessment={makeAssessment({ rationale: null })}
      />,
    );

    expect(
      document.querySelector(".recommendation-why"),
    ).toBeNull();
    expect(
      screen.queryByText("Why this recommendation"),
    ).not.toBeInTheDocument();
  });

  it("discloses evaluated options in the recommendation branch when the contract supplies them", () => {
    render(
      <DecisionSupport
        assessment={makeAssessment({
          evaluated_options: [
            {
              option_id: "OPT-0009",
              transport_mode: "Sea",
              carrier_id: "CAR-001",
              estimated_cost: 2100,
              estimated_transit_days: 21,
              risk_score: 0.9,
              feasible: false,
            },
          ],
        })}
      />,
    );

    const summary = screen.getByText(/Also evaluated — not recommended/);
    const details = summary.closest("details");

    expect(details).not.toBeNull();
    expect(within(details as HTMLElement).getByText("OPT-0009")).toBeInTheDocument();
    // The verdict column keeps the backend's own feasibility verdict.
    expect(within(details as HTMLElement).getByText("Infeasible")).toBeInTheDocument();
  });

  it("renders no evaluated-options disclosure in the recommendation branch when none are supplied", () => {
    // The production contract sends [] alongside a recommendation;
    // the disclosure must simply not exist rather than fabricate rows.
    render(<DecisionSupport assessment={makeAssessment()} />);

    expect(screen.queryByText(/Also evaluated — not recommended/)).not.toBeInTheDocument();
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
        exceptionId="EXC-001529"
        latestActionId="ACT-000001"
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
          // The classifier's literal state string (em dash).
          state: "Executed — still open",
          follow_up_required: true,
          reason: "The executed recovery did not resolve the exception.",
        })}
        interventions={[]}
        exceptionId="EXC-001529"
        latestActionId="ACT-000001"
      />,
    );

    expect(screen.getByText("Executed — still open")).toBeInTheDocument();
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
        exceptionId="EXC-001529"
        latestActionId="ACT-000001"
      />,
    );

    expect(screen.queryByText("Carrier escalation")).not.toBeInTheDocument();
  });

  // --------------------------------------------------
  // P12.5 — REASONING CHAIN: CURRENT OUTCOME
  // --------------------------------------------------

  it("consolidates the current outcome with the backend's own state and reason", () => {
    const { container } = render(
      <WorkflowAction
        state={makeInvestigationState()}
        interventions={[]}
        exceptionId="EXC-001529"
        latestActionId="ACT-000001"
      />,
    );

    const outcome = container.querySelector(".outcome-block");

    expect(outcome).not.toBeNull();
    expect(
      within(outcome as HTMLElement).getByText("Current outcome"),
    ).toBeInTheDocument();
    expect(
      within(outcome as HTMLElement).getByText("Decision required"),
    ).toBeInTheDocument();
    expect(
      within(outcome as HTMLElement).getByText(
        "A recovery action awaits a planner approve/reject decision.",
      ),
    ).toBeInTheDocument();
  });

  it("carries the decision stage class for the reasoning chain", () => {
    const { container } = render(
      <WorkflowAction
        state={makeInvestigationState()}
        interventions={[]}
        exceptionId="EXC-001529"
        latestActionId="ACT-000001"
      />,
    );

    expect(
      container.querySelector("section.section--decision"),
    ).not.toBeNull();
  });

  it("keeps the decision stage class across supported states", () => {
    // The stage class is presentation-only; it must not depend
    // on which workflow state the classifier reports.
    for (const stateName of [
      "Awaiting execution",
      "Executed — still open",
      "No system recovery available",
      "Resolved",
    ]) {
      const { container, unmount } = render(
        <WorkflowAction
          state={makeInvestigationState({ state: stateName })}
          interventions={[]}
          exceptionId="EXC-001529"
          latestActionId="ACT-000001"
        />,
      );

      expect(
        container.querySelector("section.section--decision"),
      ).not.toBeNull();
      unmount();
    }
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

// ==================================================
// P8.4 — SECTION INDEX, PROGRESSION, TIMELINE, DISCLOSURE
// ==================================================

const INDEX_SECTIONS = [
  { id: "state", label: "State" },
  { id: "situation", label: "Situation & Impact" },
  { id: "decision-support", label: "Decision Support" },
  { id: "history", label: "History" },
  { id: "sustainability", label: "Sustainability" },
  { id: "advisory", label: "AI Advisory" },
  { id: "workflow-action", label: "Workflow Action" },
];

describe("workspace section index", () => {
  it("renders a nav landmark with an anchor per section", () => {
    render(<WorkspaceSectionIndex sections={INDEX_SECTIONS} />);

    const nav = screen.getByRole("navigation", {
      name: "Workspace sections",
    });
    const links = within(nav).getAllByRole("link");

    expect(links).toHaveLength(INDEX_SECTIONS.length);
    expect(links.map((link) => link.getAttribute("href"))).toEqual(
      INDEX_SECTIONS.map((section) => `#${section.id}`),
    );
    expect(links.map((link) => link.textContent)).toEqual(
      INDEX_SECTIONS.map((section) => section.label),
    );
  });

  it("marks the first section as the initial location", () => {
    render(<WorkspaceSectionIndex sections={INDEX_SECTIONS} />);

    const links = screen.getAllByRole("link");
    const current = links.filter((link) =>
      link.hasAttribute("aria-current"),
    );

    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAttribute("aria-current", "location");
    expect(current[0].textContent).toBe("State");
  });

  it("renders nothing without sections", () => {
    const { container } = render(<WorkspaceSectionIndex sections={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});

describe("workflow progression", () => {
  it("positions each common-path state exactly, without inventing stages", () => {
    const { container: decide } = render(
      <WorkflowProgression
        state={makeInvestigationState({ state: "Decision required" })}
      />,
    );
    expect(decide.querySelectorAll("li")).toHaveLength(4);
    expect(
      decide.querySelector(".progression-step-current")!.textContent,
    ).toContain("Decision");

    const { container: execute } = render(
      <WorkflowProgression
        state={makeInvestigationState({ state: "Awaiting execution" })}
      />,
    );
    const executeItems = [...execute.querySelectorAll("li")];
    expect(executeItems).toHaveLength(4);
    expect(
      executeItems.find((li) => li.className.includes("current"))!.textContent,
    ).toContain("Execution");

    const { container: resolved } = render(
      <WorkflowProgression state={makeInvestigationState({ state: "Resolved" })} />,
    );
    expect(
      resolved.querySelector(".progression-step-current")!.textContent,
    ).toContain("Outcome");
  });

  it("uses the manual-resolution path for the manual states", () => {
    for (const stateName of [
      "No system recovery available",
      "Executed — still open",
    ]) {
      const { container, unmount } = render(
        <WorkflowProgression
          state={makeInvestigationState({ state: stateName })}
        />,
      );

      const items = [...container.querySelectorAll("li")];
      expect(items.map((li) => li.textContent)).toEqual([
        "DetectedCompleted",
        "Manual resolutionCurrent",
        "OutcomeUpcoming",
      ]);
      unmount();
    }
  });

  it("marks exactly one current step with aria-current=step", () => {
    const { container } = render(
      <WorkflowProgression
        state={makeInvestigationState({ state: "Awaiting execution" })}
      />,
    );

    const current = [...container.querySelectorAll("li")].filter((li) =>
      li.hasAttribute("aria-current"),
    );

    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAttribute("aria-current", "step");
  });

  it("renders nothing for unknown state strings", () => {
    const { container } = render(
      <WorkflowProgression
        state={makeInvestigationState({ state: "Mystery state" })}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("contains no fabricated progress percentages", () => {
    const { container } = render(
      <WorkflowProgression
        state={makeInvestigationState({ state: "Resolved" })}
      />,
    );

    expect(container.textContent).not.toMatch(/%|\d+%/);
  });
});

describe("history timeline presentation", () => {
  it("maps known event strings to neutral display markers", () => {
    const { container } = render(
      <OperationalHistory
        entries={[
          makeHistoryEntry({ event: "Exception detected", sequence: 1 }),
          makeHistoryEntry({ event: "Recovery approved", sequence: 2 }),
          makeHistoryEntry({ event: "Recovery executed", sequence: 3 }),
        ]}
      />,
    );

    expect(
      container.querySelector(".history-marker.marker-detected"),
    ).not.toBeNull();
    expect(
      container.querySelector(".history-marker.marker-decision"),
    ).not.toBeNull();
    expect(
      container.querySelector(".history-marker.marker-executed"),
    ).not.toBeNull();
  });

  it("falls back to the neutral marker for unknown event strings", () => {
    const { container } = render(
      <OperationalHistory
        entries={[makeHistoryEntry({ event: "Something entirely new" })]}
      />,
    );

    expect(
      container.querySelector(".history-marker.marker-neutral"),
    ).not.toBeNull();
  });

  it("keeps the event, detail and actor text verbatim", () => {
    render(
      <OperationalHistory
        entries={[
          makeHistoryEntry({
            event: "Recovery approved",
            detail: "ACT-000001 approved under the recovery workflow.",
            actor: "P. Planner",
          }),
        ]}
      />,
    );

    expect(screen.getByText(/Recovery approved/)).toBeInTheDocument();
    expect(
      screen.getByText("ACT-000001 approved under the recovery workflow."),
    ).toBeInTheDocument();
    expect(screen.getByText(/— P. Planner/)).toBeInTheDocument();
  });

  it("hides the display marker from assistive technology", () => {
    const { container } = render(
      <OperationalHistory entries={[makeHistoryEntry()]} />,
    );

    expect(container.querySelector(".history-marker")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });
});

describe("progressive disclosure", () => {
  it("renders the rationale as a native disclosure with a summary", () => {
    render(<DecisionSupport assessment={makeAssessment()} />);

    // P12.5: the disclosure summary is the factor table; the
    // at-a-glance reasoning block is NOT a disclosure.
    const rationaleSummary = screen
      .getByText("Factor breakdown & weights")
      .closest("summary");
    expect(rationaleSummary).not.toBeNull();
    expect(rationaleSummary!.closest("details")).not.toBeNull();

    const whyTitle = screen.getByText("Why this recommendation");
    expect(whyTitle.closest("details")).toBeNull();
    expect(whyTitle.closest("summary")).toBeNull();
  });

  it("renders evaluated infeasible options as a native disclosure", () => {
    render(
      <DecisionSupport
        assessment={makeAssessment({
          recommendation: null,
          alternatives: [],
          rationale: null,
          evaluated_options: [
            {
              option_id: "OPT-0009",
              transport_mode: "Sea",
              carrier_id: "CAR-001",
              estimated_cost: 2100,
              estimated_transit_days: 21,
              risk_score: 0.9,
              feasible: false,
            },
          ],
        })}
      />,
    );

    const evaluatedSummary = screen
      .getByText(/Evaluated recovery options/)
      .closest("summary");
    expect(evaluatedSummary).not.toBeNull();

    // The no-feasible-recovery message stays outside any disclosure.
    expect(
      screen.getByText("No feasible system recovery available."),
    ).toBeInTheDocument();
  });

  it("keeps the recommendation visible outside any disclosure", () => {
    render(<DecisionSupport assessment={makeAssessment()} />);

    expect(screen.getByText("Recommended")).toBeInTheDocument();
    expect(screen.getByText("OPT-0001 — Road")).toBeInTheDocument();
  });

  it("collapses sustainability detail behind a summary", () => {
    render(
      <SustainabilitySection sustainability={makeSustainabilityComparison()} />,
    );

    expect(
      screen.getByText(/Emissions estimates/),
    ).toBeInTheDocument();
    const sustainabilityDetails = [
      ...document.querySelectorAll("details.sustainability-details"),
    ];
    expect(sustainabilityDetails).toHaveLength(1);
  });
});
