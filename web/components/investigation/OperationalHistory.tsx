/**
 * Evidence / Operational History: the reconstructed
 * chronological timeline from the backend history contract.
 * The backend is authoritative for lifecycle semantics —
 * including the deliberate Executed ≠ Resolved distinction —
 * so this view narrates events verbatim and infers nothing.
 *
 * P8.4 presentation: a CSS timeline rule and a display-only
 * marker per entry. The HistoryEntry contract carries no
 * event-type field, so the marker is a pure string mapping
 * over the backend's verbatim event names (exactly the
 * StateChip discipline): known strings map to neutral
 * categories, unknown strings fall back to the neutral dot.
 * The original event/detail/actor text is always rendered
 * verbatim; the marker adds visual scanning, not semantics.
 */

import type { HistoryEntry } from "@/lib/types/api";

/**
 * Presentation-only mapping from the backend's verbatim event
 * strings to neutral display categories. Keys must match the
 * persisted strings exactly (source: get_exception_history).
 * Anything unmapped renders the neutral fallback.
 */
const EVENT_MARKERS: Record<string, { className: string; label: string }> = {
  "Exception detected": { className: "marker-detected", label: "Detected" },
  "Recovery options evaluated": {
    className: "marker-evaluated",
    label: "Evaluated",
  },
  "Recommendation generated": {
    className: "marker-recommendation",
    label: "Recommendation",
  },
  "Recovery approved": { className: "marker-decision", label: "Decision" },
  "Recovery rejected": { className: "marker-decision", label: "Decision" },
  "Recovery executed": { className: "marker-executed", label: "Executed" },
  "Manual intervention recorded": {
    className: "marker-manual",
    label: "Manual",
  },
  "Exception resolved through manual intervention": {
    className: "marker-resolved",
    label: "Resolved",
  },
  "Exception resolved": { className: "marker-resolved", label: "Resolved" },
  "Exception still open": { className: "marker-open", label: "Still open" },
};

const NEUTRAL_MARKER = { className: "marker-neutral", label: "Event" };

function markerFor(event: string) {
  return EVENT_MARKERS[event] ?? NEUTRAL_MARKER;
}

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
          {entries.map((entry) => {
            const marker = markerFor(entry.event);

            return (
              <li key={entry.sequence} className="history-entry">
                <span
                  className={`history-marker ${marker.className}`}
                  title={marker.label}
                  aria-hidden="true"
                />
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
            );
          })}
        </ol>
      )}
    </section>
  );
}
