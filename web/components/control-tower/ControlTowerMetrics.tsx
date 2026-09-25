/**
 * Control-tower KPI grid (P8.8): every card is a semantic
 * `<Link>` into the truthful Exception Inbox view for that
 * population — closing the Understand → Act gap identified
 * by the P8.8 audit.
 *
 * Every number is rendered exactly as the API reports it —
 * the client computes no metrics. The two population
 * semantics are preserved verbatim from the backend
 * contract, and so is the count honesty on the link targets:
 *
 * - Open / Critical / Pending decisions / Awaiting execution /
 *   Follow-up required describe the FULL operational
 *   population, while the inbox is a bounded (≤100 rows)
 *   view of that population — the target views state this;
 * - Actionable / Monitoring partition the BOUNDED inbox
 *   work-queue surface (the rows a planner can actually
 *   discover and act on), not the full population.
 *
 * No mapping is invented: each deep-link resolves to the
 * Inbox filter grammar (`?verdict=`, `?severity=`,
 * `?workflow_state=`) over fields the backend contract
 * actually exposes. The three workflow-state links use the
 * `workflow_state` values the backend derives from the same
 * evidence as `classify_investigation_state`.
 */

import Link from "next/link";

interface Props {
  summary: import("@/lib/types/api").ControlTowerSummary;
}

export function ControlTowerMetrics({ summary }: Props) {
  return (
    <div className="metric-grid">
      <Link className="metric" href="/exceptions">
        <span className="metric-label">Open Exceptions</span>
        <span className="metric-value">{summary.open_exceptions}</span>
        <span className="metric-note">Full operational population</span>
      </Link>
      <Link
        className="metric"
        href="/exceptions?workflow_state=Decision%20required"
      >
        <span className="metric-label">Pending Decisions</span>
        <span className="metric-value">{summary.pending_approvals}</span>
        <span className="metric-note">Full population</span>
      </Link>
      <Link
        className="metric"
        href="/exceptions?workflow_state=Awaiting%20execution"
      >
        <span className="metric-label">Awaiting Execution</span>
        <span className="metric-value">{summary.awaiting_execution}</span>
        <span className="metric-note">Full population</span>
      </Link>
      <Link
        className="metric"
        href="/exceptions?workflow_state=Executed%20%E2%80%94%20still%20open"
      >
        <span className="metric-label">Follow-up Required</span>
        <span className="metric-value">{summary.follow_up_required}</span>
        <span className="metric-note">
          Executed recovery, still open (full population)
        </span>
      </Link>
      <Link className="metric" href="/exceptions?severity=Critical">
        <span className="metric-label">Critical Open</span>
        <span className="metric-value metric-value-critical">
          {summary.critical_exceptions}
        </span>
        <span className="metric-note">Full population</span>
      </Link>
      <Link className="metric" href="/exceptions?verdict=actionable">
        <span className="metric-label">Actionable</span>
        <span className="metric-value">{summary.actionable_exceptions}</span>
        <span className="metric-note">
          Bounded work queue — feasible recovery available
        </span>
      </Link>
      <Link className="metric" href="/exceptions?verdict=no-feasible">
        <span className="metric-label">Monitoring</span>
        <span className="metric-value">{summary.monitoring_exceptions}</span>
        <span className="metric-note">
          Bounded work queue — no feasible recovery
        </span>
      </Link>
    </div>
  );
}
