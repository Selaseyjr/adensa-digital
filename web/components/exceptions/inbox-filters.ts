/**
 * Inbox filter / search / sort — pure functions over the
 * existing bounded inbox payload (`GET /v1/exceptions/inbox`).
 *
 * Architectural position: these helpers shape which rows the
 * work-queue table PRESENTS. They never reorder rows unless
 * the planner explicitly requests a sort (the default remains
 * the backend's operational order verbatim), never touch the
 * API client, and never recompute business semantics — the
 * "verdict" values they filter on are the same documented
 * display mapping (`feasible_option_count` /
 * `executed_still_open`) the table has always rendered, and
 * only the backend decides what those fields mean.
 *
 * All filter state is URL-representable: every value in
 * `InboxFilterState` round-trips through
 * `parseInboxFilters` / `buildInboxQueryString`.
 */

import type { InboxRow } from "@/lib/types/api";

/** The display verdict shared by the table and the state filter. */
export type InboxVerdictValue =
  | "actionable"
  | "no-feasible"
  | "executed-open";

export type InboxSortValue =
  | "backend"
  | "severity-desc"
  | "severity-asc"
  | "required-asc"
  | "eta-asc";

export interface InboxFilterState {
  /** Substring search over identifiers/reference fields in the payload. */
  q: string;
  /** Exact severity match, or "all". */
  severity: string;
  /** Display-verdict filter, or "all". */
  verdict: InboxVerdictValue | "all";
  sort: InboxSortValue;
}

export const DEFAULT_INBOX_FILTERS: InboxFilterState = {
  q: "",
  severity: "all",
  verdict: "all",
  sort: "backend",
};

const VERDICT_VALUES: readonly InboxVerdictValue[] = [
  "actionable",
  "no-feasible",
  "executed-open",
];

const SORT_VALUES: readonly InboxSortValue[] = [
  "backend",
  "severity-desc",
  "severity-asc",
  "required-asc",
  "eta-asc",
];

/**
 * The triage verdict, exactly as the work-queue table renders
 * it. Presentation-only mapping of fields the API supplies.
 */
export function verdictOf(row: InboxRow): {
  value: InboxVerdictValue;
  label: string;
  className: string;
} {
  if (row.executed_still_open) {
    return {
      value: "executed-open",
      label: "Executed, still open",
      className: "chip-warning",
    };
  }

  if (row.feasible_option_count > 0) {
    return {
      value: "actionable",
      label: "Actionable",
      className: "chip-actionable",
    };
  }

  return {
    value: "no-feasible",
    label: "No feasible recovery",
    className: "chip-neutral",
  };
}

/** Search fields: identifiers and reference text the payload carries. */
function searchHaystack(row: InboxRow): string {
  return [
    row.exception_id,
    row.shipment_id,
    row.exception_type,
    row.current_location,
    row.estimated_impact,
    row.transport_mode,
  ]
    .join("\n")
    .toLowerCase();
}

function matchesSearch(row: InboxRow, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (needle === "") {
    return true;
  }
  return searchHaystack(row).includes(needle);
}

function matchesSeverity(row: InboxRow, severity: string): boolean {
  return severity === "all" || row.severity === severity;
}

function matchesVerdict(
  row: InboxRow,
  verdict: InboxFilterState["verdict"],
): boolean {
  return verdict === "all" || verdictOf(row).value === verdict;
}

/** Apply the search/severity/verdict filters. Order is untouched. */
export function filterInboxRows(
  rows: InboxRow[],
  state: Pick<InboxFilterState, "q" | "severity" | "verdict">,
): InboxRow[] {
  return rows.filter(
    (row) =>
      matchesSearch(row, state.q) &&
      matchesSeverity(row, state.severity) &&
      matchesVerdict(row, state.verdict),
  );
}

const SEVERITY_RANK: Record<string, number> = {
  Critical: 0,
  High: 1,
  Medium: 2,
  Low: 3,
};

function severityRank(severity: string): number {
  return SEVERITY_RANK[severity] ?? SEVERITY_RANK.Low + 1;
}

/**
 * Sort rows for presentation. `backend` is a no-op — the API's
 * operational order (actionable first, then newest detected)
 * wins verbatim. All other sorts are stable, so rows with
 * equal keys keep the backend order within the sort.
 */
export function sortInboxRows(rows: InboxRow[], sort: InboxSortValue): InboxRow[] {
  if (sort === "backend") {
    return rows;
  }

  const sorted = [...rows];
  switch (sort) {
    case "severity-desc":
      sorted.sort(
        (a, b) => severityRank(a.severity) - severityRank(b.severity),
      );
      break;
    case "severity-asc":
      sorted.sort(
        (a, b) => severityRank(b.severity) - severityRank(a.severity),
      );
      break;
    case "required-asc":
      // ISO dates order lexicographically; earliest deadline first.
      sorted.sort((a, b) =>
        a.required_delivery_date.localeCompare(b.required_delivery_date),
      );
      break;
    case "eta-asc":
      // Rows without an estimated arrival sink to the end.
      sorted.sort((a, b) =>
        (a.estimated_arrival ?? "9999-12-31").localeCompare(
          b.estimated_arrival ?? "9999-12-31",
        ),
      );
      break;
  }
  return sorted;
}

/** True when any filter deviates from the default (drives Reset visibility). */
export function inboxHasActiveFilters(state: InboxFilterState): boolean {
  return (
    state.q.trim() !== "" ||
    state.severity !== DEFAULT_INBOX_FILTERS.severity ||
    state.verdict !== DEFAULT_INBOX_FILTERS.verdict ||
    state.sort !== DEFAULT_INBOX_FILTERS.sort
  );
}

/**
 * Severity options for the filter select, derived from the
 * payload itself (no invented domain): the values actually
 * present, ordered critical-first by the documented rank.
 */
export function severityOptionsIn(rows: InboxRow[]): string[] {
  const present = new Set(rows.map((row) => row.severity));
  return [...present].sort(
    (a, b) => severityRank(a) - severityRank(b) || a.localeCompare(b),
  );
}

/** Parse URL query params (Next.js searchParams) into filter state. */
export function parseInboxFilters(
  params: Record<string, string | string[] | undefined>,
): InboxFilterState {
  const first = (key: string): string => {
    const value = params[key];
    if (Array.isArray(value)) {
      return value[0] ?? "";
    }
    return value ?? "";
  };

  const q = first("q");
  const severity = first("severity") || "all";
  const rawVerdict = first("verdict");
  const rawSort = first("sort");

  return {
    q,
    severity,
    verdict: (VERDICT_VALUES as readonly string[]).includes(rawVerdict)
      ? (rawVerdict as InboxVerdictValue)
      : "all",
    sort: (SORT_VALUES as readonly string[]).includes(rawSort)
      ? (rawSort as InboxSortValue)
      : "backend",
  };
}

/**
 * Build the canonical query string for a filter state. Default
 * values are omitted so shared URLs stay clean; `exception`
 * (row selection) is preserved when provided.
 */
export function buildInboxQueryString(
  state: InboxFilterState,
  selectedExceptionId?: string | null,
): string {
  const params = new URLSearchParams();
  if (state.q.trim() !== "") {
    params.set("q", state.q.trim());
  }
  if (state.severity !== "all") {
    params.set("severity", state.severity);
  }
  if (state.verdict !== "all") {
    params.set("verdict", state.verdict);
  }
  if (state.sort !== "backend") {
    params.set("sort", state.sort);
  }
  if (selectedExceptionId) {
    params.set("exception", selectedExceptionId);
  }
  const s = params.toString();
  return s === "" ? "" : `?${s}`;
}
