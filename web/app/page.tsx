/**
 * Command Centre (v2 — "The Living Supply Chain").
 *
 * The flagship surface, structured as the manager's actual
 * attention sequence:
 *
 *   SEE        the deck (operational position) + Critical Attention
 *   UNDERSTAND the Living Operational Flow + queue composition
 *   ACT        What Needs Attention + Follow-up Required
 *   MONITOR    Analytics + Recently Resolved
 *
 * Data discipline (unchanged from P8.8/P12.2): every number is
 * rendered exactly as the /v1 contract reports it — the client
 * computes no metrics. The three datasets (summary, inbox,
 * analytics) are fetched strictly sequentially inside one
 * streamed section, so the page never holds more than one
 * in-flight request against the API — the local SQLite
 * backend's per-request connection handling is single-thread
 * bound, and the frontend respects that envelope rather than
 * racing it. One failed dependency degrades only its own zone
 * through the shared honest state panels.
 *
 * The bounded inbox is presented through two presentation-only
 * lenses (critical slice, attention queue) without re-ranking
 * the backend's operational order.
 */

import { cache, Suspense } from "react";
import {
  getAnalyticsOverview,
  getControlTowerSummary,
  getExceptionInbox,
} from "@/lib/api/client";
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
import { NetworkStrip } from "@/components/control-tower/NetworkStrip";
import { CriticalAttention } from "@/components/control-tower/CriticalAttention";
import { OperationalFlow } from "@/components/control-tower/OperationalFlow";
import { AttentionQueue } from "@/components/control-tower/AttentionQueue";
import { ManagerLookup } from "@/components/control-tower/ManagerLookup";
import type { ControlTowerSummary, InboxRow } from "@/lib/types/api";

// One request-scoped snapshot per dataset: the deck band and
// every operational section consume the SAME summary fetch,
// the two inbox lenses share the SAME bounded inbox fetch,
// and analytics stays its own dependency so an analytics
// failure cannot take down the operational position.
const getSummary = cache(getControlTowerSummary);
const getInbox = cache(getExceptionInbox);

/** The deck's KPI band. Non-data states render nothing here —
 * the operational sections below carry the honest state panel. */
async function DeckMetrics() {
  const result = await getSummary();
  if (result.kind !== "data") {
    return null;
  }
  return <ControlTowerMetrics summary={result.data} />;
}

/** The critical slice and the manager queue both present the
 * same bounded inbox through different lenses; the empty
 * state renders the calm explicit verdict once each. */
function InboxLenses({
  inbox,
  summary,
}: {
  inbox: InboxRow[] | null;
  summary: ControlTowerSummary | null;
}) {
  if (inbox === null) {
    return (
      <EmptyPanel message="The work queue is clear — no open exceptions right now." />
    );
  }
  return (
    <>
      <CriticalAttention rows={inbox} />
      <AttentionQueue rows={inbox} summary={summary} />
    </>
  );
}

async function AnalyticsZone() {
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

/**
 * The whole operational body, fetched strictly sequentially:
 * summary → inbox → analytics. Sections render in the
 * SEE → UNDERSTAND → ACT → MONITOR order as each dependency
 * resolves; every zone keeps its own honest failure state.
 */
async function CommandCentreSections() {
  const summaryResult = await getSummary();

  if (
    summaryResult.kind === "unavailable" ||
    summaryResult.kind === "unexpected" ||
    summaryResult.kind === "empty"
  ) {
    switch (summaryResult.kind) {
      case "unavailable":
        return <UnavailablePanel message={summaryResult.message} />;
      case "unexpected":
        return <UnexpectedPanel message={summaryResult.message} />;
      case "empty":
        return <EmptyPanel message="No operational data is available yet." />;
    }
  }

  const summary = summaryResult.data;
  const inboxResult = await getInbox();
  const inbox =
    inboxResult.kind === "data"
      ? inboxResult.data
      : null;

  return (
    <>
      {/* SEE — first operational priority. */}
      <InboxLenses inbox={inbox} summary={summary} />

      {/* UNDERSTAND — the loop, then the composition detail. */}
      <section className="section section-flow" aria-labelledby="flow-title">
        <h2 id="flow-title" className="section-title">
          Living Operational Flow
        </h2>
        <p className="section-caption">
          The operational loop at this snapshot — Detect → Recommend → Decide
          → Execute → Resolve. Counts are the summary populations; the system
          continuously processes the network and brings meaningful situations
          to you.
        </p>
        <OperationalFlow summary={summary} />
      </section>

      <section className="section" aria-labelledby="composition-title">
        <h2 id="composition-title" className="section-title">
          Queue Composition
        </h2>
        <p className="section-caption">
          Proportions of the counts above, at the current snapshot —
          the bounded work-queue split and the critical share of the
          open population. No history is implied.
        </p>
        <QueueCompositionBand summary={summary} />
      </section>

      {/* ACT — follow-up work requiring renewed attention. */}
      <section className="section" aria-labelledby="follow-up-title">
        <h2 id="follow-up-title" className="section-title">
          Follow-up Required
        </h2>
        <p className="section-caption">
          Executed recovery that did not resolve the exception — renewed
          planner attention required.
        </p>
        <FollowUpTable entries={summary.follow_up_queue} />
      </section>

      {/* MONITOR — analytics, then the positive resolved zone. */}
      <AnalyticsZone />

      <section className="section" aria-labelledby="resolved-title">
        <h2 id="resolved-title" className="section-title">
          Recently Resolved
        </h2>
        <p className="section-caption">
          Resolution paths are established from persisted evidence:
          system-executed recovery or recorded manual intervention.
          This is the system working as designed — recovery, not just
          alarms.
        </p>
        <RecentlyResolvedTable entries={summary.recently_resolved} />
      </section>
    </>
  );
}

export default function ControlTowerPage() {
  return (
    <>
      {/* SEE — the opening command zone: identity, the living
          network, the manager's question entry point. Static
          content paints with the shell; the KPI band streams
          in on the shared summary snapshot. */}
      <div className="command-deck deck-bleed">
        <div className="command-deck-eyebrow">Adensa Digital · Operations</div>
        <h1 className="command-deck-title">Command Centre</h1>
        <p className="command-deck-context">
          The at-a-glance operational position: open exceptions, decisions
          awaiting planners, recoveries awaiting execution, and work requiring
          follow-up. <strong>Executed does not necessarily mean resolved.</strong>
        </p>
        <NetworkStrip />
        <Suspense fallback={null}>
          <DeckMetrics />
        </Suspense>
        <ManagerLookup />
      </div>

      {/* SEE → UNDERSTAND → ACT → MONITOR — one streamed body,
          strictly sequential fetches (see the component note). */}
      <Suspense fallback={<LoadingPanel label="command centre" />}>
        <CommandCentreSections />
      </Suspense>
    </>
  );
}
