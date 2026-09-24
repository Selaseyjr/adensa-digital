/**
 * Follow-up queue: exceptions whose recovery has already
 * been executed without resolving them. The factual reason
 * per entry comes from the API; the client adds nothing.
 */

import type { ControlTowerFollowUpEntry } from "@/lib/types/api";
import { SeverityChip } from "@/components/SeverityChip";
import { FollowUpDelayIndicator } from "@/components/control-tower/FollowUpDelayIndicator";

export function FollowUpTable({ entries }: { entries: ControlTowerFollowUpEntry[] }) {
  if (entries.length === 0) {
    return <p className="section-caption">No follow-up work outstanding.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Exception</th>
            <th>Severity</th>
            <th>Issue</th>
            <th>Executed</th>
            <th>ETA vs Required</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.exception_id}>
              <td>{entry.exception_id}</td>
              <td>
                <SeverityChip severity={entry.severity} />
              </td>
              <td>{entry.exception_type}</td>
              <td>{entry.executed_at ?? "—"}</td>
              <td>
                <span className="eta-required-text">
                  {entry.estimated_arrival ?? "—"} vs{" "}
                  {entry.required_delivery_date}
                </span>
                <FollowUpDelayIndicator
                  anchorDate={entry.executed_at ?? entry.detected_at}
                  estimatedArrival={entry.estimated_arrival}
                  requiredDeliveryDate={entry.required_delivery_date}
                />
              </td>
              <td>{entry.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
