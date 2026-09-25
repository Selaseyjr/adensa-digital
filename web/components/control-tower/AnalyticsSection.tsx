import type {
  AnalyticsOverview,
  AnalyticsServicePerformancePoint,
  AnalyticsIncidencePoint,
} from "@/lib/types/api";
import {
  LineChart,
  type LineChartPoint,
} from "@/components/control-tower/LineChart";

/**
 * The Control Tower's analytical canvas (P8.7.2): two default
 * time-series panels rendered from `/v1/analytics/overview`
 * (ADR-014). A Server Component — the API client remains the
 * only fetch boundary and all four result states are handled
 * deliberately:
 *
 * - `data` → the two default panels (Service Performance,
 *   Exception Incidence);
 * - `empty` → an honest analytical empty state (a fresh or
 *   unpopulated database has no analytical population);
 * - `unavailable` / `unexpected` → the shared panel states.
 *
 * Honesty rules carried over from the P8.7 discovery and
 * ADR-014, enforced here in copy and content:
 *
 * - every panel renders the API's own `basis` wording verbatim
 *   ("Delivered shipments by planned-arrival month",
 *   "Exceptions by shipment departure month");
 * - `null` rates (zero denominators) are gaps in the line, not
 *   invented zero-percent points;
 * - population context (delivered/departing counts) is shown
 *   where useful so a rate is never presented without its
 *   denominator;
 * - no claim of workflow detection history — the incidence
 *   panel keys on shipment departure month by contract.
 *
 * P8.7.3 will add variable selection/focus on top of this
 * section; the panel structure and API consumption here are
 * its foundation.
 */

const SERVICE_PERFORMANCE_HEADING_ID =
  "service-performance-heading";
const INCIDENCE_HEADING_ID = "exception-incidence-heading";

/**
 * Coverage-honest month-span label, derived purely from the
 * returned points: a contiguous series renders as a range; a
 * series with absent months states how many months were
 * actually recorded, so the range never implies observations
 * the API did not return. (Presentation labelling only — no
 * analytical arithmetic.)
 */
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

function ServicePerformancePanel({
  series,
}: {
  series: AnalyticsServicePerformancePoint[];
}) {
  const withValues = series.filter((p) => p.on_time_rate !== null);
  const latest = withValues[withValues.length - 1];
  const chartPoints: LineChartPoint[] = series.map((p) => ({
    label: p.month,
    value: p.on_time_rate,
  }));

  return (
    <article
      className="analytics-panel"
      aria-labelledby={SERVICE_PERFORMANCE_HEADING_ID}
    >
      <header className="analytics-panel-header">
        <h3 id={SERVICE_PERFORMANCE_HEADING_ID}>Service performance</h3>
        <p className="analytics-basis">Delivered shipments by planned-arrival month</p>
      </header>

      {latest ? (
        <p className="analytics-context">
          <strong>{latest.on_time_rate}% on time</strong> across{" "}
          {latest.delivered} delivered shipments ({monthSpan(series)})
        </p>
      ) : null}

      {series.length === 0 ? (
        <p className="analytics-empty-note">
          No recorded observations yet.
        </p>
      ) : (
        <LineChart
          points={chartPoints}
          titleId={SERVICE_PERFORMANCE_HEADING_ID}
          describedById="service-performance-basis"
          valueLabel="On-time rate"
        />
      )}
      <span id="service-performance-basis" className="visually-hidden">
        Delivered shipments by planned-arrival month
      </span>
    </article>
  );
}

function IncidencePanel({
  series,
}: {
  series: AnalyticsIncidencePoint[];
}) {
  const chartPoints: LineChartPoint[] = series.map((p) => ({
    label: p.month,
    value: p.incidence_rate,
  }));
  const first = series[0];
  const last = series[series.length - 1];

  return (
    <article
      className="analytics-panel"
      aria-labelledby={INCIDENCE_HEADING_ID}
    >
      <header className="analytics-panel-header">
        <h3 id={INCIDENCE_HEADING_ID}>Exception incidence</h3>
        <p className="analytics-basis">Exceptions by shipment departure month</p>
      </header>

      {first && last ? (
        <p className="analytics-context">
          <strong>
            {last.exceptions} of {last.departing}
          </strong>{" "}
          departing shipments carried exceptions in {last.month} ({
            monthSpan(series)
          })
        </p>
      ) : null}

      {series.length === 0 ? (
        <p className="analytics-empty-note">
          No recorded observations yet.
        </p>
      ) : (
        <LineChart
          points={chartPoints}
          titleId={INCIDENCE_HEADING_ID}
          describedById="exception-incidence-basis"
          valueLabel="Incidence rate"
        />
      )}
      <span id="exception-incidence-basis" className="visually-hidden">
        Exceptions by shipment departure month
      </span>
    </article>
  );
}

export function AnalyticsSection({
  overview,
}: {
  overview: AnalyticsOverview;
}) {
  return (
    <section
      className="analytics-section"
      aria-labelledby="analytics-heading"
    >
      <h2 id="analytics-heading">Analytics</h2>
      <div className="analytics-grid">
        <ServicePerformancePanel
          series={overview.service_performance.points}
        />
        <IncidencePanel
          series={overview.exception_incidence.points}
        />
      </div>
    </section>
  );
}
