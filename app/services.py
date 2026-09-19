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

from datetime import datetime

from app.detect_exceptions import detect_exceptions
from app.decision_engine import get_recommendation
from app.errors import (
    ActionNotFoundError,
    ManualInterventionNotAllowedError,
    RecoveryWorkflowError,
)
from app.execution_engine import execute_recovery_action
from app.generate_recovery_options import generate_recovery_options
from app.repositories import exceptions_repo
from app.repositories import manual_interventions_repo
from app.repositories import recovery_actions_repo
from app.repositories import recovery_options_repo
from app.repositories import shipments_repo
from app.simulation import create_simulated_arrival
from app.workflow_engine import (
    approve_action,
    reject_action,
    generate_workflow_actions,
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

    Each row carries the count of feasible recovery options
    (feasible_option_count) from the existing option data,
    and rows are ordered actionable-first inside each
    severity class. The count is retrieved operational
    data; the UI renders the actionable/monitoring wording.
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


def get_recovery_assessment(
    connection,
    exception_id,
):
    """
    Return the recovery assessment for an exception: the
    decision-engine review plus, when no recommendation
    exists, the evaluated options that explain why.

    When the engine has a feasible option to recommend,
    the assessment carries the recommendation and its
    alternatives exactly as the review does. When it has
    none, the previously generated options - feasible and
    infeasible - are included as evaluated_options, each
    with its own operational data (mode, carrier, cost,
    transit, risk) and its feasibility verdict. The engines
    do not persist a granular rejection reason, so none is
    invented here: the verdict and the option's operational
    data are the strongest truthful information available.

    Returns None when the exception does not exist.
    """

    review = get_recommendation(
        connection,
        exception_id,
    )

    if review is None:
        return None

    if review["recommendation"] is not None:

        return {
            "recommendation": review["recommendation"],
            "alternatives": review["alternatives"],
            "evaluated_options": [],
        }

    return {
        "recommendation": None,
        "alternatives": [],
        "evaluated_options": [
            {
                "option_id": option["option_id"],
                "transport_mode": option["transport_mode"],
                "carrier_id": option["carrier_id"],
                "estimated_cost": option["estimated_cost"],
                "estimated_transit_days": option[
                    "estimated_transit_days"
                ],
                "risk_score": option["risk_score"],
                "feasible": bool(option["feasible"]),
            }
            for option in (
                recovery_options_repo.get_options_for_exception(
                    connection,
                    exception_id,
                )
            )
        ],
    }


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


# ==================================================
# EXCEPTION INVESTIGATION CONTEXT
# ==================================================

def get_exception_context(
    connection,
    exception_id,
):
    """
    Return the operational investigation context for one
    exception, or None when the exception does not exist.

    Projects the existing shared context read into an
    application-facing structure for the UI and any other
    client. Contains no business rules: every field is
    retrieved operational data.
    """

    context = exceptions_repo.get_exception_operational_context(
        connection,
        exception_id,
    )

    if context is None:
        return None

    return {
        "exception_id": context["exception_id"],
        "shipment_id": context["shipment_id"],
        "order_id": context["order_id"],
        "customer_id": context["customer_id"],
        "customer_name": context["customer_name"],
        "exception_type": context["exception_type"],
        "severity": context["severity"],
        "priority": context["priority"],
        "origin": context["origin"],
        "destination": context["destination"],
        "route": (
            f"{context['origin']} → "
            f"{context['destination']}"
        ),
        "transport_mode": context["transport_mode"],
        "carrier_id": context["carrier_id"],
        "shipment_status": context["shipment_status"],
        "planned_departure": context["planned_departure"],
        "estimated_arrival": context["estimated_arrival"],
        "required_delivery_date": context[
            "required_delivery_date"
        ],
    }


# ==================================================
# OPERATIONAL PIPELINE REFRESH
# ==================================================

def run_operational_refresh(connection):
    """
    Re-run the operational processing pipeline:

        detect exceptions
            ↓
        generate recovery options
            ↓
        generate workflow actions

    Each stage is the existing production function with its
    own idempotency guard and transaction boundary; this
    service only sequences them and aggregates the results.
    No business rules and no SQL live here, and unexpected
    errors from any stage propagate to the caller.

    Detection and option generation return no summary, so
    the newly created work is measured as before/after
    deltas through the existing repository counts. The
    action-generation summary is returned by the workflow
    engine and passed through unchanged. The identities of
    newly detected exceptions are reported through the
    latest-exception read so clients can surface exactly
    what the run has just found.
    """

    exceptions_before = exceptions_repo.count_exceptions(
        connection,
    )

    options_before = (
        recovery_options_repo.get_next_option_number(
            connection,
        )
        - 1
    )

    detect_exceptions(connection)

    generate_recovery_options(connection)

    actions_summary = generate_workflow_actions(connection)

    exceptions_after = exceptions_repo.count_exceptions(
        connection,
    )

    options_after = (
        recovery_options_repo.get_next_option_number(
            connection,
        )
        - 1
    )

    new_exception_count = (
        exceptions_after
        - exceptions_before
    )

    return {
        "new_exceptions": new_exception_count,
        "new_options": (
            options_after
            - options_before
        ),
        "new_exception_ids": (
            exceptions_repo.get_latest_exception_ids(
                connection,
                limit=new_exception_count,
            )
            if new_exception_count
            else []
        ),
        "actions_evaluated": actions_summary["evaluated"],
        "new_actions": actions_summary["created"],
        "actions_without_recommendation": actions_summary[
            "without_recommendation"
        ],
        "actions_skipped": actions_summary["skipped"],
    }


# ==================================================
# MANUAL RESOLUTION (HUMAN-DRIVEN RECOVERY)
# ==================================================

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


def get_manual_interventions(
    connection,
    exception_id,
):
    """
    Return the recorded manual interventions for an
    exception, newest first, as plain dictionaries for any
    client.
    """

    return [
        dict(row)
        for row in (
            manual_interventions_repo.get_interventions_for_exception(
                connection,
                exception_id,
            )
        )
    ]


# ==================================================
# DATA-ARRIVAL SIMULATION
# ==================================================

def run_data_arrival_simulation(connection):
    """
    Create one deterministic simulated shipment arrival.

    The simulation represents new operational data
    arriving: it creates ONLY the arrival records
    (shipment + shipment events) through the simulation
    module and repositories.

    It never creates exceptions, recovery options,
    recommendations or recovery actions, and it never
    calls the operational refresh: detecting and
    processing the arrival is the explicit job of
    run_operational_refresh(), which the user triggers
    separately.

    Returns the arrival summary dictionary from the
    simulation module, or None when the database
    contains no operational data to derive the scenario
    from.
    """

    return create_simulated_arrival(connection)
