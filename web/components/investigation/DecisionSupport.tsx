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

function RationaleBlock({
  rationale,
}: {
  rationale: NonNullable<RecoveryAssessment["rationale"]>;
}) {
  return (
    <div className="rationale">
      <h4 className="subsection-title">Why this recommendation</h4>

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

      <p className="confidence-basis">
        <strong>Confidence basis:</strong> {rationale.confidence_basis}
      </p>
    </div>
  );
}

export function DecisionSupport({
  assessment,
}: {
  assessment: RecoveryAssessment;
}) {
  return (
    <section className="section" aria-label="Decision support">
      <h3 className="section-title">Decision Support</h3>

      {assessment.recommendation !== null ? (
        <>
          <RecommendedOptionCard option={assessment.recommendation} />

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
            <RationaleBlock rationale={assessment.rationale} />
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
            <EvaluatedOptionsTable options={assessment.evaluated_options} />
          ) : null}
        </>
      )}
    </section>
  );
}
