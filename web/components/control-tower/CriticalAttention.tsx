/**
 * Critical Attention (Command Centre v2, SEE zone).
 *
 * The first operational priority: the critical slice of the
 * bounded work queue, presented for direct action. Every
 * entry comes from GET /v1/exceptions/inbox (server-ordered,
 * bounded ≤100); this component applies the presentation-only
 * filter the same way SeverityChip does — severity value →
 * tone, no operational interpretation — and derives nothing
 * the API did not state.
 *
 * The calm-empty state is explicit copy, never a blank
 * region: "no critical items" is itself operational
 * information.
 *
 * Motion: the section container carries the one-shot
 * `attention-critical` halo (twice, subtle) to say "this is
 * the live priority" — neutralized by the reduced-motion
 * guards. Individual rows never pulse.
 */

import Link from "next/link";
import type { InboxRow } from "@/lib/types/api";

/** Presentation-only criticality filter: the inbox's own
 * severity vocabulary, no invented operational rule. */
function isCritical(row: InboxRow): boolean {
  return row.severity === "Critical";
}

export function CriticalAttention({ rows }: { rows: InboxRow[] }) {
  const critical = rows.filter(isCritical).slice(0, 4);

  return (
    <section
      className="section section-critical-attention attention-critical"
      aria-labelledby="critical-attention-title"
    >
      <h2 id="critical-attention-title" className="section-title">
        Critical Attention
      </h2>
      <p className="section-caption">
        Critical open exceptions in the bounded work queue — the situations
        that need a manager first. The queue below holds the full bounded
        view.
      </p>

      {critical.length === 0 ? (
        <p className="critical-attention-empty">
          No critical exceptions are open. The highest-severity work remains
          visible in the attention queue below.
        </p>
      ) : (
        <ul className="critical-attention-list">
          {critical.map((row) => (
            <li key={row.exception_id} className="critical-attention-item">
              <div className="critical-attention-main">
                <Link
                  className="queue-link op-id"
                  href={`/exceptions/${encodeURIComponent(row.exception_id)}`}
                >
                  {row.exception_id}
                </Link>
                <span className="critical-attention-type">{row.exception_type}</span>
                <span className="critical-attention-why">{row.estimated_impact}</span>
              </div>
              <div className="critical-attention-side">
                <span className="critical-attention-ref op-id">{row.shipment_id}</span>
                <span className="chip chip-critical">{row.severity}</span>
                <span className="chip chip-neutral">{row.workflow_state}</span>
                <Link
                  className="op-exception-link"
                  href={`/exceptions/${encodeURIComponent(row.exception_id)}`}
                >
                  Investigate
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
