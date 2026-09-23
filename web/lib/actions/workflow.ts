"use server";

/**
 * Server Actions: the workflow-mutation boundary between the
 * Investigation Workspace and the existing /v1 (and legacy
 * machine-to-machine) mutation contracts (ADR-011).
 *
 * Deliberate design:
 * - The actions are the ONLY place the browser can trigger an
 *   operational mutation. They run on the Node server, so the
 *   API origin and the machine credential never reach the
 *   client (same discipline as the Server-Component reads).
 * - The backend workflow engine remains the authority: its
 *   HTTP 409 guard messages are carried through verbatim and
 *   rendered; the UI never re-interprets or bypasses them.
 * - Every result is a small discriminated union — no raw
 *   exceptions, no internal error text beyond the engine's
 *   own operational message.
 *
 * Revalidation: the reads are `cache: "no-store"`, so a
 * successful mutation only needs `revalidatePath` to refresh
 * the workspace and the work-queue surfaces.
 */

import { revalidatePath } from "next/cache";
import {
  approveRecoveryAction,
  executeRecoveryAction,
  recordManualResolution,
  rejectRecoveryAction,
} from "@/lib/api/client";
import type {
  ManualResolutionOutcome,
  ManualResolutionRequest,
  WorkflowOutcome,
} from "@/lib/types/api";

/**
 * The action-layer result: a deliberate mirror of the
 * mutation result states, so components render honest
 * outcomes without knowing HTTP details.
 */
export type WorkflowActionResult<T> =
  | { status: "success"; message: string; data: T }
  | { status: "guard"; message: string }
  | { status: "validation"; message: string }
  | { status: "notFound"; message: string }
  | { status: "unauthenticated"; message: string }
  | { status: "unavailable"; message: string }
  | { status: "unexpected"; message: string };

/** Revalidate every surface a workflow mutation can change. */
function revalidateWorkflowSurfaces(exceptionId: string): void {
  revalidatePath(`/exceptions/${exceptionId}`);
  revalidatePath("/exceptions");
  revalidatePath("/");
}

function mapMutationFailure(
  result: Exclude<
    Awaited<ReturnType<typeof approveRecoveryAction>>,
    { kind: "success" }
  >,
): { status: "guard" | "validation" | "notFound" | "unauthenticated" | "unavailable" | "unexpected"; message: string } {
  return { status: result.kind, message: result.message };
}

// --------------------------------------------------
// APPROVE
// --------------------------------------------------

const APPROVE_FORM_KEY = "approved_by";

export async function approveWorkflowAction(
  exceptionId: string,
  _prev: unknown,
  formData: FormData,
): Promise<WorkflowActionResult<WorkflowOutcome>> {
  const approvedBy = String(formData.get(APPROVE_FORM_KEY) ?? "").trim();

  if (approvedBy.length === 0) {
    return {
      status: "validation",
      message: "Enter the approving planner's name.",
    };
  }

  const result = await approveRecoveryAction(exceptionId, {
    approved_by: approvedBy,
  });

  if (result.kind === "success") {
    revalidateWorkflowSurfaces(exceptionId);

    return {
      status: "success",
      message: result.data.message,
      data: result.data,
    };
  }

  return mapMutationFailure(result);
}

// --------------------------------------------------
// REJECT
// --------------------------------------------------

const REJECT_FORM_KEY = "rejected_by";

export async function rejectWorkflowAction(
  exceptionId: string,
  _prev: unknown,
  formData: FormData,
): Promise<WorkflowActionResult<WorkflowOutcome>> {
  const rejectedBy = String(formData.get(REJECT_FORM_KEY) ?? "").trim();

  if (rejectedBy.length === 0) {
    return {
      status: "validation",
      message: "Enter the rejecting planner's name.",
    };
  }

  const result = await rejectRecoveryAction(exceptionId, {
    rejected_by: rejectedBy,
  });

  if (result.kind === "success") {
    revalidateWorkflowSurfaces(exceptionId);

    return {
      status: "success",
      message: result.data.message,
      data: result.data,
    };
  }

  return mapMutationFailure(result);
}

// --------------------------------------------------
// EXECUTE
// --------------------------------------------------

export async function executeWorkflowAction(
  exceptionId: string,
  actionId: string,
): Promise<WorkflowActionResult<WorkflowOutcome>> {
  const result = await executeRecoveryAction(actionId);

  if (result.kind === "success") {
    revalidateWorkflowSurfaces(exceptionId);

    return {
      status: "success",
      message: result.data.message,
      data: result.data,
    };
  }

  return mapMutationFailure(result);
}

// --------------------------------------------------
// MANUAL RESOLUTION
// --------------------------------------------------

export async function resolveManuallyWorkflowAction(
  exceptionId: string,
  _prev: unknown,
  formData: FormData,
): Promise<WorkflowActionResult<ManualResolutionOutcome>> {
  const request = manualResolutionRequestFrom(formData);

  // Cheap UX validation for the obvious gaps. The backend's
  // service-level rules (type/outcome enums, field
  // constraints) remain the authoritative validator.
  const fieldError = obviousFormGap(request);

  if (fieldError !== null) {
    return { status: "validation", message: fieldError };
  }

  const result = await recordManualResolution(exceptionId, request);

  if (result.kind === "success") {
    revalidateWorkflowSurfaces(exceptionId);

    return {
      status: "success",
      message: result.data.message,
      data: result.data,
    };
  }

  return mapMutationFailure(result);
}

function manualResolutionRequestFrom(
  formData: FormData,
): ManualResolutionRequest {
  return {
    intervention_type: String(formData.get("intervention_type") ?? "").trim(),
    external_party: String(formData.get("external_party") ?? "").trim(),
    resolution_summary: String(formData.get("resolution_summary") ?? "").trim(),
    recorded_by: String(formData.get("recorded_by") ?? "").trim(),
    outcome: String(formData.get("outcome") ?? "").trim(),
    new_expected_delivery:
      String(formData.get("new_expected_delivery") ?? "").trim() || null,
    notes: String(formData.get("notes") ?? "").trim() || null,
  };
}

function obviousFormGap(request: ManualResolutionRequest): string | null {
  if (request.intervention_type.length === 0) {
    return "Select the intervention type.";
  }

  if (request.external_party.length === 0) {
    return "Enter the external party involved.";
  }

  if (request.resolution_summary.length === 0) {
    return "Summarize the resolution performed outside Adensa.";
  }

  if (request.recorded_by.length === 0) {
    return "Enter the planner recording this resolution.";
  }

  if (request.outcome.length === 0) {
    return "Select the outcome.";
  }

  return null;
}
