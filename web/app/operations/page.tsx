/**
 * Operations — reserved for the pipeline controls
 * (refresh / simulated arrival) arriving in a later
 * checkpoint against POST /v1/operations/*.
 */

export default function OperationsPage() {
  return (
    <>
      <h1 className="page-title">Operations</h1>
      <p className="page-intro">
        Operational pipeline controls will be introduced here in a later
        checkpoint: refreshing detection, option generation and action
        evaluation, plus the controlled arrival simulation.
      </p>
    </>
  );
}
