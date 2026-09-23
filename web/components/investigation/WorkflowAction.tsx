"use client";

/**
 * Workflow Action: the human-controlled operational step.
 *
 * The first intentional client component in the workspace:
 * mutations must be interactive, so this section hydrates —
 * while every other section remains a Server Component. The
 * server actions it posts to run on the Node server, so the
 * API origin and the machine credential still never reach
 * the browser.
 *
 * The backend workflow engine remains the authority. UI
 * gating (which controls render for which persisted state)
 * is UX only: if a stale view attempts an invalid action,
 * the engine's 409 message is rendered verbatim rather than
 * re-interpreted or bypassed.
 */

import { useActionState, useState, useTransition } from "react";
import type {
  InvestigationState,
  ManualInterventionRecord,
  WorkflowOutcome,
} from "@/lib/types/api";
import { INTERVENTION_TYPES, MANUAL_OUTCOMES } from "@/lib/types/api";
import {
  approveWorkflowAction,
  executeWorkflowAction,
  rejectWorkflowAction,
  resolveManuallyWorkflowAction,
} from "@/lib/actions/workflow";
import type { WorkflowActionResult } from "@/lib/actions/workflow";
import { StateChip } from "@/components/StateChip";

const NEXT_STEP_BY_STATE: Record<string, string> = {
  "Decision required":
    "Review the recommendation and record the approval or rejection decision.",
  "Awaiting execution":
    "The approved recovery action is waiting to be executed by operations.",
  // The classifier's literal strings (em dash included) — the
  // map keys must match the persisted state names exactly.
  "Executed — still open":
    "The recovery action was executed; the exception remains open and requires follow-up.",
  "No system recovery available":
    "No system recovery exists — resolution requires human intervention outside the system.",
  Resolved: "The exception is resolved; no further action is required.",
};

/**
 * Workflow states in which each mutation is offered. The
 * names are the classifier's literal persisted states
 * (classify_investigation_state). UX gating only — the
 * engine remains authoritative and any stale-view attempt
 * still meets its 409.
 */
const DECIDE_STATES = new Set(["Decision required"]);
const EXECUTE_STATES = new Set(["Awaiting execution"]);
const MANUAL_RESOLVE_STATES = new Set([
  "No system recovery available",
  "Executed — still open",
]);

type ActionResult = WorkflowActionResult<WorkflowOutcome>;

const RESULT_TONE: Record<string, string> = {
  success: "var(--ok)",
  guard: "var(--warning)",
  validation: "var(--warning)",
  notFound: "var(--critical)",
  unauthenticated: "var(--critical)",
  unavailable: "var(--critical)",
  unexpected: "var(--critical)",
};

/** One shared inline banner for every mutation feedback state. */
function ResultBanner({ result }: { result: ActionResult }) {
  const tone = RESULT_TONE[result.status] ?? "var(--critical)";

  return (
    <p
      className="action-result-banner"
      role="status"
      style={{ color: tone, borderColor: tone }}
    >
      {result.message}
    </p>
  );
}

export function WorkflowAction({
  state,
  interventions,
  exceptionId,
  latestActionId,
}: {
  state: InvestigationState | null;
  interventions: ManualInterventionRecord[];
  exceptionId: string;
  latestActionId: string | null;
}) {
  const nextStep =
    state === null
      ? "The operational state could not be loaded — review the situation and history before acting."
      : NEXT_STEP_BY_STATE[state.state] ??
        "Review the exception state and operational history before acting.";

  const stateName = state?.state ?? null;
  const canDecide = stateName !== null && DECIDE_STATES.has(stateName);
  const canExecute = stateName !== null && EXECUTE_STATES.has(stateName);
  const canManuallyResolve =
    stateName !== null && MANUAL_RESOLVE_STATES.has(stateName);

  const [decisionMode, setDecisionMode] = useState<
    "approve" | "reject" | null
  >(null);
  const [approveResult, approveFormAction, approvePending] = useActionState(
    (prev: ActionResult | null, formData: FormData) =>
      approveWorkflowAction(exceptionId, prev, formData),
    null,
  );
  const [rejectResult, rejectFormAction, rejectPending] = useActionState(
    (prev: ActionResult | null, formData: FormData) =>
      rejectWorkflowAction(exceptionId, prev, formData),
    null,
  );

  const [manualResult, manualFormAction, manualPending] = useActionState(
    (prev: ActionResult | null, formData: FormData) =>
      resolveManuallyWorkflowAction(exceptionId, prev, formData),
    null,
  );

  const [isExecutePending, startExecute] = useTransition();
  const [executeResult, setExecuteResult] = useState<ActionResult | null>(
    null,
  );

  const busy = approvePending || rejectPending || manualPending || isExecutePending;

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

      {/* ---------------- decide: approve / reject ---------------- */}
      {canDecide ? (
        <div className="action-controls">
          {decisionMode === null ? (
            <>
              <button
                type="button"
                className="action-button"
                disabled={busy}
                onClick={() => setDecisionMode("approve")}
              >
                Approve recovery
              </button>
              <button
                type="button"
                className="action-button action-button-secondary"
                disabled={busy}
                onClick={() => setDecisionMode("reject")}
              >
                Reject recovery
              </button>
            </>
          ) : null}

          {decisionMode === "approve" ? (
            <form action={approveFormAction}>
              <label className="action-field">
                <span>Approving as planner</span>
                <input
                  type="text"
                  name="approved_by"
                  placeholder="Planner name"
                  disabled={approvePending}
                />
              </label>
              <div className="action-controls">
                <button type="submit" className="action-button" disabled={approvePending}>
                  {approvePending ? "Recording decision…" : "Confirm approval"}
                </button>
                <button
                  type="button"
                  className="action-button action-button-secondary"
                  disabled={approvePending}
                  onClick={() => setDecisionMode(null)}
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : null}

          {decisionMode === "reject" ? (
            <form action={rejectFormAction}>
              <label className="action-field">
                <span>Rejecting as planner</span>
                <input
                  type="text"
                  name="rejected_by"
                  placeholder="Planner name"
                  disabled={rejectPending}
                />
              </label>
              <div className="action-controls">
                <button type="submit" className="action-button" disabled={rejectPending}>
                  {rejectPending ? "Recording decision…" : "Confirm rejection"}
                </button>
                <button
                  type="button"
                  className="action-button action-button-secondary"
                  disabled={rejectPending}
                  onClick={() => setDecisionMode(null)}
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : null}

          {approveResult !== null ? <ResultBanner result={approveResult} /> : null}
          {rejectResult !== null ? <ResultBanner result={rejectResult} /> : null}
        </div>
      ) : null}

      {/* ---------------- execute ---------------- */}
      {canExecute ? (
        <div className="action-controls">
          <button
            type="button"
            className="action-button"
            disabled={busy || latestActionId === null}
            onClick={() => {
              if (latestActionId === null) {
                return;
              }

              startExecute(async () => {
                const outcome = await executeWorkflowAction(
                  exceptionId,
                  latestActionId,
                );
                setExecuteResult(outcome);
              });
            }}
          >
            {isExecutePending ? "Executing…" : "Execute recovery"}
          </button>
          {executeResult !== null ? <ResultBanner result={executeResult} /> : null}
        </div>
      ) : null}

      {/* ---------------- manual resolution ---------------- */}
      {canManuallyResolve ? (
        <form action={manualFormAction}>
          <div className="action-field-grid">
            <label className="action-field">
              <span>Intervention type</span>
              <select
                name="intervention_type"
                defaultValue=""
                disabled={manualPending}
              >
                <option value="" disabled>
                  Select…
                </option>
                {INTERVENTION_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>
            <label className="action-field">
              <span>Outcome</span>
              <select name="outcome" defaultValue="" disabled={manualPending}>
                <option value="" disabled>
                  Select…
                </option>
                {MANUAL_OUTCOMES.map((outcome) => (
                  <option key={outcome} value={outcome}>
                    {outcome}
                  </option>
                ))}
              </select>
            </label>
            <label className="action-field">
              <span>External party</span>
              <input type="text" name="external_party" disabled={manualPending} />
            </label>
            <label className="action-field">
              <span>Recorded by</span>
              <input type="text" name="recorded_by" disabled={manualPending} />
            </label>
            <label className="action-field">
              <span>New expected delivery (optional)</span>
              <input
                type="date"
                name="new_expected_delivery"
                disabled={manualPending}
              />
            </label>
            <label className="action-field">
              <span>Notes (optional)</span>
              <input type="text" name="notes" disabled={manualPending} />
            </label>
          </div>
          <label className="action-field">
            <span>Resolution summary</span>
            <input
              type="text"
              name="resolution_summary"
              disabled={manualPending}
            />
          </label>
          <div className="action-controls">
            <button
              type="submit"
              className="action-button"
              disabled={manualPending}
            >
              {manualPending ? "Recording…" : "Record manual resolution"}
            </button>
          </div>
          {manualResult !== null ? <ResultBanner result={manualResult} /> : null}
        </form>
      ) : null}

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
