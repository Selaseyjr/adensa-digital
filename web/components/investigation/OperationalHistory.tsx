/**
 * Evidence / Operational History: the reconstructed
 * chronological timeline from the backend history contract.
 * The backend is authoritative for lifecycle semantics —
 * including the deliberate Executed ≠ Resolved distinction —
 * so this view narrates events verbatim and infers nothing.
 */

import type { HistoryEntry } from "@/lib/types/api";

export function OperationalHistory({
  entries,
}: {
  entries: HistoryEntry[];
}) {
  return (
    <section className="section" aria-label="Operational history">
      <h3 className="section-title">Operational History</h3>

      {entries.length === 0 ? (
        <p className="section-caption">
          No operational history has been recorded for this exception yet.
        </p>
      ) : (
        <ol className="history-list">
          {entries.map((entry) => (
            <li key={entry.sequence} className="history-entry">
              <span className="history-timestamp">
                {entry.timestamp ?? "—"}
              </span>
              <div className="history-body">
                <p className="history-event">
                  {entry.event}
                  <span className="history-actor"> — {entry.actor}</span>
                </p>
                <p className="history-detail">{entry.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
