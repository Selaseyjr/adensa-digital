/**
 * The Investigation Workspace: the operational screen a
 * planner reaches by selecting an exception from the work
 * queue. Hierarchy (W4, carried into the web client):
 *
 *   State → Situation & Impact → Decision Support →
 *   Evidence / Operational History → AI Advisory →
 *   Workflow Action
 *
 * Data fetching follows the P3 architecture: Server
 * Components → this module's data loader → the typed API
 * client → FastAPI /v1 → services → engines → repositories.
 * No component-level fetch, no business logic in the client.
 *
 * Section resilience: only the identity/context failure
 * collapses the workspace; every other section degrades to
 * its own honest failure panel.
 *
 * The AI advisory consumes GET
 * /v1/exceptions/{id}/decision-brief (P4.x): the advisory
 * layer is subordinate to the deterministic recommendation
 * and renders its own honest failure states without
 * affecting the rest of the workspace.
 */

import Link from "next/link";
import {
  getExceptionContext,
  getInvestigationState,
  getRecoveryAssessment,
  getExceptionHistory,
  getSustainabilityAssessment,
  getManualInterventions,
  getDecisionBrief,
} from "@/lib/api/client";
import type { ApiResult } from "@/lib/api/client";
import {
  EmptyPanel,
  UnexpectedPanel,
  UnavailablePanel,
} from "@/components/StatePanels";
import { WorkspaceHeader } from "@/components/investigation/WorkspaceHeader";
import { SituationImpact } from "@/components/investigation/SituationImpact";
import { DecisionSupport } from "@/components/investigation/DecisionSupport";
import { OperationalHistory } from "@/components/investigation/OperationalHistory";
import { SustainabilitySection } from "@/components/investigation/SustainabilitySection";
import { WorkflowAction } from "@/components/investigation/WorkflowAction";
import { AiDecisionBrief } from "@/components/investigation/AiDecisionBrief";

export type WorkspaceData = {
  state: Awaited<ReturnType<typeof getInvestigationState>>;
  context: Awaited<ReturnType<typeof getExceptionContext>>;
  assessment: Awaited<ReturnType<typeof getRecoveryAssessment>>;
  history: Awaited<ReturnType<typeof getExceptionHistory>>;
  sustainability: Awaited<ReturnType<typeof getSustainabilityAssessment>>;
  interventions: Awaited<ReturnType<typeof getManualInterventions>>;
  brief: Awaited<ReturnType<typeof getDecisionBrief>>;
};

export async function loadInvestigationData(
  exceptionId: string,
): Promise<WorkspaceData> {
  return {
    context: await getExceptionContext(exceptionId),
    state: await getInvestigationState(exceptionId),
    assessment: await getRecoveryAssessment(exceptionId),
    history: await getExceptionHistory(exceptionId),
    sustainability: await getSustainabilityAssessment(exceptionId),
    interventions: await getManualInterventions(exceptionId),
    brief: await getDecisionBrief(exceptionId),
  };
}

/** Optional-section fallback: fail the section, not the workspace. */
function OptionalSectionFallback({
  result,
  section,
}: {
  result: ApiResult<unknown>;
  section: string;
}) {
  if (result.kind === "unavailable") {
    return (
      <UnavailablePanel
        message={`${section} is currently unavailable — ${result.message}`}
      />
    );
  }

  return (
    <UnexpectedPanel
      message={`${section} returned an unexpected response — the section is withheld rather than shown incorrectly.`}
    />
  );
}

async function InvestigationWorkspace({
  exceptionId,
}: {
  exceptionId: string;
}) {
  const data = await loadInvestigationData(exceptionId);

  // Primary context: the workspace cannot exist without it.
  if (data.context.kind === "unavailable") {
    return <UnavailablePanel message={data.context.message} />;
  }

  if (data.context.kind === "unexpected") {
    return <UnexpectedPanel message={data.context.message} />;
  }

  if (data.context.kind === "empty") {
    return (
      <EmptyPanel
        message={`Exception ${exceptionId} was not found in the operational records.`}
      />
    );
  }

  const state =
    data.state.kind === "data" ? data.state.data : null;

  return (
    <>
      {state !== null ? (
        <WorkspaceHeader context={data.context.data} state={state} />
      ) : (
        <section
          className="section workspace-header"
          aria-label="Investigation state"
        >
          <div className="workspace-header-main">
            <h2 className="section-title">
              {data.context.data.exception_id} —{" "}
              {data.context.data.exception_type}
            </h2>
            <p className="workspace-header-meta">
              Shipment {data.context.data.shipment_id} · Order{" "}
              {data.context.data.order_id} · {data.context.data.customer_name}
            </p>
          </div>
          <div className="workspace-header-state">
            <span className="chip chip-neutral">State unavailable</span>
          </div>
        </section>
      )}

      <SituationImpact context={data.context.data} />

      {data.assessment.kind === "data" ? (
        <DecisionSupport assessment={data.assessment.data} />
      ) : data.assessment.kind === "empty" ? (
        <section className="section" aria-label="Decision support">
          <h3 className="section-title">Decision Support</h3>
          <p className="section-caption">
            No recovery assessment exists for this exception.
          </p>
        </section>
      ) : (
        <OptionalSectionFallback
          result={data.assessment}
          section="Decision support"
        />
      )}

      {data.history.kind === "data" ? (
        <OperationalHistory entries={data.history.data} />
      ) : data.history.kind === "empty" ? (
        <section className="section" aria-label="Operational history">
          <h3 className="section-title">Operational History</h3>
          <p className="section-caption">
            No operational history is available for this exception.
          </p>
        </section>
      ) : (
        <OptionalSectionFallback
          result={data.history}
          section="Operational history"
        />
      )}

      {data.sustainability.kind === "data" ? (
        <SustainabilitySection sustainability={data.sustainability.data} />
      ) : (
        <OptionalSectionFallback
          result={data.sustainability}
          section="Sustainability impact"
        />
      )}

      {data.brief.kind === "data" ? (
        <AiDecisionBrief brief={data.brief.data} />
      ) : data.brief.kind === "empty" ? (
        <aside className="section ai-advisory" aria-label="AI advisory">
          <h3 className="section-title">AI Advisory</h3>
          <p className="section-caption">
            No advisory brief is available for this exception. The
            deterministic recommendation above remains the authoritative
            decision support.
          </p>
        </aside>
      ) : (
        <OptionalSectionFallback
          result={data.brief}
          section="AI advisory"
        />
      )}

      {data.interventions.kind === "data" || data.interventions.kind === "empty" ? (
        <WorkflowAction
          state={state}
          interventions={
            data.interventions.kind === "data" ? data.interventions.data : []
          }
        />
      ) : (
        <OptionalSectionFallback
          result={data.interventions}
          section="Workflow action"
        />
      )}
    </>
  );
}

export default async function InvestigationPage({
  params,
}: {
  params: Promise<{ exceptionId: string }>;
}) {
  const { exceptionId } = await params;

  return (
    <>
      <nav aria-label="Breadcrumb" className="breadcrumb">
        <Link href="/exceptions">Exceptions</Link>
        <span aria-hidden="true"> / </span>
        <span aria-current="page">{exceptionId}</span>
      </nav>
      <h1 className="page-title">Investigation Workspace</h1>
      <p className="page-intro">
        Situation, decision support, evidence and workflow state for one
        operational exception.
      </p>
      <InvestigationWorkspace exceptionId={exceptionId} />
    </>
  );
}
