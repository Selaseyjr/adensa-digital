/**
 * Exceptions — the operational work queue.
 *
 * Server Component consuming GET /v1/exceptions/inbox
 * through the typed API client. Selection uses the
 * exception ID in the URL (`?exception=...`), which is the
 * business-appropriate interaction: linkable, shareable and
 * free of the AppTest constraints that shaped the Streamlit
 * inbox.
 *
 * Filtering, search and sorting (P8.2) are client-side over
 * the bounded inbox payload and equally URL-driven
 * (`?q=&severity=&verdict=&sort=`): the page parses the query
 * params, the pure helpers in `inbox-filters.ts` narrow and
 * order the rows, and the whole filtered view is a
 * bookmarkable URL. The default presentation remains the
 * backend's operational order verbatim — no client-side sort
 * unless the planner explicitly requests one.
 */

import { Suspense } from "react";
import { getExceptionInbox } from "@/lib/api/client";
import {
  EmptyPanel,
  LoadingPanel,
  UnexpectedPanel,
  UnavailablePanel,
} from "@/components/StatePanels";
import { ExceptionInboxTable } from "@/components/exceptions/ExceptionInboxTable";
import { InboxToolbar } from "@/components/exceptions/InboxToolbar";
import { SelectedExceptionPanel } from "@/components/exceptions/SelectedExceptionPanel";
import {
  filterInboxRows,
  parseInboxFilters,
  severityOptionsIn,
  sortInboxRows,
} from "@/components/exceptions/inbox-filters";

async function ExceptionInbox({
  selectedExceptionId,
  filterState,
}: {
  selectedExceptionId?: string;
  filterState: ReturnType<typeof parseInboxFilters>;
}) {
  const result = await getExceptionInbox();

  switch (result.kind) {
    case "unavailable":
      return <UnavailablePanel message={result.message} />;
    case "unexpected":
      return <UnexpectedPanel message={result.message} />;
    case "empty":
      return (
        <EmptyPanel message="No open exceptions. The operational queue is clear." />
      );
    case "data": {
      const selected =
        result.data.find(
          (row) => row.exception_id === selectedExceptionId,
        ) ?? null;

      const filteredRows = sortInboxRows(
        filterInboxRows(result.data, filterState),
        filterState.sort,
      );

      return (
        <>
          <section className="section" aria-label="Exception work queue">
            <InboxToolbar
              state={filterState}
              severityOptions={severityOptionsIn(result.data)}
              visibleCount={filteredRows.length}
              totalCount={result.data.length}
              selectedExceptionId={selected?.exception_id ?? null}
            />
            {filteredRows.length > 0 ? (
              <ExceptionInboxTable
                rows={filteredRows}
                selectedExceptionId={selected?.exception_id ?? null}
              />
            ) : (
              <div className="state-panel inbox-filtered-empty">
                <p className="state-panel-strong">
                  No exceptions match the active filters.
                </p>
                <p>
                  {result.data.length} queued{" "}
                  {result.data.length === 1 ? "exception" : "exceptions"} fall
                  outside the current search, severity and recovery-state
                  selection.
                </p>
              </div>
            )}
          </section>
          {selected !== null ? (
            <SelectedExceptionPanel exception={selected} />
          ) : (
            <p className="section-caption">
              Select an exception in the queue to focus it.
            </p>
          )}
        </>
      );
    }
  }
}

export default async function ExceptionsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const filterState = parseInboxFilters(params);

  return (
    <>
      <h1 className="page-title">Exceptions</h1>
      <p className="page-intro">
        The bounded operational work queue, ordered actionable-first by the
        backend: exceptions with feasible recovery ahead of monitored ones,
        newest detected work first. Search, filter and sort to shape the
        queue — filtered views are ordinary URLs you can bookmark.
      </p>
      <Suspense fallback={<LoadingPanel label="exception queue" />}>
        <ExceptionInbox
          selectedExceptionId={params.exception as string | undefined}
          filterState={filterState}
        />
      </Suspense>
    </>
  );
}
