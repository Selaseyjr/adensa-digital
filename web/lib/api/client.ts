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
  InboxRow,
} from "@/lib/types/api";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

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

const CONTROL_TOWER_SUMMARY_PATH = "/v1/control-tower/summary";
const EXCEPTION_INBOX_PATH = "/v1/exceptions/inbox";

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

export type { ApiErrorBody };
