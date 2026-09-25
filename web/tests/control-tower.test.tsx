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
import { QueueCompositionBand } from "@/components/control-tower/QueueCompositionBand";
import { FollowUpDelayIndicator } from "@/components/control-tower/FollowUpDelayIndicator";
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

  it("deep-links every KPI card to its truthful Inbox view (P8.8)", () => {
    render(<ControlTowerMetrics summary={summary} />);

    const hrefOf = (label: string): string | null => {
      const link = screen.getByRole("link", { name: new RegExp(label) });
      return link.getAttribute("href");
    };

    expect(hrefOf("Open Exceptions")).toBe("/exceptions");
    expect(hrefOf("Pending Decisions")).toBe(
      "/exceptions?workflow_state=Decision%20required",
    );
    expect(hrefOf("Awaiting Execution")).toBe(
      "/exceptions?workflow_state=Awaiting%20execution",
    );
    expect(hrefOf("Follow-up Required")).toBe(
      "/exceptions?workflow_state=Executed%20%E2%80%94%20still%20open",
    );
    expect(hrefOf("Critical Open")).toBe("/exceptions?severity=Critical");
    expect(hrefOf("Actionable")).toBe("/exceptions?verdict=actionable");
    expect(hrefOf("Monitoring")).toBe("/exceptions?verdict=no-feasible");
  });

  it("renders all seven KPI cards as keyboard-reachable semantic links", () => {
    render(<ControlTowerMetrics summary={summary} />);

    const links = screen.getAllByRole("link");

    expect(links).toHaveLength(7);
    for (const link of links) {
      expect(link.tagName).toBe("A");
      expect(link.getAttribute("href")).toMatch(/^\/exceptions/);
    }
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

  it("keeps the dates as text and adds the supplementary indicator only for late entries", () => {
    render(
      <FollowUpTable
        entries={[
          {
            exception_id: "EXC-900100",
            severity: "High",
            exception_type: "Shipment Delay",
            detected_at: "2026-09-01 06:00:00",
            action_id: "ACT-000123",
            executed_at: "2026-09-02 09:00:00",
            estimated_arrival: "2026-09-19",
            required_delivery_date: "2026-09-15",
            actionable: true,
            reason:
              "Recovery ACT-000123 executed 2026-09-02 09:00:00, but estimated arrival 2026-09-19 remains later than required delivery 2026-09-15.",
          },
          {
            exception_id: "EXC-900101",
            severity: "Medium",
            exception_type: "Shipment Delay",
            detected_at: "2026-09-01 06:00:00",
            action_id: "ACT-000124",
            executed_at: "2026-09-02 09:00:00",
            estimated_arrival: null,
            required_delivery_date: "2026-09-15",
            actionable: false,
            reason:
              "Recovery ACT-000124 executed 2026-09-02 09:00:00; no estimated arrival is available.",
          },
        ]}
      />,
    );

    // Dates remain verbatim text for both entries.
    expect(screen.getByText("2026-09-19 vs 2026-09-15")).toBeInTheDocument();
    expect(screen.getByText("— vs 2026-09-15")).toBeInTheDocument();

    // Indicator present only for the late entry with a real ETA.
    expect(screen.getAllByText(/ETA \d+ days? after required/)).toHaveLength(1);
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

describe("queue composition band", () => {
  it("renders proportions from the documented partition verbatim", () => {
    render(
      <QueueCompositionBand
        summary={makeSummary({
          actionable_exceptions: 75,
          monitoring_exceptions: 25,
          critical_exceptions: 100,
          open_exceptions: 400,
        })}
      />,
    );

    const tracks = screen.getAllByRole("img");
    expect(tracks).toHaveLength(2);

    // Partition band: 75/100 of the width.
    const segments = [...tracks[0].querySelectorAll(".band-segment")];
    expect(segments[0]).toHaveStyle({ width: "75%" });
    expect(segments[1]).toHaveStyle({ width: "25%" });

    // Critical share: 100/400 of the width.
    const criticalSegments = [...tracks[1].querySelectorAll(".band-segment")];
    expect(criticalSegments[0]).toHaveStyle({ width: "25%" });
    expect(criticalSegments[1]).toHaveStyle({ width: "75%" });
  });

  it("carries the exact counts in visible and aria text", () => {
    render(
      <QueueCompositionBand
        summary={makeSummary({
          actionable_exceptions: 3,
          monitoring_exceptions: 2,
          critical_exceptions: 271,
          open_exceptions: 2256,
        })}
      />,
    );

    expect(screen.getByText("Actionable 3 · Monitoring 2")).toBeInTheDocument();
    expect(screen.getByText("Critical 271 · Other open 1985")).toBeInTheDocument();

    expect(
      screen.getByRole("img", {
        name: "Bounded work queue: Actionable 3, Monitoring 2.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", {
        name: "Open population: Critical 271, Other open 1985.",
      }),
    ).toBeInTheDocument();
  });

  it("is zero-safe: zero queue renders an empty band, never NaN or 100%", () => {
    render(
      <QueueCompositionBand
        summary={makeSummary({
          actionable_exceptions: 0,
          monitoring_exceptions: 0,
          critical_exceptions: 0,
          open_exceptions: 0,
        })}
      />,
    );

    const tracks = screen.getAllByRole("img");
    expect(tracks).toHaveLength(2);

    for (const track of tracks) {
      const filled = track.querySelectorAll(
        ".band-segment:not(.band-segment-empty)",
      );
      expect(filled).toHaveLength(0);
      expect(track.querySelector(".band-segment-empty")).not.toBeNull();
    }

    // True counts still visible.
    expect(screen.getByText("Actionable 0 · Monitoring 0")).toBeInTheDocument();
    expect(screen.getByText("Critical 0 · Other open 0")).toBeInTheDocument();
  });

  it("is zero-safe when the queue is empty but the population is not", () => {
    render(
      <QueueCompositionBand
        summary={makeSummary({
          actionable_exceptions: 0,
          monitoring_exceptions: 0,
          critical_exceptions: 5,
          open_exceptions: 50,
        })}
      />,
    );

    const tracks = screen.getAllByRole("img");
    // Queue band empty; critical band renders 10% / 90%.
    expect(
      tracks[0].querySelector(".band-segment-empty"),
    ).not.toBeNull();
    const criticalSegments = [...tracks[1].querySelectorAll(".band-segment")];
    expect(criticalSegments[0]).toHaveStyle({ width: "10%" });
    expect(criticalSegments[1]).toHaveStyle({ width: "90%" });
  });
});

describe("follow-up delay indicator", () => {
  it("renders nothing without an ETA, preserving the plain fallback", () => {
    const { container } = render(
      <FollowUpDelayIndicator
        anchorDate="2026-09-12 09:00:00"
        estimatedArrival={null}
        requiredDeliveryDate="2026-09-15"
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders the late window with the required-date marker for late entries", () => {
    // Anchor 09-01 -> ETA 09-15 (14-day span); required 09-10
    // -> marker at 9/14 of the track, late zone the rest.
    const { container } = render(
      <FollowUpDelayIndicator
        anchorDate="2026-09-01"
        estimatedArrival="2026-09-15"
        requiredDeliveryDate="2026-09-10"
      />,
    );

    const late = container.querySelector(".delay-indicator-late") as HTMLElement;
    const marker = container.querySelector(
      ".delay-indicator-marker",
    ) as HTMLElement;

    // Proportional arithmetic within floating-point precision:
    // the marker sits at 9/14 of the track, the late zone is
    // the remainder (the component computes width as 100 − left).
    const markerPercent = (9 / 14) * 100;
    expect(parseFloat(late.style.left)).toBeCloseTo(markerPercent, 10);
    expect(parseFloat(late.style.width)).toBeCloseTo(100 - markerPercent, 10);
    expect(parseFloat(marker.style.left)).toBeCloseTo(markerPercent, 10);
    expect(container.textContent).toContain(
      "ETA 5 days after required",
    );
  });

  it("is hidden from assistive technology — dates remain the content", () => {
    const { container } = render(
      <FollowUpDelayIndicator
        anchorDate="2026-09-01"
        estimatedArrival="2026-09-15"
        requiredDeliveryDate="2026-09-10"
      />,
    );

    expect(container.firstElementChild).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });

  it("renders nothing when the ETA is not after the required date", () => {
    const { container } = render(
      <FollowUpDelayIndicator
        anchorDate="2026-09-01"
        estimatedArrival="2026-09-10"
        requiredDeliveryDate="2026-09-10"
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the anchor date is missing or unparseable", () => {
    const missing = render(
      <FollowUpDelayIndicator
        anchorDate={null}
        estimatedArrival="2026-09-15"
        requiredDeliveryDate="2026-09-10"
      />,
    );
    expect(missing.container).toBeEmptyDOMElement();

    const garbage = render(
      <FollowUpDelayIndicator
        anchorDate="not-a-date"
        estimatedArrival="2026-09-15"
        requiredDeliveryDate="2026-09-10"
      />,
    );
    expect(garbage.container).toBeEmptyDOMElement();
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
