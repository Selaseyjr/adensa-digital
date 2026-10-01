/**
 * What Needs Attention (Command Centre v2, ACT zone): the
 * bounded work queue presented for decisions. Rows render in
 * the backend's own operational order — no client-side
 * re-ranking, no derived priority — exactly the semantics the
 * Exception Inbox already owns; each row answers what
 * happened / which shipment / why it matters / what stage /
 * what to do.
 *
 * The bounded-window honesty note renders whenever the full
 * population exceeds the bounded view (the summary carries
 * the full-population counts), so "10 of 786" can never read
 * as the whole operation. The empty state is the calm,
 * explicit verdict — not a blank region.
 */

import Link from "next/link";
import type { ControlTowerSummary, InboxRow } from "@/lib/types/api";

export function AttentionQueue({
  rows,
  summary,
}: {
  rows: InboxRow[];
  summary: ControlTowerSummary | null;
}) {
  const queue = rows.slice(0, 10);
  const boundedBeyond =
    summary !== null && summary.open_exceptions > queue.length;

  return (
    <section className="section" aria-labelledby="attention-queue-title">
      <h2 id="attention-queue-title" className="section-title">
        What Needs Attention
      </h2>
      <p className="section-caption">
        The bounded work queue in the backend&apos;s operational order — feasible
        recovery first, then newest detected. Every row links into its
        investigation workspace.
      </p>

      {queue.length === 0 ? (
        <p className="critical-attention-empty">
          The work queue is clear. No open exceptions are waiting for
          manager review.
        </p>
      ) : (
        <ol className="attention-queue-list">
          {queue.map((row) => (
            <li key={row.exception_id} className="attention-queue-item">
              <div className="attention-queue-main">
                <Link
                  className="queue-link op-id"
                  href={`/exceptions/${encodeURIComponent(row.exception_id)}`}
                >
                  {row.exception_id}
                </Link>
                <span className="attention-queue-type">{row.exception_type}</span>
                <span className="attention-queue-why">{row.estimated_impact}</span>
              </div>
              <div className="attention-queue-side">
                <span className="attention-queue-ref op-id">{row.shipment_id}</span>
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
        </ol>
      )}

      {boundedBeyond && (
        <p className="attention-queue-note">
          Showing {queue.length} of {summary.open_exceptions} open exceptions —
          the bounded operational window. The{" "}
          <Link href="/exceptions">full Exception Inbox</Link> carries the
          complete view with every filter.
        </p>
      )}
    </section>
  );
}
