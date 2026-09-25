"use client";

/**
 * The Control Tower's analytical canvas (P8.7.2, selection in
 * P8.7.3), rendered from `/v1/analytics/overview` (ADR-014).
 *
 * Interaction model (approved audit): a single-focus,
 * slot-based selector — one radio group of six analytical
 * variables feeding two persistent panel slots:
 *
 * - left slot  = service-class metrics (Service performance,
 *   Shipment volume, Exception incidence);
 * - right slot = population/quality metrics (Transport,
 *   Carriers, Warehouses).
 *
 * Defaults are exactly the P8.7.2 pair: Service performance |
 * Exception incidence. Selecting a variable places it into its
 * slot; the selected panel renders at full emphasis and every
 * other analytical panel is visually muted (0.45 opacity on
 * figure content — headers stay readable so a muted panel can
 * still be read and chosen next). Unselected content is never
 * removed from the DOM and the slots never mount six charts at
 * once; the two non-shown variables of the selected slot are
 * simply muted. Severity is deliberately excluded: its current
 * snapshot duplicates the Queue Composition band directly
 * above this section.
 *
 * The selector is a native `<fieldset>` of radio inputs —
 * keyboard arrow navigation and assistive technology come
 * free; the only client state is one `useState` for the
 * selected variable. Selection is deliberately local (no URL
 * persistence in P8.7.3).
 *
 * Honesty rules carried over from P8.7.2 and ADR-014, enforced
 * here in copy and content:
 *
 * - every panel renders the API's own `basis` wording verbatim;
 * - `null` rates (zero denominators) are gaps/"No observation",
 *   never invented zero-percent values;
 * - population context (delivered/departing counts) is shown
 *   where useful so a rate is never presented without its
 *   denominator;
 * - no claim of workflow detection history — the incidence
 *   panel keys on shipment departure month by contract;
 * - no business arithmetic anywhere: charts map the API's own
 *   values; this file computes only presentation geometry
 *   support (month-span labelling).
 */

import { useState } from "react";
import type { ReactNode } from "react";
import type {
  AnalyticsOverview,
} from "@/lib/types/api";
import {
  LineChart,
  type LineChartPoint,
} from "@/components/control-tower/LineChart";
import {
  BarChart,
  type BarChartEntry,
} from "@/components/control-tower/BarChart";

/** Coverage-honest month-span label, derived purely from the
 * returned points: a contiguous series renders as a range; a
 * series with absent months states how many months were
 * actually recorded, so the range never implies observations
 * the API did not return. (Presentation labelling only — no
 * analytical arithmetic.) */
function monthSpan(points: { month: string }[]): string {
  if (points.length === 0) return "";
  const first = points[0].month;
  const last = points[points.length - 1].month;
  if (points.length === 1 || first === last) return first;
  const [fy, fm] = first.split("-").map(Number);
  const [ly, lm] = last.split("-").map(Number);
  const expectedMonths = (ly - fy) * 12 + (lm - fm) + 1;
  return expectedMonths === points.length
    ? `${first} – ${last}`
    : `${first} – ${last}, ${points.length} recorded months`;
}

// --------------------------------------------------
// Variable registry — the single source of what each
// selectable variable is, which slot it occupies, and which
// series/charts it renders. Deterministic slot assignment:
// time-series/service-class variables own the left slot,
// categorical population/quality variables the right.
// --------------------------------------------------

const LEFT_SLOT = "service";
const RIGHT_SLOT = "population";

/** The persistent slot defaults. Initial pair is exactly the
 * P8.7.2 duo (Service performance | Exception incidence). A
 * slot shows its default whenever the selected variable does
 * not occupy it — with one displacement rule: Exception
 * incidence is a left-slot variable that initially renders in
 * the right panel, so selecting it displaces the right slot to
 * its own group default (Transport) rather than duplicating EI
 * into both panels. */
const DEFAULT_LEFT: VariableId = "service_performance";
const INITIAL_RIGHT: VariableId = "exception_incidence";
const DISPLACED_RIGHT: VariableId = "transport";

type VariableId =
  | "service_performance"
  | "shipment_volume"
  | "exception_incidence"
  | "transport"
  | "carriers"
  | "warehouses";

interface VariableDescriptor {
  id: VariableId;
  label: string;
  slot: typeof LEFT_SLOT | typeof RIGHT_SLOT;
}

const VARIABLES: VariableDescriptor[] = [
  { id: "service_performance", label: "Service performance", slot: LEFT_SLOT },
  { id: "shipment_volume", label: "Shipment volume", slot: LEFT_SLOT },
  { id: "exception_incidence", label: "Exception incidence", slot: LEFT_SLOT },
  { id: "transport", label: "Transport", slot: RIGHT_SLOT },
  { id: "carriers", label: "Carriers", slot: RIGHT_SLOT },
  { id: "warehouses", label: "Warehouses", slot: RIGHT_SLOT },
];

const HEADING_IDS: Record<VariableId, string> = {
  service_performance: "service-performance-heading",
  shipment_volume: "shipment-volume-heading",
  exception_incidence: "exception-incidence-heading",
  transport: "transport-heading",
  carriers: "carriers-heading",
  warehouses: "warehouses-heading",
};

/** Context + chart rendering per variable, from the overview
 * payload only. Each returns the panel's context sentence (or
 * null) and the chart element. No analytical arithmetic. */
function renderVariable(
  id: VariableId,
  overview: AnalyticsOverview,
): { context: ReactNode; chart: ReactNode } {
  switch (id) {
    case "service_performance": {
      const series = overview.service_performance.points;
      const withValues = series.filter((p) => p.on_time_rate !== null);
      const latest = withValues[withValues.length - 1];
      const chartPoints: LineChartPoint[] = series.map((p) => ({
        label: p.month,
        value: p.on_time_rate,
      }));
      return {
        context: latest ? (
          <p className="analytics-context">
            <strong>{latest.on_time_rate}% on time</strong> across{" "}
            {latest.delivered} delivered shipments ({monthSpan(series)})
          </p>
        ) : null,
        chart:
          series.length === 0 ? (
            <p className="analytics-empty-note">
              No recorded observations yet.
            </p>
          ) : (
            <LineChart
              points={chartPoints}
              titleId={HEADING_IDS.service_performance}
              describedById="service-performance-basis"
              valueLabel="On-time rate"
            />
          ),
      };
    }
    case "shipment_volume": {
      const series = overview.shipment_volume.points;
      const latest = series[series.length - 1];
      const chartPoints: LineChartPoint[] = series.map((p) => ({
        label: p.month,
        value: p.shipments,
      }));
      // Count series: absolute scale tops at the largest returned
      // value (presentation geometry), integer formatting, no unit.
      const valueMax = Math.max(...series.map((p) => p.shipments), 0);
      return {
        context: latest ? (
          <p className="analytics-context">
            <strong>{latest.shipments} shipments</strong> departed in{" "}
            {latest.month} ({monthSpan(series)})
          </p>
        ) : null,
        chart:
          series.length === 0 ? (
            <p className="analytics-empty-note">
              No recorded observations yet.
            </p>
          ) : (
            <LineChart
              points={chartPoints}
              titleId={HEADING_IDS.shipment_volume}
              describedById="shipment-volume-basis"
              valueLabel="Shipments"
              unit=""
              yMax={valueMax > 0 ? valueMax : 1}
              gridStep={
                valueMax > 0
                  ? Math.max(1, Math.ceil(valueMax / 4 / 25) * 25)
                  : 1
              }
              formatValue={(value) => value.toLocaleString("en-US")}
            />
          ),
      };
    }
    case "exception_incidence": {
      const series = overview.exception_incidence.points;
      const chartPoints: LineChartPoint[] = series.map((p) => ({
        label: p.month,
        value: p.incidence_rate,
      }));
      const first = series[0];
      const last = series[series.length - 1];
      return {
        context:
          first && last ? (
            <p className="analytics-context">
              <strong>
                {last.exceptions} of {last.departing}
              </strong>{" "}
              departing shipments carried exceptions in {last.month} (
              {monthSpan(series)})
            </p>
          ) : null,
        chart:
          series.length === 0 ? (
            <p className="analytics-empty-note">
              No recorded observations yet.
            </p>
          ) : (
            <LineChart
              points={chartPoints}
              titleId={HEADING_IDS.exception_incidence}
              describedById="exception-incidence-basis"
              valueLabel="Incidence rate"
            />
          ),
      };
    }
    case "transport": {
      const entries = overview.transport.entries;
      const barEntries: BarChartEntry[] = entries.map((e) => ({
        label: e.transport_mode,
        value: e.on_time_rate,
      }));
      return {
        context: null,
        chart:
          entries.length === 0 ? (
            <p className="analytics-empty-note">
              No recorded observations yet.
            </p>
          ) : (
            <BarChart
              entries={barEntries}
              titleId={HEADING_IDS.transport}
              describedById="transport-basis"
              valueLabel="On-time rate"
            />
          ),
      };
    }
    case "carriers": {
      const entries = overview.carriers.entries;
      const barEntries: BarChartEntry[] = entries.map((e) => ({
        label: e.carrier_name,
        value: e.on_time_rate,
      }));
      return {
        context: null,
        chart:
          entries.length === 0 ? (
            <p className="analytics-empty-note">
              No recorded observations yet.
            </p>
          ) : (
            <BarChart
              entries={barEntries}
              titleId={HEADING_IDS.carriers}
              describedById="carriers-basis"
              valueLabel="On-time rate"
            />
          ),
      };
    }
    case "warehouses": {
      const entries = overview.warehouses.entries;
      const barEntries: BarChartEntry[] = entries.map((e) => ({
        label: e.warehouse_name,
        value: e.exceptions,
      }));
      return {
        context: null,
        chart:
          entries.length === 0 ? (
            <p className="analytics-empty-note">
              No recorded observations yet.
            </p>
          ) : (
            <BarChart
              entries={barEntries}
              titleId={HEADING_IDS.warehouses}
              describedById="warehouses-basis"
              valueLabel="Exceptions"
              unit=""
              formatValue={(value) => value.toLocaleString("en-US")}
            />
          ),
      };
    }
  }
}

function VariablePanel({
  variable,
  overview,
  muted,
}: {
  variable: VariableDescriptor;
  overview: AnalyticsOverview;
  muted: boolean;
}) {
  const { context, chart } = renderVariable(variable.id, overview);
  return (
    <article
      className={`analytics-panel${muted ? " is-muted" : " is-focused"}`}
      aria-labelledby={HEADING_IDS[variable.id]}
    >
      <header className="analytics-panel-header">
        <h3 id={HEADING_IDS[variable.id]}>{variable.label}</h3>
        <p className="analytics-basis">{basisFor(variable.id, overview)}</p>
      </header>
      {context}
      {chart}
      <span id={`${variable.id.replace("_", "-")}-basis`} className="visually-hidden">
        {basisFor(variable.id, overview)}
      </span>
    </article>
  );
}

/** The API's own analytical-basis wording for a variable —
 * rendered verbatim; the UI never paraphrases the contract. */
function basisFor(id: VariableId, overview: AnalyticsOverview): string {
  switch (id) {
    case "service_performance":
      return overview.service_performance.basis;
    case "shipment_volume":
      return overview.shipment_volume.basis;
    case "exception_incidence":
      return overview.exception_incidence.basis;
    case "transport":
      return overview.transport.basis;
    case "carriers":
      return overview.carriers.basis;
    case "warehouses":
      return overview.warehouses.basis;
  }
}

export function AnalyticsSection({
  overview,
}: {
  overview: AnalyticsOverview;
}) {
  const [selected, setSelected] = useState<VariableId>(DEFAULT_LEFT);

  // Slot assignment (deterministic): the selected variable takes
  // its own slot; the other slot shows its default, except when
  // the selection *is* that default (see DISPLACED_RIGHT above).
  const selectedVariable = VARIABLES.find((v) => v.id === selected)!;
  const varById = (id: VariableId) =>
    VARIABLES.find((v) => v.id === id)!;
  const leftVariable =
    selectedVariable.slot === LEFT_SLOT
      ? selectedVariable
      : varById(DEFAULT_LEFT);
  const rightVariable =
    selectedVariable.slot === RIGHT_SLOT
      ? selectedVariable
      : selected === INITIAL_RIGHT
        ? varById(DISPLACED_RIGHT)
        : varById(INITIAL_RIGHT);

  const panelIsMuted = (v: VariableDescriptor) => v.id !== selected;

  return (
    <section
      className="analytics-section"
      aria-labelledby="analytics-heading"
    >
      <h2 id="analytics-heading">Analytics</h2>

      {/* Single-focus variable selector: native radios inside a
          fieldset — keyboard arrow navigation and AT semantics
          come from the platform, not custom ARIA authoring. */}
      <fieldset className="analytics-selector">
        <legend>Select the analytical focus</legend>
        {VARIABLES.map((variable) => (
          <label key={variable.id} className="analytics-chip">
            <input
              type="radio"
              name="analytics-variable"
              value={variable.id}
              checked={selected === variable.id}
              onChange={() => setSelected(variable.id)}
            />
            <span>{variable.label}</span>
          </label>
        ))}
      </fieldset>

      <div className="analytics-grid">
        <VariablePanel
          variable={leftVariable}
          overview={overview}
          muted={panelIsMuted(leftVariable)}
        />
        <VariablePanel
          variable={rightVariable}
          overview={overview}
          muted={panelIsMuted(rightVariable)}
        />
      </div>
    </section>
  );
}
