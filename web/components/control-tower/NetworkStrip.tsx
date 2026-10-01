/**
 * The living-network strip (Command Centre v2 hero element).
 *
 * A deliberately abstract representation of Adensa's
 * operational loop — Detect → Recommend → Decide → Execute →
 * Resolve — as a horizontal flow of nodes carrying subtle
 * one-shot activity. It is decoration with an argument: the
 * system continuously processes the network; the manager
 * does not operate every shipment by hand.
 *
 * Rules:
 * - Pure SVG, dependency-free, token-driven (--series-*) so
 *   it belongs to both themes without variants.
 * - The activity animation is a ONE-SHOT progress wash on
 *   load (not a loop) and is fully neutralized by the global
 *   prefers-reduced-motion guard and [data-motion="reduced"].
 * - aria-hidden: the operational narrative is carried by the
 *   deck copy and the Living Flow section; this element is
 *   never the information carrier.
 */

const STAGES = ["Detect", "Recommend", "Decide", "Execute", "Resolve"] as const;

export function NetworkStrip() {
  return (
    <div className="network-strip" aria-hidden="true">
      <svg
        viewBox="0 0 640 56"
        focusable="false"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* The flow line: the continuity of the loop. */}
        <line
          className="network-strip-line"
          x1="16"
          y1="28"
          x2="624"
          y2="28"
        />
        {/* One-shot activity wash travelling the line. */}
        <line
          className="network-strip-pulse"
          x1="16"
          y1="28"
          x2="624"
          y2="28"
        />
        {STAGES.map((stage, i) => {
          const cx = 16 + i * ((624 - 16) / (STAGES.length - 1));
          return (
            <g key={stage} className="network-strip-node">
              <circle cx={cx} cy="28" r="5" />
              <circle className="network-strip-node-halo" cx={cx} cy="28" r="9" />
              <text x={cx} y="52" textAnchor="middle">
                {stage}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
