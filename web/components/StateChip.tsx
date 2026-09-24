/**
 * Lifecycle-state presentation. Presentation-only mapping
 * from the backend's persisted-evidence state value to a
 * chip class — no new states are invented here.
 *
 * The keys are the classifier's literal state strings
 * (classify_investigation_state), em dashes included —
 * unmatched states fall back to the neutral chip, so an
 * incorrect key would silently mis-tint real states.
 */

const STATE_CLASSES: Record<string, string> = {
  "Decision required": "chip-warning",
  "Awaiting execution": "chip-actionable",
  "Executed — still open": "chip-warning",
  "No system recovery available": "chip-warning",
  Resolved: "chip-actionable",
};

export function StateChip({ state }: { state: string }) {
  const className = STATE_CLASSES[state] ?? "chip-neutral";

  return <span className={`chip ${className}`}>{state}</span>;
}
