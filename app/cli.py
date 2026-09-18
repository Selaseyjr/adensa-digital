"""
Terminal command-line entry points for Adensa Digital.

This module owns every terminal-only presentation concern:
the display helpers formerly living at the tail of the
workflow, decision, and execution engines, plus the
python -m entry points that previously existed as __main__
blocks inside those engines.

The business logic stays in the engines and the data access
in the repositories; the functions here format and log the
results the engines and repositories provide.

Entry points:

    python -m app.cli workflow    status summary + sample actions
    python -m app.cli decision    evaluate all open exceptions
    python -m app.cli execution   information (no action taken)
"""

import logging

from app.database import get_connection
from app.decision_engine import get_recommendation
from app.repositories import exceptions_repo
from app.repositories import recovery_actions_repo
from app.workflow_engine import EXECUTED


logger = logging.getLogger(__name__)


# ==================================================
# WORKFLOW SUMMARY
# ==================================================

def show_workflow_summary(connection):
    """
    Display the current recovery-action status distribution.
    """

    statuses = recovery_actions_repo.get_status_counts(
        connection
    )

    if not statuses:
        logger.info(
            "No recovery actions exist yet."
        )
        return

    for row in statuses:

        logger.info(
            f"{row['status']}: "
            f"{row['count']}"
        )


# ==================================================
# SAMPLE RECOVERY ACTIONS
# ==================================================

def show_sample_actions(
    connection,
    limit=5,
):
    """
    Display a small sample of recovery actions.
    """

    actions = recovery_actions_repo.list_actions(
        connection,
        limit=limit,
    )

    logger.info("\nSample Recovery Actions")
    logger.info("=" * 50)

    for action in actions:

        logger.info(
            f"\nAction: "
            f"{action['action_id']}"
        )

        logger.info(
            f"Exception: "
            f"{action['exception_id']}"
        )

        logger.info(
            f"Option: "
            f"{action['option_id']}"
        )

        logger.info(
            f"Type: "
            f"{action['action_type']}"
        )

        logger.info(
            f"Status: "
            f"{action['status']}"
        )

        logger.info(
            f"Approved By: "
            f"{action['approved_by']}"
        )

        logger.info(
            f"Approved At: "
            f"{action['approved_at']}"
        )

        logger.info(
            f"Description: "
            f"{action['description']}"
        )


# ==================================================
# DISPLAY RECOMMENDATION
# ==================================================

def display_recommendation(result):
    """Display a recommendation in the terminal."""

    recommendation = result["recommendation"]

    if recommendation is None:

        logger.info(
            f"\nException: {result['exception_id']}"
        )

        logger.info(
            "No feasible recovery recommendation."
        )

        return

    logger.info(
        f"\nException: {result['exception_id']}"
    )

    logger.info(
        f"Shipment: {result['shipment_id']}"
    )

    logger.info(
        f"Priority: {result['priority']}"
    )

    logger.info(
        f"Severity: {result['severity']}"
    )

    logger.info(
        f"Recommended mode: "
        f"{recommendation['transport_mode']}"
    )

    logger.info(
        f"Decision score: "
        f"{recommendation['decision_score']}/100"
    )

    logger.info(
        f"Confidence: "
        f"{recommendation['confidence']}"
    )

    logger.info(
        f"Cost: "
        f"€{recommendation['estimated_cost']:,.2f}"
    )

    logger.info(
        f"Transit: "
        f"{recommendation['estimated_transit_days']} days"
    )

    logger.info(
        f"Risk: "
        f"{recommendation['risk_score']}"
    )

    reason = (
        f"Recommend "
        f"{recommendation['transport_mode']} recovery "
        f"with an estimated cost of "
        f"€{recommendation['estimated_cost']:,.2f}, "
        f"transit time of "
        f"{recommendation['estimated_transit_days']} days "
        f"and operational risk score of "
        f"{recommendation['risk_score']}. "
        f"Decision score: "
        f"{recommendation['decision_score']}/100. "
        f"Confidence: "
        f"{recommendation['confidence']}. "
        f"{recommendation['reason']}"
    )

    logger.info(f"Reason: {reason}")

    alternatives = result["alternatives"]

    if not alternatives:
        logger.info("Alternatives: None feasible")
        return

    logger.info("Alternatives:")

    for option in alternatives:

        logger.info(
            f"  - {option['transport_mode']} | "
            f"Score: {option['decision_score']}/100 | "
            f"Cost: €{option['estimated_cost']:,.2f} | "
            f"Transit: "
            f"{option['estimated_transit_days']} days | "
            f"Risk: {option['risk_score']}"
        )


# ==================================================
# DECISION ANALYSIS
# ==================================================

def run_decision_engine(connection):
    """Evaluate all currently open exceptions."""

    exceptions = exceptions_repo.get_open_exception_ids(
        connection
    )

    recommendations = 0
    without_recommendation = 0

    for index, exception in enumerate(exceptions):

        result = get_recommendation(
            connection,
            exception["exception_id"],
        )

        if result["recommendation"] is None:
            without_recommendation += 1

        else:
            recommendations += 1

        # Display only the first ten cases during
        # terminal-based testing.
        if index < 10:
            display_recommendation(result)

    logger.info("\n" + "=" * 55)
    logger.info("Decision Engine Summary")
    logger.info("=" * 55)

    logger.info(
        f"Exceptions evaluated: "
        f"{len(exceptions)}"
    )

    logger.info(
        f"Recommendations available: "
        f"{recommendations}"
    )

    logger.info(
        f"Exceptions without feasible recommendation: "
        f"{without_recommendation}"
    )


# ==================================================
# VERIFY EXECUTION
# ==================================================

def show_execution_result(
    connection,
    action_id,
):
    """
    Display the current database state of an executed
    recovery action.
    """

    result = recovery_actions_repo.get_execution_result(
        connection,
        action_id,
    )

    if result is None:
        logger.info(
            f"Action {action_id} not found."
        )
        return

    logger.info("\nExecution Result")
    logger.info("=" * 50)

    logger.info(
        f"Action: "
        f"{result['action_id']}"
    )

    logger.info(
        f"Exception: "
        f"{result['exception_id']}"
    )

    logger.info(
        f"Option: "
        f"{result['option_id']}"
    )

    logger.info(
        f"Action status: "
        f"{result['action_status']}"
    )

    logger.info(
        f"Executed at: "
        f"{result['executed_at']}"
    )

    logger.info(
        f"Shipment: "
        f"{result['shipment_id']}"
    )

    logger.info(
        f"Transport mode: "
        f"{result['transport_mode']}"
    )

    logger.info(
        f"Carrier: "
        f"{result['carrier_id']}"
    )

    logger.info(
        f"Estimated arrival: "
        f"{result['estimated_arrival']}"
    )

    logger.info(
        f"Exception status: "
        f"{result['resolution_status']}"
    )

    logger.info(
        f"Resolved at: "
        f"{result['resolved_at']}"
    )


# ==================================================
# MAIN
# ==================================================

if __name__ == "__main__":

    import sys

    logging.basicConfig(level=logging.INFO)

    mode = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "workflow"
    )

    connection = get_connection()

    try:

        if mode == "workflow":

            show_workflow_summary(connection)
            show_sample_actions(connection)

        elif mode == "decision":

            run_decision_engine(connection)

        elif mode == "execution":

            logger.info(
                "Execution engine loaded successfully."
            )
            logger.info(
                "No recovery action was executed."
            )

        else:

            logger.info(
                f"Unknown mode '{mode}'. "
                f"Use workflow, decision or execution."
            )

    finally:

        connection.close()
