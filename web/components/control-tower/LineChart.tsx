/**
 * Reusable SVG line-chart primitive (P8.7.2).
 *
 * Deliberately small and dependency-free: the analytical
 * contract is a bounded list of labelled points with one
 * primary rate series per panel, which needs no charting
 * library. Architectural rules:
 *
 * - The chart never computes analytics. It maps the API's
 *   label/value pairs onto axes and renders them; percentages
 *   are the API's own 0–100 values with a unit suffix applied
 *   for display only. No frontend business arithmetic.
 * - A `null` value means the backend had no observation for
 *   that label (e.g. a month with zero delivered shipments —
 *   zero denominator). The path breaks there rather than
 *   inventing a point, and the label still renders.
 * - Responsive by viewBox scaling inside a width-constrained
 *   parent; the SVG never introduces page-level overflow.
 * - Accessibility: `role="img"` labelled by the panel heading
 *   and described by the panel's basis text, plus a
 *   visually-hidden data-table fallback so the chart is never
 *   the only representation of the information.
 * - Motion: a one-shot 200ms ease-out reveal (`chart-reveal`);
 *   the global `prefers-reduced-motion` guard neutralizes it
 *   to the steady state.
 *
 * Pure Server-Component-safe rendering: no hooks, no state.
 */

export interface LineChartPoint {
  /** X-axis label, verbatim from the API (e.g. "2026-01"). */
  label: string;
  /** API value; null means "no observation for this label". */
  value: number | null;
}

interface LineChartProps {
  points: LineChartPoint[];
  /** Id of the panel heading this chart belongs to (aria-labelledby). */
  titleId: string;
  /** Id of the panel's analytical-basis text (aria-describedby). */
  describedById: string;
  /** Column header for the data-table fallback, e.g. "On-time rate". */
  valueLabel: string;
  /** Unit suffix for the default value formatter (default "%"). */
  unit?: string;
  /** Top of the y scale (default 100 for percentage series). */
  yMax?: number;
  /** Gridline spacing from 0 up to yMax (default 25). */
  gridStep?: number;
  /** Optional custom value formatter (default appends the unit). */
  formatValue?: (value: number) => string;
}

// Fixed viewBox geometry; the SVG scales fluidly to its parent.
// PAD.right keeps the final (right-edge) x-axis label fully
// inside the viewBox: centre-anchored at the plot boundary,
// a 16px pad clipped its right half ("2026-0").
const W = 480;
const H = 300;
const PAD = { top: 16, right: 24, bottom: 36, left: 46 };

export function LineChart({
  points,
  titleId,
  describedById,
  valueLabel,
  unit = "%",
  yMax = 100,
  gridStep = 25,
  formatValue,
}: LineChartProps) {
  const format = formatValue ?? ((value: number) => `${value}${unit}`);
  if (points.length === 0) return null;

  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const xAt = (i: number): number =>
    PAD.left +
    (points.length === 1 ? innerW / 2 : (i * innerW) / (points.length - 1));
  const yAt = (value: number): number => {
    // Presentation-level clamping keeps a stray out-of-range
    // value inside the plot area; it never alters the data.
    const clamped = Math.min(Math.max(value, 0), yMax);
    return PAD.top + innerH * (1 - clamped / yMax);
  };

  const gridValues: number[] = [];
  for (let g = 0; g <= yMax + 1e-9; g += gridStep) {
    gridValues.push(g);
  }

  // Thin x labels on dense series; never drop the last label.
  const labelEvery =
    points.length <= 12 ? 1 : Math.ceil(points.length / 12);

  // The path breaks at null observations instead of inventing
  // a point, and dots render only where a value exists.
  let path = "";
  let pen = false;
  points.forEach((point, i) => {
    if (point.value === null || !Number.isFinite(point.value)) {
      pen = false;
      return;
    }
    path += `${pen ? " L" : " M"} ${xAt(i).toFixed(1)} ${yAt(point.value).toFixed(1)}`;
    pen = true;
  });

  return (
    <figure className="chart-figure chart-reveal">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-labelledby={`${titleId} ${describedById}`}
        focusable="false"
      >
        {gridValues.map((g) => (
          <g key={g}>
            <line
              className="chart-grid"
              x1={PAD.left}
              x2={W - PAD.right}
              y1={yAt(g)}
              y2={yAt(g)}
              vectorEffect="non-scaling-stroke"
            />
            <text
              className="chart-axis-label chart-axis-label-y"
              x={PAD.left - 8}
              y={yAt(g) + 4}
              textAnchor="end"
            >
              {format(g)}
            </text>
          </g>
        ))}

        {path ? (
          <path
            className="chart-path"
            d={path}
            fill="none"
            vectorEffect="non-scaling-stroke"
          />
        ) : null}

        {points.map((point, i) =>
          point.value === null || !Number.isFinite(point.value) ? null : (
            <circle
              key={point.label}
              className="chart-dot"
              cx={xAt(i)}
              cy={yAt(point.value)}
              r={3.5}
            />
          ),
        )}

        {points.map((point, i) =>
          i % labelEvery !== 0 && i !== points.length - 1 ? null : (
            <text
              key={`x-${point.label}`}
              className="chart-axis-label chart-axis-label-x"
              x={xAt(i)}
              y={H - 14}
              textAnchor="middle"
            >
              {point.label}
            </text>
          ),
        )}
      </svg>

      {/* Visually-hidden data-table fallback: the exact API
          values, including explicit "no observation" months. */}
      <table className="visually-hidden">
        <caption>
          {valueLabel} by month (chart data)
        </caption>
        <thead>
          <tr>
            <th scope="col">Month</th>
            <th scope="col">{valueLabel}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.label}>
              <th scope="row">{point.label}</th>
              <td>
                {point.value === null || !Number.isFinite(point.value)
                  ? "No observation"
                  : format(point.value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
