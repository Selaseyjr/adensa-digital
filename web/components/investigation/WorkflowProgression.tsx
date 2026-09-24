/**
 * Workflow progression: the operational lifecycle position of
 * an investigated exception, derived ONLY from the persisted
 * investigation state — the backend classifier's literal
 * strings, exactly as `NEXT_STEP_BY_STATE` and the workflow
 * gating already consume them. No percentages, no progress
 * metrics, no inferred history: the strip communicates which
 * workflow stage is current, not what happened historically
 * (the Operational History timeline owns that evidence).
 *
 * Two truthful paths exist in the domain:
 *
 *   Detect → Decide → Execute → Resolve
 *   Detect → (manual resolution path) → Resolve
 *
 * The manual path is the backend's own semantic for "No
 * system recovery available" (resolution requires human
 * intervention outside the system) and "Executed — still
 * open" (system recovery did not resolve the exception).
 * Which future stages remain is implied by the state itself;
 * stages are labelled and marked current with
 * `aria-current="step"`. Text remains the accessible
 * statement of position; the strip adds structure, not new
 * claims.
 */

import type { InvestigationState } from "@/lib/types/api";

type StageId = "detect" | "decide" | "execute" | "manual" | "outcome";

interface Stage {
  id: StageId;
  label: string;
}

const COMMON_STAGES: Stage[] = [
  { id: "detect", label: "Detected" },
  { id: "decide", label: "Decision" },
  { id: "execute", label: "Execution" },
  { id: "outcome", label: "Outcome" },
];

const MANUAL_STAGES: Stage[] = [
  { id: "detect", label: "Detected" },
  { id: "manual", label: "Manual resolution" },
  { id: "outcome", label: "Outcome" },
];

/** Stage-position per classifier state: current stage + completed stages. */
const STATE_POSITION: Record<string, { stages: Stage[]; current: StageId; done: StageId[] }> = {
  "Decision required": {
    stages: COMMON_STAGES,
    current: "decide",
    done: ["detect"],
  },
  "Awaiting execution": {
    stages: COMMON_STAGES,
    current: "execute",
    done: ["detect", "decide"],
  },
  "Executed — still open": {
    // The execute→resolve path did not complete; the backend
    // offers the manual path from here.
    stages: MANUAL_STAGES,
    current: "manual",
    done: ["detect"],
  },
  "No system recovery available": {
    stages: MANUAL_STAGES,
    current: "manual",
    done: ["detect"],
  },
  Resolved: {
    stages: COMMON_STAGES,
    current: "outcome",
    done: ["detect", "decide", "execute"],
  },
};

export function WorkflowProgression({
  state,
}: {
  state: InvestigationState;
}) {
  const position = STATE_POSITION[state.state];

  // Unknown state strings render nothing rather than an
  // invented position.
  if (!position) {
    return null;
  }

  return (
    <ol
      className="workflow-progression"
      aria-label="Workflow progression"
    >
      {position.stages.map((stage) => {
        const isCurrent = stage.id === position.current;
        const isDone = position.done.includes(stage.id);

        return (
          <li
            key={stage.id}
            className={`progression-step${isCurrent ? " progression-step-current" : ""}${isDone ? " progression-step-done" : ""}`}
            aria-current={isCurrent ? "step" : undefined}
          >
            <span className="progression-step-label">{stage.label}</span>
            <span className="progression-step-status">
              {isCurrent ? "Current" : isDone ? "Completed" : "Upcoming"}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
