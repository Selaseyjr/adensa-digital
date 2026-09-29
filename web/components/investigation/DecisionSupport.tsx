/**
 * Decision Support: the deterministic recovery assessment
 * rendered transparently — recommendation, alternatives,
 * evaluated (infeasible) options, factor scores, weights,
 * weighted contributions, trade-offs and confidence.
 *
 * Everything shown is backend decision-engine output read
 * verbatim; nothing is recalculated, re-ranked or rescored
 * in the client (W4/W6 discipline carried into the web
 * client).
 *
 * P12.5 (reasoning chain): the recommendation's reasoning —
 * confidence basis and trade-offs — is promoted out of the
 * disclosure so the basic "why" reads at a glance; the
 * detailed factor table remains a native disclosure. Options
 * the engine evaluated without recommending are disclosed
 * under "Also evaluated" whenever the contract supplies them.
 * Still no recomputation: every rendered sentence is a
 * contract field verbatim.
 */

import type {
  EvaluatedOption,
  RecoveryAssessment,
  ScoredOption,
} from "@/lib/types/api";

function formatFactorKey(factor: string): string {
  return factor
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function RecommendedOptionCard({ option }: { option: ScoredOption }) {
  return (
    <div className="recommended-option">
      <div className="recommended-option-head">
        <span className="recommended-option-label">Recommended</span>
        <span className="recommended-option-title">
          {option.option_id} — {option.transport_mode}
        </span>
        {option.confidence !== null ? (
          <span className="chip chip-actionable">{option.confidence}</span>
        ) : null}
      </div>
      <p className="recommended-option-reason">{option.reason}</p>
      <dl className="option-facts">
        <div>
          <dt>Estimated cost</dt>
          <dd>{option.estimated_cost}</dd>
        </div>
        <div>
          <dt>Transit (days)</dt>
          <dd>{option.estimated_transit_days}</dd>
        </div>
        <div>
          <dt>Risk score</dt>
          <dd>{option.risk_score}</dd>
        </div>
        <div>
          <dt>Decision score</dt>
          <dd>{option.decision_score}</dd>
        </div>
      </dl>
    </div>
  );
}

/**
 * P12.5: the at-a-glance reasoning for the recommendation —
 * the rationale's confidence basis and trade-off sentences,
 * promoted out of the disclosure. Every line is a verbatim
 * contract field; nothing is summarized, reinterpreted or
 * invented here.
 */
function RecommendationWhy({
  rationale,
}: {
  rationale: NonNullable<RecoveryAssessment["rationale"]>;
}) {
  return (
    <div className="recommendation-why">
      <h4 className="subsection-title">Why this recommendation</h4>
      <p className="recommendation-why-basis">{rationale.confidence_basis}</p>
      {rationale.trade_offs.length > 0 ? (
        <ul className="trade-off-list">
          {rationale.trade_offs.map((tradeOff) => (
            <li key={tradeOff.option_id}>
              <strong>
                {tradeOff.option_id} ({tradeOff.transport_mode})
              </strong>{" "}
              is stronger on{" "}
              {tradeOff.stronger_factors.map(formatFactorKey).join(", ")}.
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function AlternativeRow({ option }: { option: ScoredOption }) {
  return (
    <tr>
      <td>
        {option.option_id} — {option.transport_mode}
      </td>
      <td>{option.estimated_cost}</td>
      <td>{option.estimated_transit_days}</td>
      <td>{option.risk_score}</td>
      <td>{option.decision_score}</td>
      <td>{option.confidence ?? "—"}</td>
    </tr>
  );
}

function EvaluatedOptionsTable({ options }: { options: EvaluatedOption[] }) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Option</th>
            <th>Mode</th>
            <th>Cost</th>
            <th>Transit (days)</th>
            <th>Risk</th>
            <th>Assessment</th>
          </tr>
        </thead>
        <tbody>
          {options.map((option) => (
            <tr key={option.option_id}>
              <td>{option.option_id}</td>
              <td>{option.transport_mode}</td>
              <td>{option.estimated_cost}</td>
              <td>{option.estimated_transit_days}</td>
              <td>{option.risk_score}</td>
              <td>{option.feasible ? "Feasible" : "Infeasible"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * P12.5: the detailed factor table keeps its native
 * disclosure — the at-a-glance reasoning above carries the
 * confidence basis and trade-offs, this carries the weights
 * and per-factor contributions.
 */
function FactorBreakdownDisclosure({
  rationale,
}: {
  rationale: NonNullable<RecoveryAssessment["rationale"]>;
}) {
  return (
    <details className="rationale subsection-details">
      <summary className="subsection-summary">
        Factor breakdown &amp; weights
      </summary>

      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Factor</th>
              <th>Weight</th>
              {rationale.factor_breakdown[0]?.values.map((value) => (
                <th key={value.option_id}>
                  {value.option_id} ({value.transport_mode})
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rationale.factor_breakdown.map((factor) => (
              <tr key={factor.factor}>
                <th>{formatFactorKey(factor.factor)}</th>
                <td>{factor.weight}</td>
                {factor.values.map((value) => (
                  <td key={value.option_id}>
                    {value.score} ({value.contribution})
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="rationale-note">
        Each cell: factor score (weighted contribution to the decision score).
        Weights are policy configuration — unchanged by this view.
      </p>
    </details>
  );
}

export function DecisionSupport({
  assessment,
}: {
  assessment: RecoveryAssessment;
}) {
  return (
    <section
      className="section section--options"
      aria-label="Decision support"
    >
      <h3 className="section-title">Decision Support</h3>

      {assessment.recommendation !== null ? (
        <>
          <RecommendedOptionCard option={assessment.recommendation} />

          {assessment.rationale !== null ? (
            <RecommendationWhy rationale={assessment.rationale} />
          ) : null}

          {assessment.alternatives.length > 0 ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Alternative</th>
                    <th>Cost</th>
                    <th>Transit (days)</th>
                    <th>Risk</th>
                    <th>Decision score</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {assessment.alternatives.map((option) => (
                    <AlternativeRow key={option.option_id} option={option} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="section-caption">
              No comparable alternatives were evaluated.
            </p>
          )}

          {assessment.rationale !== null ? (
            <FactorBreakdownDisclosure rationale={assessment.rationale} />
          ) : null}

          {/* P12.5: options the engine evaluated without
              recommending, whenever the contract supplies them.
              The neutral label stays truthful under every
              contract shape; the table's own Feasible/Infeasible
              column carries each verdict. */}
          {assessment.evaluated_options.length > 0 ? (
            <details className="subsection-details">
              <summary className="subsection-summary">
                Also evaluated — not recommended (
                {assessment.evaluated_options.length}{" "}
                {assessment.evaluated_options.length === 1
                  ? "option"
                  : "options"}
                )
              </summary>
              <EvaluatedOptionsTable options={assessment.evaluated_options} />
            </details>
          ) : null}
        </>
      ) : (
        <>
          <p className="state-panel-strong">
            No feasible system recovery available.
          </p>
          <p className="section-caption">
            Every evaluated recovery option is infeasible for this situation —
            resolution requires human intervention outside the system.
          </p>
          {assessment.evaluated_options.length > 0 ? (
            <details className="subsection-details">
              <summary className="subsection-summary">
                Evaluated recovery options ({assessment.evaluated_options.length}{" "}
                {assessment.evaluated_options.length === 1 ? "option" : "options"})
              </summary>
              <EvaluatedOptionsTable options={assessment.evaluated_options} />
            </details>
          ) : null}
        </>
      )}
    </section>
  );
}
