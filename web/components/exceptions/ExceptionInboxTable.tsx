/**
 * The exception work-queue table.
 *
 * Columns are the operational fields the API already
 * supplies (Exception, Severity, Issue, Mode, Location,
 * Required, State) and the State verdict repeats the
 * backend's own semantics: Actionable (feasible recovery
 * available) vs No feasible recovery vs Executed, still
 * open. No ordering or classification happens here — rows
 * render in the API's order and the verdict maps 1:1 to
 * `feasible_option_count` / `executed_still_open` as the
 * backend defines them.
 */

import Link from "next/link";
import type { InboxRow } from "@/lib/types/api";
import { SeverityChip } from "@/components/SeverityChip";

function stateVerdict(row: InboxRow): { label: string; className: string } {
  if (row.executed_still_open) {
    return { label: "Executed, still open", className: "chip-warning" };
  }

  if (row.feasible_option_count > 0) {
    return { label: "Actionable", className: "chip-actionable" };
  }

  return { label: "No feasible recovery", className: "chip-neutral" };
}

export function ExceptionInboxTable({
  rows,
  selectedExceptionId,
}: {
  rows: InboxRow[];
  selectedExceptionId: string | null;
}) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Exception</th>
            <th>Severity</th>
            <th>Issue</th>
            <th>Mode</th>
            <th>Location</th>
            <th>Required</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const verdict = stateVerdict(row);
            const isSelected = row.exception_id === selectedExceptionId;

            return (
              <tr
                key={row.exception_id}
                style={
                  isSelected
                    ? { background: "#eef4fa", outline: "1px solid var(--accent)" }
                    : undefined
                }
              >
                <td>
                  <Link
                    className="queue-link"
                    href={`/exceptions?exception=${encodeURIComponent(
                      row.exception_id,
                    )}`}
                    aria-current={isSelected ? "true" : undefined}
                  >
                    {row.exception_id}
                  </Link>
                </td>
                <td>
                  <SeverityChip severity={row.severity} />
                </td>
                <td>{row.exception_type}</td>
                <td>{row.transport_mode}</td>
                <td>{row.current_location}</td>
                <td>{row.required_delivery_date}</td>
                <td>
                  <span className={`chip ${verdict.className}`}>
                    {verdict.label}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
