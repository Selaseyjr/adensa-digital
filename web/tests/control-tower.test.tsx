/**
 * Control Tower contract tests: the surface renders the API
 * summary verbatim, preserves the documented population
 * semantics, and the API client maps every failure mode to a
 * deliberate state.
 *
 * Structure tests target the presentational components with
 * typed props — the exact objects the /v1 contract delivers.
 * The helpers double as contract samples: api-client.test.ts
 * verifies the same payloads pass the client's validators
 * against a mocked /v1 server, so the chain
 * (Pydantic model -> sample payload -> rendered component)
 * stays connected.
 *
 * Network behaviour (real fetch through lib/api/client) is
 * covered in api-client.test.ts.
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ControlTowerMetrics } from "@/components/control-tower/ControlTowerMetrics";
import { FollowUpTable } from "@/components/control-tower/FollowUpTable";
import { RecentlyResolvedTable } from "@/components/control-tower/RecentlyResolvedTable";
import {
  LoadingPanel,
  UnavailablePanel,
  UnexpectedPanel,
  EmptyPanel,
} from "@/components/StatePanels";
import { makeSummary } from "./helpers/api-mocks";

afterEach(() => cleanup());

const summary = makeSummary({
  follow_up_queue: [
    {
      exception_id: "EXC-900100",
      severity: "High",
      exception_type: "Shipment Delay",
      detected_at: "2026-09-10 12:00:00",
      action_id: "ACT-000123",
      executed_at: "2026-09-12 09:00:00",
      estimated_arrival: "2026-09-19",
      required_delivery_date: "2026-09-15",
      actionable: true,
      reason:
        "Recovery ACT-000123 executed 2026-09-12 09:00:00, but estimated arrival 2026-09-19 remains later than required delivery 2026-09-15.",
    },
  ],
  recently_resolved: [
    {
      exception_id: "EXC-900200",
      exception_type: "Shipment Delay",
      severity: "Medium",
      resolution_status: "Resolved",
      resolved_at: "2026-09-14 10:00:00",
      resolution_path: "Manually resolved",
    },
  ],
});

describe("control tower metrics", () => {
  it("renders every KPI from the API summary verbatim", () => {
    render(<ControlTowerMetrics summary={summary} />);

    expect(screen.getByText("Open Exceptions")).toBeInTheDocument();
    expect(screen.getByText(String(summary.open_exceptions))).toBeInTheDocument();
    expect(screen.getByText("Pending Decisions")).toBeInTheDocument();
    expect(screen.getByText(String(summary.pending_approvals))).toBeInTheDocument();
    expect(screen.getByText("Awaiting Execution")).toBeInTheDocument();
    expect(
      screen.getByText(String(summary.awaiting_execution)),
    ).toBeInTheDocument();
    expect(screen.getByText("Follow-up Required")).toBeInTheDocument();
    expect(
      screen.getByText(String(summary.follow_up_required)),
    ).toBeInTheDocument();
    expect(screen.getByText("Critical Open")).toBeInTheDocument();
    expect(
      screen.getByText(String(summary.critical_exceptions)),
    ).toBeInTheDocument();
    expect(screen.getByText("Actionable")).toBeInTheDocument();
    expect(
      screen.getByText(String(summary.actionable_exceptions)),
    ).toBeInTheDocument();
    expect(screen.getByText("Monitoring")).toBeInTheDocument();
    expect(
      screen.getByText(String(summary.monitoring_exceptions)),
    ).toBeInTheDocument();
  });

  it("preserves the documented population semantics in the labels", () => {
    render(<ControlTowerMetrics summary={summary} />);

    // Full-population metrics.
    expect(screen.getByText("Full operational population")).toBeInTheDocument();

    // Bounded work-queue metrics carry their own note.
    expect(
      screen.getByText("Bounded work queue — feasible recovery available"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Bounded work queue — no feasible recovery"),
    ).toBeInTheDocument();

    // The follow-up metric states the honesty rule.
    expect(
      screen.getByText("Executed recovery, still open (full population)"),
    ).toBeInTheDocument();
  });

  it("renders zero values without treating them as missing", () => {
    render(
      <ControlTowerMetrics summary={makeSummary({ pending_approvals: 0 })} />,
    );

    expect(screen.getByText("0")).toBeInTheDocument();
  });
});

describe("follow-up queue", () => {
  it("renders the executed-but-still-open entries with the API's factual reason", () => {
    render(<FollowUpTable entries={summary.follow_up_queue} />);

    expect(screen.getByText("EXC-900100")).toBeInTheDocument();
    expect(
      screen.getByText(/remains later than required delivery/),
    ).toBeInTheDocument();
    expect(screen.getByText("2026-09-19 vs 2026-09-15")).toBeInTheDocument();
  });

  it("shows the quiet state when no follow-up work exists", () => {
    render(<FollowUpTable entries={[]} />);

    expect(
      screen.getByText("No follow-up work outstanding."),
    ).toBeInTheDocument();
  });
});

describe("recently resolved queue", () => {
  it("renders resolution paths decided by the backend evidence", () => {
    render(<RecentlyResolvedTable entries={summary.recently_resolved} />);

    expect(screen.getByText("EXC-900200")).toBeInTheDocument();
    expect(screen.getByText("Manually resolved")).toBeInTheDocument();
  });

  it("renders the empty state when nothing is resolved yet", () => {
    render(<RecentlyResolvedTable entries={[]} />);

    expect(
      screen.getByText("No exceptions resolved yet."),
    ).toBeInTheDocument();
  });
});

describe("deliberate UI states", () => {
  it("loading panel announces itself politely", () => {
    render(<LoadingPanel label="control tower" />);

    expect(
      screen.getByRole("status", { name: "control tower — loading" }),
    ).toBeInTheDocument();
  });

  it("unavailable panel describes the operational impact without backend detail", () => {
    render(
      <UnavailablePanel message="The Adensa API is unreachable." />,
    );

    expect(
      screen.getByRole("alert"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Operational data unavailable"),
    ).toBeInTheDocument();
  });

  it("unexpected panel reports contract violations", () => {
    render(
      <UnexpectedPanel message="The Adensa API returned an unexpected response shape." />,
    );

    expect(screen.getByText("Unexpected API response")).toBeInTheDocument();
  });

  it("empty panel renders the honest empty message", () => {
    render(<EmptyPanel message="No operational data is available yet." />);

    expect(
      screen.getByText("No operational data is available yet."),
    ).toBeInTheDocument();
  });
});
