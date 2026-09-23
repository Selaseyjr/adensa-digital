/**
 * Lifecycle-state presentation. Presentation-only mapping
 * from the backend's persisted-evidence state value to a
 * chip class — no new states are invented here.
 */

const STATE_CLASSES: Record<string, string> = {
  "Decision required": "chip-warning",
  "Awaiting execution": "chip-actionable",
  "Executed, still open": "chip-warning",
  "Follow-up required": "chip-warning",
  "No feasible recovery": "chip-neutral",
  Resolved: "chip-actionable",
};

export function StateChip({ state }: { state: string }) {
  const className = STATE_CLASSES[state] ?? "chip-neutral";

  return <span className={`chip ${className}`}>{state}</span>;
}
