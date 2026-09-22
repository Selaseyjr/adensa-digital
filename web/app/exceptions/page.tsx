/**
 * Exceptions — the operational work queue.
 *
 * Server Component consuming GET /v1/exceptions/inbox
 * through the typed API client. Selection uses the
 * exception ID in the URL (`?exception=...`), which is the
 * business-appropriate interaction: linkable, shareable and
 * free of the AppTest constraints that shaped the Streamlit
 * inbox. Backend ordering (actionable first, then newest
 * detected) is preserved verbatim — no client-side sorting.
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
import { SelectedExceptionPanel } from "@/components/exceptions/SelectedExceptionPanel";

async function ExceptionInbox({
  selectedExceptionId,
}: {
  selectedExceptionId?: string;
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

      return (
        <>
          <section className="section" aria-label="Exception work queue">
            <ExceptionInboxTable
              rows={result.data}
              selectedExceptionId={selected?.exception_id ?? null}
            />
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
  searchParams: Promise<{ exception?: string }>;
}) {
  const params = await searchParams;

  return (
    <>
      <h1 className="page-title">Exceptions</h1>
      <p className="page-intro">
        The bounded operational work queue, ordered actionable-first by the
        backend: exceptions with feasible recovery ahead of monitored ones,
        newest detected work first.
      </p>
      <Suspense fallback={<LoadingPanel label="exception queue" />}>
        <ExceptionInbox selectedExceptionId={params.exception} />
      </Suspense>
    </>
  );
}
