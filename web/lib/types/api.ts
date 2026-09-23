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
// INVESTIGATION WORKSPACE (P4)
// ==================================================

/** The investigation context for one exception (Situation & Impact surface). */
export interface ExceptionContext {
  exception_id: string;
  shipment_id: string;
  order_id: string;
  customer_id: string;
  customer_name: string;
  exception_type: string;
  severity: string;
  status: string;
  description: string;
  priority: string;
  origin: string;
  destination: string;
  route: string;
  transport_mode: string;
  carrier_id: string;
  shipment_status: string;
  planned_departure: string;
  estimated_arrival: string | null;
  required_delivery_date: string;
}

/** The persisted-evidence classification of an investigated exception. */
export interface InvestigationState {
  state: string;
  follow_up_required: boolean;
  reason: string;
}

/** One reconstructed operational-history event (timestamp is null for steps the schema never dates). */
export interface HistoryEntry {
  timestamp: string | null;
  event: string;
  detail: string;
  actor: string;
  sequence: number;
}

/** A scored recovery option exactly as the decision engine produced it. */
export interface ScoredOption {
  option_id: string;
  transport_mode: string;
  carrier_id: string;
  estimated_cost: number;
  estimated_transit_days: number;
  risk_score: number;
  cost_score: number;
  transit_score: number;
  risk_component: number;
  priority_score: number;
  cost_contribution: number;
  transit_contribution: number;
  risk_contribution: number;
  priority_contribution: number;
  decision_score: number;
  confidence: string | null;
  reason: string | null;
}

/** An evaluated recovery option when no feasible recommendation exists. */
export interface EvaluatedOption {
  option_id: string;
  transport_mode: string;
  carrier_id: string;
  estimated_cost: number;
  estimated_transit_days: number;
  risk_score: number;
  feasible: boolean;
}

/** One factor's values across the assessed options. */
export interface FactorValue {
  option_id: string;
  transport_mode: string;
  score: number;
  contribution: number;
}

export interface RationaleFactor {
  factor: string;
  weight: number;
  values: FactorValue[];
}

export interface RationaleTradeOff {
  option_id: string;
  transport_mode: string;
  stronger_factors: string[];
}

/** The decision rationale: policy weights, per-factor breakdown, trade-offs, confidence basis. */
export interface RecommendationRationale {
  weights: Record<string, number>;
  factor_breakdown: RationaleFactor[];
  trade_offs: RationaleTradeOff[];
  confidence_basis: string;
}

/**
 * The recovery assessment. `recommendation: null` with
 * `evaluated_options` populated is the backend's structured
 * "no feasible system recovery" outcome — the presentation
 * reads that distinction, it does not recompute it.
 */
export interface RecoveryAssessment {
  recommendation: ScoredOption | null;
  alternatives: ScoredOption[];
  evaluated_options: EvaluatedOption[];
  rationale: RecommendationRationale | null;
}

/** One option's estimated emissions, or an honest unavailable record. */
export interface SustainabilityEstimate {
  transport_mode: string;
  option_id: string | null;
  status: string;
  reason: string | null;
  shipment_weight_kg: number | null;
  shipment_weight_tonnes: number | null;
  distance_km: number | null;
  emissions_factor: number | null;
  estimated_co2e_kg: number | null;
  unit: string | null;
  methodology: string | null;
  data_quality_note: string | null;
}

export interface SustainabilityTradeOff {
  option_id: string;
  transport_mode: string;
  estimated_co2e_kg: number;
  difference_kg: number;
  relative_to_recommendation: string;
}

export interface LowestEmissionOption {
  option_id: string;
  transport_mode: string;
  estimated_co2e_kg: number;
}

/** Informational emissions comparison; never part of the recommendation. */
export interface SustainabilityComparison {
  status: string;
  unit: string;
  methodology: string;
  data_quality_note: string;
  estimates: SustainabilityEstimate[];
  trade_offs: SustainabilityTradeOff[];
  lowest_emission_option: LowestEmissionOption | null;
}

/** The structured unavailable state when there is nothing to compare. */
export interface SustainabilityUnavailable {
  status: string;
  reason: string;
}

export interface ManualInterventionRecord {
  intervention_id: string;
  exception_id: string;
  intervention_type: string;
  external_party: string;
  resolution_summary: string;
  new_expected_delivery: string | null;
  outcome: string;
  notes: string | null;
  recorded_by: string;
  recorded_at: string;
}

/**
 * The advisory AI decision brief exactly as the ai_support
 * contract produces it — never the operational authority.
 * The available state carries the planner-facing brief; the
 * structured unavailable state carries only `status` and
 * `message`.
 */
export interface DecisionBrief {
  status: string;
  advisory_label: string | null;
  situation_summary: string | null;
  recommended_action: string | null;
  rationale: string | null;
  tradeoffs: string | null;
  verification_points: string[] | null;
  disclaimer: string | null;
  provider: string | null;
  message: string | null;
}

// ==================================================
// ERROR CONTRACT
// ==================================================

/** FastAPI's error envelope: `{"detail": "..."}`. */
export interface ApiErrorBody {
  detail: string;
}
