/**
 * API-client unit tests: every fetch failure mode maps to one
 * of the four deliberate result states, and the boundary
 * rules (single base URL, no URL building in components)
 * hold.
 */

import { afterEach, beforeAll, afterAll, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import {
  createApiServer,
  inboxPath,
  makeInboxRow,
  makeSummary,
  summaryPath,
} from "./helpers/api-mocks";
import {
  getControlTowerSummary,
  getExceptionInbox,
} from "@/lib/api/client";

const server = createApiServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("getControlTowerSummary", () => {
  it("returns the data state with the parsed summary", async () => {

    const result = await getControlTowerSummary();

    expect(result.kind).toBe("data");

    if (result.kind === "data") {
      expect(result.data.open_exceptions).toBe(2256);
      expect(result.data.follow_up_queue).toEqual([]);
    }
  });

  it("returns the empty state on 404", async () => {
    server.use(
      http.get(summaryPath, () =>
        HttpResponse.json({ detail: "not found" }, { status: 404 }),
      ),
    );

    const result = await getControlTowerSummary();

    expect(result.kind).toBe("empty");
  });

  it("returns the unavailable state when the server is unreachable", async () => {
    // Stop intercepting so fetch truly fails to connect.
    server.close();

    try {
      const result = await getControlTowerSummary();

      expect(result.kind).toBe("unavailable");

      if (result.kind === "unavailable") {
        expect(result.message).toMatch(/unreachable/i);
      }
    } finally {
      server.listen({ onUnhandledRequest: "bypass" });
    }
  });

  it("returns the unavailable state on an HTTP error", async () => {
    server.use(
      http.get(summaryPath, () =>
        HttpResponse.json({ detail: "boom" }, { status: 503 }),
      ),
    );

    const result = await getControlTowerSummary();

    expect(result.kind).toBe("unavailable");

    if (result.kind === "unavailable") {
      expect(result.message).toContain("503");
    }
  });

  it("returns the unexpected state when the summary contract is violated", async () => {
    server.use(
      http.get(summaryPath, () =>
        HttpResponse.json({ open_exceptions: "not-a-number" }),
      ),
    );

    const result = await getControlTowerSummary();

    expect(result.kind).toBe("unexpected");
  });
});

describe("getExceptionInbox", () => {
  it("returns the data state with typed rows", async () => {

    const result = await getExceptionInbox();

    expect(result.kind).toBe("data");

    if (result.kind === "data") {
      expect(result.data[0].exception_id).toBe("EXC-001529");
    }
  });

  it("returns the empty state for an empty queue", async () => {
    server.use(http.get(inboxPath, () => HttpResponse.json([])));

    const result = await getExceptionInbox();

    expect(result.kind).toBe("empty");
  });

  it("returns the unexpected state when a row is not an object", async () => {
    server.use(
      http.get(inboxPath, () => HttpResponse.json(["nope"])),
    );

    const result = await getExceptionInbox();

    expect(result.kind).toBe("unexpected");
  });

  it("returns the unexpected state when a row misses contract fields", async () => {
    server.use(
      http.get(inboxPath, () =>
        HttpResponse.json([
          { exception_id: "EXC-1", severity: "High" }, // missing required fields
        ]),
      ),
    );

    const result = await getExceptionInbox();

    expect(result.kind).toBe("unexpected");
  });
});

describe("boundary rules", () => {
  it("calls the /v1 paths on the configured base URL exactly", async () => {
    const seen: string[] = [];

    server.events.on("request:start", ({ request }) => {
      seen.push(new URL(request.url).pathname);
    });

    await getControlTowerSummary();
    await getExceptionInbox();

    expect(seen).toEqual([
      "/v1/control-tower/summary",
      "/v1/exceptions/inbox",
    ]);
  });

  it("sends JSON negotiation and no credential when none is configured", async () => {
    let headers: Record<string, string> = {};

    server.use(
      http.get(summaryPath, ({ request }) => {
        headers = Object.fromEntries(request.headers.entries());
        return HttpResponse.json(makeSummary());
      }),
    );

    await getControlTowerSummary();

    expect(headers["accept"]).toBe("application/json");
    expect(headers["x-api-key"]).toBeUndefined();
  });

  it("presents the configured server-side machine credential", async () => {
    // The /v1 boundary is API-key protected (ADR-008/011). The
    // Next server is a trusted server-side consumer and presents
    // the machine credential from its own environment — never a
    // browser-visible variable.
    vi.resetModules();
    vi.stubEnv("API_KEY", "test-machine-key");

    try {
      const { getControlTowerSummary: keyedSummary } = await import(
        "@/lib/api/client"
      );
      let seen: string | undefined;

      server.use(
        http.get(summaryPath, ({ request }) => {
          seen = request.headers.get("x-api-key") ?? undefined;
          return HttpResponse.json(makeSummary());
        }),
      );

      await keyedSummary();

      expect(seen).toBe("test-machine-key");
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("matches the representative payloads to the typed contract", () => {
    // A structural sanity net: the test helpers' payloads are
    // the contracts the components rely on.
    const row = makeInboxRow();
    const summary = makeSummary();

    expect(Object.keys(row).sort()).toEqual(
      [
        "exception_id",
        "shipment_id",
        "exception_type",
        "severity",
        "estimated_impact",
        "resolution_status",
        "transport_mode",
        "current_location",
        "estimated_arrival",
        "priority",
        "required_delivery_date",
        "feasible_option_count",
        "executed_still_open",
      ].sort(),
    );

    expect(Object.keys(summary).sort()).toEqual(
      [
        "open_exceptions",
        "actionable_exceptions",
        "monitoring_exceptions",
        "pending_approvals",
        "awaiting_execution",
        "critical_exceptions",
        "follow_up_required",
        "follow_up_queue",
        "recently_resolved",
      ].sort(),
    );
  });
});
