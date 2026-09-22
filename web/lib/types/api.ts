/**
 * TypeScript contract types for the Adensa Digital /v1 API
 * (ADR-011).
 *
 * These mirror the Pydantic response models in app/api.py —
 * the API contract is the source of truth, so the frontend
 * never invents operational fields. Nullability follows the
 * database schema exactly as the API exposes it.
 *
 * Deliberate decision (documented in web/README.md): these
 * types are maintained by hand rather than generated from the
 * OpenAPI schema. At the current surface size the generation
 * toolchain costs more than it saves; the contract tests in
 * `lib/api/__tests__` verify the hand-written types against
 * the live API shapes.
 */

// ==================================================
// CONTROL TOWER
// ==================================================

/** One entry of the follow-up queue: executed recovery that did not resolve. */
export interface ControlTowerFollowUpEntry {
  exception_id: string;
  severity: string;
  exception_type: string;
  detected_at: string;
  action_id: string | null;
  executed_at: string | null;
  estimated_arrival: string | null;
  required_delivery_date: string;
  actionable: boolean;
  reason: string;
}

/** One recently resolved exception with its evidence-based resolution path. */
export interface ControlTowerRecentlyResolved {
  exception_id: string;
  exception_type: string;
  severity: string;
  resolution_status: string;
  resolved_at: string | null;
  resolution_path: string;
}

/**
 * The control-tower projection. Population semantics are
 * owned by the backend and must not be recomputed here:
 *
 * - `open_exceptions`, `critical_exceptions`, `follow_up_required`,
 *   `pending_approvals`, `awaiting_execution` are FULL-POPULATION
 *   metrics;
 * - `actionable_exceptions` + `monitoring_exceptions` partition
 *   the BOUNDED inbox work-queue surface, not the full population.
 */
export interface ControlTowerSummary {
  open_exceptions: number;
  actionable_exceptions: number;
  monitoring_exceptions: number;
  pending_approvals: number;
  awaiting_execution: number;
  critical_exceptions: number;
  follow_up_required: number;
  follow_up_queue: ControlTowerFollowUpEntry[];
  recently_resolved: ControlTowerRecentlyResolved[];
}

// ==================================================
// EXCEPTION INBOX
// ==================================================

/** One open exception in the bounded operational work queue (actionable first, then newest detected). */
export interface InboxRow {
  exception_id: string;
  shipment_id: string;
  exception_type: string;
  severity: string;
  /** Descriptive operational sentence, e.g. "Estimated delivery delay of 6 day(s)..." — the underlying column is text, not a numeric amount. */
  estimated_impact: string;
  resolution_status: string;
  transport_mode: string;
  current_location: string;
  estimated_arrival: string | null;
  priority: string;
  required_delivery_date: string;
  feasible_option_count: number;
  executed_still_open: number;
}

// ==================================================
// ERROR CONTRACT
// ==================================================

/** FastAPI's error envelope: `{"detail": "..."}`. */
export interface ApiErrorBody {
  detail: string;
}
