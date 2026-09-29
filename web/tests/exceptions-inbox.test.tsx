/**
 * Exception inbox contract tests: the work queue renders the
 * API rows in backend order, selection works through a link
 * with the exception in the URL, and the architectural rule
 * "no client-side business rules" is pinned.
 *
 * The payloads are the typed contract samples verified
 * against the client validators in api-client.test.ts.
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ExceptionInboxTable } from "@/components/exceptions/ExceptionInboxTable";
import { SelectedExceptionPanel } from "@/components/exceptions/SelectedExceptionPanel";
import { makeInboxRow } from "./helpers/api-mocks";

afterEach(() => cleanup());

describe("exception work queue table", () => {
  it("renders the operational columns from the API contract", () => {
    render(<ExceptionInboxTable rows={[makeInboxRow()]} selectedExceptionId={null} />);

    const header = screen.getByText("Exception").closest("thead")!;

    expect(header.textContent).toContain("Severity");
    expect(header.textContent).toContain("Issue");
    expect(header.textContent).toContain("Mode");
    expect(header.textContent).toContain("Location");
    expect(header.textContent).toContain("Required");
    expect(header.textContent).toContain("State");
  });

  it("renders rows in backend order without re-sorting", () => {
    render(
      <ExceptionInboxTable
        rows={[
          makeInboxRow({ exception_id: "EXC-Z", feasible_option_count: 0 }),
          makeInboxRow({ exception_id: "EXC-A", feasible_option_count: 9 }),
        ]}
        selectedExceptionId={null}
      />,
    );

    const rows = screen.getAllByRole("row");

    // Row 0 is the header row. A client-side sort would flip
    // these; the backend order must win verbatim.
    expect(rows[1].textContent).toContain("EXC-Z");
    expect(rows[2].textContent).toContain("EXC-A");
  });

  it("presents the backend triage verdicts, not client-computed ones", () => {
    render(
      <ExceptionInboxTable
        rows={[
          makeInboxRow({ exception_id: "EXC-A", feasible_option_count: 2 }),
          makeInboxRow({
            exception_id: "EXC-B",
            feasible_option_count: 0,
            executed_still_open: 0,
          }),
          makeInboxRow({
            exception_id: "EXC-C",
            feasible_option_count: 0,
            executed_still_open: 1,
          }),
        ]}
        selectedExceptionId={null}
      />,
    );

    expect(screen.getByText("Actionable")).toBeInTheDocument();
    expect(screen.getByText("No feasible recovery")).toBeInTheDocument();
    expect(screen.getByText("Executed, still open")).toBeInTheDocument();
  });

  it("links each exception to its investigation route", () => {
    render(
      <ExceptionInboxTable
        rows={[makeInboxRow()]}
        selectedExceptionId={null}
      />,
    );

    const link = screen.getByRole("link", { name: "EXC-001529" });

    expect(link).toHaveAttribute(
      "href",
      "/exceptions/EXC-001529",
    );
  });

  it("marks the selected row with aria-current", () => {
    render(
      <ExceptionInboxTable
        rows={[makeInboxRow()]}
        selectedExceptionId="EXC-001529"
      />,
    );

    const link = screen.getByRole("link", { name: "EXC-001529" });

    expect(link).toHaveAttribute("aria-current", "true");
  });
});

describe("selected exception panel", () => {
  it("presents the situation fields the inbox contract supplies", () => {
    render(
      <SelectedExceptionPanel exception={makeInboxRow()} />,
    );

    expect(screen.getByText("EXC-001529 — Shipment Delay")).toBeInTheDocument();
    expect(screen.getByText("SHP-SIM-0002")).toBeInTheDocument();
    expect(screen.getByText("Medium")).toBeInTheDocument(); // priority
    expect(screen.getByText("Sea · At sea")).toBeInTheDocument();
    expect(screen.getByText("2026-09-21")).toBeInTheDocument(); // eta
    expect(screen.getByText("2026-09-15")).toBeInTheDocument(); // required
  });
});

describe("inbox architectural rule — no client-side business rules", () => {
  it("exports only the presentation component from the table module", async () => {
    const tableModule = await import(
      "@/components/exceptions/ExceptionInboxTable"
    );

    // Any sort / score / classify helper would have to be
    // exported to be reusable — its absence is the protection.
    expect(Object.keys(tableModule)).toEqual(["ExceptionInboxTable"]);
  });

  it("keeps the triage verdict mapping presentation-only", () => {
    // The verdict strings must match the backend semantics the
    // API documents: feasible_option_count > 0 means
    // Actionable; executed_still_open means executed-but-open;
    // otherwise no feasible recovery.
    render(
      <ExceptionInboxTable
        rows={[makeInboxRow({ feasible_option_count: 1 })]}
        selectedExceptionId={null}
      />,
    );

    expect(screen.getByText("Actionable")).toBeInTheDocument();
  });
});

// ==================================================
// P12.5 — SEVERITY RAILS / SCANABILITY
// ==================================================
// Presentation-only: data-severity carries a display tone
// derived from the row's severity; rails, washes and dots
// are decoration. The severity text/chip remains the
// semantic source; unknown severities must fall back to
// neutral.

describe("inbox severity presentation (P12.5)", () => {
  it("carries a data-severity tone on every row for all four severities", () => {
    render(
      <ExceptionInboxTable
        rows={[
          makeInboxRow({ exception_id: "EXC-C", severity: "Critical" }),
          makeInboxRow({ exception_id: "EXC-H", severity: "High" }),
          makeInboxRow({ exception_id: "EXC-M", severity: "Medium" }),
          makeInboxRow({ exception_id: "EXC-L", severity: "Low" }),
        ]}
        selectedExceptionId={null}
      />,
    );

    const rows = screen.getAllByRole("row");

    expect(rows[1]).toHaveAttribute("data-severity", "critical");
    expect(rows[2]).toHaveAttribute("data-severity", "high");
    expect(rows[3]).toHaveAttribute("data-severity", "medium");
    expect(rows[4]).toHaveAttribute("data-severity", "low");
  });

  it("falls back to the neutral tone for an unknown severity", () => {
    render(
      <ExceptionInboxTable
        rows={[makeInboxRow({ severity: "Cosmic" })]}
        selectedExceptionId={null}
      />,
    );

    const row = screen.getAllByRole("row")[1];

    expect(row).toHaveAttribute("data-severity", "neutral");
    expect(screen.getByText("Cosmic")).toBeInTheDocument();
  });

  it("renders visible dots for every known severity including Medium and Low", () => {
    render(
      <ExceptionInboxTable
        rows={[
          makeInboxRow({ exception_id: "EXC-C", severity: "Critical" }),
          makeInboxRow({ exception_id: "EXC-H", severity: "High" }),
          makeInboxRow({ exception_id: "EXC-M", severity: "Medium" }),
          makeInboxRow({ exception_id: "EXC-L", severity: "Low" }),
        ]}
        selectedExceptionId={null}
      />,
    );

    const dots = document.querySelectorAll(".severity-dot");

    expect(dots).toHaveLength(4);
    expect(
      document.querySelector(".severity-dot-critical"),
    ).not.toBeNull();
    expect(document.querySelector(".severity-dot-high")).not.toBeNull();
    expect(document.querySelector(".severity-dot-medium")).not.toBeNull();
    expect(document.querySelector(".severity-dot-low")).not.toBeNull();
    // Every dot is decorative: the chip text is the semantic carrier.
    for (const dot of dots) {
      expect(dot).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("keeps the selected row authoritative — the accent rail wins", () => {
    render(
      <ExceptionInboxTable
        rows={[makeInboxRow({ severity: "Critical" })]}
        selectedExceptionId="EXC-001529"
      />,
    );

    const row = screen.getAllByRole("row")[1];

    // The row carries both the selection class and the severity
    // tone; CSS resolves the rail in favour of selection. The
    // class contract is pinned here so a styling regression
    // (double rail) cannot ship silently.
    expect(row).toHaveClass("queue-row-selected");
    expect(row).toHaveAttribute("data-severity", "critical");
  });

  it("echoes the severity tone on the selected-exception panel", () => {
    render(
      <SelectedExceptionPanel
        exception={makeInboxRow({ severity: "Critical" })}
      />,
    );

    const panel = screen.getByLabelText("Selected exception");

    expect(panel).toHaveAttribute("data-severity", "critical");
  });

  it("preserves the backend row order with severity attributes present", () => {
    render(
      <ExceptionInboxTable
        rows={[
          makeInboxRow({ exception_id: "EXC-Z", severity: "Low" }),
          makeInboxRow({ exception_id: "EXC-A", severity: "Critical" }),
        ]}
        selectedExceptionId={null}
      />,
    );

    const rows = screen.getAllByRole("row");

    expect(rows[1].textContent).toContain("EXC-Z");
    expect(rows[2].textContent).toContain("EXC-A");
    expect(rows[1]).toHaveAttribute("data-severity", "low");
    expect(rows[2]).toHaveAttribute("data-severity", "critical");
  });
});
