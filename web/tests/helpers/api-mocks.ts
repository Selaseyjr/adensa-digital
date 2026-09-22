/**
 * Shared test helpers: representative /v1 payloads matching
 * the P2 contracts and fetch mocks for the two endpoints the
 * frontend consumes.
 */

import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type { ControlTowerSummary, InboxRow } from "@/lib/types/api";

export const API_BASE_URL = "http://127.0.0.1:8000";

export const summaryPath = `${API_BASE_URL}/v1/control-tower/summary`;
export const inboxPath = `${API_BASE_URL}/v1/exceptions/inbox`;

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

/** Intercept only the two consumed endpoints; anything else fails the test. */
export function createApiServer() {
  return setupServer(
    http.get(summaryPath, () => HttpResponse.json(makeSummary())),
    http.get(inboxPath, () => HttpResponse.json([makeInboxRow()])),
  );
}

export { http, HttpResponse };
