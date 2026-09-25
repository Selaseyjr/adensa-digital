/**
 * Control Tower — the first functional product surface.
 *
 * Server Component consuming GET /v1/control-tower/summary
 * through the typed API client. All four deliberate states
 * (loading / unavailable / unexpected / data) are handled
 * here; the client computes no metrics.
 *
 * Loading is rendered via the Suspense boundary below, so
 * the shell paints immediately while operational data is
 * fetched on the server.
 */

import { Suspense } from "react";
import { getAnalyticsOverview, getControlTowerSummary } from "@/lib/api/client";
import {
  EmptyPanel,
  LoadingPanel,
  UnexpectedPanel,
  UnavailablePanel,
} from "@/components/StatePanels";
import { ControlTowerMetrics } from "@/components/control-tower/ControlTowerMetrics";
import { QueueCompositionBand } from "@/components/control-tower/QueueCompositionBand";
import { FollowUpTable } from "@/components/control-tower/FollowUpTable";
import { RecentlyResolvedTable } from "@/components/control-tower/RecentlyResolvedTable";
import { AnalyticsSection } from "@/components/control-tower/AnalyticsSection";

async function ControlTower() {
  const result = await getControlTowerSummary();

  switch (result.kind) {
    case "unavailable":
      return <UnavailablePanel message={result.message} />;
    case "unexpected":
      return <UnexpectedPanel message={result.message} />;
    case "empty":
      return (
        <EmptyPanel message="No operational data is available yet." />
      );
    case "data":
      return (
        <>
          <ControlTowerMetrics summary={result.data} />
          <section className="section" aria-labelledby="composition-title">
            <h2 id="composition-title" className="section-title">
              Queue Composition
            </h2>
            <p className="section-caption">
              Proportions of the counts above, at the current snapshot —
              the bounded work-queue split and the critical share of the
              open population. No history is implied.
            </p>
            <QueueCompositionBand summary={result.data} />
          </section>
          <AnalyticsOverviewSection />
          <section className="section" aria-labelledby="follow-up-title">
            <h2 id="follow-up-title" className="section-title">
              Follow-up Required
            </h2>
            <p className="section-caption">
              Executed recovery that did not resolve the exception — renewed
              planner attention required.
            </p>
            <FollowUpTable entries={result.data.follow_up_queue} />
          </section>
          <section className="section" aria-labelledby="resolved-title">
            <h2 id="resolved-title" className="section-title">
              Recently Resolved
            </h2>
            <p className="section-caption">
              Resolution paths are established from persisted evidence:
              system-executed recovery or recorded manual intervention.
            </p>
            <RecentlyResolvedTable entries={result.data.recently_resolved} />
          </section>
        </>
      );
  }
}

/**
 * The analytical canvas, fetched independently of the
 * operational snapshot so an analytics fetch failure does not
 * take down the operational position. All four result states
 * are handled deliberately: panels render on data, the honest
 * analytical empty state renders on `empty`, and the shared
 * unavailable/unexpected panels render on failure.
 */
async function AnalyticsOverviewSection() {
  const analytics = await getAnalyticsOverview();
  switch (analytics.kind) {
    case "unavailable":
      return <UnavailablePanel message={analytics.message} />;
    case "unexpected":
      return <UnexpectedPanel message={analytics.message} />;
    case "empty":
      return (
        <section className="section" aria-labelledby="analytics-heading">
          <h2 id="analytics-heading" className="section-title">
            Analytics
          </h2>
          <p className="section-caption">
            No analytical population is recorded yet — shipments and
            exceptions appear here once the database holds them.
          </p>
          <EmptyPanel message="No analytics available yet." />
        </section>
      );
    case "data":
      return <AnalyticsSection overview={analytics.data} />;
  }
}

export default function ControlTowerPage() {
  return (
    <>
      <h1 className="page-title">Control Tower</h1>
      <p className="page-intro">
        The at-a-glance operational position: open exceptions, decisions
        awaiting planners, recoveries awaiting execution, and work requiring
        follow-up. Executed does not necessarily mean resolved.
      </p>
      <Suspense fallback={<LoadingPanel label="control tower" />}>
        <ControlTower />
      </Suspense>
    </>
  );
}
