/**
 * Command Centre v2 component contracts: the living-network
 * strip, Critical Attention, the Living Operational Flow,
 * the attention queue, and the Manager Lookup entry point.
 * All data comes from the committed /v1 contract samples —
 * no invented fields, no client-side metric computation.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NetworkStrip } from "@/components/control-tower/NetworkStrip";
import { CriticalAttention } from "@/components/control-tower/CriticalAttention";
import { OperationalFlow } from "@/components/control-tower/OperationalFlow";
import { AttentionQueue } from "@/components/control-tower/AttentionQueue";
import { ManagerLookup } from "@/components/control-tower/ManagerLookup";
import { makeSummary, makeInboxRow } from "./helpers/api-mocks";

afterEach(() => cleanup());

describe("NetworkStrip", () => {
  it("renders the abstract network as decoration only", () => {
    render(<NetworkStrip />);

    const strip = document.querySelector(".network-strip");
    expect(strip).toHaveAttribute("aria-hidden", "true");
    expect(strip?.querySelectorAll(".network-strip-node")).toHaveLength(5);
  });
});

describe("CriticalAttention", () => {
  it("renders the critical slice with direct investigation links", () => {
    const rows = [
      makeInboxRow({
        exception_id: "EXC-900100",
        severity: "Critical",
        shipment_id: "SHP-900100",
        exception_type: "Shipment Delay",
        estimated_impact: "Estimated delivery delay of 4 day(s).",
        workflow_state: "Decision required",
      }),
      makeInboxRow({
        exception_id: "EXC-900101",
        severity: "Low",
        exception_type: "Shipment Delay",
      }),
    ];

    render(<CriticalAttention rows={rows} />);

    // Only the critical row is surfaced; the low row is not.
    expect(screen.getByRole("link", { name: "EXC-900100" })).toBeInTheDocument();
    expect(screen.queryByText("EXC-900101")).not.toBeInTheDocument();

    // Direct action into the workspace.
    expect(
      screen.getAllByRole("link", {
        name: /Investigate/,
      })[0],
    ).toHaveAttribute("href", "/exceptions/EXC-900100");

    // The row answers what happened / which shipment / what stage.
    expect(screen.getByText("Shipment Delay")).toBeInTheDocument();
    expect(screen.getByText(/Estimated delivery delay/)).toBeInTheDocument();
    expect(screen.getByText("SHP-900100")).toBeInTheDocument();
    expect(screen.getByText("Decision required")).toBeInTheDocument();
  });

  it("shows the calm explicit state when nothing is critical", () => {
    render(
      <CriticalAttention
        rows={[makeInboxRow({ exception_id: "EXC-900100", severity: "Low" })]}
      />,
    );

    expect(
      screen.getByText(/No critical exceptions are open/),
    ).toBeInTheDocument();
  });

  it("caps the critical list at four entries", () => {
    const rows = Array.from({ length: 6 }, (_, i) =>
      makeInboxRow({ exception_id: `EXC-9002${i}`, severity: "Critical" }),
    );

    render(<CriticalAttention rows={rows} />);

    expect(document.querySelectorAll(".critical-attention-item")).toHaveLength(4);
  });
});

describe("OperationalFlow", () => {
  it("maps the real summary populations onto the five stages", () => {
    const summary = makeSummary({
      open_exceptions: 40,
      actionable_exceptions: 12,
      pending_approvals: 5,
      awaiting_execution: 3,
      recently_resolved: [
        {
          exception_id: "EXC-900200",
          exception_type: "Shipment Delay",
          severity: "Medium",
          resolution_status: "Resolved",
          resolved_at: null,
          resolution_path: "System recovery executed",
        },
      ],
    });

    render(<OperationalFlow summary={summary} />);

    const flow = screen.getByRole("list", { name: "Living operational flow" });
    expect(flow).toBeInTheDocument();

    // Verbatim counts from the summary fields — one value span
    // per stage, asserted by class (index badges also hold digits).
    const values = [...flow.querySelectorAll(".operational-flow-value")].map(
      (el) => el.textContent,
    );
    expect(values).toEqual(["40", "12", "5", "3", "1"]);

    // Stage labels and truthful deep-links.
    const links = [...flow.querySelectorAll("a")].map((a) =>
      a.getAttribute("href"),
    );
    expect(links[0]).toBe("/exceptions");
    expect(links[2]).toBe("/exceptions?workflow_state=Decision%20required");
    expect(links[4]).toBe("#monitor");
  });

  it("renders zero stages as zero without hiding them", () => {
    const summary = makeSummary({
      open_exceptions: 0,
      actionable_exceptions: 0,
      pending_approvals: 0,
      awaiting_execution: 0,
      recently_resolved: [],
    });

    render(<OperationalFlow summary={summary} />);

    const values = [
      ...document.querySelectorAll(".operational-flow-value"),
    ].map((el) => el.textContent);
    expect(values).toEqual(["0", "0", "0", "0", "0"]);
    expect(document.querySelectorAll(".operational-flow-step.is-live")).toHaveLength(0);
  });
});

describe("AttentionQueue", () => {
  it("renders the bounded queue in the backend's order with bounded honesty", () => {
    const rows = [
      makeInboxRow({ exception_id: "EXC-900100", estimated_impact: "Delay of 4 day(s)." }),
      makeInboxRow({ exception_id: "EXC-900101", estimated_impact: "Delay of 2 day(s)." }),
    ];
    const summary = makeSummary({ open_exceptions: 786 });

    render(<AttentionQueue rows={rows} summary={summary} />);

    expect(screen.getByRole("link", { name: "EXC-900100" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "EXC-900101" })).toBeInTheDocument();
    expect(
      screen.getByText(/Showing 2 of 786 open exceptions/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /full Exception Inbox/i })).toHaveAttribute(
      "href",
      "/exceptions",
    );
  });

  it("omits the bounded note when the window covers the population", () => {
    render(
      <AttentionQueue
        rows={[makeInboxRow({ exception_id: "EXC-900100" })]}
        summary={makeSummary({ open_exceptions: 1 })}
      />,
    );

    expect(screen.queryByText(/Showing \d+ of/)).not.toBeInTheDocument();
  });

  it("renders the calm explicit empty state", () => {
    render(<AttentionQueue rows={[]} summary={makeSummary({ open_exceptions: 0 })} />);

    expect(
      screen.getByText(/work queue is clear/),
    ).toBeInTheDocument();
  });

  it("caps the queue at ten rows", () => {
    const rows = Array.from({ length: 12 }, (_, i) =>
      makeInboxRow({ exception_id: `EXC-9003${String(i).padStart(2, "0")}` }),
    );

    render(<AttentionQueue rows={rows} summary={null} />);

    expect(document.querySelectorAll(".attention-queue-item")).toHaveLength(10);
  });
});

describe("ManagerLookup", () => {
  it("routes EXC identifiers to the investigation workspace", async () => {
    const user = userEvent.setup();
    render(<ManagerLookup />);

    await user.type(
      screen.getByLabelText(/Shipment or exception identifier/),
      "exc-001529",
    );
    await user.click(screen.getByRole("button", { name: "Look up" }));

    expect(useRouterPushMock).toHaveBeenCalledWith("/exceptions/EXC-001529");
  });

  it("routes everything else to the inbox search", async () => {
    const user = userEvent.setup();
    render(<ManagerLookup />);

    await user.type(
      screen.getByLabelText(/Shipment or exception identifier/),
      "Hamburg",
    );
    await user.click(screen.getByRole("button", { name: "Look up" }));

    expect(useRouterPushMock).toHaveBeenCalledWith("/exceptions?q=Hamburg");
  });

  it("does nothing on an empty query", async () => {
    const user = userEvent.setup();
    render(<ManagerLookup />);

    await user.click(screen.getByRole("button", { name: "Look up" }));

    expect(useRouterPushMock).not.toHaveBeenCalled();
  });
});

// The router mock must exist before the component under test
// imports next/navigation; hoisted here and consumed above.
const useRouterPushMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: useRouterPushMock }),
}));
