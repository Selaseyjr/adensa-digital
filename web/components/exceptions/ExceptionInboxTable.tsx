/**
 * The exception work-queue table.
 *
 * Columns are the operational fields the API already
 * supplies (Exception, Severity, Issue, Mode, Location,
 * Required, State) and the State verdict repeats the
 * backend's own semantics: Actionable (feasible recovery
 * available) vs No feasible recovery vs Executed, still
 * open. No ordering or classification happens here — rows
 * render in the order the page passes (the API's operational
 * order, or the planner's explicit sort) and the verdict maps
 * 1:1 to `feasible_option_count` / `executed_still_open` as
 * the backend defines them.
 *
 * Narrow-width behavior uses column prioritization (P8.2):
 * each cell carries a `data-priority` tier, and the P8.1
 * responsive foundation hides lower tiers on narrow screens
 * (Mode and Location fold into the primary cell's stacked
 * reference line, so essential operational information and
 * the investigation link always remain accessible).
 */

import Link from "next/link";
import type { InboxRow } from "@/lib/types/api";
import { SeverityChip } from "@/components/SeverityChip";
import { verdictOf } from "./inbox-filters";

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
            <th data-priority="secondary">Mode</th>
            <th data-priority="secondary">Location</th>
            <th data-priority="tertiary">Required</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const verdict = verdictOf(row);
            const isSelected = row.exception_id === selectedExceptionId;

            return (
              <tr
                key={row.exception_id}
                className={isSelected ? "queue-row-selected" : undefined}
              >
                <td>
                  <Link
                    className="queue-link"
                    href={`/exceptions/${encodeURIComponent(
                      row.exception_id,
                    )}`}
                    aria-current={isSelected ? "true" : undefined}
                  >
                    {row.exception_id}
                  </Link>
                  <span className="queue-cell-reference">
                    {row.shipment_id} · {row.transport_mode} ·{" "}
                    {row.current_location}
                  </span>
                </td>
                <td>
                  <SeverityChip severity={row.severity} />
                </td>
                <td>{row.exception_type}</td>
                <td data-priority="secondary">{row.transport_mode}</td>
                <td data-priority="secondary">{row.current_location}</td>
                <td data-priority="tertiary">{row.required_delivery_date}</td>
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
