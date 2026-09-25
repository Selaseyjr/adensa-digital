/**
 * Analytical-layer tests (P8.7.2 + P8.7.3): the LineChart and
 * BarChart SVG primitives, the AnalyticsSection panels fed by
 * the real `/v1/analytics/overview` contract (P8.7.1), the
 * client function's four result states, the single-focus
 * variable selection, and the strict per-series categorical
 * validation.
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
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { AnalyticsSection } from "@/components/control-tower/AnalyticsSection";
import { LineChart } from "@/components/control-tower/LineChart";
import { BarChart } from "@/components/control-tower/BarChart";
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

describe("BarChart primitive (P8.7.3)", () => {
  const barBase = {
    titleId: "transport-heading",
    describedById: "transport-basis",
    valueLabel: "On-time rate",
  };

  it("renders category labels and API values verbatim", () => {
    render(
      <BarChart
        {...barBase}
        entries={[
          { label: "Road", value: 74.3 },
          { label: "Sea", value: 59.3 },
        ]}
      />,
    );
    const table = screen.getByRole("table", {
      name: /On-time rate by category/i,
    });
    expect(table).toHaveTextContent("Road");
    expect(table).toHaveTextContent("74.3%");
    expect(table).toHaveTextContent("Sea");
    expect(table).toHaveTextContent("59.3%");
  });

  it("keeps the role=img / labelled / described accessibility contract", () => {
    const { container } = render(
      <BarChart {...barBase} entries={[{ label: "Road", value: 74.3 }]} />,
    );
    const svg = container.querySelector("svg[role='img']");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute(
      "aria-labelledby",
      "transport-heading transport-basis",
    );
  });

  it("renders No observation for a null rate and draws no bar", () => {
    const { container } = render(
      <BarChart {...barBase} entries={[{ label: "Rail", value: null }]} />,
    );
    // The category still renders; the value is "No observation"
    // (in both the SVG value label and the fallback table), never
    // a fabricated 0%, and no bar length is invented.
    expect(screen.getAllByText("No observation")).toHaveLength(2);
    expect(container.querySelector(".bar-fill")).toBeNull();
    expect(container.querySelector("svg")?.textContent).not.toContain("0%");
  });

  it("renders count series with the custom formatter (no unit)", () => {
    render(
      <BarChart
        {...barBase}
        valueLabel="Exceptions"
        unit=""
        formatValue={(v) => v.toLocaleString("en-US")}
        entries={[
          { label: "Rotterdam Hub", value: 120 },
          { label: "Munich Cross-dock", value: 0 },
        ]}
      />,
    );
    const table = screen.getByRole("table", {
      name: /Exceptions by category/i,
    });
    expect(table).toHaveTextContent("120");
    expect(table).toHaveTextContent("Munich Cross-dock");
  });

  it("renders nothing (and no empty svg) for zero entries", () => {
    const { container } = render(<BarChart {...barBase} entries={[]} />);
    expect(container.querySelector("svg")).toBeNull();
  });
});

describe("AnalyticsSection — variable selection (P8.7.3)", () => {
  it("renders the default Service performance | Exception incidence state", () => {
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    expect(
      screen.getByRole("heading", { name: "Service performance" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Exception incidence" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Transport" })).toBeNull();

    // Exactly two charts render — the slots never mount six.
    expect(document.querySelectorAll("svg[role='img']")).toHaveLength(2);
    // The default focused panel is Service performance; the
    // other analytical panel is muted, not removed.
    const focused = document.querySelectorAll(".analytics-panel.is-focused");
    expect(focused).toHaveLength(1);
    expect(focused[0]).toHaveTextContent("Service performance");
    expect(document.querySelector(".analytics-panel.is-muted")).not.toBeNull();
  });

  it("exposes the selector as a labelled radio group of six variables", () => {
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    const group = screen.getByRole("group", {
      name: "Select the analytical focus",
    });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(6);
    expect(radios.map((r) => r.closest("label")?.textContent)).toEqual([
      "Service performance",
      "Shipment volume",
      "Exception incidence",
      "Transport",
      "Carriers",
      "Warehouses",
    ]);
    expect(radios[0]).toBeChecked();
  });

  it("places a selected categorical variable into the right slot and mutes the left panel", async () => {
    const user = userEvent.setup();
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    await user.click(screen.getByRole("radio", { name: "Transport" }));

    // Slot assignment: Transport takes the right slot; the left
    // slot falls back to its Service performance default.
    expect(
      screen.getByRole("heading", { name: "Transport" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Service performance" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Exception incidence" }),
    ).toBeNull();

    // Focus/dim: exactly one focused panel (Transport); the
    // Service performance panel is muted, still in the DOM.
    const focused = document.querySelectorAll(".analytics-panel.is-focused");
    expect(focused).toHaveLength(1);
    expect(focused[0]).toHaveTextContent("Transport");
    const muted = document.querySelectorAll(".analytics-panel.is-muted");
    expect(muted).toHaveLength(1);
    expect(muted[0]).toHaveTextContent("Service performance");
  });

  it("keeps the right-slot default (Exception incidence) when a left variable is selected", async () => {
    const user = userEvent.setup();
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    await user.click(screen.getByRole("radio", { name: "Shipment volume" }));

    expect(
      screen.getByRole("heading", { name: "Shipment volume" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Exception incidence" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Transport" })).toBeNull();
  });

  it("displaces the right slot to Transport when Exception incidence itself is selected", async () => {
    // Exception incidence initially renders in the right panel
    // but belongs to the left slot's service-class group; selecting
    // it must move it to the left slot and displace the right
    // slot to that group's default (Transport) — never duplicate
    // the same variable into both panels.
    const user = userEvent.setup();
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    await user.click(screen.getByRole("radio", { name: "Exception incidence" }));

    const panels = document.querySelectorAll(".analytics-panel");
    expect(panels).toHaveLength(2);
    expect(panels[0]).toHaveTextContent("Exception incidence");
    expect(panels[1]).toHaveTextContent("Transport");
    expect(panels[0]).toHaveClass("is-focused");
    expect(panels[1]).toHaveClass("is-muted");
    // Exactly one Exception incidence heading exists.
    expect(
      screen.getAllByRole("heading", { name: "Exception incidence" }),
    ).toHaveLength(1);
  });

  it("renders Transport from API values verbatim with basis wording", async () => {
    const user = userEvent.setup();
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    await user.click(screen.getByRole("radio", { name: "Transport" }));

    const table = screen.getByRole("table", {
      name: /On-time rate by category/i,
    });
    expect(table).toHaveTextContent("Road");
    expect(table).toHaveTextContent("74.3%");
    // Basis wording verbatim from the API contract.
    expect(
      screen.getAllByText("Delivered shipments by transport mode").length,
    ).toBeGreaterThan(0);
  });

  it("renders Warehouses with count formatting and all entries", async () => {
    const user = userEvent.setup();
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    await user.click(screen.getByRole("radio", { name: "Warehouses" }));

    const table = screen.getByRole("table", {
      name: /Exceptions by category/i,
    });
    expect(table).toHaveTextContent("Rotterdam Hub");
    expect(table).toHaveTextContent("120");
    expect(table).toHaveTextContent("Munich Cross-dock");
  });

  it("renders the categorical null rate as an explicit gap (zero denominator)", async () => {
    const user = userEvent.setup();
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    await user.click(screen.getByRole("radio", { name: "Transport" }));

    const table = screen.getByRole("table", {
      name: /On-time rate by category/i,
    });
    expect(table).toHaveTextContent("Rail");
    expect(table).toHaveTextContent("No observation");
  });

  it("supports keyboard arrow navigation across the radio group", async () => {
    const user = userEvent.setup();
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    await user.click(screen.getByRole("radio", { name: "Service performance" }));
    await user.keyboard("{ArrowDown}");

    // Native radio semantics: ArrowDown moves to the next radio
    // in the group and selects it.
    expect(
      screen.getByRole("radio", { name: "Shipment volume" }),
    ).toBeChecked();
    expect(
      screen.getByRole("heading", { name: "Shipment volume" }),
    ).toBeInTheDocument();
  });

  it("renders Shipment volume from API values without recomputation", async () => {
    const user = userEvent.setup();
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    await user.click(screen.getByRole("radio", { name: "Shipment volume" }));

    const table = screen.getByRole("table", { name: /Shipments by month/i });
    expect(table).toHaveTextContent("542");
    expect(table).toHaveTextContent("488");
    expect(
      screen.getAllByText("All shipments by planned-departure month").length,
    ).toBeGreaterThan(0);
  });

  it("keeps unselected analytical content in the DOM (muted, not removed)", async () => {
    const user = userEvent.setup();
    render(<AnalyticsSection overview={makeAnalyticsOverview()} />);

    await user.click(screen.getByRole("radio", { name: "Carriers" }));

    const panels = document.querySelectorAll(".analytics-panel");
    expect(panels).toHaveLength(2);
    expect(
      screen.getByRole("heading", { name: "Carriers" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Service performance" }),
    ).toBeInTheDocument();
    expect(document.querySelector(".analytics-panel.is-muted")).not.toBeNull();
  });
});

describe("getAnalyticsOverview — strict categorical validation (P8.7.3)", () => {
  // The P8.7.3 validator validates each categorical series
  // against its exact backend field spec. These cases pin the
  // fail-closed behaviour introduced alongside the per-series
  // typing.
  const mutatePayload = (
    mutate: (p: Record<string, unknown>) => void,
  ): Record<string, unknown> => {
    const p = makeAnalyticsOverview() as unknown as Record<string, unknown>;
    mutate(p);
    return p;
  };

  it("accepts a valid nullable rate entry", async () => {
    server.use(
      http.get(analyticsPath, () =>
        HttpResponse.json(mutatePayload(() => {})),
      ),
    );
    const r = await getAnalyticsOverview();
    expect(r.kind).toBe("data");
    if (r.kind === "data") {
      const rail = r.data.transport.entries.find(
        (e) => e.transport_mode === "Rail",
      );
      expect(rail?.on_time_rate).toBeNull();
    }
  });

  it("rejects a missing field", async () => {
    server.use(
      http.get(analyticsPath, () =>
        HttpResponse.json(mutatePayload((p) => {
          const t = p.transport as { entries: Record<string, unknown>[] };
          delete t.entries[0].delivered;
        })),
      ),
    );
    expect((await getAnalyticsOverview()).kind).toBe("unexpected");
  });

  it("rejects an unexpected extra field", async () => {
    server.use(
      http.get(analyticsPath, () =>
        HttpResponse.json(mutatePayload((p) => {
          const s = p.severity as { entries: Record<string, unknown>[] };
          s.entries[0].sneaky = 1;
        })),
      ),
    );
    expect((await getAnalyticsOverview()).kind).toBe("unexpected");
  });

  it("rejects an incorrect field type", async () => {
    server.use(
      http.get(analyticsPath, () =>
        HttpResponse.json(mutatePayload((p) => {
          const w = p.warehouses as { entries: Record<string, unknown>[] };
          w.entries[0].exceptions = "120";
        })),
      ),
    );
    expect((await getAnalyticsOverview()).kind).toBe("unexpected");
  });

  it("rejects a non-numeric non-null rate", async () => {
    server.use(
      http.get(analyticsPath, () =>
        HttpResponse.json(mutatePayload((p) => {
          const t = p.transport as { entries: Record<string, unknown>[] };
          t.entries[0].on_time_rate = "74.3";
        })),
      ),
    );
    expect((await getAnalyticsOverview()).kind).toBe("unexpected");
  });
});
