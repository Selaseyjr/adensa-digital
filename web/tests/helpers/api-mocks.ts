/**
 * Shared test helpers: representative /v1 payloads matching
 * the P2 contracts and fetch mocks for the endpoints the
 * frontend consumes.
 */

import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type {
  ControlTowerSummary,
  DecisionBrief,
  ExceptionContext,
  HistoryEntry,
  InboxRow,
  InvestigationState,
  ManualInterventionRecord,
  ManualResolutionOutcome,
  RecoveryActionRef,
  RecoveryAssessment,
  ScoredOption,
  SustainabilityComparison,
  WorkflowOutcome,
} from "@/lib/types/api";

export const API_BASE_URL = "http://127.0.0.1:8000";

export const summaryPath = `${API_BASE_URL}/v1/control-tower/summary`;
export const inboxPath = `${API_BASE_URL}/v1/exceptions/inbox`;
export const analyticsPath = `${API_BASE_URL}/v1/analytics/overview`;

export function exceptionApiPath(
  suffix: string,
  exceptionId = "EXC-001529",
): string {
  return `${API_BASE_URL}/v1/exceptions/${encodeURIComponent(exceptionId)}/${suffix}`;
}

export const contextPath = (id?: string) =>
  exceptionApiPath("context", id);
export const statePath = (id?: string) => exceptionApiPath("state", id);

// Workflow mutations: approve/reject/execute live on the legacy
// machine-to-machine compatibility paths (ADR-011) — the exact
// URLs the production client posts to.
export const approveApiPath = (id = "EXC-001529") =>
  `${API_BASE_URL}/exceptions/${encodeURIComponent(id)}/approve`;
export const rejectApiPath = (id = "EXC-001529") =>
  `${API_BASE_URL}/exceptions/${encodeURIComponent(id)}/reject`;
export const executeApiPath = (actionId = "ACT-000001") =>
  `${API_BASE_URL}/recovery-actions/${encodeURIComponent(actionId)}/execute`;
export const manualResolutionApiPath = (id = "EXC-001529") =>
  `${API_BASE_URL}/v1/exceptions/${encodeURIComponent(id)}/manual-resolution`;
export const latestActionApiPath = (id = "EXC-001529") =>
  `${API_BASE_URL}/exceptions/${encodeURIComponent(id)}/actions/latest`;
export const assessmentPath = (id?: string) =>
  exceptionApiPath("assessment", id);
export const historyPath = (id?: string) => exceptionApiPath("history", id);
export const sustainabilityPath = (id?: string) =>
  exceptionApiPath("sustainability", id);
export const interventionsPath = (id?: string) =>
  exceptionApiPath("interventions", id);
export const decisionBriefPath = (id?: string) =>
  exceptionApiPath("decision-brief", id);

export function makeInboxRow(overrides: Partial<InboxRow> = {}): InboxRow {
  return {
    exception_id: "EXC-001529",
    shipment_id: "SHP-SIM-0002",
    exception_type: "Shipment Delay",
    severity: "High",
    estimated_impact:
      "Estimated delivery delay of 21 day(s). Customer delivery commitment at risk.",
    resolution_status: "Open",
    transport_mode: "Sea",
    current_location: "At sea",
    estimated_arrival: "2026-09-21",
    priority: "Medium",
    required_delivery_date: "2026-09-15",
    feasible_option_count: 2,
    executed_still_open: 0,
    ...overrides,
  };
}

export function makeSummary(
  overrides: Partial<ControlTowerSummary> = {},
): ControlTowerSummary {
  return {
    open_exceptions: 2256,
    actionable_exceptions: 3,
    monitoring_exceptions: 2,
    pending_approvals: 12,
    awaiting_execution: 4,
    critical_exceptions: 271,
    follow_up_required: 6,
    follow_up_queue: [],
    recently_resolved: [],
    ...overrides,
  };
}

export function makeContext(
  overrides: Partial<ExceptionContext> = {},
): ExceptionContext {
  return {
    exception_id: "EXC-001529",
    shipment_id: "SHP-SIM-0002",
    order_id: "ORD-0002",
    customer_id: "CUS-0002",
    customer_name: "Meridian Foods",
    exception_type: "Shipment Delay",
    severity: "High",
    status: "Open",
    description:
      "Shipment delayed at origin consolidation point; customer delivery commitment at risk.",
    priority: "Medium",
    origin: "Shanghai",
    destination: "Rotterdam",
    route: "Shanghai → Rotterdam",
    transport_mode: "Sea",
    carrier_id: "CAR-001",
    shipment_status: "In Transit",
    planned_departure: "2026-09-01",
    estimated_arrival: "2026-09-21",
    required_delivery_date: "2026-09-15",
    ...overrides,
  };
}

export function makeInvestigationState(
  overrides: Partial<InvestigationState> = {},
): InvestigationState {
  return {
    state: "Decision required",
    follow_up_required: false,
    reason:
      "A recovery action awaits a planner approve/reject decision.",
    ...overrides,
  };
}

export function makeScoredOption(
  overrides: Partial<ScoredOption> = {},
): ScoredOption {
  return {
    option_id: "OPT-0001",
    transport_mode: "Road",
    carrier_id: "CAR-002",
    estimated_cost: 3200,
    estimated_transit_days: 4,
    risk_score: 0.2,
    cost_score: 0.8,
    transit_score: 0.9,
    risk_component: 0.2,
    priority_score: 0.75,
    cost_contribution: 0.24,
    transit_contribution: 0.27,
    risk_contribution: 0.08,
    priority_contribution: 0.19,
    decision_score: 0.78,
    confidence: "High",
    reason: "Lowest weighted cost with acceptable transit time.",
    ...overrides,
  };
}

export function makeAssessment(
  overrides: Partial<RecoveryAssessment> = {},
): RecoveryAssessment {
  return {
    recommendation: makeScoredOption(),
    alternatives: [
      makeScoredOption({
        option_id: "OPT-0002",
        transport_mode: "Air",
        decision_score: 0.64,
        confidence: "Medium",
      }),
    ],
    evaluated_options: [],
    rationale: {
      weights: { cost: 0.3, transit: 0.3, risk: 0.25, priority: 0.15 },
      factor_breakdown: [
        {
          factor: "cost",
          weight: 0.3,
          values: [
            {
              option_id: "OPT-0001",
              transport_mode: "Road",
              score: 0.8,
              contribution: 0.24,
            },
            {
              option_id: "OPT-0002",
              transport_mode: "Air",
              score: 0.4,
              contribution: 0.12,
            },
          ],
        },
      ],
      trade_offs: [
        {
          option_id: "OPT-0002",
          transport_mode: "Air",
          stronger_factors: ["transit"],
        },
      ],
      confidence_basis:
        "Score separation between the leading options and the field.",
    },
    ...overrides,
  };
}

export function makeHistoryEntry(
  overrides: Partial<HistoryEntry> = {},
): HistoryEntry {
  return {
    timestamp: "2026-09-14 08:32",
    event: "Exception detected",
    detail: "Delay detected against required delivery date.",
    actor: "System",
    sequence: 1,
    ...overrides,
  };
}

export function makeSustainabilityComparison(
  overrides: Partial<SustainabilityComparison> = {},
): SustainabilityComparison {
  return {
    status: "available",
    unit: "kg CO₂e",
    methodology:
      "Distance-based emissions factors applied to shipment weight (prototype factors).",
    data_quality_note:
      "Estimates use prototype emissions factors and are informational only.",
    estimates: [
      {
        transport_mode: "Road",
        option_id: "OPT-0001",
        status: "estimated",
        reason: null,
        shipment_weight_kg: 8000,
        shipment_weight_tonnes: 8,
        distance_km: 12000,
        emissions_factor: 0.08,
        estimated_co2e_kg: 7680,
        unit: "kg CO₂e",
        methodology:
          "Distance-based emissions factors applied to shipment weight (prototype factors).",
        data_quality_note:
          "Estimates use prototype emissions factors and are informational only.",
      },
      {
        transport_mode: "Air",
        option_id: "OPT-0002",
        status: "estimated",
        reason: null,
        shipment_weight_kg: 8000,
        shipment_weight_tonnes: 8,
        distance_km: 8000,
        emissions_factor: 0.6,
        estimated_co2e_kg: 38400,
        unit: "kg CO₂e",
        methodology:
          "Distance-based emissions factors applied to shipment weight (prototype factors).",
        data_quality_note:
          "Estimates use prototype emissions factors and are informational only.",
      },
    ],
    trade_offs: [
      {
        option_id: "OPT-0002",
        transport_mode: "Air",
        estimated_co2e_kg: 38400,
        difference_kg: 30720,
        relative_to_recommendation: "+400%",
      },
    ],
    lowest_emission_option: {
      option_id: "OPT-0001",
      transport_mode: "Road",
      estimated_co2e_kg: 7680,
    },
    ...overrides,
  };
}

export function makeDecisionBrief(
  overrides: Partial<DecisionBrief> = {},
): DecisionBrief {
  return {
    status: "available",
    advisory_label: "AI-assisted · Advisory only",
    situation_summary:
      "Shipment Delay (High severity) on shipment SHP-SIM-0002 for Meridian Foods.",
    recommended_action:
      "Adensa recommends Road via CAR-002 (option OPT-0001): decision score 0.78, confidence High.",
    rationale:
      "Policy weights favour this option (cost 30%, transit 30%, risk 25%, priority 15%): cost fit 80 contributing 0.24.",
    tradeoffs:
      "Air (OPT-0002) scores higher on transit — the recommendation still wins on the weighted overall score.",
    verification_points: [
      "Confirm the revised delivery plan — estimated arrival remains later than required.",
    ],
    disclaimer:
      "AI-assisted summary of Adensa's deterministic assessment. Advisory only: it does not approve, execute, or resolve anything — the planner decides.",
    provider: "adensa-evidence-brief/v1",
    message: null,
    ...overrides,
  };
}

export function makeManualIntervention(
  overrides: Partial<ManualInterventionRecord> = {},
): ManualInterventionRecord {
  return {
    intervention_id: "INT-0001",
    exception_id: "EXC-001529",
    intervention_type: "Carrier escalation",
    external_party: "Ocean carrier ops",
    resolution_summary:
      "Carrier confirmed priority re-handling at the transshipment port.",
    new_expected_delivery: "2026-09-18",
    outcome: "Resolved",
    notes: null,
    recorded_by: "planner",
    recorded_at: "2026-09-14 09:15",
    ...overrides,
  };
}

// --------------------------------------------------
// WORKFLOW MUTATION PAYLOAD FACTORIES
// --------------------------------------------------

export function makeWorkflowOutcome(
  overrides: Partial<WorkflowOutcome> = {},
): WorkflowOutcome {
  return {
    success: true,
    message: "Recovery action ACT-000001 approved successfully.",
    action_id: "ACT-000001",
    shipment_id: "SHP-SIM-0002",
    previous_mode: "Sea",
    new_mode: "Road",
    ...overrides,
  };
}

export function makeManualResolutionOutcome(
  overrides: Partial<ManualResolutionOutcome> = {},
): ManualResolutionOutcome {
  return {
    ...makeWorkflowOutcome({
      // The manual-resolution contract carries null identity
      // fields — no system action is involved (P7.2 live
      // verification surfaced this real backend shape).
      action_id: null,
      shipment_id: null,
      previous_mode: null,
      new_mode: null,
      message: "Manual resolution INT-0001 recorded for EXC-001529.",
    }),
    exception_id: "EXC-001529",
    intervention_id: "INT-0001",
    intervention_type: "Carrier call",
    external_party: "Ocean carrier ops",
    resolution_summary:
      "Carrier confirmed a revised delivery plan after planner coordination.",
    new_expected_delivery: "2026-09-18",
    outcome: "Resolved",
    notes: null,
    recorded_by: "P. Planner",
    recorded_at: "2026-09-21 10:30",
    exception_status: "Resolved",
    ...overrides,
  };
}

/** One service-performance month, echoing the P8.7.1 contract. */
export function makeServicePerformancePoint(
  overrides: Partial<{
    month: string;
    delivered: number;
    on_time: number;
    on_time_rate: number | null;
  }> = {},
): {
  month: string;
  delivered: number;
  on_time: number;
  on_time_rate: number | null;
} {
  return {
    month: "2026-01",
    delivered: 100,
    on_time: 70,
    on_time_rate: 70,
    ...overrides,
  };
}

/** One departure-month incidence point. */
export function makeIncidencePoint(
  overrides: Partial<{
    month: string;
    departing: number;
    exceptions: number;
    incidence_rate: number | null;
  }> = {},
): {
  month: string;
  departing: number;
  exceptions: number;
  incidence_rate: number | null;
} {
  return {
    month: "2026-01",
    departing: 200,
    exceptions: 60,
    incidence_rate: 30,
    ...overrides,
  };
}

/**
 * A full AnalyticsOverview payload matching the P8.7.1
 * backend contract, at real dev-dataset scale where useful so
 * percentage/axis rendering is exercised against truthful
 * values; override any part per test.
 */
export function makeAnalyticsOverview(
  overrides: {
    service_performance?: unknown;
    exception_incidence?: unknown;
  } = {},
): import("@/lib/types/api").AnalyticsOverview {
  return {
    service_performance: {
      basis: "Delivered shipments by planned-arrival month",
      points: [
        makeServicePerformancePoint({
          month: "2026-01",
          delivered: 95,
          on_time: 60,
          on_time_rate: 63.2,
        }),
        makeServicePerformancePoint({
          month: "2026-02",
          delivered: 110,
          on_time: 82,
          on_time_rate: 74.5,
        }),
        makeServicePerformancePoint({
          month: "2026-03",
          delivered: 0,
          on_time: 0,
          on_time_rate: null,
        }),
        makeServicePerformancePoint({
          month: "2026-04",
          delivered: 120,
          on_time: 96,
          on_time_rate: 80,
        }),
      ],
    },
    exception_incidence: {
      basis: "Exceptions by shipment departure month",
      points: [
        makeIncidencePoint({
          month: "2026-01",
          departing: 542,
          exceptions: 167,
          incidence_rate: 30.8,
        }),
        makeIncidencePoint({
          month: "2026-02",
          departing: 488,
          exceptions: 130,
          incidence_rate: 26.6,
        }),
      ],
    },
    shipment_volume: {
      basis: "All shipments by planned-departure month",
      points: [
        { month: "2026-01", shipments: 542 },
        { month: "2026-02", shipments: 488 },
      ],
    },
    transport: {
      basis: "Delivered shipments by transport mode",
      entries: [
        { transport_mode: "Road", delivered: 700, on_time: 520, on_time_rate: 74.3 },
      ],
    },
    carriers: {
      basis: "Delivered shipments by carrier",
      entries: [
        {
          carrier_id: "CAR-001",
          carrier_name: "Meridian Freight",
          delivered: 300,
          on_time: 220,
          on_time_rate: 73.3,
        },
      ],
    },
    warehouses: {
      basis: "Exceptions by origin warehouse",
      entries: [
        { warehouse_id: "WH-01", warehouse_name: "Rotterdam Hub", exceptions: 120 },
      ],
    },
    severity: {
      basis: "Open exceptions by severity (current snapshot)",
      entries: [{ severity: "Critical", exceptions: 271 }],
    },
    ...overrides,
  } as import("@/lib/types/api").AnalyticsOverview;
}

export function makeLatestAction(
  overrides: Partial<RecoveryActionRef> = {},
): RecoveryActionRef {
  return {
    action_id: "ACT-000001",
    option_id: "OPT-0001",
    action_type: "Execute recovery",
    status: "Pending Approval",
    approved_by: null,
    approved_at: null,
    executed_at: null,
    ...overrides,
  };
}

/** Intercept every /v1 endpoint the workspace and queue consume. */
export function createApiServer() {
  return setupServer(
    http.get(summaryPath, () => HttpResponse.json(makeSummary())),
    http.get(inboxPath, () => HttpResponse.json([makeInboxRow()])),
    http.get(contextPath(), () => HttpResponse.json(makeContext())),
    http.get(statePath(), () => HttpResponse.json(makeInvestigationState())),
    http.get(assessmentPath(), () => HttpResponse.json(makeAssessment())),
    http.get(historyPath(), () =>
      HttpResponse.json([makeHistoryEntry()]),
    ),
    http.get(sustainabilityPath(), () =>
      HttpResponse.json(makeSustainabilityComparison()),
    ),
    http.get(interventionsPath(), () =>
      HttpResponse.json([makeManualIntervention()]),
    ),
    http.get(decisionBriefPath(), () =>
      HttpResponse.json(makeDecisionBrief()),
    ),
    http.get(latestActionApiPath(), () =>
      HttpResponse.json(makeLatestAction()),
    ),
    http.post(approveApiPath(), () =>
      HttpResponse.json(
        makeWorkflowOutcome({
          message: "Recovery action ACT-000001 approved successfully.",
        }),
      ),
    ),
    http.post(rejectApiPath(), () =>
      HttpResponse.json(
        makeWorkflowOutcome({
          success: true,
          message: "Recovery action ACT-000001 rejected successfully.",
        }),
      ),
    ),
    http.post(executeApiPath(), () =>
      HttpResponse.json(
        makeWorkflowOutcome({
          success: true,
          message: "Recovery executed successfully for SHP-SIM-0002.",
        }),
      ),
    ),
    http.post(manualResolutionApiPath(), () =>
      HttpResponse.json(makeManualResolutionOutcome()),
    ),
  );
}

export { http, HttpResponse };
