"""
Manual resolution (human-driven recovery) service group (P12.3 decomposition).

Records manual interventions with their full validation
and atomic transaction boundary.
"""

from datetime import datetime
from app.errors import (
    ActionNotFoundError,
    ManualInterventionNotAllowedError,
    RecoveryWorkflowError,
)
from app.repositories import exceptions_repo
from app.repositories import manual_interventions_repo
from app.repositories import recovery_actions_repo


INTERVENTION_TYPES = (
    "Carrier call",
    "Carrier email",
    "Supplier coordination",
    "Customer coordination",
    "Internal coordination",
    "Other",
)

OUTCOME_RESOLVED = "Resolved"

OUTCOME_STILL_OPEN = "Still Open"


def record_manual_resolution(
    connection,
    exception_id,
    intervention_type,
    external_party,
    resolution_summary,
    recorded_by,
    outcome,
    new_expected_delivery=None,
    notes=None,
):
    """
    Record a manual resolution for an exception that the
    human planner resolved outside Adensa.

    A manual intervention is a distinct operational event:
    it never creates recovery-option or recovery-action
    records and never touches the system-driven recovery
    workflow. The intervention record and the exception
    status update commit atomically in one transaction.

    Validation (all failures raise before any write):

    - the exception must exist and be open;
    - a system recovery action for the exception must not
      be Pending Approval or Approved, so recording a
      manual resolution can never silently bypass the
      human-in-the-loop recovery workflow;
    - intervention type and outcome must be valid domain
      values; free-text fields must not be empty.

    Resolution follows the existing state rules: the
    exception becomes Resolved only when the recorded
    outcome is Resolved; otherwise it remains open and
    monitored. recorded_at is the current wall-clock time.
    """

    if intervention_type not in INTERVENTION_TYPES:
        raise ManualInterventionNotAllowedError(
            f"Unknown intervention type: {intervention_type}."
        )

    if outcome not in (OUTCOME_RESOLVED, OUTCOME_STILL_OPEN):
        raise ManualInterventionNotAllowedError(
            f"Unknown outcome: {outcome}."
        )

    for field_value, field_name in (
        (external_party, "external party"),
        (resolution_summary, "resolution summary"),
        (recorded_by, "recorder"),
    ):

        if not field_value or not field_value.strip():
            raise ManualInterventionNotAllowedError(
                f"The {field_name} is required."
            )

    exception = exceptions_repo.get_exception_resolution_status(
        connection,
        exception_id,
    )

    if exception is None:
        raise ActionNotFoundError(
            f"Exception {exception_id} not found."
        )

    if exception["resolution_status"] != "Open":
        raise ManualInterventionNotAllowedError(
            f"Exception {exception_id} is already "
            f"{exception['resolution_status']} and cannot "
            f"receive further interventions."
        )

    action = recovery_actions_repo.get_latest_action_for_exception(
        connection,
        exception_id,
    )

    if action and action["status"] in (
        "Pending Approval",
        "Approved",
    ):
        raise ManualInterventionNotAllowedError(
            f"Exception {exception_id} has a system recovery "
            f"action ({action['action_id']}) that is "
            f"{action['status']}. Resolve it through the "
            f"recovery workflow before recording a manual "
            f"resolution."
        )

    intervention_id = (
        f"INT-{manual_interventions_repo.get_next_intervention_number(connection):06d}"
    )

    recorded_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    try:

        manual_interventions_repo.insert_manual_intervention(
            connection,
            (
                intervention_id,
                exception_id,
                intervention_type,
                external_party.strip(),
                resolution_summary.strip(),
                new_expected_delivery,
                outcome,
                notes,
                recorded_by.strip(),
                recorded_at,
            ),
        )

        if outcome == OUTCOME_RESOLVED:

            rows_updated = exceptions_repo.mark_exception_resolved(
                connection,
                exception_id,
                resolved_at=recorded_at,
            )

            if rows_updated != 1:
                raise RecoveryWorkflowError(
                    f"Exception {exception_id} could not be "
                    f"marked as Resolved."
                )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return {
        "success": True,
        "message": (
            f"Manual resolution {intervention_id} recorded "
            f"for {exception_id}."
        ),
        "intervention_id": intervention_id,
        "exception_id": exception_id,
        "intervention_type": intervention_type,
        "external_party": external_party.strip(),
        "resolution_summary": resolution_summary.strip(),
        "new_expected_delivery": new_expected_delivery,
        "outcome": outcome,
        "notes": notes,
        "recorded_by": recorded_by.strip(),
        "recorded_at": recorded_at,
        "exception_status": (
            "Resolved"
            if outcome == OUTCOME_RESOLVED
            else "Open"
        ),
    }
