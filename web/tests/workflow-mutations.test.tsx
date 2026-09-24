/**
 * P7.2 workflow-mutation tests: the client-level mutation
 * result mapping (approve/reject/execute/manual-resolution
 * against every documented failure mode) and the
 * WorkflowAction component's state gating, pending states and
 * inline result rendering.
 *
 * MSW runs with onUnhandledRequest: "error" (inherited from
 * the shared createApiServer pattern): a POST to an endpoint
 * the client posts to but the mock server does not handle
 * fails loudly — the mutation contract cannot drift silently.
 */

import {
  afterEach,
  beforeAll,
  afterAll,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  createApiServer,
  makeInvestigationState,
  makeManualResolutionOutcome,
  makeWorkflowOutcome,
  approveApiPath,
  executeApiPath,
  manualResolutionApiPath,
  http,
  HttpResponse,
} from "./helpers/api-mocks";
import {
  approveRecoveryAction,
  rejectRecoveryAction,
  executeRecoveryAction,
  recordManualResolution,
  getLatestRecoveryAction,
} from "@/lib/api/client";
import { WorkflowAction } from "@/components/investigation/WorkflowAction";
import type { ManualResolutionRequest } from "@/lib/types/api";

// Server actions call next/cache's revalidatePath after a
// successful mutation; under Vitest there is no request
// scope, so Next's static-render guard (E263) would throw.
// The mock also lets the tests assert the revalidation
// policy — the workspace and list surfaces must refresh.
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

const server = createApiServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
});
afterAll(() => server.close());

// ==================================================
// CLIENT-LEVEL RESULT MAPPING
// ==================================================

describe("mutation client — approve", () => {
  it("maps a 200 outcome to the success state", async () => {
    const result = await approveRecoveryAction("EXC-001529", {
      approved_by: "P. Planner",
    });

    expect(result).toEqual({
      kind: "success",
      data: makeWorkflowOutcome(),
    });
  });

  it("maps a 409 workflow guard to the guard state with the engine message", async () => {
    server.use(
      http.post(approveApiPath(), () =>
        HttpResponse.json(
          { detail: "Invalid workflow transition: Pending Approval → Executed" },
          { status: 409 },
        ),
      ),
    );

    const result = await approveRecoveryAction("EXC-001529", {
      approved_by: "P. Planner",
    });

    expect(result).toEqual({
      kind: "guard",
      message: "Invalid workflow transition: Pending Approval → Executed",
    });
  });

  it("maps a 401 to the unauthenticated state without leaking internals", async () => {
    server.use(
      http.post(approveApiPath(), () =>
        HttpResponse.json({ detail: "Unauthorized" }, { status: 401 }),
      ),
    );

    const result = await approveRecoveryAction("EXC-001529", {
      approved_by: "P. Planner",
    });

    expect(result.kind).toBe("unauthenticated");
  });

  it("maps a 404 to the notFound state", async () => {
    server.use(
      http.post(approveApiPath(), () =>
        HttpResponse.json(
          { detail: "No recovery action exists for exception EXC-001529." },
          { status: 404 },
        ),
      ),
    );

    const result = await approveRecoveryAction("EXC-001529", {
      approved_by: "P. Planner",
    });

    expect(result.kind).toBe("notFound");
  });

  it("maps a 422 to the validation state", async () => {
    server.use(
      http.post(approveApiPath(), () =>
        HttpResponse.json(
          {
            detail: [
              {
                type: "missing",
                loc: ["body", "approved_by"],
                msg: "Field required",
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );

    const result = await approveRecoveryAction("EXC-001529", {
      approved_by: "P. Planner",
    });

    expect(result.kind).toBe("validation");
  });

  it("maps an unreachable API to the unavailable state", async () => {
    server.use(
      http.post(approveApiPath(), () => HttpResponse.error()),
    );

    const result = await approveRecoveryAction("EXC-001529", {
      approved_by: "P. Planner",
    });

    expect(result.kind).toBe("unavailable");
  });
});

describe("mutation client — reject and execute", () => {
  it("maps a reject outcome to the success state", async () => {
    const result = await rejectRecoveryAction("EXC-001529", {
      rejected_by: "P. Planner",
    });

    expect(result.kind).toBe("success");
    expect(
      result.kind === "success" && result.data.message,
    ).toContain("rejected");
  });

  it("maps an execute outcome to the success state", async () => {
    const result = await executeRecoveryAction("ACT-000001");

    expect(result.kind).toBe("success");
    expect(
      result.kind === "success" && result.data.message,
    ).toContain("executed");
  });

  it("maps an execute 409 closed-exception failure to the guard state", async () => {
    server.use(
      http.post(executeApiPath(), () =>
        HttpResponse.json(
          {
            detail:
              "Recovery execution failed: the exception is closed and no longer accepts execution.",
          },
          { status: 409 },
        ),
      ),
    );

    const result = await executeRecoveryAction("ACT-000001");

    expect(result.kind).toBe("guard");
  });
});

describe("mutation client — manual resolution", () => {
  const request: ManualResolutionRequest = {
    intervention_type: "Carrier call",
    external_party: "Ocean carrier ops",
    resolution_summary: "Coordinated a revised delivery plan.",
    recorded_by: "P. Planner",
    outcome: "Resolved",
  };

  it("maps a recorded resolution to the success state", async () => {
    const result = await recordManualResolution("EXC-001529", request);

    expect(result).toEqual({
      kind: "success",
      data: makeManualResolutionOutcome(),
    });
  });

  it("maps the pending-system-action guard to the guard state", async () => {
    server.use(
      http.post(manualResolutionApiPath(), () =>
        HttpResponse.json(
          {
            detail:
              "Exception EXC-001527 has a system recovery action (ACT-000828) that is Pending Approval. Resolve it through the recovery workflow before recording a manual resolution.",
          },
          { status: 409 },
        ),
      ),
    );

    const result = await recordManualResolution("EXC-001529", request);

    expect(result.kind).toBe("guard");
    expect(
      result.kind === "guard" && result.message.includes("Pending Approval"),
    ).toBe(true);
  });
});

describe("mutation client — latest action read", () => {
  it("resolves the null body convention to the empty state", async () => {
    server.use(
      http.get(
        "http://127.0.0.1:8000/exceptions/EXC-001529/actions/latest",
        () => HttpResponse.json(null),
      ),
    );

    const result = await getLatestRecoveryAction("EXC-001529");

    expect(result).toEqual({ kind: "empty" });
  });
});

// ==================================================
// COMPONENT-LEVEL BEHAVIOR
// ==================================================

function renderWorkflowAction(stateName: string) {
  return render(
    <WorkflowAction
      state={makeInvestigationState({ state: stateName })}
      interventions={[]}
      exceptionId="EXC-001529"
      latestActionId="ACT-000001"
    />,
  );
}

describe("WorkflowAction — state gating", () => {
  it("offers the decision controls only in the decision state", () => {
    renderWorkflowAction("Decision required");

    expect(
      screen.getByRole("button", { name: "Approve recovery" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reject recovery" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Execute recovery" }),
    ).not.toBeInTheDocument();
  });

  it("offers execute only in the awaiting-execution state", () => {
    renderWorkflowAction("Awaiting execution");

    expect(
      screen.getByRole("button", { name: "Execute recovery" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve recovery" }),
    ).not.toBeInTheDocument();
  });

  it("offers the manual-resolution form only in manual states", () => {
    // The classifier's literal state string.
    renderWorkflowAction("No system recovery available");

    expect(
      screen.getByRole("button", { name: "Record manual resolution" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve recovery" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Execute recovery" }),
    ).not.toBeInTheDocument();
  });

  it("offers no mutation controls in the resolved state", () => {
    renderWorkflowAction("Resolved");

    expect(
      screen.queryByRole("button", { name: "Approve recovery" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Execute recovery" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Record manual resolution" }),
    ).not.toBeInTheDocument();
  });
});

describe("WorkflowAction — decision flow", () => {
  it("completes approve, renders the backend outcome and revalidates the workspace surfaces", async () => {
    const { revalidatePath } = await import("next/cache");
    const user = userEvent.setup();
    renderWorkflowAction("Decision required");

    await user.click(screen.getByRole("button", { name: "Approve recovery" }));

    const nameInput = screen.getByPlaceholderText("Planner name");
    await user.type(nameInput, "P. Planner");
    await user.click(screen.getByRole("button", { name: "Confirm approval" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Recovery action ACT-000001 approved successfully.",
      );
    });

    // P8.4 focus management: the result banner is the focus
    // target so keyboard/SR users land on the outcome.
    expect(screen.getByRole("status")).toHaveFocus();

    expect(revalidatePath).toHaveBeenCalledWith(
      "/exceptions/EXC-001529",
    );
    expect(revalidatePath).toHaveBeenCalledWith("/exceptions");
    expect(revalidatePath).toHaveBeenCalledWith("/");
  });

  it("completes reject and renders the backend outcome", async () => {
    const user = userEvent.setup();
    renderWorkflowAction("Decision required");

    await user.click(screen.getByRole("button", { name: "Reject recovery" }));
    await user.type(screen.getByPlaceholderText("Planner name"), "P. Planner");
    await user.click(screen.getByRole("button", { name: "Confirm rejection" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("rejected");
    });
  });

  it("blocks an empty planner name with the local validation message", async () => {
    const user = userEvent.setup();
    renderWorkflowAction("Decision required");

    await user.click(screen.getByRole("button", { name: "Approve recovery" }));
    await user.click(screen.getByRole("button", { name: "Confirm approval" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Enter the approving planner's name.",
    );
  });

  it("renders the backend 409 guard message verbatim for a stale decision", async () => {
    server.use(
      http.post(approveApiPath(), () =>
        HttpResponse.json(
          {
            detail:
              "Invalid workflow transition: Pending Approval → Executed",
          },
          { status: 409 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWorkflowAction("Decision required");

    await user.click(screen.getByRole("button", { name: "Approve recovery" }));
    await user.type(screen.getByPlaceholderText("Planner name"), "P. Planner");
    await user.click(screen.getByRole("button", { name: "Confirm approval" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Invalid workflow transition: Pending Approval → Executed",
      );
    });
  });
});

describe("WorkflowAction — execute flow", () => {
  it("completes execute and renders the backend outcome", async () => {
    const user = userEvent.setup();
    renderWorkflowAction("Awaiting execution");

    await user.click(screen.getByRole("button", { name: "Execute recovery" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Recovery executed successfully for SHP-SIM-0002.",
      );
    });
  });
});

describe("WorkflowAction — manual resolution flow", () => {
  it("requires the obvious fields before submitting", async () => {
    const user = userEvent.setup();
    // The classifier's literal state string.
    renderWorkflowAction("No system recovery available");

    await user.click(
      screen.getByRole("button", { name: "Record manual resolution" }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Select the intervention type.",
    );
  });

  it("records a complete manual resolution and renders the outcome", async () => {
    const user = userEvent.setup();
    // The classifier's literal state string.
    renderWorkflowAction("No system recovery available");

    await user.selectOptions(
      screen.getByLabelText("Intervention type"),
      "Carrier call",
    );
    await user.selectOptions(screen.getByLabelText("Outcome"), "Resolved");
    await user.type(
      screen.getByLabelText("External party"),
      "Ocean carrier ops",
    );
    await user.type(screen.getByLabelText("Recorded by"), "P. Planner");
    await user.type(
      screen.getByLabelText("Resolution summary"),
      "Coordinated a revised delivery plan.",
    );
    await user.click(
      screen.getByRole("button", { name: "Record manual resolution" }),
    );

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Manual resolution INT-0001 recorded for EXC-001529.",
      );
    });
  });
});
