/**
 * Workflow Action: the human-controlled operational step,
 * driven entirely by the backend's persisted-evidence state.
 * The client invents no lifecycle states and performs no
 * mutations — workflow mutations arrive in a later
 * checkpoint; this surface states where the exception
 * stands and what the next operational step is.
 */

import type {
  InvestigationState,
  ManualInterventionRecord,
} from "@/lib/types/api";
import { StateChip } from "@/components/StateChip";

const NEXT_STEP_BY_STATE: Record<string, string> = {
  "Decision required":
    "Review the recommendation and record the approval or rejection decision.",
  "Awaiting execution":
    "The approved recovery action is waiting to be executed by operations.",
  "Executed, still open":
    "The recovery action was executed; the exception remains open and requires follow-up.",
  "Follow-up required":
    "Operational follow-up is outstanding on this exception.",
  "No feasible recovery":
    "No system recovery exists — resolution requires human intervention outside the system.",
  Resolved: "The exception is resolved; no further action is required.",
};

export function WorkflowAction({
  state,
  interventions,
}: {
  state: InvestigationState | null;
  interventions: ManualInterventionRecord[];
}) {
  const nextStep =
    state === null
      ? "The operational state could not be loaded — review the situation and history before acting."
      : NEXT_STEP_BY_STATE[state.state] ??
        "Review the exception state and operational history before acting.";

  return (
    <section className="section" aria-label="Workflow action">
      <h3 className="section-title">Workflow Action</h3>

      {state !== null ? (
        <>
          <p className="workflow-state-line">
            Current state: <StateChip state={state.state} />
          </p>
          <p className="section-caption">{state.reason}</p>
        </>
      ) : (
        <p className="section-caption">
          The operational state could not be loaded for this exception.
        </p>
      )}
      <p className="workflow-next-step">{nextStep}</p>

      {interventions.length > 0 ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Intervention</th>
                <th>External party</th>
                <th>Outcome</th>
                <th>Recorded</th>
                <th>By</th>
              </tr>
            </thead>
            <tbody>
              {interventions.map((intervention) => (
                <tr key={intervention.intervention_id}>
                  <td>{intervention.intervention_type}</td>
                  <td>{intervention.external_party}</td>
                  <td>{intervention.outcome}</td>
                  <td>{intervention.recorded_at}</td>
                  <td>{intervention.recorded_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
