/**
 * Living Operational Flow (Command Centre v2, UNDERSTAND
 * zone): the Detect → Recommend → Decide → Execute → Resolve
 * loop as a five-node stepper whose counts are the real
 * summary populations — the connection between the command
 * centre and Adensa's actual workflow architecture.
 *
 * The mapping is presentation-only and conservative — every
 * value is a field the summary contract already carries:
 *
 *   Detect   open_exceptions        everything currently detected
 *   Recommend actionable_exceptions the bounded queue with feasible recovery
 *   Decide   pending_approvals      decisions awaiting a planner
 *   Execute  awaiting_execution     approved recovery awaiting execution
 *   Resolve  recently_resolved      evidence-backed resolutions (bounded window)
 *
 * No stage is derived, computed, or invented; zero counts
 * render as zero — the honest snapshot. Labels carry the
 * summary's own population semantics in their captions.
 */

import Link from "next/link";
import type { ControlTowerSummary } from "@/lib/types/api";

export function OperationalFlow({ summary }: { summary: ControlTowerSummary }) {
  const stages = [
    {
      key: "detect",
      label: "Detect",
      value: summary.open_exceptions,
      caption: "Open exceptions across the network",
      href: "/exceptions",
    },
    {
      key: "recommend",
      label: "Recommend",
      value: summary.actionable_exceptions,
      caption: "Bounded queue with feasible recovery",
      href: "/exceptions?verdict=actionable",
    },
    {
      key: "decide",
      label: "Decide",
      value: summary.pending_approvals,
      caption: "Decisions awaiting a planner",
      href: "/exceptions?workflow_state=Decision%20required",
    },
    {
      key: "execute",
      label: "Execute",
      value: summary.awaiting_execution,
      caption: "Approved recovery awaiting execution",
      href: "/exceptions?verdict=actionable&workflow_state=Awaiting%20execution",
    },
    {
      key: "resolve",
      label: "Resolve",
      value: summary.recently_resolved.length,
      caption: "Recently resolved, evidence-backed",
      href: "#monitor",
    },
  ] as const;

  return (
    <ol className="operational-flow" aria-label="Living operational flow">
      {stages.map((stage, index) => (
        <li key={stage.key} className={`operational-flow-step operational-flow-step-${stage.key}${stage.value > 0 ? " is-live" : ""}`}>
          <Link className="operational-flow-link" href={stage.href}>
            <span className="operational-flow-node" aria-hidden="true">
              <span className="operational-flow-index">{index + 1}</span>
            </span>
            <span className="operational-flow-value">{stage.value}</span>
            <span className="operational-flow-label">{stage.label}</span>
            <span className="operational-flow-caption">{stage.caption}</span>
          </Link>
        </li>
      ))}
    </ol>
  );
}
