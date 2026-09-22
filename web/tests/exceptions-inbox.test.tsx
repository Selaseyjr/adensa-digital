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

  it("links each exception for selection with the exception in the URL", () => {
    render(
      <ExceptionInboxTable
        rows={[makeInboxRow()]}
        selectedExceptionId={null}
      />,
    );

    const link = screen.getByRole("link", { name: "EXC-001529" });

    expect(link).toHaveAttribute(
      "href",
      "/exceptions?exception=EXC-001529",
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
