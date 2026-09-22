/**
 * Severity presentation. Presentation-only: the mapping from
 * severity value to visual class is a display concern, not an
 * operational rule.
 */

const SEVERITY_CLASSES: Record<string, string> = {
  Critical: "chip-critical",
  High: "chip-high",
  Medium: "chip-neutral",
  Low: "chip-neutral",
};

export function SeverityChip({ severity }: { severity: string }) {
  const className = SEVERITY_CLASSES[severity] ?? "chip-neutral";

  return <span className={`chip ${className}`}>{severity}</span>;
}
