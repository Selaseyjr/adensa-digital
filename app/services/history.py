"""
Operational history / manual interventions service group (P12.3 decomposition).

Composes one exception's chronological history from
persisted records and projects recorded interventions.
"""

from app.repositories import exceptions_repo
from app.repositories import manual_interventions_repo
from app.repositories import recovery_actions_repo
from app.repositories import recovery_options_repo
from app.workflow_engine import (
    REJECTED,
    APPROVED,
    EXECUTED,
    PENDING_APPROVAL,
    approve_action,
    reject_action,
    generate_workflow_actions,
)


def get_exception_history(
    connection,
    exception_id,
):
    """
    Compose the chronological operational history of one
    exception from real persisted records — never invented
    events.

    Every entry carries the timestamp actually stored for
    that lifecycle step; steps with no persisted timestamp
    (option evaluation, the still-open outcome) are dated
    "—" in the UI so no time is fabricated. Timestamps
    across the domain share the same ISO format, so sorting
    on (anchor, sequence) is chronological even when several
    steps share a timestamp: dated entries sort by their
    stored time, the undated evaluation entry is anchored to
    its detection time (it always follows detection), and
    the undated still-open outcome — the current state, not
    a past event — sorts last.

    Sources:

    - exceptions.detected_at        -> detection
    - recovery_options rows         -> evaluated options
    - recovery_actions rows         -> recommendation,
                                      decision, execution
    - manual_interventions rows     -> recorded interventions
    - exceptions.resolved_at        -> resolution
    """

    exception = exceptions_repo.get_exception_lifecycle(
        connection,
        exception_id,
    )

    if exception is None:
        return None

    history = []

    # --------------------------------------------------
    # DETECTION (always present)
    # --------------------------------------------------

    history.append(
        {
            "timestamp": exception["detected_at"],
            "event": "Exception detected",
            "detail": (
                f"{exception['severity']} severity — "
                f"{exception['description']}"
            ),
            "actor": "Adensa operational pipeline",
            "sequence": 0,
        }
    )

    # --------------------------------------------------
    # OPTION EVALUATION (narrative position: right after
    # detection; the options carry no timestamps)
    # --------------------------------------------------

    options = (
        recovery_options_repo.get_options_for_exception(
            connection,
            exception_id,
        )
    )

    option_count = len(options)

    if option_count:

        feasible_count = len(
            recovery_options_repo.get_feasible_options_for_exception(
                connection,
                exception_id,
            )
        )

        if feasible_count:
            result = (
                f"{feasible_count} feasible — "
                f"{option_count - feasible_count} "
                f"infeasible"
            )
        else:
            result = "none feasible — no system " "recommendation"

        history.append(
            {
                "timestamp": None,
                "event": "Recovery options evaluated",
                "detail": (
                    f"{option_count} options assessed; "
                    f"{result}"
                ),
                "actor": "Adensa recovery engine",
                "sequence": 1,
            }
        )

    # --------------------------------------------------
    # SYSTEM RECOVERY ACTIONS (oldest first)
    # --------------------------------------------------

    for action in (
        recovery_actions_repo.get_actions_for_exception(
            connection,
            exception_id,
        )
    ):

        history.append(
            {
                "timestamp": action["approved_at"],
                "event": "Recommendation generated",
                "detail": (
                    f"{action['action_id']} — "
                    f"{action['description']}"
                ),
                "actor": "Adensa decision engine",
                "sequence": len(history),
            }
        )

        if action["status"] == REJECTED:

            history.append(
                {
                    "timestamp": action["approved_at"],
                    "event": "Recovery rejected",
                    "detail": (
                        f"{action['action_id']} — system "
                        f"recommendation not accepted"
                    ),
                    "actor": action["approved_by"],
                    "sequence": len(history),
                }
            )

        elif action["approved_at"]:

            # A human decision was recorded: the action's
            # approval audit fields are the persisted record
            # of it. This covers Approved and Executed
            # actions alike — the decision happened in both
            # cases.

            history.append(
                {
                    "timestamp": action["approved_at"],
                    "event": "Recovery approved",
                    "detail": (
                        f"{action['action_id']} by "
                        f"{action['approved_by']}"
                    ),
                    "actor": action["approved_by"],
                    "sequence": len(history),
                }
            )

            if action["executed_at"]:

                history.append(
                    {
                        "timestamp": action["executed_at"],
                        "event": "Recovery executed",
                        "detail": (
                            f"{action['action_id']} — shipment "
                            f"recovered through the system "
                            f"recovery workflow"
                        ),
                        "actor": action["approved_by"],
                        "sequence": len(history),
                    }
                )

    # --------------------------------------------------
    # MANUAL INTERVENTIONS (newest first from the repo;
    # emitted oldest first for the timeline)
    # --------------------------------------------------

    for intervention in reversed(
        manual_interventions_repo.get_interventions_for_exception(
            connection,
            exception_id,
        )
    ):

        history.append(
            {
                "timestamp": intervention["recorded_at"],
                "event": "Manual intervention recorded",
                "detail": (
                    f"{intervention['intervention_id']} — "
                    f"{intervention['intervention_type']} with "
                    f"{intervention['external_party']}: "
                    f"{intervention['resolution_summary']}"
                ),
                "actor": intervention["recorded_by"],
                "sequence": len(history),
            }
        )

        if intervention["outcome"] == "Resolved":

            history.append(
                {
                    "timestamp": intervention["recorded_at"],
                    "event": "Exception resolved through "
                    "manual intervention",
                    "detail": (
                        f"Outcome recorded by "
                        f"{intervention['recorded_by']}"
                    ),
                    "actor": intervention["recorded_by"],
                    "sequence": len(history),
                }
            )

    # --------------------------------------------------
    # OUTCOME
    #
    # The outcome entry states the current resolution state
    # with the persisted evidence behind it: the shipment's
    # recorded estimated arrival (updated by the execution
    # engine) against the order's required delivery date.
    # Executed does not imply resolved: when the recorded
    # arrival still misses the required date, the entry
    # says so explicitly.
    # --------------------------------------------------

    if exception["resolution_status"] == "Resolved":

        history.append(
            {
                "timestamp": exception["resolved_at"],
                "event": "Exception resolved",
                "detail": (
                    f"Current status: Resolved — estimated "
                    f"arrival "
                    f"{exception['estimated_arrival']} meets "
                    f"required delivery "
                    f"{exception['required_delivery_date']} "
                    f"({exception['estimated_impact']} "
                    f"estimated impact)"
                ),
                "actor": "Adensa operational pipeline",
                "sequence": len(history),
            }
        )

    else:

        history.append(
            {
                "timestamp": None,
                "event": "Exception still open",
                "detail": (
                    f"Current status: Open — estimated "
                    f"arrival "
                    f"{exception['estimated_arrival']} still "
                    f"misses required delivery "
                    f"{exception['required_delivery_date']} "
                    f"— monitored until recovery is recorded"
                ),
                "actor": "Adensa operational pipeline",
                "sequence": len(history),
            }
        )

    # --------------------------------------------------
    # CHRONOLOGICAL ORDER: stable sort on (anchor,
    # sequence). Dated entries anchor to their stored
    # timestamp. The undated evaluation entry anchors to
    # the detection time — it always happens right after
    # detection and before any action. The undated
    # still-open outcome is the current state, not a past
    # event, so it anchors last.
    # --------------------------------------------------

    undated_anchors = {
        "Recovery options evaluated": (
            exception["detected_at"]
        ),
        "Exception still open": "9999-12-31 23:59:59",
    }

    def _sort_key(entry):

        if entry["timestamp"] is not None:

            return (
                entry["timestamp"],
                entry["sequence"],
            )

        return (
            undated_anchors.get(
                entry["event"],
                "9999-12-31 23:59:59",
            ),
            entry["sequence"],
        )

    history.sort(key=_sort_key)

    return history


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
