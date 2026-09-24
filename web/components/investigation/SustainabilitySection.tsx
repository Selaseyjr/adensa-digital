/**
 * Sustainability: the informational emissions comparison,
 * kept deliberately subordinate to the operational decision
 * (Checkpoint V framing). Estimated, prototype-factor-based
 * figures are labelled as such; the structured unavailable
 * state is rendered as an honest "no comparison" record.
 *
 * The estimate table and methodology are secondary,
 * high-density information and sit inside a native
 * <details> disclosure (P8.4): verbatim content, native
 * semantics, keyboard accessible, no JS state.
 */

import type {
  SustainabilityComparison,
  SustainabilityUnavailable,
} from "@/lib/types/api";

export function SustainabilitySection({
  sustainability,
}: {
  sustainability: SustainabilityComparison | SustainabilityUnavailable;
}) {
  if (!("estimates" in sustainability)) {
    return (
      <section className="section" aria-label="Sustainability">
        <h3 className="section-title">Sustainability Impact</h3>
        <p className="section-caption">{sustainability.reason}</p>
      </section>
    );
  }

  const available = sustainability.estimates.filter(
    (estimate) => estimate.estimated_co2e_kg !== null,
  );

  return (
    <section className="section" aria-label="Sustainability">
      <h3 className="section-title">Sustainability Impact</h3>

      <p className="section-caption">
        Informational only — estimated emissions ({sustainability.unit}) never
        affect the recovery recommendation. {sustainability.data_quality_note}
      </p>

      {available.length === 0 ? (
        <p className="section-caption">
          No emissions estimates are available for this exception&apos;s
          recovery options.
        </p>
      ) : (
        <details className="subsection-details sustainability-details">
          <summary className="subsection-summary">
            Emissions estimates ({available.length}{" "}
            {available.length === 1 ? "option" : "options"}) &amp; methodology
          </summary>

          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Option</th>
                  <th>Mode</th>
                  <th>Estimated CO₂e (kg)</th>
                  <th>vs Recommended</th>
                </tr>
              </thead>
              <tbody>
                {available.map((estimate) => {
                  const tradeOff = sustainability.trade_offs.find(
                    (candidate) => candidate.option_id === estimate.option_id,
                  );

                  return (
                    <tr key={estimate.option_id ?? estimate.transport_mode}>
                      <td>{estimate.option_id ?? "—"}</td>
                      <td>{estimate.transport_mode}</td>
                      <td>{estimate.estimated_co2e_kg}</td>
                      <td>
                        {tradeOff ? tradeOff.relative_to_recommendation : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <p className="section-caption sustainability-methodology">
            Methodology: {sustainability.methodology}
          </p>
        </details>
      )}
    </section>
  );
}
