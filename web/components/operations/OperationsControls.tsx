"use client";

/**
 * Operations: the two operational controls the legacy
 * Streamlit sidebar exposes, migrated to the Next.js client
 * (P9.1) — simulated shipment arrival and the operational
 * pipeline refresh, against the existing /v1 endpoints.
 *
 * Architecture: the only client component on the page. The
 * server actions it posts to run on the Node server, so the
 * API origin and the machine credential still never reach the
 * browser (same discipline as the workflow mutations). The
 * backend remains the authority — its HTTP 409 guard ("no
 * operational data to derive a simulated arrival from") is
 * rendered verbatim, never re-interpreted.
 *
 * Pending discipline: each control is a distinct form whose
 * button is disabled while its mutation is in flight, so an
 * accidental double submission is impossible. The two
 * controls also disable each other: an arrival simulation
 * followed by a refresh is the natural sequence, and running
 * them concurrently would make the refresh's delta summary
 * ambiguous. No optimistic UI — the results render only what
 * the backend returned.
 */

import { useActionState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  refreshPipelineAction,
  simulateArrivalAction,
} from "@/lib/actions/operations";
import type {
  OperationalRefreshSummary,
  SimulatedArrivalSummary,
} from "@/lib/types/api";
import type { OperationsActionResult } from "@/lib/actions/operations";

/**
 * Result-banner tone per action state — the same mapping the
 * workflow mutations use: recoverable operational states read
 * as warnings, hard failures as errors.
 */
const RESULT_TONE: Record<string, string> = {
  guard: "var(--warning)",
  validation: "var(--warning)",
};

/**
 * P8.4 focus discipline, shared: the banner is a focus target
 * (`tabIndex={-1}`) that receives focus when a result arrives,
 * so keyboard and screen-reader users land on the outcome.
 * The effect keys on the result identity, so a later run of
 * the same control moves focus to its fresh result.
 */
function useResultFocus<T>(
  result: OperationsActionResult<T> | null,
): (el: HTMLElement | null) => void {
  const elementRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (result !== null) elementRef.current?.focus();
  }, [result]);

  return (el: HTMLElement | null) => {
    elementRef.current = el;
  };
}

/**
 * The Streamlit affordance, preserved: when exactly one new
 * exception is detected, that investigation becomes the
 * prominent next step rather than one row among many.
 */
function isSingleNewException(summary: OperationalRefreshSummary): boolean {
  return summary.new_exceptions === 1 && summary.new_exception_ids.length === 1;
}

/** One refresh-summary metric, mirroring the KPI presentation. */
function RefreshFigure({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="op-figure">
      <span className="op-figure-label">{label}</span>
      <span className="op-figure-value">{value}</span>
    </div>
  );
}

function RefreshResult({
  result,
}: {
  result: OperationsActionResult<OperationalRefreshSummary>;
}) {
  const bannerRef = useResultFocus(result);

  if (result.status === "success") {
    const data = result.data;
    const single = isSingleNewException(data);
    const singleId = single ? data.new_exception_ids[0] : null;

    return (
      <div className="op-result" role="status" tabIndex={-1} ref={bannerRef}>
        <p className="op-result-message">{result.message}</p>
        {single && singleId !== null ? (
          <p className="op-single-exception">
            <Link
              className="op-single-link"
              href={`/exceptions/${encodeURIComponent(singleId)}`}
            >
              Investigate {singleId}
            </Link>
          </p>
        ) : null}
        {!single && data.new_exception_ids.length > 0 ? (
          <ul className="op-exception-links">
            {data.new_exception_ids.map((id) => (
              <li key={id}>
                <Link
                  className="op-exception-link"
                  href={`/exceptions/${encodeURIComponent(id)}`}
                >
                  Investigate {id}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
        <div className="op-figures">
          <RefreshFigure label="New exceptions" value={data.new_exceptions} />
          <RefreshFigure label="New recovery options" value={data.new_options} />
          <RefreshFigure label="New workflow actions" value={data.new_actions} />
          <RefreshFigure
            label="Actions evaluated"
            value={data.actions_evaluated}
          />
          <RefreshFigure
            label="Without recommendation"
            value={data.actions_without_recommendation}
          />
          <RefreshFigure label="Actions skipped" value={data.actions_skipped} />
        </div>
      </div>
    );
  }

  const tone = RESULT_TONE[result.status] ?? "var(--critical)";

  return (
    <p
      ref={bannerRef}
      className="op-result action-result-banner"
      role="status"
      tabIndex={-1}
      style={{ color: tone, borderColor: tone }}
    >
      {result.message}
    </p>
  );
}

function SimulateResult({
  result,
}: {
  result: OperationsActionResult<SimulatedArrivalSummary>;
}) {
  const bannerRef = useResultFocus(result);

  if (result.status === "success") {
    const data = result.data;

    return (
      <div className="op-result" role="status" tabIndex={-1} ref={bannerRef}>
        <p className="op-result-message">{result.message}</p>
        <dl className="op-simulation">
          <div className="op-sim-row">
            <dt>Shipment</dt>
            <dd>{data.shipment_id}</dd>
          </div>
          <div className="op-sim-row">
            <dt>Order</dt>
            <dd>{data.order_id}</dd>
          </div>
          <div className="op-sim-row">
            <dt>Carrier</dt>
            <dd>{data.carrier_id}</dd>
          </div>
          <div className="op-sim-row">
            <dt>Events recorded</dt>
            <dd>{data.event_count}</dd>
          </div>
          <div className="op-sim-row">
            <dt>Required delivery</dt>
            <dd>{data.required_delivery}</dd>
          </div>
          <div className="op-sim-row">
            <dt>Estimated arrival</dt>
            <dd>{data.estimated_arrival}</dd>
          </div>
          <div className="op-sim-row">
            <dt>Delay</dt>
            <dd>{data.delay_days} day(s)</dd>
          </div>
        </dl>
        <p className="op-sim-note">
          The arrival is recorded only — run Refresh Operations Pipeline to
          detect any exception it creates.
        </p>
      </div>
    );
  }

  // The known guard: the backend has no operational data to
  // derive a scenario from. Rendered as an honest operational
  // state (warning tone), not an error. Other recoverable
  // states get the same treatment; hard failures read as
  // errors.
  const tone = RESULT_TONE[result.status] ?? "var(--critical)";

  return (
    <p
      ref={bannerRef}
      className="op-result action-result-banner"
      role="status"
      tabIndex={-1}
      style={{ color: tone, borderColor: tone }}
    >
      {result.message}
    </p>
  );
}

export function OperationsControls() {
  const [refreshResult, refreshFormAction, refreshPending] = useActionState(
    () => refreshPipelineAction(),
    null,
  );
  const [simulateResult, simulateFormAction, simulatePending] = useActionState(
    () => simulateArrivalAction(),
    null,
  );

  const busy = refreshPending || simulatePending;

  return (
    <div className="op-controls">
      {/* ---------------- simulate arrival ---------------- */}
      <section
        className="section op-panel"
        aria-labelledby="simulate-heading"
      >
        <h2 id="simulate-heading" className="section-title">
          Simulate Shipment Arrival
        </h2>
        <p className="section-caption">
          Record one controlled simulated shipment arrival, derived from
          existing operational data. The simulation never detects exceptions
          itself — refresh the pipeline afterwards.
        </p>
        <form action={simulateFormAction} aria-busy={simulatePending}>
          <button
            type="submit"
            className="action-button"
            disabled={busy}
          >
            {simulatePending ? "Recording arrival…" : "Simulate Shipment Arrival"}
          </button>
        </form>
        {simulateResult !== null ? <SimulateResult result={simulateResult} /> : null}
      </section>

      {/* ---------------- refresh pipeline ---------------- */}
      <section className="section op-panel" aria-labelledby="refresh-heading">
        <h2 id="refresh-heading" className="section-title">
          Refresh Operations Pipeline
        </h2>
        <p className="section-caption">
          Re-run the operational pipeline — detect → options → actions — and
          report exactly what the run created. Safe to repeat: each stage is
          idempotent, so a refresh only ever reports new work.
        </p>
        <form action={refreshFormAction} aria-busy={refreshPending}>
          <button
            type="submit"
            className="action-button"
            disabled={busy}
          >
            {refreshPending
              ? "Running detect → options → actions…"
              : "Refresh Operations Pipeline"}
          </button>
        </form>
        {refreshResult !== null ? <RefreshResult result={refreshResult} /> : null}
      </section>
    </div>
  );
}
