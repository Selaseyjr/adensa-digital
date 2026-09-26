/**
 * Operations — the operational pipeline controls (P9.1).
 *
 * Two controls migrated from the legacy Streamlit surface
 * against the existing /v1 endpoints: the simulated shipment
 * arrival and the operational pipeline refresh. The controls
 * are the client island; everything else on this page is
 * static. The page preserves the Streamlit app's canonical
 * lifecycle wording — Detect → Analyze → Recommend → Approve →
 * Execute → Resolve — as the operational frame for both.
 *
 * The server actions invoked from here run on the Node
 * server; the API origin and the machine credential never
 * reach the browser.
 */

import { OperationsControls } from "@/components/operations/OperationsControls";

export default function OperationsPage() {
  return (
    <>
      <h1 className="page-title">Operations</h1>
      <p className="page-intro">
        Controlled operational actions for the supply-chain pipeline:
        recording a simulated shipment arrival and re-running the
        detection pipeline. The lifecycle they feed — Detect → Analyze →
        Recommend → Approve → Execute → Resolve — continues in the
        Exception Inbox and Investigation Workspace.
      </p>
      <OperationsControls />
    </>
  );
}
