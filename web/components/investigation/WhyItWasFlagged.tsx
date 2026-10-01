/**
 * Why It Was Flagged: the operational trigger, stated from
 * the persisted evidence only.
 *
 * The explanation composes exactly two backend fields — the
 * context contract's operational description (the detection
 * engine's own wording) and the investigation state's reason
 * (the persisted-evidence classifier's own wording) — under a
 * single "why" frame in the established `impact-frame`
 * vocabulary. No explanation text is written here: an
 * unavailable field is simply absent from the frame, and the
 * section never implies a fact the API did not state.
 */

import type { ExceptionContext, InvestigationState } from "@/lib/types/api";

export function WhyItWasFlagged({
  context,
  state,
}: {
  context: ExceptionContext;
  state: InvestigationState | null;
}) {
  return (
    <section
      className="section section--flagged"
      aria-label="Why it was flagged"
    >
      <h3 className="section-title">Why It Was Flagged</h3>

      <div
        className="impact-frame flagged-frame"
        role="note"
        aria-label="Operational trigger"
      >
        <span className="impact-frame-title">Operational trigger</span>
        <p>{context.description}</p>
      </div>

      {state !== null ? (
        <div
          className="impact-frame flagged-frame"
          role="note"
          aria-label="Current standing"
        >
          <span className="impact-frame-title">Why it needs attention now</span>
          <p>{state.reason}</p>
        </div>
      ) : null}
    </section>
  );
}
