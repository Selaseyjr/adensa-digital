/**
 * Control-tower composition bands: current-state proportions
 * the summary contract already documents. Two bands:
 *
 * - the bounded work-queue split (Actionable vs Monitoring),
 *   which the backend defines as a partition of the visible
 *   inbox (actionable + monitoring = the visible row count);
 * - the critical share of the open population (critical is a
 *   documented subset of open).
 *
 * Presentation-level arithmetic is used ONLY for proportions
 * (segment widths); every count is rendered verbatim in
 * visible and accessibility text. No historical data, no
 * trends, no new business semantics — the KPI grid above
 * remains the numeric source of truth; these bands are
 * subordinate proportions of exactly those numbers.
 *
 * Zero-safe: a zero denominator renders an explicit empty
 * band with the true counts in text — never a NaN width, an
 * Infinity, or a misleading filled bar.
 */

import type { ControlTowerSummary } from "@/lib/types/api";

function percentOf(part: number, total: number): number | null {
  if (total <= 0 || part < 0 || part > total) {
    return null;
  }
  return (part / total) * 100;
}

function Band({
  label,
  aLabel,
  aCount,
  aPercent,
  bLabel,
  bCount,
  bPercent,
  classNameA,
  classNameB,
}: {
  label: string;
  aLabel: string;
  aCount: number;
  aPercent: number | null;
  bLabel: string;
  bCount: number;
  bPercent: number | null;
  classNameA: string;
  classNameB: string;
}) {
  const aria = `${label}: ${aLabel} ${aCount}, ${bLabel} ${bCount}.`;
  const hasSegments = aPercent !== null && bPercent !== null;

  return (
    <div className="band-row">
      <div className="band-header">
        <span className="band-label">{label}</span>
        <span className="band-counts">
          {aLabel} {aCount} · {bLabel} {bCount}
        </span>
      </div>
      <div
        className="band-track"
        role="img"
        aria-label={aria}
      >
        {hasSegments ? (
          <>
            <span
              className={`band-segment ${classNameA}`}
              style={{ width: `${aPercent}%` }}
            />
            <span
              className={`band-segment ${classNameB}`}
              style={{ width: `${bPercent}%` }}
            />
          </>
        ) : (
          <span className="band-segment band-segment-empty" />
        )}
      </div>
    </div>
  );
}

export function QueueCompositionBand({
  summary,
}: {
  summary: ControlTowerSummary;
}) {
  const queueTotal =
    summary.actionable_exceptions + summary.monitoring_exceptions;

  return (
    <div className="composition-band">
      <Band
        label="Bounded work queue"
        aLabel="Actionable"
        aCount={summary.actionable_exceptions}
        aPercent={percentOf(summary.actionable_exceptions, queueTotal)}
        bLabel="Monitoring"
        bCount={summary.monitoring_exceptions}
        bPercent={percentOf(summary.monitoring_exceptions, queueTotal)}
        classNameA="band-segment-actionable"
        classNameB="band-segment-monitoring"
      />
      <Band
        label="Open population"
        aLabel="Critical"
        aCount={summary.critical_exceptions}
        aPercent={percentOf(summary.critical_exceptions, summary.open_exceptions)}
        bLabel="Other open"
        bCount={Math.max(
          summary.open_exceptions - summary.critical_exceptions,
          0,
        )}
        bPercent={percentOf(
          summary.open_exceptions - summary.critical_exceptions,
          summary.open_exceptions,
        )}
        classNameA="band-segment-critical"
        classNameB="band-segment-monitoring"
      />
    </div>
  );
}
