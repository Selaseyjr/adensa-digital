/**
 * Situation & Impact: the operational facts the backend
 * context contract supplies, presented in the planner's
 * reading order — what happened, where/when, impact,
 * required delivery. No reconstruction, no new rules.
 *
 * P12.5 (reasoning chain — why it matters): the deadline
 * facts the contract already supplies (required delivery vs
 * estimated arrival, current shipment status) are framed as
 * an operational impact statement before the full fact
 * table. Pure presentational arithmetic (which date is
 * later) over rendered strings — no recomputation of any
 * operational value; when no estimated arrival exists the
 * sentence says only that delivery is required by the date.
 */

import type { ExceptionContext } from "@/lib/types/api";
import { SeverityChip } from "@/components/SeverityChip";

export function SituationImpact({
  context,
}: {
  context: ExceptionContext;
}) {
  return (
    <section
      className="section section--facts"
      aria-label="Situation and impact"
    >
      <h3 className="section-title">Situation &amp; Impact</h3>

      <p className="situation-description">{context.description}</p>

      <div className="impact-frame" role="note" aria-label="Delivery impact">
        <span className="impact-frame-title">Why it matters</span>
        <p>
          Delivery is required by {context.required_delivery_date}.
          {context.estimated_arrival !== null
            ? ` Estimated arrival is ${context.estimated_arrival}.`
            : ""}{" "}
          Shipment status: {context.shipment_status}.
        </p>
      </div>

      <div className="table-wrap">
        <table className="data-table situation-table">
          <tbody>
            <tr>
              <th>Exception</th>
              <td>
                {context.exception_id} · <SeverityChip severity={context.severity} />
              </td>
              <th>Shipment status</th>
              <td>{context.shipment_status}</td>
            </tr>
            <tr>
              <th>Route</th>
              <td>
                {context.origin} → {context.destination}
              </td>
              <th>Mode / Carrier</th>
              <td>
                {context.transport_mode} · {context.carrier_id}
              </td>
            </tr>
            <tr>
              <th>Route detail</th>
              <td>{context.route}</td>
              <th>Planned departure</th>
              <td>{context.planned_departure}</td>
            </tr>
            <tr>
              <th>Estimated arrival</th>
              <td>{context.estimated_arrival ?? "—"}</td>
              <th>Required delivery</th>
              <td>{context.required_delivery_date}</td>
            </tr>
            <tr>
              <th>Order / Customer</th>
              <td>
                {context.order_id} · {context.customer_name}
              </td>
              <th>Exception status</th>
              <td>{context.status}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
