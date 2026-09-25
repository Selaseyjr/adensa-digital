/**
 * Horizontal SVG bar-chart primitive for the categorical
 * analytical variables (P8.7.3): transport, carriers,
 * warehouses.
 *
 * Sibling to `LineChart` and bound to the same production
 * rules:
 *
 * - The chart never computes analytics. It maps the API's
 *   category/value pairs onto geometry and renders them;
 *   percentages are the API's own 0–100 values with a unit
 *   suffix applied for display only. No frontend business
 *   arithmetic.
 * - A `null` value means the backend had no observation for
 *   that category (e.g. a mode with zero delivered shipments —
 *   zero denominator). The bar is simply absent and the value
 *   column reads "No observation"; no length is invented.
 * - Responsive by viewBox scaling inside a width-constrained
 *   parent; the SVG never introduces page-level overflow.
 * - Accessibility: `role="img"` labelled by the panel heading
 *   and described by the panel's basis text, plus a
 *   visually-hidden data-table fallback so the chart is never
 *   the only representation of the information.
 * - Motion: the shared one-shot 200ms ease-out reveal
 *   (`chart-reveal`); the global `prefers-reduced-motion`
 *   guard neutralizes it to the steady state.
 *
 * Pure Server-Component-safe rendering: no hooks, no state.
 */

export interface BarChartEntry {
  /** Category label, verbatim from the API (e.g. "Road"). */
  label: string;
  /** API value; null means "no observation for this category". */
  value: number | null;
}

interface BarChartProps {
  entries: BarChartEntry[];
  /** Id of the panel heading this chart belongs to (aria-labelledby). */
  titleId: string;
  /** Id of the panel's analytical-basis text (aria-describedby). */
  describedById: string;
  /** Row header for the data-table fallback, e.g. "On-time rate". */
  valueLabel: string;
  /** Unit suffix for the default value formatter (default "%"). */
  unit?: string;
  /**
   * Top of the value scale (default 100 for percentage series).
   * Omit for count series: the scale then tops at the largest
   * returned value — presentation geometry only, never a data
   * change.
   */
  valueMax?: number;
  /** Optional custom value formatter (default appends the unit). */
  formatValue?: (value: number) => string;
}

// Fixed viewBox width; height scales with the row count so the
// SVG stays proportionate at every panel width.
const W = 480;
const ROW_H = 34;
const PAD = { top: 8, bottom: 8 };
const LABEL_X = 132; // right edge of the category-label column
const VALUE_GUTTER = 58; // reserved for the end-of-bar value text

export function BarChart({
  entries,
  titleId,
  describedById,
  valueLabel,
  unit = "%",
  valueMax,
  formatValue,
}: BarChartProps) {
  const format = formatValue ?? ((value: number) => `${value}${unit}`);
  if (entries.length === 0) return null;

  const scaleTop =
    valueMax ?? Math.max(...entries.map((e) => e.value ?? 0), 0);
  // A scale of 0 (all-null or all-zero series) would divide by
  // zero; any nonzero value then dominates, so fall back to 1.
  const safeTop = scaleTop > 0 ? scaleTop : 1;
  const barMaxW = W - LABEL_X - VALUE_GUTTER;
  const H = PAD.top + entries.length * ROW_H + PAD.bottom;
  const rowY = (i: number) => PAD.top + i * ROW_H;
  const barW = (value: number) => {
    const clamped = Math.min(Math.max(value, 0), safeTop);
    return (clamped / safeTop) * barMaxW;
  };

  return (
    <figure className="chart-figure bar-figure chart-reveal">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-labelledby={`${titleId} ${describedById}`}
        focusable="false"
      >
        {entries.map((entry, i) => {
          const y = rowY(i);
          const hasValue = entry.value !== null && Number.isFinite(entry.value);
          const width = hasValue ? barW(entry.value as number) : 0;
          return (
            <g key={entry.label}>
              <text
                className="chart-axis-label bar-category-label"
                x={LABEL_X - 8}
                y={y + ROW_H / 2 + 3.5}
                textAnchor="end"
              >
                {entry.label}
              </text>
              <line
                className="bar-track"
                x1={LABEL_X}
                x2={W - VALUE_GUTTER}
                y1={y + ROW_H / 2}
                y2={y + ROW_H / 2}
                vectorEffect="non-scaling-stroke"
              />
              {hasValue ? (
                <rect
                  className="bar-fill"
                  x={LABEL_X}
                  y={y + ROW_H / 2 - 9}
                  width={width}
                  height={18}
                  rx={3}
                />
              ) : null}
              <text
                className="chart-axis-label bar-value-label"
                x={LABEL_X + width + 6}
                y={y + ROW_H / 2 + 3.5}
                textAnchor="start"
              >
                {hasValue ? format(entry.value as number) : "No observation"}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Visually-hidden data-table fallback: the exact API
          values, including explicit "no observation" categories. */}
      <table className="visually-hidden">
        <caption>
          {valueLabel} by category (chart data)
        </caption>
        <thead>
          <tr>
            <th scope="col">Category</th>
            <th scope="col">{valueLabel}</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.label}>
              <th scope="row">{entry.label}</th>
              <td>
                {entry.value === null || !Number.isFinite(entry.value)
                  ? "No observation"
                  : format(entry.value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
