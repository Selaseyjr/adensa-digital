"""
Workflow outcomes service group (P12.3 decomposition).

Approve / reject / execute transitions over the workflow
engine, composed into application outcome dictionaries.
"""

from app.errors import (
    ActionNotFoundError,
    ManualInterventionNotAllowedError,
    RecoveryWorkflowError,
)
from app.execution_engine import execute_recovery_action
from app.repositories import exceptions_repo
from app.repositories import recovery_actions_repo
from app.repositories import recovery_options_repo
from app.repositories import shipments_repo
from app.workflow_engine import (
    REJECTED,
    APPROVED,
    EXECUTED,
    PENDING_APPROVAL,
    approve_action,
    reject_action,
    generate_workflow_actions,
)


def approve_recovery(
    connection,
    action_id,
    approved_by,
):
    """
    Approve a pending recovery action and return the
    application outcome dictionary.

    The workflow transition is performed by the workflow
    engine, including its transaction boundary and its
    validation: a missing action, an invalid transition or
    a closed exception raises before any state changes.

    The outcome context is resolved from application state
    through the repositories: the action's exception and
    option identity, the exception's operational context
    and the recovery option stored on the action.
    """

    approve_action(
        connection,
        action_id,
        approved_by,
    )

    action = recovery_actions_repo.get_action_by_id(
        connection,
        action_id,
    )

    context = exceptions_repo.get_exception_operational_context(
        connection,
        action["exception_id"],
    )

    option = recovery_options_repo.get_option_by_id(
        connection,
        action["option_id"],
    )

    return {
        "success": True,
        "message": (
            f"Recovery action "
            f"{action_id} "
            f"approved successfully."
        ),
        "action_id": action_id,
        "shipment_id": context["shipment_id"],
        "previous_mode": context["transport_mode"],
        "new_mode": option["transport_mode"],
        "carrier_id": option["carrier_id"],
        "new_eta": "Pending execution",
        "recovery_event": "Pending execution",
        "required_delivery": context["required_delivery_date"],
        "exception_status": "Open",
    }


def reject_recovery(
    connection,
    action_id,
    rejected_by,
):
    """
    Reject a pending recovery action and return the
    application outcome dictionary.

    The workflow transition is performed by the workflow
    engine, including its transaction boundary and its
    validation. No recovery option is consulted: rejection
    does not execute anything, so the outcome carries the
    existing sentinel values.
    """

    reject_action(
        connection,
        action_id,
        rejected_by,
    )

    action = recovery_actions_repo.get_action_by_id(
        connection,
        action_id,
    )

    context = exceptions_repo.get_exception_operational_context(
        connection,
        action["exception_id"],
    )

    return {
        "success": True,
        "message": (
            f"Recovery action "
            f"{action_id} "
            f"rejected."
        ),
        "action_id": action_id,
        "shipment_id": context["shipment_id"],
        "previous_mode": context["transport_mode"],
        "new_mode": context["transport_mode"],
        "carrier_id": "No execution",
        "new_eta": "No execution",
        "recovery_event": "None",
        "required_delivery": context["required_delivery_date"],
        "exception_status": "Open",
    }


def execute_approved_recovery(
    connection,
    action_id,
):
    """
    Execute an approved recovery action and return the
    application outcome dictionary.

    The service resolves its own context through the
    repositories: the action's exception, the exception's
    operational context and the shipment's transport mode
    captured BEFORE the engine mutates it. The engine then
    performs the execution and its transaction boundary;
    this service collects the resulting application state
    and normalizes it into the outcome dictionary.

    On failure the returned dictionary carries
    success False and the error message, mirroring the
    application behavior previously implemented by the UI.
    """

    action = recovery_actions_repo.get_action_by_id(
        connection,
        action_id,
    )

    if action is None:
        raise ActionNotFoundError(
            f"Action {action_id} not found."
        )

    context = exceptions_repo.get_exception_operational_context(
        connection,
        action["exception_id"],
    )

    shipment_id = context["shipment_id"]

    exception_id = action["exception_id"]

    required_delivery = context["required_delivery_date"]

    # Capture the current shipment state before execution.
    previous_shipment = shipments_repo.get_shipment_transport_mode_and_carrier(
        connection,
        shipment_id,
    )

    previous_mode = (
        previous_shipment["transport_mode"]
    )

    try:
        # Called through the package facade so the historical
        # patch seam keeps working: tests patch
        # services.execute_recovery_action at the package
        # namespace, exactly as they did against the pre-split
        # module. Call-time resolution, same engine function.
        from app import services

        services.execute_recovery_action(
            connection,
            action_id,
        )
    except RecoveryWorkflowError as error:

        return {
            "success": False,
            "message": (
                f"Recovery execution failed: "
                f"{error}"
            ),
        }

    updated_shipment = shipments_repo.get_shipment_delivery_state(
        connection,
        shipment_id,
    )

    recovery_event = shipments_repo.get_latest_recovery_event_id(
        connection,
        shipment_id,
    )

    final_exception = exceptions_repo.get_exception_resolution_status(
        connection,
        exception_id,
    )

    exception_status = (
        final_exception[
            "resolution_status"
        ]
    )

    return {
        "success": True,
        "message": (
            f"Recovery executed successfully "
            f"for "
            f"{shipment_id}."
        ),
        "action_id": action_id,
        "shipment_id": shipment_id,
        "previous_mode": previous_mode,
        "new_mode": updated_shipment[
            "transport_mode"
        ],
        "carrier_id": updated_shipment[
            "carrier_id"
        ],
        "new_eta": updated_shipment[
            "estimated_arrival"
        ],
        "recovery_event": (
            recovery_event["event_id"]
            if recovery_event
            else "Not recorded"
        ),
        "required_delivery": required_delivery,
        "exception_status": exception_status,
    }
