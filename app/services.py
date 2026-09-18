"""
Application service layer.

Owns the application/workflow orchestration that previously
lived in the Streamlit UI (app/main.py):

    Streamlit UI
         ↓
      main.py
         ↓
      services        ← this module
         ↓
      engines
         ↓
    repositories
         ↓
       SQLite

Rules:

- Services sequence engines and repositories and construct
  application-level result dictionaries for any frontend.
- Business rules stay in the engines; this module never
  duplicates them.
- No Streamlit imports and no UI strings: the UI consumes
  the returned dictionaries.
- No commits and no transaction management: transaction
  boundaries remain exactly where they were (inside the
  engine operations).
- Plain functions only: no classes, no frameworks.
"""

from app.decision_engine import get_recommendation
from app.errors import RecoveryWorkflowError
from app.execution_engine import execute_recovery_action
from app.repositories import exceptions_repo
from app.repositories import recovery_actions_repo
from app.repositories import recovery_options_repo
from app.repositories import shipments_repo
from app.workflow_engine import (
    approve_action,
    reject_action,
)


# ==================================================
# DASHBOARD DATA
# ==================================================

def get_dashboard_metrics(connection):
    """
    Return the KPI metrics shown on the dashboard.

    Aggregated from the repositories; no business rules.
    """

    return {
        "open_exceptions":
            exceptions_repo.count_open_exceptions(connection),
        "critical_exceptions":
            exceptions_repo.count_open_critical_exceptions(connection),
        "pending_approvals": recovery_actions_repo.count_actions_by_status(
            connection,
            status="Pending Approval",
        ),
    }


def get_exception_inbox(connection):
    """
    Return the open-exception inbox rows for the dashboard.
    """

    return exceptions_repo.get_open_exceptions_inbox(connection)


# ==================================================
# EXCEPTION REVIEW
# ==================================================

def get_exception_review(
    connection,
    exception_id,
):
    """
    Build the decision-engine review for an exception.

    The returned dictionary contains the engine's
    recommendation structure unchanged, including the
    selected option_id when a feasible recommendation
    exists.
    """

    return get_recommendation(
        connection,
        exception_id,
    )


def get_latest_action(
    connection,
    exception_id,
):
    """
    Return the most recent recovery action for an
    exception, or None.
    """

    return recovery_actions_repo.get_latest_action_for_exception(
        connection,
        exception_id,
    )


# ==================================================
# WORKFLOW OUTCOMES
# ==================================================

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
    exception_id,
    shipment_id,
    required_delivery,
):
    """
    Execute an approved recovery action and return the
    application outcome dictionary for the UI.

    The engine performs the execution and its transaction
    boundary; this service collects the resulting
    application state and normalizes it into the outcome
    dictionary.

    On failure the returned dictionary carries
    success False and the error message, mirroring the
    application behavior previously implemented by the UI.
    """

    # Capture the current shipment state before execution.
    previous_shipment = shipments_repo.get_shipment_transport_mode_and_carrier(
        connection,
        shipment_id,
    )

    previous_mode = (
        previous_shipment["transport_mode"]
    )

    try:
        execute_recovery_action(
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
