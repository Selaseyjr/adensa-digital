/**
 * Recently resolved queue. The resolution path is decided by
 * the backend from persisted evidence (system-executed
 * recovery vs manual intervention); the client renders it
 * verbatim and derives nothing.
 */

import type { ControlTowerRecentlyResolved } from "@/lib/types/api";

export function RecentlyResolvedTable({
  entries,
}: {
  entries: ControlTowerRecentlyResolved[];
}) {
  if (entries.length === 0) {
    return <p className="section-caption">No exceptions resolved yet.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Exception</th>
            <th>Severity</th>
            <th>Issue</th>
            <th>Resolution Path</th>
            <th>Resolved</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.exception_id}>
              <td>{entry.exception_id}</td>
              <td>{entry.severity}</td>
              <td>{entry.exception_type}</td>
              <td>{entry.resolution_path}</td>
              <td>{entry.resolved_at ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
