/**
 * Severity presentation. Presentation-only: the mapping from
 * severity value to visual class is a display concern, not an
 * operational rule.
 *
 * P8.9: carries a small aria-hidden severity dot beside the
 * chip so the column scans by colour as well as by text. The
 * chip text remains the semantic carrier; unknown severities
 * fall back to the neutral dot + chip, exactly as before.
 *
 * P12.5: all four severities now carry a visible dot, so the
 * whole queue scans without reading chip text. Medium and Low
 * differentiate by dot weight/opacity within the existing
 * neutral vocabulary — no new hues, no rainbow palette. The
 * severity *text* is always the semantic source; the dots are
 * aria-hidden decoration.
 *
 * The tone mapping is exported for presentation consumers
 * (inbox rows' data-severity rails) only. It is a display
 * concern, not an operational rule: unknown severities map to
 * "neutral" rather than being interpreted.
 */

/** Presentation-only severity tone. Unknown values → "neutral". */
export function severityToneOf(severity: string): string {
  switch (severity) {
    case "Critical":
      return "critical";
    case "High":
      return "high";
    case "Medium":
      return "medium";
    case "Low":
      return "low";
    default:
      return "neutral";
  }
}

const SEVERITY_CLASSES: Record<string, string> = {
  Critical: "chip-critical",
  High: "chip-high",
  Medium: "chip-neutral",
  Low: "chip-neutral",
};

/** Dot classes for all four severities plus the neutral fallback. */
const DOT_CLASSES: Record<string, string> = {
  Critical: "severity-dot-critical",
  High: "severity-dot-high",
  Medium: "severity-dot-medium",
  Low: "severity-dot-low",
};

export function SeverityChip({ severity }: { severity: string }) {
  const className = SEVERITY_CLASSES[severity] ?? "chip-neutral";
  const dotClass = DOT_CLASSES[severity];

  return (
    <span className="severity-cell" data-severity={severityToneOf(severity)}>
      {dotClass ? (
        <span aria-hidden="true" className={`severity-dot ${dotClass}`} />
      ) : null}
      <span className={`chip ${className}`}>{severity}</span>
    </span>
  );
}
