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
  RecoveryAssessment,
  ScoredOption,
  SustainabilityComparison,
} from "@/lib/types/api";

export const API_BASE_URL = "http://127.0.0.1:8000";

export const summaryPath = `${API_BASE_URL}/v1/control-tower/summary`;
export const inboxPath = `${API_BASE_URL}/v1/exceptions/inbox`;

export function exceptionApiPath(
  suffix: string,
  exceptionId = "EXC-001529",
): string {
  return `${API_BASE_URL}/v1/exceptions/${encodeURIComponent(exceptionId)}/${suffix}`;
}

export const contextPath = (id?: string) =>
  exceptionApiPath("context", id);
export const statePath = (id?: string) => exceptionApiPath("state", id);
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
  );
}

export { http, HttpResponse };
