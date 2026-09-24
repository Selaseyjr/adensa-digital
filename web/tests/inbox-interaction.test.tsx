/**
 * P8.2 — Exception Inbox interaction tests.
 *
 * Covers the pure filter/search/sort/URL-state helpers and
 * the URL-driven toolbar. All operations stay within the
 * existing bounded `GET /v1/exceptions/inbox` payload: no new
 * backend data, no client-side business rules, no state
 * library. The toolbar navigates through `next/navigation`
 * (mocked per the shell-test pattern) — it never calls fetch.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  buildInboxQueryString,
  DEFAULT_INBOX_FILTERS,
  filterInboxRows,
  inboxHasActiveFilters,
  parseInboxFilters,
  severityOptionsIn,
  sortInboxRows,
} from "@/components/exceptions/inbox-filters";
import { InboxToolbar } from "@/components/exceptions/InboxToolbar";
import { ExceptionInboxTable } from "@/components/exceptions/ExceptionInboxTable";
import { makeInboxRow } from "./helpers/api-mocks";
import type { InboxRow } from "@/lib/types/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

afterEach(() => {
  cleanup();
  pushMock.mockClear();
  window.history.replaceState(null, "", "/exceptions");
});

// ------------------------------------------------------------
// Pure helpers
// ------------------------------------------------------------

function queueRows(): InboxRow[] {
  return [
    makeInboxRow({
      exception_id: "EXC-A",
      severity: "High",
      feasible_option_count: 2,
      executed_still_open: 0,
      required_delivery_date: "2026-09-15",
      estimated_arrival: "2026-09-21",
      current_location: "At sea",
    }),
    makeInboxRow({
      exception_id: "EXC-B",
      severity: "Critical",
      feasible_option_count: 0,
      executed_still_open: 0,
      required_delivery_date: "2026-09-10",
      estimated_arrival: null,
      current_location: "Warehouse Hamburg",
      transport_mode: "Road",
    }),
    makeInboxRow({
      exception_id: "EXC-C",
      severity: "Low",
      feasible_option_count: 0,
      executed_still_open: 1,
      required_delivery_date: "2026-09-20",
      estimated_arrival: "2026-09-18",
      current_location: "Port of Rotterdam",
    }),
  ];
}

describe("inbox filter helpers", () => {
  it("filters by severity using exact payload values", () => {
    const rows = filterInboxRows(queueRows(), {
      q: "",
      severity: "Critical",
      verdict: "all",
    });

    expect(rows.map((row) => row.exception_id)).toEqual(["EXC-B"]);
  });

  it("filters by the documented triage verdict", () => {
    const actionable = filterInboxRows(queueRows(), {
      q: "",
      severity: "all",
      verdict: "actionable",
    });

    expect(actionable.map((row) => row.exception_id)).toEqual(["EXC-A"]);

    const executedOpen = filterInboxRows(queueRows(), {
      q: "",
      severity: "all",
      verdict: "executed-open",
    });

    expect(executedOpen.map((row) => row.exception_id)).toEqual(["EXC-C"]);
  });

  it("searches identifiers and reference fields case-insensitively", () => {
    const byShipment = filterInboxRows(queueRows(), {
      q: "shp-sim-0002",
      severity: "all",
      verdict: "all",
    });

    expect(byShipment).toHaveLength(3); // same shipment id on every fixture row

    const byLocation = filterInboxRows(queueRows(), {
      q: "hamburg",
      severity: "all",
      verdict: "all",
    });

    expect(byLocation.map((row) => row.exception_id)).toEqual(["EXC-B"]);
  });

  it("keeps backend order when only filtering (no implicit sort)", () => {
    const rows = filterInboxRows(queueRows(), {
      q: "",
      severity: "all",
      verdict: "all",
    });

    expect(rows.map((row) => row.exception_id)).toEqual([
      "EXC-A",
      "EXC-B",
      "EXC-C",
    ]);
  });

  it("sorts severity critical-first, stably, without mutating input", () => {
    const rows = queueRows();
    const sorted = sortInboxRows(rows, "severity-desc");

    expect(sorted.map((row) => row.exception_id)).toEqual([
      "EXC-B",
      "EXC-A",
      "EXC-C",
    ]);
    // Backend order preserved in the source array.
    expect(rows.map((row) => row.exception_id)).toEqual([
      "EXC-A",
      "EXC-B",
      "EXC-C",
    ]);
  });

  it("sorts required delivery earliest-first", () => {
    const sorted = sortInboxRows(queueRows(), "required-asc");

    expect(sorted.map((row) => row.required_delivery_date)).toEqual([
      "2026-09-10",
      "2026-09-15",
      "2026-09-20",
    ]);
  });

  it("sorts estimated arrival earliest-first and sinks missing ETAs", () => {
    const sorted = sortInboxRows(queueRows(), "eta-asc");

    expect(sorted.map((row) => row.exception_id)).toEqual([
      "EXC-C",
      "EXC-A",
      "EXC-B",
    ]);
  });

  it("treats the backend sort as a no-op", () => {
    const rows = queueRows();

    expect(sortInboxRows(rows, "backend")).toEqual(rows);
  });
});

describe("inbox URL state", () => {
  it("parses known params and rejects unknown values to defaults", () => {
    const parsed = parseInboxFilters({
      q: "hamburg",
      severity: "Critical",
      verdict: "actionable",
      sort: "severity-desc",
    });

    expect(parsed).toEqual({
      q: "hamburg",
      severity: "Critical",
      verdict: "actionable",
      sort: "severity-desc",
    });

    const hardened = parseInboxFilters({
      verdict: "not-a-verdict",
      sort: "drop-tables",
      severity: "",
    });

    expect(hardened.verdict).toBe("all");
    expect(hardened.sort).toBe("backend");
    expect(hardened.severity).toBe("all");
  });

  it("handles array-valued params by taking the first value", () => {
    const parsed = parseInboxFilters({
      severity: ["Critical", "High"],
    });

    expect(parsed.severity).toBe("Critical");
  });

  it("omits default values from the canonical query string", () => {
    expect(buildInboxQueryString(DEFAULT_INBOX_FILTERS)).toBe("");
    expect(
      buildInboxQueryString({
        q: "",
        severity: "High",
        verdict: "all",
        sort: "backend",
      }),
    ).toBe("?severity=High");
    expect(
      buildInboxQueryString(
        { ...DEFAULT_INBOX_FILTERS, q: "hamburg", sort: "eta-asc" },
        "EXC-000009",
      ),
    ).toBe("?q=hamburg&sort=eta-asc&exception=EXC-000009");
  });

  it("round-trips a state through query string and parser", () => {
    const state = {
      q: "hamburg",
      severity: "Critical",
      verdict: "actionable",
      sort: "required-asc",
    } as const;

    const query = buildInboxQueryString(state).slice(1);
    const params = Object.fromEntries(new URLSearchParams(query));
    const parsed = parseInboxFilters(params);

    expect(parsed).toEqual(state);
  });

  it("reports active filters and drives reset visibility", () => {
    expect(inboxHasActiveFilters(DEFAULT_INBOX_FILTERS)).toBe(false);
    expect(
      inboxHasActiveFilters({ ...DEFAULT_INBOX_FILTERS, q: " x " }),
    ).toBe(true);
  });

  it("derives severity options from the payload, critical-first", () => {
    expect(severityOptionsIn(queueRows())).toEqual([
      "Critical",
      "High",
      "Low",
    ]);
  });
});

// ------------------------------------------------------------
// Toolbar (URL-driven interaction)
// ------------------------------------------------------------

describe("inbox toolbar", () => {
  it("renders labelled search, severity, verdict and sort controls", () => {
    render(
      <InboxToolbar
        state={DEFAULT_INBOX_FILTERS}
        severityOptions={["Critical", "High", "Low"]}
        visibleCount={3}
        totalCount={3}
        selectedExceptionId={null}
      />,
    );

    expect(screen.getByLabelText("Search")).toBeInTheDocument();
    expect(screen.getByLabelText("Severity")).toBeInTheDocument();
    expect(screen.getByLabelText("Recovery state")).toBeInTheDocument();
    expect(screen.getByLabelText("Sort")).toBeInTheDocument();
    expect(
      screen.getByRole("search", { name: "Filter the exception work queue" }),
    ).toBeInTheDocument();
  });

  it("navigates with the active filters plus preserved selection on submit", async () => {
    const user = userEvent.setup();
    window.history.replaceState(
      null,
      "",
      "/exceptions?exception=EXC-001529",
    );

    render(
      <InboxToolbar
        state={DEFAULT_INBOX_FILTERS}
        severityOptions={["Critical"]}
        visibleCount={1}
        totalCount={1}
        selectedExceptionId="EXC-001529"
      />,
    );

    await user.type(screen.getByLabelText("Search"), "hamburg{Enter}");

    expect(pushMock).toHaveBeenCalledTimes(1);
    expect(pushMock).toHaveBeenCalledWith(
      "/exceptions?q=hamburg&exception=EXC-001529",
    );
  });

  it("submits on select change and carries the chosen value in the URL", async () => {
    const user = userEvent.setup();

    render(
      <InboxToolbar
        state={DEFAULT_INBOX_FILTERS}
        severityOptions={["Critical", "High"]}
        visibleCount={2}
        totalCount={2}
        selectedExceptionId={null}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Severity"), "Critical");

    expect(pushMock).toHaveBeenCalledWith("/exceptions?severity=Critical");
  });

  it("pushes the bare route when filters return to defaults", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/exceptions?severity=High");

    render(
      <InboxToolbar
        state={{ q: "", severity: "High", verdict: "all", sort: "backend" }}
        severityOptions={["High"]}
        visibleCount={1}
        totalCount={1}
        selectedExceptionId={null}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Severity"), "all");

    expect(pushMock).toHaveBeenCalledWith("/exceptions");
  });

  it("shows the reset control only when filters are active", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/exceptions?severity=High");

    render(
      <InboxToolbar
        state={{ q: "", severity: "High", verdict: "all", sort: "backend" }}
        severityOptions={["High"]}
        visibleCount={1}
        totalCount={1}
        selectedExceptionId={null}
      />,
    );

    const reset = screen.getByRole("button", { name: "Reset filters" });
    await user.click(reset);

    expect(pushMock).toHaveBeenCalledWith("/exceptions");
  });

  it("announces filtered result counts as a polite status region", () => {
    render(
      <InboxToolbar
        state={{ ...DEFAULT_INBOX_FILTERS, severity: "Critical" }}
        severityOptions={["Critical"]}
        visibleCount={1}
        totalCount={3}
        selectedExceptionId={null}
      />,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status.textContent).toContain("Showing 1 of 3");
    expect(status.textContent).toContain("severity Critical");
  });

  it("keeps the plain count when no filter is active", () => {
    render(
      <InboxToolbar
        state={DEFAULT_INBOX_FILTERS}
        severityOptions={[]}
        visibleCount={7}
        totalCount={7}
        selectedExceptionId={null}
      />,
    );

    expect(screen.getByRole("status").textContent).toBe(
      "7 queued exceptions",
    );
  });
});

// ------------------------------------------------------------
// Table: selected-row accessibility + prioritized columns
// ------------------------------------------------------------

describe("inbox table prioritization", () => {
  it("marks priority-tier cells with data-priority attributes", () => {
    render(
      <ExceptionInboxTable rows={[makeInboxRow()]} selectedExceptionId={null} />,
    );

    const table = screen.getByRole("table");
    expect(table.querySelector('th[data-priority="secondary"]')).toBeTruthy();
    expect(
      table.querySelector('td[data-priority="secondary"]'),
    ).toBeTruthy();
    expect(
      table.querySelector('td[data-priority="tertiary"]'),
    ).toBeTruthy();
  });

  it("stacks the shipment/mode/location reference in the primary cell", () => {
    render(
      <ExceptionInboxTable rows={[makeInboxRow()]} selectedExceptionId={null} />,
    );

    const primaryCell = screen
      .getByRole("link", { name: "EXC-001529" })
      .closest("td")!;
    const reference = within(primaryCell).getByText(
      "SHP-SIM-0002 · Sea · At sea",
    );

    expect(reference).toHaveClass("queue-cell-reference");
  });

  it("preserves aria-current selected-row semantics alongside the P8.1 class", () => {
    render(
      <ExceptionInboxTable
        rows={[makeInboxRow()]}
        selectedExceptionId="EXC-001529"
      />,
    );

    const row = screen
      .getByRole("link", { name: "EXC-001529" })
      .closest("tr")!;

    expect(
      screen.getByRole("link", { name: "EXC-001529" }),
    ).toHaveAttribute("aria-current", "true");
    expect(row).toHaveClass("queue-row-selected");
  });

  it("keeps the investigation link intact under an active sort", () => {
    const sorted = sortInboxRows(queueRows(), "required-asc");

    render(
      <ExceptionInboxTable rows={sorted} selectedExceptionId={null} />,
    );

    const links = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));

    expect(links).toEqual([
      "/exceptions/EXC-B",
      "/exceptions/EXC-A",
      "/exceptions/EXC-C",
    ]);
  });
});
