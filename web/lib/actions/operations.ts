"use server";

/**
 * Server Actions: the operations boundary between the Next.js
 * Operations surface and the two existing /v1 operational
 * controls (P9.1) — the same endpoints the legacy Streamlit
 * sidebar drives, consumed through the same typed, fail-closed
 * client and the same server-action discipline as the workflow
 * mutations.
 *
 * Deliberate design (mirroring workflow.ts):
 * - The actions are the ONLY place the browser can trigger an
 *   operational mutation. They run on the Node server, so the
 *   API origin and the machine credential never reach the
 *   client.
 * - The backend remains the authority: its HTTP 409 guard
 *   ("no operational data to derive a simulated arrival from")
 *   is carried through verbatim and rendered; the UI never
 *   re-interprets or bypasses it.
 * - Every result is a small discriminated union — no raw
 *   exceptions, no internal error text.
 *
 * Revalidation: an operational refresh changes exceptions,
 * recovery options and workflow actions — the surfaces that
 * present them are the Control Tower (`/`) and the Exception
 * Inbox (`/exceptions`). Nothing else is revalidated.
 */

import { revalidatePath } from "next/cache";
import {
  refreshOperationsPipeline,
  simulateShipmentArrival,
} from "@/lib/api/client";
import type {
  OperationalRefreshSummary,
  SimulatedArrivalSummary,
} from "@/lib/types/api";

/**
 * The action-layer result: a deliberate mirror of the
 * mutation result states, so components render honest
 * outcomes without knowing HTTP details. The two operations
 * endpoints cannot legitimately produce every transport
 * state (no request body → no 422; fixed paths → no 404),
 * but the union preserves them anyway: if the boundary ever
 * reports one, the UI says so instead of collapsing it into
 * a generic failure.
 */
export type OperationsActionResult<T> =
  | { status: "success"; message: string; data: T }
  | { status: "guard"; message: string }
  | { status: "validation"; message: string }
  | { status: "notFound"; message: string }
  | { status: "unauthenticated"; message: string }
  | { status: "unavailable"; message: string }
  | { status: "unexpected"; message: string };

/** Revalidate every surface an operational change can affect. */
function revalidateOperationalSurfaces(): void {
  revalidatePath("/");
  revalidatePath("/exceptions");
}

// --------------------------------------------------
// REFRESH OPERATIONS PIPELINE
// --------------------------------------------------

export async function refreshPipelineAction(): Promise<
  OperationsActionResult<OperationalRefreshSummary>
> {
  const result = await refreshOperationsPipeline();

  if (result.kind === "success") {
    revalidateOperationalSurfaces();

    const data = result.data;
    const newCount = data.new_exceptions;

    return {
      status: "success",
      message:
        newCount === 1
          ? "Detected 1 new exception."
          : `Detected ${newCount} new exceptions.`,
      data,
    };
  }

  return mapOperationsFailure(result);
}

// --------------------------------------------------
// SIMULATE SHIPMENT ARRIVAL
// --------------------------------------------------

export async function simulateArrivalAction(): Promise<
  OperationsActionResult<SimulatedArrivalSummary>
> {
  const result = await simulateShipmentArrival();

  if (result.kind === "success") {
    revalidateOperationalSurfaces();

    return {
      status: "success",
      message: `Shipment ${result.data.shipment_id} arrived.`,
      data: result.data,
    };
  }

  return mapOperationsFailure(result);
}

function mapOperationsFailure(
  result: Exclude<
    Awaited<ReturnType<typeof refreshOperationsPipeline>>,
    { kind: "success" }
  >,
): {
  status:
    | "guard"
    | "validation"
    | "notFound"
    | "unauthenticated"
    | "unavailable"
    | "unexpected";
  message: string;
} {
  return { status: result.kind, message: result.message };
}
