/**
 * The Investigation Workspace header: identity, severity and
 * the persisted-evidence operational state, established
 * before any decision or evidence content.
 */

import type { ExceptionContext, InvestigationState } from "@/lib/types/api";
import { SeverityChip } from "@/components/SeverityChip";
import { StateChip } from "@/components/StateChip";

export function WorkspaceHeader({
  context,
  state,
}: {
  context: ExceptionContext;
  state: InvestigationState;
}) {
  return (
    <section className="section workspace-header" aria-label="Investigation state">
      <div className="workspace-header-main">
        <h2 className="section-title">
          {context.exception_id} — {context.exception_type}
        </h2>
        <p className="workspace-header-meta">
          Shipment {context.shipment_id} · Order {context.order_id} ·{" "}
          {context.customer_name}
        </p>
      </div>
      <div className="workspace-header-state">
        <SeverityChip severity={context.severity} />
        <StateChip state={state.state} />
      </div>
    </section>
  );
}
