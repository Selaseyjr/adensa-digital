/**
 * Follow-up delay indicator: a supplementary proportional
 * marker for the gap the follow-up entry's own factual
 * `reason` already states — estimated arrival vs required
 * delivery.
 *
 * The track spans a truthful, fully-supplied window — from
 * the anchor date (execution time, falling back to detection
 * time) to the estimated arrival — and the marker sits at the
 * required date's real position within that window. The zone
 * after the marker is the late zone. Nothing is inferred: no
 * operational state, no severity scale, no projected dates.
 * The actual dates remain visible as text in the same table
 * cell, and the plain fallback (—) is preserved for entries
 * without an ETA. If the ETA is not after the required date
 * (or the window cannot be established from real dates), the
 * indicator renders nothing rather than implying a state the
 * contract does not carry.
 *
 * Accessibility: the visual is hidden from assistive
 * technology (`aria-hidden`) — the dates and the API's
 * factual reason text are the accessible content.
 */

const DAY_MS = 24 * 60 * 60 * 1000;

function daysBetween(from: Date, to: Date): number {
  return (to.getTime() - from.getTime()) / DAY_MS;
}

export function FollowUpDelayIndicator({
  anchorDate,
  estimatedArrival,
  requiredDeliveryDate,
}: {
  /** Execution timestamp, or detection time as fallback — real dates only. */
  anchorDate: string | null;
  estimatedArrival: string | null;
  requiredDeliveryDate: string;
}) {
  if (anchorDate === null || estimatedArrival === null) {
    return null;
  }

  const anchor = new Date(anchorDate);
  const eta = new Date(estimatedArrival);
  const required = new Date(requiredDeliveryDate);

  if (
    Number.isNaN(anchor.getTime()) ||
    Number.isNaN(eta.getTime()) ||
    Number.isNaN(required.getTime())
  ) {
    return null;
  }

  const spanDays = daysBetween(anchor, eta);
  const requiredOffsetDays = daysBetween(anchor, required);

  // The indicator exists only for the late case (ETA after
  // required) with a positive, representable window.
  if (spanDays <= 0 || requiredOffsetDays >= spanDays) {
    return null;
  }

  const lateDays = Math.max(
    Math.round(daysBetween(required, eta)),
    0,
  );
  const markerPercent = Math.min(
    Math.max((requiredOffsetDays / spanDays) * 100, 0),
    100,
  );
  const latePercent = 100 - markerPercent;

  return (
    <span className="delay-indicator" aria-hidden="true">
      <span className="delay-indicator-track">
        <span
          className="delay-indicator-late"
          style={{ left: `${markerPercent}%`, width: `${latePercent}%` }}
        />
        <span
          className="delay-indicator-marker"
          style={{ left: `${markerPercent}%` }}
        />
      </span>
      <span className="delay-indicator-caption">
        ETA {lateDays} {lateDays === 1 ? "day" : "days"} after required
      </span>
    </span>
  );
}
