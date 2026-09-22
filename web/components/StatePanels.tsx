/**
 * Deliberate UI states shared by every surface: loading,
 * API-unavailable, unexpected-response and empty. Raw backend
 * errors never reach the user — the client maps every failure
 * to one of these panels.
 */

export function LoadingPanel({ label }: { label: string }) {
  return (
    <div
      className="state-panel"
      role="status"
      aria-live="polite"
      aria-label={`${label} — loading`}
    >
      <div className="skeleton-line" />
      <div className="skeleton-line" />
      <div className="skeleton-line" />
      <p className="state-panel-strong">Loading {label}…</p>
    </div>
  );
}

export function UnavailablePanel({ message }: { message: string }) {
  return (
    <div className="state-panel state-error" role="alert">
      <p className="state-panel-strong">Operational data unavailable</p>
      <p>{message}</p>
    </div>
  );
}

export function UnexpectedPanel({ message }: { message: string }) {
  return (
    <div className="state-panel state-error" role="alert">
      <p className="state-panel-strong">Unexpected API response</p>
      <p>{message}</p>
    </div>
  );
}

export function EmptyPanel({ message }: { message: string }) {
  return (
    <div className="state-panel">
      <p>{message}</p>
    </div>
  );
}
