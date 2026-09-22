/**
 * The selected-exception focus panel. It presents only the
 * fields the inbox contract already carries — the full
 * investigation workflow (assessment, history, workflow
 * actions) arrives in later checkpoints against its own
 * /v1 endpoints.
 */

import type { InboxRow } from "@/lib/types/api";
import { SeverityChip } from "@/components/SeverityChip";

export function SelectedExceptionPanel({ exception }: { exception: InboxRow }) {
  return (
    <section className="section" aria-label="Selected exception">
      <h2 className="section-title">
        {exception.exception_id} — {exception.exception_type}
      </h2>
      <div className="table-wrap">
        <table className="data-table">
          <tbody>
            <tr>
              <th>Severity</th>
              <td>
                <SeverityChip severity={exception.severity} />
              </td>
              <th>Priority</th>
              <td>{exception.priority}</td>
            </tr>
            <tr>
              <th>Shipment</th>
              <td>{exception.shipment_id}</td>
              <th>Mode / Location</th>
              <td>
                {exception.transport_mode} · {exception.current_location}
              </td>
            </tr>
            <tr>
              <th>Estimated arrival</th>
              <td>{exception.estimated_arrival ?? "—"}</td>
              <th>Required delivery</th>
              <td>{exception.required_delivery_date}</td>
            </tr>
            <tr>
              <th>Estimated impact</th>
              <td>{exception.estimated_impact}</td>
              <th>Feasible recovery options</th>
              <td>{exception.feasible_option_count}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
