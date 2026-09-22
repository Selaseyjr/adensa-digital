/**
 * Control-tower KPI grid.
 *
 * Every number is rendered exactly as the API reports it —
 * the client computes no metrics. The two population
 * semantics are preserved verbatim from the backend
 * contract:
 *
 * - Open / Critical / Pending decisions / Awaiting execution /
 *   Follow-up required describe the FULL operational
 *   population;
 * - Actionable / Monitoring partition the BOUNDED inbox
 *   work-queue surface (the rows a planner can actually
 *   discover and act on), not the full population.
 */

interface Props {
  summary: import("@/lib/types/api").ControlTowerSummary;
}

export function ControlTowerMetrics({ summary }: Props) {
  return (
    <div className="metric-grid">
      <div className="metric">
        <span className="metric-label">Open Exceptions</span>
        <span className="metric-value">{summary.open_exceptions}</span>
        <span className="metric-note">Full operational population</span>
      </div>
      <div className="metric">
        <span className="metric-label">Pending Decisions</span>
        <span className="metric-value">{summary.pending_approvals}</span>
        <span className="metric-note">Full population</span>
      </div>
      <div className="metric">
        <span className="metric-label">Awaiting Execution</span>
        <span className="metric-value">{summary.awaiting_execution}</span>
        <span className="metric-note">Full population</span>
      </div>
      <div className="metric">
        <span className="metric-label">Follow-up Required</span>
        <span className="metric-value">{summary.follow_up_required}</span>
        <span className="metric-note">
          Executed recovery, still open (full population)
        </span>
      </div>
      <div className="metric">
        <span className="metric-label">Critical Open</span>
        <span className="metric-value">{summary.critical_exceptions}</span>
        <span className="metric-note">Full population</span>
      </div>
      <div className="metric">
        <span className="metric-label">Actionable</span>
        <span className="metric-value">{summary.actionable_exceptions}</span>
        <span className="metric-note">
          Bounded work queue — feasible recovery available
        </span>
      </div>
      <div className="metric">
        <span className="metric-label">Monitoring</span>
        <span className="metric-value">{summary.monitoring_exceptions}</span>
        <span className="metric-note">
          Bounded work queue — no feasible recovery
        </span>
      </div>
    </div>
  );
}
