/**
 * P8.7.2 tests: the analytical layer on the Control Tower —
 * the LineChart SVG primitive, the AnalyticsSection panels
 * fed by the real `/v1/analytics/overview` contract (P8.7.1),
 * and the client function's four result states.
 *
 * Test architecture note (matching the suite's established
 * pattern): jsdom cannot render async Server Components, so
 * structure tests target the presentational components with
 * typed props — the exact objects the API contract delivers —
 * and network/state behaviour is tested against the real
 * client with MSW (onUnhandledRequest: "error").
 *
 * Honesty rules under test:
 * - the panels render the API's own basis wording verbatim;
 * - a null rate (zero denominator) is a gap, never a 0%
 *   point or a fabricated value;
 * - no business arithmetic: displayed percentages come from
 *   the API payload, not recomputation;
 * - empty and unavailable analytics map to distinct,
 *   deliberate client states.
 */

import { afterEach, beforeAll, afterAll, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { AnalyticsSection } from "@/components/control-tower/AnalyticsSection";
import { LineChart } from "@/components/control-tower/LineChart";
import { getAnalyticsOverview } from "@/lib/api/client";
import {
  analyticsPath,
  createApiServer,
  makeAnalyticsOverview,
  makeServicePerformancePoint,
} from "./helpers/api-mocks";

const server = createApiServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

/** The mock overview payload, typed as the record MSW expects. */
const overview = (overrides: {
  service_performance?: unknown;
  exception_incidence?: unknown;
} = {}): Record<string, unknown> =>
  makeAnalyticsOverview(overrides) as unknown as Record<string, unknown>;

describe("AnalyticsSection — default panels", () => {
  it("renders service performance from real API values", () => {
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    expect(
      screen.getByRole("heading", { name: "Service performance" }),
    ).toBeInTheDocument();
    // Percentage text comes verbatim from the API payload.
    expect(screen.getByText("80% on time")).toBeInTheDocument();
  });

  it("renders exception incidence with departure-month wording", () => {
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    expect(
      screen.getByRole("heading", { name: "Exception incidence" }),
    ).toBeInTheDocument();
    // Basis wording verbatim from the API contract.
    expect(
      screen.getAllByText("Exceptions by shipment departure month").length,
    ).toBeGreaterThan(0);
    // The emphasised count pair renders verbatim (130 of 488).
    const contextParagraphs = document.querySelectorAll<HTMLParagraphElement>(
      ".analytics-context",
    );
    const incidenceContext = Array.from(contextParagraphs).find((p) =>
      p.textContent?.includes("departing shipments"),
    );
    expect(incidenceContext).toHaveTextContent(
      "130 of 488 departing shipments carried exceptions in 2026-02",
    );
  });

  it("renders correct percentage values without recomputation", () => {
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    // 63.2 and 74.5 exist only if the API's own rates render.
    const table = screen.getAllByRole("table", {
      name: /On-time rate by month/i,
    })[0];
    expect(table).toHaveTextContent("63.2%");
    expect(table).toHaveTextContent("74.5%");
    expect(table).toHaveTextContent("80%");
  });

  it("renders month labels on the chart x-axes", () => {
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    // SVG text nodes: axis labels plus the fallback tables.
    expect(screen.getAllByText("2026-01").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2026-04").length).toBeGreaterThan(0);
  });

  it("states the recorded-month count when series months are absent", () => {
    // A series with a gap between first and last month must not
    // imply continuous coverage ("Jan–Apr") — the span label
    // states how many months were actually recorded.
    render(
      <AnalyticsSection
        overview={makeAnalyticsOverview({
          service_performance: {
            basis: "Delivered shipments by planned-arrival month",
            points: [
              makeServicePerformancePoint({
                month: "2026-01",
                delivered: 90,
                on_time: 57,
                on_time_rate: 63.3,
              }),
              makeServicePerformancePoint({
                month: "2026-04",
                delivered: 100,
                on_time: 78,
                on_time_rate: 78,
              }),
            ],
          },
        })}
      />,
    );

    expect(
      screen.getByText(/2026-01 – 2026-04, 2 recorded months/),
    ).toBeInTheDocument();
  });

  it("renders the analytical basis/context text for both panels", () => {
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    expect(
      screen.getAllByText("Delivered shipments by planned-arrival month")
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Exceptions by shipment departure month").length,
    ).toBeGreaterThan(0);
  });

  it("renders an explicit gap for a null rate month (zero denominator)", () => {
    render(
      <AnalyticsSection
        overview={makeAnalyticsOverview({
          service_performance: {
            basis: "Delivered shipments by planned-arrival month",
            points: [
              makeServicePerformancePoint({
                month: "2026-03",
                delivered: 0,
                on_time: 0,
                on_time_rate: null,
              }),
            ],
          },
        })}
      />,
    );

    const table = screen.getAllByRole("table", {
      name: /On-time rate by month/i,
    })[0];
    // The month still renders; the value is "No observation",
    // never a fabricated 0%.
    expect(table).toHaveTextContent("2026-03");
    expect(table).toHaveTextContent("No observation");
    expect(table).not.toHaveTextContent("0%");
  });

  it("renders no panels when both default series are empty", () => {
    render(
      <AnalyticsSection
        overview={makeAnalyticsOverview({
          service_performance: {
            basis: "Delivered shipments by planned-arrival month",
            points: [],
          },
          exception_incidence: {
            basis: "Exceptions by shipment departure month",
            points: [],
          },
        })}
      />,
    );

    // Panel headings stay (the sections exist), but the charts
    // are withheld and the honest no-observations note renders.
    expect(
      screen.getAllByText("No recorded observations yet."),
    ).toHaveLength(2);
    expect(document.querySelector("svg[role='img']")).toBeNull();
  });

  it("keeps chart and fallback inside an accessible figure structure", () => {
    const { container } = render(
      <AnalyticsSection overview={makeAnalyticsOverview()} />,
    );
    // Every chart is an svg role=img labelled by its panel.
    const svgs = container.querySelectorAll("svg[role='img']");
    expect(svgs).toHaveLength(2);
    svgs.forEach((svg) => {
      expect(svg).toHaveAttribute("aria-labelledby");
    });
  });
});

describe("getAnalyticsOverview — client result states", () => {
  it("returns the data state with a structurally valid overview", async () => {
    server.use(
      http.get(analyticsPath, () => HttpResponse.json(overview())),
    );

    const result = await getAnalyticsOverview();

    expect(result.kind).toBe("data");
    if (result.kind === "data") {
      expect(result.data.service_performance.points).toHaveLength(4);
      expect(result.data.exception_incidence.points[0]?.incidence_rate).toBe(
        30.8,
      );
      expect(result.data.service_performance.basis).toBe(
        "Delivered shipments by planned-arrival month",
      );
    }
  });

  it("maps an all-empty overview to the deliberate empty state", async () => {
    // makeAnalyticsOverview ships populated categorical series
    // by default; the empty state requires *every* dataset to
    // be empty, so this payload clears them all.
    const payload = overview({
      service_performance: {
        basis: "Delivered shipments by planned-arrival month",
        points: [],
      },
      exception_incidence: {
        basis: "Exceptions by shipment departure month",
        points: [],
      },
    });
    (payload.transport as { entries: unknown[] }).entries = [];
    (payload.carriers as { entries: unknown[] }).entries = [];
    (payload.warehouses as { entries: unknown[] }).entries = [];
    (payload.severity as { entries: unknown[] }).entries = [];
    (payload.shipment_volume as { points: unknown[] }).points = [];
    server.use(http.get(analyticsPath, () => HttpResponse.json(payload)));

    const result = await getAnalyticsOverview();

    expect(result.kind).toBe("empty");
  });

  it("maps an HTTP failure to the unavailable state", async () => {
    server.use(
      http.get(analyticsPath, () =>
        HttpResponse.json({}, { status: 503 }),
      ),
    );

    const result = await getAnalyticsOverview();

    expect(result.kind).toBe("unavailable");
  });

  it("maps a malformed payload to the unexpected state", async () => {
    server.use(
      http.get(analyticsPath, () =>
        HttpResponse.json({ service_performance: 42 }),
      ),
    );

    const result = await getAnalyticsOverview();

    expect(result.kind).toBe("unexpected");
  });

  it("preserves null rates exactly as the backend delivered them", async () => {
    server.use(
      http.get(analyticsPath, () =>
        HttpResponse.json(
          overview({
            service_performance: {
              basis: "Delivered shipments by planned-arrival month",
              points: [
                makeServicePerformancePoint({
                  month: "2026-03",
                  delivered: 0,
                  on_time: 0,
                  on_time_rate: null,
                }),
              ],
            },
          }),
        ),
      ),
    );

    const result = await getAnalyticsOverview();

    expect(result.kind).toBe("data");
    if (result.kind === "data") {
      expect(
        result.data.service_performance.points[0]?.on_time_rate,
      ).toBeNull();
    }
  });
});

describe("LineChart primitive", () => {
  const base = {
    titleId: "t",
    describedById: "d",
    valueLabel: "On-time rate",
  };

  it("renders an accessible image with title and description wiring", () => {
    const { container } = render(
      <LineChart
        {...base}
        points={[
          { label: "2026-01", value: 70 },
          { label: "2026-02", value: 82.5 },
        ]}
      />,
    );
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("role", "img");
    expect(svg).toHaveAttribute(
      "aria-labelledby",
      expect.stringContaining("t"),
    );
  });

  it("keeps the data-table fallback for screen readers", () => {
    render(
      <LineChart {...base} points={[{ label: "2026-01", value: 70 }]} />,
    );
    expect(
      screen.getByRole("table", { name: /On-time rate by month/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "70%" })).toBeInTheDocument();
  });

  it("draws no dots for null observations but keeps their labels", () => {
    const { container } = render(
      <LineChart
        {...base}
        points={[
          { label: "2026-01", value: null },
          { label: "2026-02", value: 50 },
        ]}
      />,
    );
    const dots = container.querySelectorAll("circle");
    expect(dots).toHaveLength(1);
    expect(container.querySelectorAll("text").length).toBeGreaterThan(0);
  });

  it("breaks the path at null observations (no line implies an observation)", () => {
    const { container } = render(
      <LineChart
        {...base}
        points={[
          { label: "2026-01", value: 60 },
          { label: "2026-02", value: null },
          { label: "2026-03", value: 80 },
        ]}
      />,
    );
    const path = container.querySelector("path")?.getAttribute("d") ?? "";
    // Two disjoint subpaths, zero line segments — the null month
    // is crossed by nothing.
    expect(path.match(/M /g)).toHaveLength(2);
    expect(path.match(/L /g)).toBeNull();

    // Contrast: a fully-populated series draws one continuous
    // path (1 move, 2 line segments).
    const { container: full } = render(
      <LineChart
        {...base}
        points={[
          { label: "2026-01", value: 60 },
          { label: "2026-02", value: 70 },
          { label: "2026-03", value: 80 },
        ]}
      />,
    );
    const fullPath =
      full.querySelector("path")?.getAttribute("d") ?? "";
    expect(fullPath.match(/M /g)).toHaveLength(1);
    expect(fullPath.match(/L /g)).toHaveLength(2);
  });

  it("writes an explicit No observation entry in the fallback table", () => {
    render(
      <LineChart
        {...base}
        points={[
          { label: "2026-01", value: 60 },
          { label: "2026-02", value: null },
        ]}
      />,
    );
    const table = screen.getByRole("table", {
      name: /On-time rate by month/i,
    });
    expect(table).toHaveTextContent("2026-02");
    expect(table).toHaveTextContent("No observation");
  });

  it("renders nothing (and no empty svg) for zero points", () => {
    const { container } = render(<LineChart {...base} points={[]} />);
    expect(container.querySelector("svg")).toBeNull();
  });

  it("respects the grid step in axis labels", () => {
    const { container } = render(
      <LineChart
        {...base}
        points={[{ label: "2026-01", value: 66 }]}
        yMax={100}
        gridStep={25}
      />,
    );
    const labels = Array.from(container.querySelectorAll("text")).map(
      (t) => t.textContent,
    );
    expect(labels).toContain("0%");
    expect(labels).toContain("50%");
    expect(labels).toContain("100%");
  });

  it("uses a custom formatter when provided", () => {
    render(
      <LineChart
        {...base}
        points={[{ label: "2026-01", value: 42 }]}
        formatValue={(v) => `${v} pt`}
      />,
    );
    expect(screen.getByRole("cell", { name: "42 pt" })).toBeInTheDocument();
  });
});
