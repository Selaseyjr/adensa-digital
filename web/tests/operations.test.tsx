/**
 * P9.1 operations tests: the client-level result mapping and
 * strict validators for the two operational endpoints, plus
 * the Operations page component — pending/disabled states,
 * result rendering, deep links and the preserved
 * single-new-exception affordance.
 *
 * MSW runs with onUnhandledRequest: "error" (inherited from
 * the shared createApiServer pattern): a POST to an endpoint
 * the client posts to but the mock server does not handle
 * fails loudly — the operations contract cannot drift
 * silently.
 *
 * Server actions call next/cache's revalidatePath after a
 * successful mutation; under Vitest there is no request
 * scope, so the module is mocked and the tests assert the
 * revalidation policy directly: `/` and `/exceptions` only.
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
  makeRefreshSummary,
  makeSimulatedArrival,
  operationsRefreshPath,
  operationsSimulatePath,
  API_BASE_URL,
  http,
  HttpResponse,
} from "./helpers/api-mocks";
import {
  refreshOperationsPipeline,
  simulateShipmentArrival,
  isOperationalRefreshSummary,
  isSimulatedArrivalSummary,
} from "@/lib/api/client";
import { OperationsControls } from "@/components/operations/OperationsControls";
import OperationsPage from "@/app/operations/page";
import {
  refreshPipelineAction,
  simulateArrivalAction,
} from "@/lib/actions/operations";

const revalidateMock = vi.hoisted(() => vi.fn());

vi.mock("next/cache", () => ({ revalidatePath: revalidateMock }));

const server = createApiServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  revalidateMock.mockClear();
  cleanup();
});
afterAll(() => server.close());

// ==================================================
// CLIENT-LEVEL VALIDATION (fail closed)
// ==================================================

describe("operations client — response validation", () => {
  it("accepts a valid refresh summary", async () => {
    const payload = makeRefreshSummary({
      new_exceptions: 2,
      new_options: 3,
      new_exception_ids: ["EXC-001530", "EXC-001531"],
      actions_evaluated: 5,
      new_actions: 2,
      actions_without_recommendation: 1,
      actions_skipped: 2,
    });

    expect(isOperationalRefreshSummary(payload)).toEqual(payload);
  });

  it("rejects a refresh summary with a missing field", () => {
    const { actions_skipped, ...incomplete } = makeRefreshSummary();

    expect(actions_skipped).toBe(0);
    expect(isOperationalRefreshSummary(incomplete)).toBeNull();
  });

  it("rejects a refresh summary with an unexpected extra field", () => {
    const payload = makeRefreshSummary() as unknown as Record<string, unknown>;
    payload.extra = true;

    expect(isOperationalRefreshSummary(payload)).toBeNull();
  });

  it("rejects a refresh summary with wrongly typed counts", () => {
    const payload = makeRefreshSummary({
      new_exceptions: "2" as unknown as number,
    });

    expect(isOperationalRefreshSummary(payload)).toBeNull();
  });

  it("rejects a refresh summary with non-string exception IDs", () => {
    const payload = makeRefreshSummary({
      new_exception_ids: [42] as unknown as string[],
    });

    expect(isOperationalRefreshSummary(payload)).toBeNull();
  });

  it("accepts a valid simulated-arrival summary", async () => {
    const payload = makeSimulatedArrival();

    expect(isSimulatedArrivalSummary(payload)).toEqual(payload);
  });

  it("rejects a simulated-arrival summary with a missing field", () => {
    const { delay_days, ...incomplete } = makeSimulatedArrival();

    expect(delay_days).toBe(6);
    expect(isSimulatedArrivalSummary(incomplete)).toBeNull();
  });

  it("rejects a simulated-arrival summary with an unexpected extra field", () => {
    const payload = makeSimulatedArrival() as unknown as Record<string, unknown>;
    payload.extra = true;

    expect(isSimulatedArrivalSummary(payload)).toBeNull();
  });

  it("rejects non-object bodies for both validators", () => {
    expect(isOperationalRefreshSummary(null)).toBeNull();
    expect(isOperationalRefreshSummary("summary")).toBeNull();
    expect(isOperationalRefreshSummary([makeRefreshSummary()])).toBeNull();
    expect(isSimulatedArrivalSummary(undefined)).toBeNull();
    expect(isSimulatedArrivalSummary(7)).toBeNull();
  });

  it("maps a 200 refresh response to the success state", async () => {
    const result = await refreshOperationsPipeline();

    expect(result).toEqual({
      kind: "success",
      data: makeRefreshSummary(),
    });
  });

  it("maps a 200 simulate response to the success state", async () => {
    const result = await simulateShipmentArrival();

    expect(result).toEqual({
      kind: "success",
      data: makeSimulatedArrival(),
    });
  });

  it("fails closed when the refresh response is malformed", async () => {
    server.use(
      http.post(operationsRefreshPath(), () =>
        HttpResponse.json({ new_exceptions: "many" }),
      ),
    );

    const result = await refreshOperationsPipeline();

    expect(result).toEqual({
      kind: "unexpected",
      message: "The Adensa API returned an unexpected response shape.",
    });
  });

  it("fails closed when the simulate response is malformed", async () => {
    server.use(
      http.post(operationsSimulatePath(), () =>
        HttpResponse.json({ shipment_id: 123 }),
      ),
    );

    const result = await simulateShipmentArrival();

    expect(result).toEqual({
      kind: "unexpected",
      message: "The Adensa API returned an unexpected response shape.",
    });
  });

  it("maps the simulate 409 guard to the guard state with the backend message", async () => {
    server.use(
      http.post(operationsSimulatePath(), () =>
        HttpResponse.json(
          { detail: "No operational data to derive a simulated arrival from." },
          { status: 409 },
        ),
      ),
    );

    const result = await simulateShipmentArrival();

    expect(result).toEqual({
      kind: "guard",
      message: "No operational data to derive a simulated arrival from.",
    });
  });

  it("maps a network failure to the unavailable state", async () => {
    server.use(
      http.post(operationsRefreshPath(), () => HttpResponse.error()),
    );

    const result = await refreshOperationsPipeline();

    expect(result.kind).toBe("unavailable");
  });

  it("maps an HTTP 500 to the unavailable state without leaking internals", async () => {
    server.use(
      http.post(operationsSimulatePath(), () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    const result = await simulateShipmentArrival();

    expect(result).toEqual({
      kind: "unavailable",
      message: "The Adensa API reported an error (HTTP 500).",
    });
  });

  it("posts without a request body to both endpoints", async () => {
    const bodies: unknown[] = [];

    server.use(
      http.post(operationsRefreshPath(), async ({ request }) => {
        bodies.push(await request.text());
        return HttpResponse.json(makeRefreshSummary());
      }),
      http.post(operationsSimulatePath(), async ({ request }) => {
        bodies.push(await request.text());
        return HttpResponse.json(makeSimulatedArrival());
      }),
    );

    await refreshOperationsPipeline();
    await simulateShipmentArrival();

    expect(bodies).toEqual(["", ""]);
  });
});

// ==================================================
// SERVER ACTIONS
// ==================================================

describe("operations server actions", () => {
  it("returns the success result and revalidates / and /exceptions on refresh", async () => {
    const result = await refreshPipelineAction();

    expect(result.status).toBe("success");
    expect(result.status === "success" && result.data).toEqual(
      makeRefreshSummary(),
    );
    expect(revalidateMock).toHaveBeenCalledTimes(2);
    expect(revalidateMock).toHaveBeenNthCalledWith(1, "/");
    expect(revalidateMock).toHaveBeenNthCalledWith(2, "/exceptions");
  });

  it("returns the success result and revalidates / and /exceptions on simulate", async () => {
    const result = await simulateArrivalAction();

    expect(result.status).toBe("success");
    expect(
      result.status === "success" &&
        result.data.shipment_id === "SHP-010000",
    ).toBe(true);
    expect(revalidateMock).toHaveBeenCalledTimes(2);
    expect(revalidateMock).toHaveBeenNthCalledWith(1, "/");
    expect(revalidateMock).toHaveBeenNthCalledWith(2, "/exceptions");
  });

  it("does not revalidate when the refresh is unavailable", async () => {
    server.use(
      http.post(operationsRefreshPath(), () => HttpResponse.error()),
    );

    const result = await refreshPipelineAction();

    expect(result.status).toBe("unavailable");
    expect(revalidateMock).not.toHaveBeenCalled();
  });

  it("carries the simulate 409 guard through verbatim without revalidating", async () => {
    server.use(
      http.post(operationsSimulatePath(), () =>
        HttpResponse.json(
          { detail: "No operational data to derive a simulated arrival from." },
          { status: 409 },
        ),
      ),
    );

    const result = await simulateArrivalAction();

    expect(result).toEqual({
      status: "guard",
      message: "No operational data to derive a simulated arrival from.",
    });
    expect(revalidateMock).not.toHaveBeenCalled();
  });

  it("maps a contract violation to the unexpected state", async () => {
    server.use(
      http.post(operationsRefreshPath(), () =>
        HttpResponse.json({ oops: true }),
      ),
    );

    const result = await refreshPipelineAction();

    expect(result).toEqual({
      status: "unexpected",
      message: "The Adensa API returned an unexpected response shape.",
    });
    expect(revalidateMock).not.toHaveBeenCalled();
  });
});

// ==================================================
// OPERATIONS PAGE COMPONENT
// ==================================================

describe("OperationsControls", () => {
  it("renders both controls with the preserved terminology", () => {
    render(<OperationsControls />);

    expect(
      screen.getByRole("button", { name: "Simulate Shipment Arrival" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Refresh Operations Pipeline" }),
    ).toBeInTheDocument();
  });

  it("the page preserves the canonical lifecycle terminology", () => {
    render(<OperationsPage />);

    expect(
      screen.getByText(/Detect → Analyze → Recommend → Approve → Execute → Resolve/),
    ).toBeInTheDocument();
  });

  it("renders the refresh result summary with all reported figures", async () => {
    server.use(
      http.post(operationsRefreshPath(), () =>
        HttpResponse.json(
          makeRefreshSummary({
            new_exceptions: 2,
            new_options: 3,
            new_exception_ids: ["EXC-001530", "EXC-001531"],
            actions_evaluated: 5,
            new_actions: 2,
            actions_without_recommendation: 1,
            actions_skipped: 2,
          }),
        ),
      ),
    );

    const user = userEvent.setup();
    render(<OperationsControls />);

    await user.click(
      screen.getByRole("button", { name: "Refresh Operations Pipeline" }),
    );

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Detected 2 new exceptions.");
    expect(screen.getByText("New exceptions")).toBeInTheDocument();
    expect(screen.getByText("New recovery options")).toBeInTheDocument();
    expect(screen.getByText("New workflow actions")).toBeInTheDocument();
    expect(screen.getByText("Actions evaluated")).toBeInTheDocument();
    expect(screen.getByText("Without recommendation")).toBeInTheDocument();
    expect(screen.getByText("Actions skipped")).toBeInTheDocument();
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("links each returned new exception ID to its investigation workspace", async () => {
    server.use(
      http.post(operationsRefreshPath(), () =>
        HttpResponse.json(
          makeRefreshSummary({
            new_exceptions: 2,
            new_exception_ids: ["EXC-001530", "EXC-001531"],
          }),
        ),
      ),
    );

    const user = userEvent.setup();
    render(<OperationsControls />);

    await user.click(
      screen.getByRole("button", { name: "Refresh Operations Pipeline" }),
    );

    const links = await screen.findAllByRole("link", {
      name: /Investigate EXC-00153/,
    });

    expect(links).toHaveLength(2);
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      `/exceptions/${encodeURIComponent("EXC-001530")}`,
      `/exceptions/${encodeURIComponent("EXC-001531")}`,
    ]);
  });

  it("makes a single new exception the prominent investigation affordance", async () => {
    server.use(
      http.post(operationsRefreshPath(), () =>
        HttpResponse.json(
          makeRefreshSummary({
            new_exceptions: 1,
            new_options: 1,
            new_exception_ids: ["EXC-001530"],
            actions_evaluated: 1,
            new_actions: 1,
          }),
        ),
      ),
    );

    const user = userEvent.setup();
    render(<OperationsControls />);

    await user.click(
      screen.getByRole("button", { name: "Refresh Operations Pipeline" }),
    );

    const link = await screen.findByRole("link", {
      name: "Investigate EXC-001530",
    });

    // The prominent affordance: exactly one, accent-styled.
    expect(link).toHaveClass("op-single-link");
    expect(
      screen.queryByRole("list", { name: "" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryAllByRole("link", { name: /Investigate EXC-/ }),
    ).toHaveLength(1);
    expect(screen.getByText("Detected 1 new exception.")).toBeInTheDocument();
  });

  it("renders the simulation summary from the backend payload", async () => {
    const user = userEvent.setup();
    render(<OperationsControls />);

    await user.click(
      screen.getByRole("button", { name: "Simulate Shipment Arrival" }),
    );

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Shipment SHP-010000 arrived.");
    expect(screen.getByText("SHP-010000")).toBeInTheDocument();
    expect(screen.getByText("ORD-0001")).toBeInTheDocument();
    expect(screen.getByText("CAR-001")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("2026-09-15")).toBeInTheDocument();
    expect(screen.getByText("2026-09-21")).toBeInTheDocument();
    expect(screen.getByText("6 day(s)")).toBeInTheDocument();
    expect(
      screen.getByText(/run Refresh Operations Pipeline to detect/i),
    ).toBeInTheDocument();
  });

  it("renders the simulate 409 guard honestly as an operational state", async () => {
    server.use(
      http.post(operationsSimulatePath(), () =>
        HttpResponse.json(
          { detail: "No operational data to derive a simulated arrival from." },
          { status: 409 },
        ),
      ),
    );

    const user = userEvent.setup();
    render(<OperationsControls />);

    await user.click(
      screen.getByRole("button", { name: "Simulate Shipment Arrival" }),
    );

    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent(
      "No operational data to derive a simulated arrival from.",
    );
  });

  it("renders an unavailable failure without leaking internals", async () => {
    server.use(
      http.post(operationsRefreshPath(), () =>
        HttpResponse.json({ detail: "internal boom" }, { status: 500 }),
      ),
    );

    const user = userEvent.setup();
    render(<OperationsControls />);

    await user.click(
      screen.getByRole("button", { name: "Refresh Operations Pipeline" }),
    );

    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent(
      "The Adensa API reported an error (HTTP 500).",
    );
    expect(banner).not.toHaveTextContent("internal boom");
  });

  it("disables both controls while a mutation is pending and restores them after", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });

    server.use(
      http.post(operationsSimulatePath(), async () => {
        await gate;
        return HttpResponse.json(makeSimulatedArrival());
      }),
    );

    const user = userEvent.setup();
    render(<OperationsControls />);

    const simulateButton = screen.getByRole("button", {
      name: "Simulate Shipment Arrival",
    });
    const refreshButton = screen.getByRole("button", {
      name: "Refresh Operations Pipeline",
    });

    await user.click(simulateButton);

    // Pending: both controls are disabled, the pending label is
    // visible, and the forms expose aria-busy — no accidental
    // repeated submission is possible.
    expect(screen.getByText("Recording arrival…")).toBeDisabled();
    expect(refreshButton).toBeDisabled();
    expect(simulateButton.closest("form")).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(refreshButton.closest("form")).toHaveAttribute(
      "aria-busy",
      "false",
    );

    release();
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("arrived");
    });

    expect(screen.getByRole("button", { name: "Simulate Shipment Arrival" })).toBeEnabled();
    expect(refreshButton).toBeEnabled();
    expect(simulateButton.closest("form")).toHaveAttribute(
      "aria-busy",
      "false",
    );
  });

  it("revalidation policy: the actions target only / and /exceptions", async () => {
    // Direct policy assertion against the mocked next/cache —
    // complements the per-action assertions above.
    await simulateArrivalAction();

    const paths = revalidateMock.mock.calls.map((call) => call[0]);

    expect(paths).toEqual(["/", "/exceptions"]);
    expect(paths).not.toContain("/operations");
  });

  it("the mock server has default handlers for both operations endpoints", () => {
    // Guard on the shared mock infrastructure itself: the two
    // endpoints the client posts to must be handled by default,
    // or every unmocked render of this page would fail loudly.
    const handlers = server.listHandlers();
    const urls = handlers.map((handler) =>
      (handler as unknown as { info?: { path?: unknown } }).info?.path?.toString(),
    );

    expect(urls).toContain(operationsRefreshPath());
    expect(urls).toContain(operationsSimulatePath());
    expect(urls).not.toContain(`${API_BASE_URL}/v1/operations/unknown`);
  });
});
