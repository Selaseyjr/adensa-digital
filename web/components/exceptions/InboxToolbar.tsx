/**
 * The exception work-queue toolbar: client-side filtering,
 * search and sorting over the bounded inbox payload, with all
 * state carried in the URL (`?q=&severity=&verdict=&sort=`)
 * alongside the existing `?exception=` selection param.
 *
 * Implementation shape: a plain GET `<form>` targeting the
 * inbox route. Submitting (or changing a select) performs a
 * navigation the App Router renders as a Server-Component
 * refresh — the typed API client remains the only fetch
 * boundary, no mutation semantics are involved, and the
 * filtered view is bookmarkable/shareable by construction.
 * The filter state lives in the URL, not in client state, so
 * there is nothing to desynchronize and no state library.
 *
 * Labels are explicit (`<label htmlFor>`) and the result
 * count is a polite live region so assistive technology can
 * announce the effect of a filter change.
 */

"use client";

import { useRouter } from "next/navigation";
import { useRef } from "react";
import {
  inboxHasActiveFilters,
  WORKFLOW_STATES,
  type InboxFilterState,
  type InboxSortValue,
  type InboxVerdictValue,
} from "./inbox-filters";

const VERDICT_LABELS: Record<InboxVerdictValue, string> = {
  actionable: "Actionable",
  "no-feasible": "No feasible recovery",
  "executed-open": "Executed, still open",
};

const SORT_LABELS: Record<InboxSortValue, string> = {
  backend: "Operational order",
  "severity-desc": "Severity (critical first)",
  "severity-asc": "Severity (lowest first)",
  "required-asc": "Required delivery (earliest)",
  "eta-asc": "Estimated arrival (earliest)",
};

export function InboxToolbar({
  state,
  severityOptions,
  visibleCount,
  totalCount,
  selectedExceptionId,
}: {
  state: InboxFilterState;
  severityOptions: string[];
  visibleCount: number;
  totalCount: number;
  selectedExceptionId: string | null;
}) {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);

  const navigateWith = (mutate: (params: URLSearchParams) => void) => {
    const params = new URLSearchParams(window.location.search);
    mutate(params);
    const query = params.toString();
    router.push(query === "" ? "/exceptions" : `/exceptions?${query}`);
  };

  // Selects submit the form on change; text search submits on
  // Enter or via the Search button.
  const navigateFromForm = () => {
    const form = formRef.current;
    if (form === null) {
      return;
    }
    const data = new FormData(form);
    const params = new URLSearchParams();
    const q = String(data.get("q") ?? "").trim();
    if (q !== "") {
      params.set("q", q);
    }
    if (data.get("severity") !== "all") {
      params.set("severity", String(data.get("severity")));
    }
    if (data.get("verdict") !== "all") {
      params.set("verdict", String(data.get("verdict")));
    }
    if (data.get("workflow_state") !== "all") {
      params.set("workflow_state", String(data.get("workflow_state")));
    }
    if (data.get("sort") !== "backend") {
      params.set("sort", String(data.get("sort")));
    }
    if (selectedExceptionId) {
      params.set("exception", selectedExceptionId);
    }
    const query = params.toString();
    router.push(query === "" ? "/exceptions" : `/exceptions?${query}`);
  };

  const reset = () => {
    navigateWith((params) => {
      params.delete("q");
      params.delete("severity");
      params.delete("verdict");
      params.delete("workflow_state");
      params.delete("sort");
    });
  };

  const active = inboxHasActiveFilters(state);
  const filtered = visibleCount !== totalCount;
  const activeChips: string[] = [];
  if (state.q.trim() !== "") {
    activeChips.push(`search “${state.q.trim()}”`);
  }
  if (state.severity !== "all") {
    activeChips.push(`severity ${state.severity}`);
  }
  if (state.verdict !== "all") {
    activeChips.push(VERDICT_LABELS[state.verdict]);
  }
  if (state.workflow_state !== "all") {
    activeChips.push(`workflow state ${state.workflow_state}`);
  }
  if (state.sort !== "backend") {
    activeChips.push(SORT_LABELS[state.sort]);
  }

  return (
    <div className="inbox-toolbar">
      <form
        ref={formRef}
        className="inbox-toolbar-form"
        role="search"
        aria-label="Filter the exception work queue"
        onSubmit={(event) => {
          event.preventDefault();
          navigateFromForm();
        }}
      >
        <div className="action-field inbox-field-grow">
          <label htmlFor="inbox-q">Search</label>
          <input
            id="inbox-q"
            name="q"
            type="search"
            defaultValue={state.q}
            placeholder="ID, shipment, type, location…"
          />
        </div>

        <div className="action-field">
          <label htmlFor="inbox-severity">Severity</label>
          <select
            id="inbox-severity"
            name="severity"
            defaultValue={state.severity}
            onChange={navigateFromForm}
          >
            <option value="all">All severities</option>
            {severityOptions.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </select>
        </div>

        <div className="action-field">
          <label htmlFor="inbox-verdict">Recovery state</label>
          <select
            id="inbox-verdict"
            name="verdict"
            defaultValue={state.verdict}
            onChange={navigateFromForm}
          >
            <option value="all">All states</option>
            {(Object.keys(VERDICT_LABELS) as InboxVerdictValue[]).map(
              (value) => (
                <option key={value} value={value}>
                  {VERDICT_LABELS[value]}
                </option>
              ),
            )}
          </select>
        </div>

        <div className="action-field">
          <label htmlFor="inbox-workflow-state">Workflow state</label>
          <select
            id="inbox-workflow-state"
            name="workflow_state"
            defaultValue={state.workflow_state}
            onChange={navigateFromForm}
          >
            <option value="all">All workflow states</option>
            {WORKFLOW_STATES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>

        <div className="action-field">
          <label htmlFor="inbox-sort">Sort</label>
          <select
            id="inbox-sort"
            name="sort"
            defaultValue={state.sort}
            onChange={navigateFromForm}
          >
            {(Object.keys(SORT_LABELS) as InboxSortValue[]).map((value) => (
              <option key={value} value={value}>
                {SORT_LABELS[value]}
              </option>
            ))}
          </select>
        </div>

        <div className="inbox-toolbar-actions">
          <button type="submit" className="action-button action-button-secondary">
            Apply
          </button>
          {active ? (
            <button
              type="button"
              className="action-button action-button-secondary"
              onClick={reset}
            >
              Reset filters
            </button>
          ) : null}
        </div>
      </form>

      <p className="inbox-result-count" role="status" aria-live="polite">
        {filtered
          ? `Showing ${visibleCount} of ${totalCount} queued exceptions — ${activeChips.join(", ")}`
          : `${totalCount} queued exceptions`}
      </p>

      {/* Count honesty (P8.8): KPI deep-links arrive from
          full-population metrics, while this queue is bounded
          to 100 rows — the distinction is stated, never left
          for the planner to reconcile. */}
      {state.severity !== "all" || state.workflow_state !== "all" ? (
        <p className="inbox-bounded-note">
          Control Tower counts describe the full open population;
          this bounded queue shows at most 100 rows, so fewer
          matches here does not mean fewer exceptions overall.
        </p>
      ) : null}
    </div>
  );
}
