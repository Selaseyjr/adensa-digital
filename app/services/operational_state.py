"""
Operational state service group (P12.3 decomposition).

Investigation-state classification, the follow-up queue, the
control-tower summary and the analytics overview: read-only
projections over persisted operational evidence.
"""

from app.repositories import exceptions_repo
from app.repositories import manual_interventions_repo
from app.repositories import recovery_actions_repo
from app.repositories import analytics_repo

from app.workflow_engine import (
    APPROVED,
    EXECUTED,
    PENDING_APPROVAL,
)

from app.services.inbox import get_exception_inbox


def classify_investigation_state(
    connection,
    exception_id,
):
    """
    Classify an investigated exception's current operational
    state from persisted evidence only, so the planner can
    distinguish what needs what kind of attention.

    States (mutually exclusive, checked in order):

    - 'Resolved': the persisted resolution status is
      Resolved (via system execution or a recorded manual
      intervention outcome).
    - 'Awaiting execution': the latest recovery action is
      Approved — a human has decided; execution remains.
    - 'Executed — still open': the latest recovery action
      is Executed but the exception remains open, with the
      persisted arrival-versus-required evidence for why it
      is still open. This situation requires follow-up.
    - 'Decision required': the latest recovery action is
      Pending Approval.
    - 'No system recovery available': no recovery action
      exists (no feasible system recovery was found, or
      none was generated).

    Returns None when the exception does not exist. No
    state is invented: every branch reads a persisted
    column, and the follow-up reason quotes the recorded
    dates rather than a vague verdict.
    """

    exception = exceptions_repo.get_exception_resolution_status(
        connection,
        exception_id,
    )

    if exception is None:
        return None

    if exception["resolution_status"] == "Resolved":

        return {
            "state": "Resolved",
            "follow_up_required": False,
            "reason": (
                "The persisted operational evidence records "
                "this exception as resolved."
            ),
        }

    action = (
        recovery_actions_repo
        .get_latest_action_for_exception(
            connection,
            exception_id,
        )
    )

    if action is None:

        return {
            "state": "No system recovery available",
            "follow_up_required": False,
            "reason": (
                "No system recovery action exists for this "
                "exception."
            ),
        }

    if action["status"] == APPROVED:

        return {
            "state": "Awaiting execution",
            "follow_up_required": False,
            "reason": (
                f"Recovery action {action['action_id']} has "
                f"been approved and is ready for execution."
            ),
        }

    if action["status"] == EXECUTED:

        execution = recovery_actions_repo.get_execution_result(
            connection,
            action["action_id"],
        )

        return {
            "state": "Executed — still open",
            "follow_up_required": True,
            "reason": (
                f"Recovery executed, but estimated arrival "
                f"{execution['estimated_arrival']} remains "
                f"later than required delivery "
                f"{execution['required_delivery_date']}. "
                f"Exception remains open after recovery "
                f"execution."
            ),
        }

    return {
        "state": "Decision required",
        "follow_up_required": False,
        "reason": (
            f"Recovery action {action['action_id']} is "
            f"awaiting a planner approval or rejection "
            f"decision."
        ),
    }


def get_follow_up_queue(
    connection,
    limit=10,
):
    """
    Return the follow-up work queue: open exceptions whose
    recovery has already been executed without resolving
    them, newest detection first, with the factual reason
    for each entry.

    Bounded work-queue surface (Checkpoint P semantics
    apply): the full-population count of this population is
    reported separately by get_control_tower_summary via
    count_open_follow_up_required.
    """

    rows = exceptions_repo.get_follow_up_required_exceptions(
        connection,
        limit,
    )

    queue = []

    for row in rows:

        queue.append(
            {
                "exception_id": row["exception_id"],
                "severity": row["severity"],
                "exception_type": row["exception_type"],
                "detected_at": row["detected_at"],
                "action_id": row["action_id"],
                "executed_at": row["executed_at"],
                "estimated_arrival": row["estimated_arrival"],
                "required_delivery_date": row[
                    "required_delivery_date"
                ],
                "actionable": row["feasible_option_count"] > 0,
                "reason": (
                    f"Recovery {row['action_id']} executed "
                    f"{row['executed_at']}, but estimated "
                    f"arrival {row['estimated_arrival']} "
                    f"remains later than required delivery "
                    f"{row['required_delivery_date']}."
                ),
            }
        )

    return queue


def get_control_tower_summary(
    connection,
    resolved_limit=10,
):
    """
    Compose the operational control-tower projection: the
    at-a-glance state of the open exception population and
    the most recently resolved outcomes.

    Aggregation/projection only:

    - counts come from the existing repository reads
      (the same reads behind the dashboard metrics and the
      workflow-action status counts);
    - the actionable/monitoring split is derived from the
      feasible-option counts ALREADY carried by the inbox
      rows (get_exception_inbox) — feasibility is never
      recomputed here. The two counts partition the BOUNDED
      inbox work-queue surface (actionable + monitoring =
      the visible inbox row count), not the full open
      population behind the inbox cap;
    - a resolved exception's path is reported only where
      recorded evidence establishes it: an executed recovery
      action for the exception (system-resolved) or a manual
      intervention record (manually resolved). Without such
      evidence the neutral "Resolved" is reported.

    Does not replace get_dashboard_metrics (the external
    API contract); this is the richer internal view the
    control-tower UI renders.
    """

    inbox = get_exception_inbox(connection)

    # The inbox is the bounded operational-work surface
    # (the first rows of the open-exception work queue), so
    # these two counts describe the population the planner
    # can actually discover and act on — NOT the full open
    # population behind the inbox cap. They partition the
    # visible queue: actionable rows (feasible recovery
    # available) + monitoring rows (no feasible recovery)
    # = the inbox row count. Both split numbers come from
    # the feasible-option counts ALREADY carried by the
    # inbox rows; feasibility is never recomputed here.
    actionable = sum(
        1
        for row in inbox
        if row["feasible_option_count"] > 0
    )

    monitoring = len(inbox) - actionable

    recently_resolved = [
        dict(row)
        for row in exceptions_repo.get_recently_resolved_exceptions(
            connection,
            resolved_limit,
        )
    ]

    for resolved in recently_resolved:

        exception_id = resolved["exception_id"]

        actions = recovery_actions_repo.get_actions_for_exception(
            connection,
            exception_id,
        )

        if any(
            action["status"] == EXECUTED
            for action in actions
        ):

            resolved["resolution_path"] = (
                "System-executed recovery"
            )

            continue

        interventions = (
            manual_interventions_repo
            .get_interventions_for_exception(
                connection,
                exception_id,
            )
        )

        if interventions:

            resolved["resolution_path"] = (
                "Manually resolved"
            )

        else:

            resolved["resolution_path"] = "Resolved"

    return {
        "open_exceptions":
            exceptions_repo.count_open_exceptions(connection),
        "actionable_exceptions": actionable,
        "monitoring_exceptions": monitoring,
        "pending_approvals":
            recovery_actions_repo.count_actions_by_status(
                connection,
                status=PENDING_APPROVAL,
            ),
        "awaiting_execution":
            recovery_actions_repo.count_actions_by_status(
                connection,
                status=APPROVED,
            ),
        "critical_exceptions":
            exceptions_repo
            .count_open_critical_exceptions(connection),
        "follow_up_required":
            exceptions_repo
            .count_open_follow_up_required(connection),
        "follow_up_queue": get_follow_up_queue(
            connection,
            resolved_limit,
        ),
        "recently_resolved": recently_resolved,
    }


def get_analytics_overview(connection):
    """
    Compose the analytical overview for the control-tower
    visualization layer (ADR-014).

    Aggregation/projection only — each dataset is the
    corresponding read-only repository query unchanged. The
    per-dataset `basis` strings are part of the CONTRACT, not
    UI copy: the frontend must be able to state every series'
    analytical basis honestly ("Delivered shipments by
    planned-arrival month") without the assumptions living
    in component text.

    Deliberately absent (the discovery audit's honesty
    rules): no recovery-performance, resolution-performance
    or exception-detection-trend series — the current data
    carries no temporal observations for those analyses, and
    the single batch detection timestamp is not a time
    series. Rendering empty or synthetic history is worse
    than rendering nothing.
    """

    return {
        "service_performance": {
            "basis": (
                "Delivered shipments by planned-arrival month"
            ),
            "points": analytics_repo
            .get_service_performance_by_month(connection),
        },
        "exception_incidence": {
            "basis": (
                "Exceptions by shipment departure month"
            ),
            "points": analytics_repo
            .get_exception_incidence_by_month(connection),
        },
        "shipment_volume": {
            "basis": (
                "All shipments by planned-departure month"
            ),
            "points": analytics_repo
            .get_shipment_volume_by_month(connection),
        },
        "transport": {
            "basis": (
                "Delivered shipments by transport mode"
            ),
            "entries": analytics_repo
            .get_transport_mode_performance(connection),
        },
        "carriers": {
            "basis": "Delivered shipments per carrier",
            "entries": analytics_repo
            .get_carrier_performance(connection),
        },
        "warehouses": {
            "basis": (
                "Exceptions per origin warehouse"
            ),
            "entries": analytics_repo
            .get_exceptions_by_warehouse(connection),
        },
        "severity": {
            "basis": (
                "Open exceptions by severity (current snapshot)"
            ),
            "entries": analytics_repo
            .get_severity_composition(connection),
        },
    }
