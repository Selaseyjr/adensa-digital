/**
 * Typed API client for the Adensa Digital /v1 boundary
 * (ADR-011).
 *
 * Architectural rule: React components never call fetch and
 * never embed API URLs — they consume the data functions in
 * this module. The base URL comes exclusively from
 * environment configuration (`API_BASE_URL`, server-side).
 *
 * Deliberate rendering-strategy note (documented in
 * web/README.md): these functions run on the Node server
 * (Server Components), so the browser never sees the API
 * origin and no API key can leak into client code. The API's
 * X-API-Key mechanism is a machine-to-machine contract, not
 * browser authentication, and stays server-side.
 *
 * Every read returns one of four deliberate result states —
 * `data`, `empty`, `unavailable` (API down / unreachable) or
 * `unexpected` (contract violation) — so components render
 * honest states instead of guessing, and no raw backend
 * error ever reaches the UI.
 */

import type {
  ApiErrorBody,
  ControlTowerSummary,
  DecisionBrief,
  ExceptionContext,
  HistoryEntry,
  InboxRow,
  InvestigationState,
  ManualInterventionRecord,
  ManualResolutionOutcome,
  ManualResolutionRequest,
  ApproveRequest,
  RejectRequest,
  RecoveryActionRef,
  RecoveryAssessment,
  SustainabilityComparison,
  SustainabilityUnavailable,
  WorkflowOutcome,
} from "@/lib/types/api";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

// The localhost fallback exists for local development only. A
// production deployment must configure API_BASE_URL explicitly;
// depending on the fallback there is deliberately loud (warned
// once at module load), never silent.
if (process.env.NODE_ENV === "production" && !process.env.API_BASE_URL) {
  console.warn(
    "[adensa] API_BASE_URL is not configured; the API client is " +
      "falling back to http://127.0.0.1:8000. Production deployments " +
      "must set API_BASE_URL to the FastAPI /v1 origin.",
  );
}

/**
 * Server-side machine credential for the /v1 boundary.
 *
 * The /v1 endpoints are protected by the existing X-API-Key
 * mechanism (ADR-008 / ADR-011). The Next server is a trusted
 * server-side consumer — exactly like Power Automate — so it
 * presents the same machine credential from its own
 * environment. This variable is deliberately NOT
 * NEXT_PUBLIC-prefixed: it is read only in Server Components
 * on the Node server and is never shipped to the browser.
 * Browser authentication for human users remains a future
 * checkpoint; this is machine-to-machine configuration.
 */
const API_KEY = process.env.API_KEY;

const REQUEST_HEADERS: HeadersInit = {
  Accept: "application/json",
  ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
};

// The workflow mutations intentionally span the versioned
// boundary and the legacy machine-to-machine compatibility
// paths (ADR-011): approve/reject/execute predate /v1 and are
// consumed exactly as they exist — not re-versioned in P7.
const APPROVE_PATH = "/exceptions/{id}/approve";
const REJECT_PATH = "/exceptions/{id}/reject";
const EXECUTE_PATH = "/recovery-actions/{id}/execute";
const MANUAL_RESOLUTION_PATH = "/v1/exceptions/{id}/manual-resolution";

const EXCEPTION_LATEST_ACTION_PATH = "/exceptions/{id}/actions/latest";
const CONTROL_TOWER_SUMMARY_PATH = "/v1/control-tower/summary";
const EXCEPTION_INBOX_PATH = "/v1/exceptions/inbox";
const EXCEPTION_CONTEXT_PATH = "/v1/exceptions/{id}/context";
const EXCEPTION_STATE_PATH = "/v1/exceptions/{id}/state";
const EXCEPTION_ASSESSMENT_PATH = "/v1/exceptions/{id}/assessment";
const EXCEPTION_HISTORY_PATH = "/v1/exceptions/{id}/history";
const EXCEPTION_SUSTAINABILITY_PATH = "/v1/exceptions/{id}/sustainability";
const EXCEPTION_INTERVENTIONS_PATH = "/v1/exceptions/{id}/interventions";
const EXCEPTION_DECISION_BRIEF_PATH = "/v1/exceptions/{id}/decision-brief";

function exceptionPath(template: string, exceptionId: string): string {
  return template.replace("{id}", encodeURIComponent(exceptionId));
}

export type ApiResult<T> =
  | { kind: "data"; data: T }
  | { kind: "empty" }
  | { kind: "unavailable"; message: string }
  | { kind: "unexpected"; message: string };

/**
 * Perform one GET against the /v1 boundary and normalize
 * every failure mode into the result states above.
 */
async function getFromApi<T>(
  path: string,
  validate: (body: unknown) => T | null,
): Promise<ApiResult<T>> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      // Operational data must never be served stale.
      cache: "no-store",
      headers: REQUEST_HEADERS,
    });
  } catch {
    return {
      kind: "unavailable",
      message:
        "The Adensa API is unreachable. Confirm the API server is running and try again.",
    };
  }

  if (response.status === 404) {
    return { kind: "empty" };
  }

  if (!response.ok) {
    return {
      kind: "unavailable",
      message: `The Adensa API reported an error (HTTP ${response.status}).`,
    };
  }

  let body: unknown;

  try {
    body = await response.json();
  } catch {
    return {
      kind: "unexpected",
      message: "The Adensa API returned a malformed response.",
    };
  }

  const data = validate(body);

  if (data === null) {
    return {
      kind: "unexpected",
      message: "The Adensa API returned an unexpected response shape.",
    };
  }

  return { kind: "data", data };
}

/**
 * Structural validator for a list contract: every element must
 * be a non-null object. Field-level trust stays with the typed
 * contract; this guards the shape boundary where it is cheap.
 */
function validateArray<T>(body: unknown): T[] | null {
  if (!Array.isArray(body)) {
    return null;
  }

  if (!body.every((item) => typeof item === "object" && item !== null)) {
    return null;
  }

  return body as T[];
}

/**
 * Mutation result states: the same honest-failure philosophy
 * as the read results, plus the workflow-specific states —
 * a backend workflow guard (HTTP 409, the engine's own
 * message), validation (HTTP 422), the addressed resource
 * not existing (HTTP 404) and the caller lacking the machine
 * credential (HTTP 401/403).
 */
export type MutationResult<T> =
  | { kind: "success"; data: T }
  | { kind: "guard"; message: string }
  | { kind: "validation"; message: string }
  | { kind: "notFound"; message: string }
  | { kind: "unauthenticated"; message: string }
  | { kind: "unavailable"; message: string }
  | { kind: "unexpected"; message: string };

/** FastAPI 422 bodies carry a `detail` array of field errors, not a string. */
function isValidationErrorBody(body: unknown): boolean {
  return (
    typeof body === "object" &&
    body !== null &&
    Array.isArray((body as { detail?: unknown }).detail)
  );
}

/**
 * Perform one POST against the API boundary and normalize
 * every failure mode into the mutation result states above.
 * Same transport discipline as the reads: server-side
 * credential headers, no caching, no browser exposure.
 */
async function postToApi<T>(
  path: string,
  payload: Record<string, unknown> | null,
  validate: (body: unknown) => T | null,
): Promise<MutationResult<T>> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      // Mutations are never cacheable.
      cache: "no-store",
      method: "POST",
      headers: {
        ...REQUEST_HEADERS,
        ...(payload === null
          ? {}
          : { "Content-Type": "application/json" }),
      },
      ...(payload === null ? {} : { body: JSON.stringify(payload) }),
    });
  } catch {
    return {
      kind: "unavailable",
      message:
        "The Adensa API is unreachable. Confirm the API server is running and try again.",
    };
  }

  if (response.status === 401 || response.status === 403) {
    return {
      kind: "unauthenticated",
      message:
        "The operation was rejected — the server is not configured with a valid API credential.",
    };
  }

  if (response.status === 404) {
    return {
      kind: "notFound",
      message:
        "The addressed exception or recovery action no longer exists — refresh the workspace.",
    };
  }

  if (response.status === 409) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null;

    return {
      kind: "guard",
      message:
        body && typeof body.detail === "string"
          ? body.detail
          : "The workflow rejected this operation in its current state.",
    };
  }

  if (response.status === 422) {
    const body = (await response.json().catch(() => null)) as unknown;

    return {
      kind: "validation",
      message: isValidationErrorBody(body)
        ? "One or more fields were rejected — check the highlighted values."
        : "The operation payload was rejected as invalid.",
    };
  }

  if (!response.ok) {
    return {
      kind: "unavailable",
      message: `The Adensa API reported an error (HTTP ${response.status}).`,
    };
  }

  const body = (await response.json().catch(() => null)) as unknown;

  if (body === null) {
    return {
      kind: "unexpected",
      message: "The Adensa API returned a malformed response.",
    };
  }

  const data = validate(body);

  if (data === null) {
    return {
      kind: "unexpected",
      message: "The Adensa API returned an unexpected response shape.",
    };
  }

  return { kind: "success", data };
}

/**
 * Structural validator for a workflow-mutation outcome: the
 * fields every approve/reject/execute/manual-resolution
 * response carries. `action_id` and `shipment_id` are the
 * backend's nullable identity fields — the manual-resolution
 * outcome legitimately carries null for both, so the
 * validator must accept exactly what the contract declares
 * (`str | None`), not the populated shape of the
 * approve/reject/execute paths.
 */
export function isWorkflowOutcome(body: unknown): WorkflowOutcome | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;
  const isStringOrNull = (value: unknown) =>
    value === null || typeof value === "string";

  return typeof candidate.success === "boolean" &&
    typeof candidate.message === "string" &&
    isStringOrNull(candidate.action_id) &&
    isStringOrNull(candidate.shipment_id) &&
    isStringOrNull(candidate.previous_mode) &&
    isStringOrNull(candidate.new_mode)
    ? (body as WorkflowOutcome)
    : null;
}

function isManualResolutionOutcome(
  body: unknown,
): ManualResolutionOutcome | null {
  const outcome = isWorkflowOutcome(body);

  if (outcome === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;

  return typeof candidate.intervention_id === "string" &&
    typeof candidate.exception_id === "string" &&
    typeof candidate.exception_status === "string" &&
    typeof candidate.recorded_at === "string"
    ? (body as ManualResolutionOutcome)
    : null;
}

function isLatestAction(body: unknown): RecoveryActionRef | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;

  return typeof candidate.action_id === "string" &&
    typeof candidate.status === "string"
    ? (body as RecoveryActionRef)
    : null;
}

export function isControlTowerSummary(body: unknown): ControlTowerSummary | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;

  return typeof candidate.open_exceptions === "number" &&
    typeof candidate.actionable_exceptions === "number" &&
    typeof candidate.monitoring_exceptions === "number" &&
    typeof candidate.pending_approvals === "number" &&
    typeof candidate.awaiting_execution === "number" &&
    typeof candidate.critical_exceptions === "number" &&
    typeof candidate.follow_up_required === "number" &&
    Array.isArray(candidate.follow_up_queue) &&
    Array.isArray(candidate.recently_resolved)
    ? (body as ControlTowerSummary)
    : null;
}

export function isInboxRow(body: unknown): InboxRow | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;

  return typeof candidate.exception_id === "string" &&
    typeof candidate.severity === "string" &&
    typeof candidate.exception_type === "string" &&
    typeof candidate.feasible_option_count === "number" &&
    typeof candidate.executed_still_open === "number"
    ? (body as InboxRow)
    : null;
}

function isInvestigationState(body: unknown): InvestigationState | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;

  return typeof candidate.state === "string" &&
    typeof candidate.follow_up_required === "boolean" &&
    typeof candidate.reason === "string"
    ? (body as InvestigationState)
    : null;
}

function isExceptionContext(body: unknown): ExceptionContext | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;

  const strings = [
    "exception_id",
    "shipment_id",
    "order_id",
    "customer_id",
    "customer_name",
    "exception_type",
    "severity",
    "status",
    "description",
    "priority",
    "origin",
    "destination",
    "route",
    "transport_mode",
    "carrier_id",
    "shipment_status",
    "planned_departure",
    "required_delivery_date",
  ];

  return strings.every((key) => typeof candidate[key] === "string") &&
    (candidate.estimated_arrival === null ||
      typeof candidate.estimated_arrival === "string")
    ? (body as ExceptionContext)
    : null;
}

function isHistoryEntry(body: unknown): HistoryEntry | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;

  return typeof candidate.event === "string" &&
    typeof candidate.detail === "string" &&
    typeof candidate.actor === "string" &&
    typeof candidate.sequence === "number" &&
    (candidate.timestamp === null ||
      typeof candidate.timestamp === "string")
    ? (body as HistoryEntry)
    : null;
}

function isScoredOption(body: unknown): boolean {
  if (typeof body !== "object" || body === null) {
    return false;
  }

  const candidate = body as Record<string, unknown>;

  return (
    [
      "option_id",
      "transport_mode",
      "carrier_id",
      "estimated_cost",
      "estimated_transit_days",
      "risk_score",
      "cost_score",
      "transit_score",
      "risk_component",
      "priority_score",
      "cost_contribution",
      "transit_contribution",
      "risk_contribution",
      "priority_contribution",
      "decision_score",
    ].every((key) =>
      key === "option_id" ||
      key === "transport_mode" ||
      key === "carrier_id"
        ? typeof candidate[key] === "string"
        : typeof candidate[key] === "number",
    ) &&
    (candidate.confidence === null ||
      typeof candidate.confidence === "string") &&
    (candidate.reason === null || typeof candidate.reason === "string")
  );
}

function isRecoveryAssessment(body: unknown): RecoveryAssessment | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;

  if (
    !Array.isArray(candidate.alternatives) ||
    !Array.isArray(candidate.evaluated_options) ||
    !candidate.alternatives.every(isScoredOption)
  ) {
    return null;
  }

  const recommendationOk =
    candidate.recommendation === null ||
    (candidate.recommendation !== null && isScoredOption(candidate.recommendation));

  if (!recommendationOk) {
    return null;
  }

  if (candidate.rationale === null || candidate.rationale === undefined) {
    return { ...(body as RecoveryAssessment), rationale: null };
  }

  const rationale = candidate.rationale as Record<string, unknown>;

  return typeof rationale.confidence_basis === "string" &&
    typeof rationale.weights === "object" &&
    rationale.weights !== null &&
    Array.isArray(rationale.factor_breakdown) &&
    Array.isArray(rationale.trade_offs)
    ? (body as RecoveryAssessment)
    : null;
}

function isSustainabilityPayload(
  body: unknown,
): SustainabilityComparison | SustainabilityUnavailable | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;

  if (typeof candidate.status !== "string") {
    return null;
  }

  // The structured unavailable state: status + reason only.
  if (
    candidate.estimates === undefined &&
    typeof candidate.reason === "string"
  ) {
    return body as SustainabilityUnavailable;
  }

  return Array.isArray(candidate.estimates) &&
    Array.isArray(candidate.trade_offs) &&
    typeof candidate.unit === "string" &&
    typeof candidate.methodology === "string" &&
    typeof candidate.data_quality_note === "string"
    ? (body as SustainabilityComparison)
    : null;
}

function isManualIntervention(
  body: unknown,
): ManualInterventionRecord | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;

  const strings = [
    "intervention_id",
    "exception_id",
    "intervention_type",
    "external_party",
    "resolution_summary",
    "outcome",
    "recorded_by",
    "recorded_at",
  ];

  return strings.every((key) => typeof candidate[key] === "string") &&
    (candidate.new_expected_delivery === null ||
      typeof candidate.new_expected_delivery === "string") &&
    (candidate.notes === null || typeof candidate.notes === "string")
    ? (body as ManualInterventionRecord)
    : null;
}

/** GET /v1/control-tower/summary */
export function getControlTowerSummary(): Promise<ApiResult<ControlTowerSummary>> {
  return getFromApi(CONTROL_TOWER_SUMMARY_PATH, isControlTowerSummary);
}

/** GET /v1/exceptions/inbox */
export function getExceptionInbox(): Promise<ApiResult<InboxRow[]>> {
  return getFromApi(EXCEPTION_INBOX_PATH, (body) => {
    const rows = validateArray<InboxRow>(body);

    if (rows === null || !rows.every((row) => isInboxRow(row) !== null)) {
      return null;
    }

    return rows;
  }).then((result) =>
    // An empty work queue is the deliberate empty state, not a
    // data payload of zero rows — components render the
    // empty-queue panel without inspecting array lengths.
    result.kind === "data" && result.data.length === 0
      ? { kind: "empty" as const }
      : result,
  );
}

/** GET /v1/exceptions/{id}/context — unknown exceptions map to the empty state. */
export function getExceptionContext(
  exceptionId: string,
): Promise<ApiResult<ExceptionContext>> {
  return getFromApi(
    exceptionPath(EXCEPTION_CONTEXT_PATH, exceptionId),
    isExceptionContext,
  );
}

/** GET /v1/exceptions/{id}/state */
export function getInvestigationState(
  exceptionId: string,
): Promise<ApiResult<InvestigationState>> {
  return getFromApi(
    exceptionPath(EXCEPTION_STATE_PATH, exceptionId),
    isInvestigationState,
  );
}

/** GET /v1/exceptions/{id}/assessment */
export function getRecoveryAssessment(
  exceptionId: string,
): Promise<ApiResult<RecoveryAssessment>> {
  return getFromApi(
    exceptionPath(EXCEPTION_ASSESSMENT_PATH, exceptionId),
    isRecoveryAssessment,
  );
}

/** GET /v1/exceptions/{id}/history */
export function getExceptionHistory(
  exceptionId: string,
): Promise<ApiResult<HistoryEntry[]>> {
  return getFromApi(
    exceptionPath(EXCEPTION_HISTORY_PATH, exceptionId),
    (body) => {
      const rows = validateArray<HistoryEntry>(body);

      if (rows === null || !rows.every((row) => isHistoryEntry(row) !== null)) {
        return null;
      }

      return rows;
    },
  );
}

/**
 * GET /v1/exceptions/{id}/sustainability — resolves to the
 * structured `SustainabilityUnavailable` payload when the
 * backend has nothing to compare (HTTP 200 with a 2-field
 * body), so components can render an honest "no comparison
 * available" panel from the data state.
 */
export function getSustainabilityAssessment(
  exceptionId: string,
): Promise<
  ApiResult<SustainabilityComparison | SustainabilityUnavailable>
> {
  return getFromApi(
    exceptionPath(EXCEPTION_SUSTAINABILITY_PATH, exceptionId),
    isSustainabilityPayload,
  );
}

function isDecisionBrief(body: unknown): DecisionBrief | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const candidate = body as Record<string, unknown>;

  if (typeof candidate.status !== "string") {
    return null;
  }

  // The structured unavailable state: status + message only.
  if (
    candidate.situation_summary === undefined &&
    typeof candidate.message === "string"
  ) {
    return body as DecisionBrief;
  }

  const strings = [
    "advisory_label",
    "situation_summary",
    "recommended_action",
    "rationale",
    "tradeoffs",
    "disclaimer",
    "provider",
  ];

  return strings.every((key) => typeof candidate[key] === "string") &&
    Array.isArray(candidate.verification_points) &&
    candidate.verification_points.every(
      (point) => typeof point === "string",
    )
    ? (body as DecisionBrief)
    : null;
}

/**
 * GET /v1/exceptions/{id}/decision-brief — the advisory AI
 * decision brief, or the structured unavailable state when the
 * advisory layer has nothing to present. Advisory only: never
 * the operational authority.
 */
export function getDecisionBrief(
  exceptionId: string,
): Promise<ApiResult<DecisionBrief>> {
  return getFromApi(
    exceptionPath(EXCEPTION_DECISION_BRIEF_PATH, exceptionId),
    isDecisionBrief,
  );
}

/** GET /v1/exceptions/{id}/interventions */
export function getManualInterventions(
  exceptionId: string,
): Promise<ApiResult<ManualInterventionRecord[]>> {
  return getFromApi(
    exceptionPath(EXCEPTION_INTERVENTIONS_PATH, exceptionId),
    (body) => {
      const rows = validateArray<ManualInterventionRecord>(body);

      if (
        rows === null ||
        !rows.every((row) => isManualIntervention(row) !== null)
      ) {
        return null;
      }

      return rows;
    },
  );
}

/**
 * The endpoint returns a literal JSON `null` body when the
 * exception has no action; this sentinel lets the shared
 * GET helper carry that distinction through validation so
 * the caller can map it to the deliberate empty state.
 */
const LATEST_ACTION_NONE = Symbol("latest-action-none");

/**
 * GET /exceptions/{id}/actions/latest — the latest recovery
 * action for an exception (legacy machine-to-machine path,
 * ADR-011 compatibility treatment). Resolves to the empty
 * state when the exception has no action at all.
 */
export function getLatestRecoveryAction(
  exceptionId: string,
): Promise<ApiResult<RecoveryActionRef>> {
  return getFromApi(
    exceptionPath(EXCEPTION_LATEST_ACTION_PATH, exceptionId),
    (body): RecoveryActionRef | null =>
      body === null
        ? (LATEST_ACTION_NONE as unknown as RecoveryActionRef)
        : isLatestAction(body),
  ).then((result) =>
    result.kind === "data" && result.data === (LATEST_ACTION_NONE as unknown)
      ? { kind: "empty" as const }
      : result,
  );
}

/**
 * POST /exceptions/{id}/approve — approve the exception's
 * latest recovery action. The body's only field is the
 * planner identity recorded against the decision.
 */
export function approveRecoveryAction(
  exceptionId: string,
  request: ApproveRequest,
): Promise<MutationResult<WorkflowOutcome>> {
  return postToApi(
    exceptionPath(APPROVE_PATH, exceptionId),
    { approved_by: request.approved_by },
    isWorkflowOutcome,
  );
}

/**
 * POST /exceptions/{id}/reject — reject the exception's
 * latest recovery action. The exception remains open with
 * no system recovery in flight.
 */
export function rejectRecoveryAction(
  exceptionId: string,
  request: RejectRequest,
): Promise<MutationResult<WorkflowOutcome>> {
  return postToApi(
    exceptionPath(REJECT_PATH, exceptionId),
    { rejected_by: request.rejected_by },
    isWorkflowOutcome,
  );
}

/**
 * POST /recovery-actions/{id}/execute — execute an approved
 * recovery action. No request body: the addressed action is
 * the resource.
 */
export function executeRecoveryAction(
  actionId: string,
): Promise<MutationResult<WorkflowOutcome>> {
  return postToApi(
    EXECUTE_PATH.replace("{id}", encodeURIComponent(actionId)),
    null,
    isWorkflowOutcome,
  );
}

/**
 * POST /v1/exceptions/{id}/manual-resolution — record a
 * planner-performed manual resolution for an exception the
 * system could not recover automatically.
 */
export function recordManualResolution(
  exceptionId: string,
  request: ManualResolutionRequest,
): Promise<MutationResult<ManualResolutionOutcome>> {
  return postToApi(
    exceptionPath(MANUAL_RESOLUTION_PATH, exceptionId),
    {
      intervention_type: request.intervention_type,
      external_party: request.external_party,
      resolution_summary: request.resolution_summary,
      recorded_by: request.recorded_by,
      outcome: request.outcome,
      ...(request.new_expected_delivery
        ? { new_expected_delivery: request.new_expected_delivery }
        : {}),
      ...(request.notes ? { notes: request.notes } : {}),
    },
    isManualResolutionOutcome,
  );
}

export type { ApiErrorBody };
