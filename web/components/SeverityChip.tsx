/**
 * Severity presentation. Presentation-only: the mapping from
 * severity value to visual class is a display concern, not an
 * operational rule.
 *
 * P8.9: carries a small aria-hidden severity dot beside the
 * chip so the column scans by colour as well as by text. The
 * chip text remains the semantic carrier; unknown severities
 * fall back to the neutral dot + chip, exactly as before.
 */

const SEVERITY_CLASSES: Record<string, string> = {
  Critical: "chip-critical",
  High: "chip-high",
  Medium: "chip-neutral",
  Low: "chip-neutral",
};

const DOT_CLASSES: Record<string, string> = {
  Critical: "severity-dot-critical",
  High: "severity-dot-high",
};

export function SeverityChip({ severity }: { severity: string }) {
  const className = SEVERITY_CLASSES[severity] ?? "chip-neutral";
  const dotClass = DOT_CLASSES[severity];

  return (
    <span className="severity-cell">
      {dotClass ? (
        <span aria-hidden="true" className={`severity-dot ${dotClass}`} />
      ) : null}
      <span className={`chip ${className}`}>{severity}</span>
    </span>
  );
}
