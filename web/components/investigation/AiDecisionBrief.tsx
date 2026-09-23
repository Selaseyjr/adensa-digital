/**
 * AI Advisory: the advisory decision brief from the /v1
 * decision-brief endpoint, rendered strictly subordinate to
 * the deterministic Decision Support above it.
 *
 * The brief interprets evidence the deterministic engine has
 * already established; it never approves, executes or
 * resolves anything. This component presents the backend's
 * advisory framing verbatim — label, disclaimer, verification
 * points — and adds no interpretation of its own. The
 * structured unavailable state renders honestly; an advisory
 * failure never affects the rest of the workspace.
 */

import type { DecisionBrief } from "@/lib/types/api";

export function AiDecisionBrief({ brief }: { brief: DecisionBrief }) {
  if (brief.status !== "available") {
    return (
      <aside className="section ai-advisory" aria-label="AI advisory">
        <h3 className="section-title">AI Advisory</h3>
        <p className="section-caption">{brief.message}</p>
      </aside>
    );
  }

  return (
    <aside className="section ai-advisory" aria-label="AI advisory">
      <div className="ai-advisory-head">
        <h3 className="section-title">AI Advisory</h3>
        <span className="chip chip-neutral">{brief.advisory_label}</span>
      </div>

      <p className="section-caption">
        Supporting interpretation of the deterministic assessment above —
        advisory only, never the operational decision.
      </p>

      <h4 className="subsection-title">Situation</h4>
      <p className="advisory-text">{brief.situation_summary}</p>

      <h4 className="subsection-title">Recommended action</h4>
      <p className="advisory-text">{brief.recommended_action}</p>

      <h4 className="subsection-title">Rationale</h4>
      <p className="advisory-text">{brief.rationale}</p>

      <h4 className="subsection-title">Trade-offs</h4>
      <p className="advisory-text">{brief.tradeoffs}</p>

      {brief.verification_points && brief.verification_points.length > 0 ? (
        <>
          <h4 className="subsection-title">Verify before acting</h4>
          <ul className="trade-off-list">
            {brief.verification_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </>
      ) : null}

      <p className="advisory-disclaimer">{brief.disclaimer}</p>
      <p className="advisory-provider">Advisory provider: {brief.provider}</p>
    </aside>
  );
}
