import logging

from app.config import SIMULATION_TIMESTAMP
from app.database import get_connection
from app.decision_engine import get_recommendation
from app.errors import RecoveryWorkflowError
from app.repositories import recovery_actions_repo

logger = logging.getLogger(__name__)


# ==================================================
# WORKFLOW STATES
# ==================================================

PENDING_APPROVAL = "Pending Approval"
APPROVED = "Approved"
REJECTED = "Rejected"
EXECUTED = "Executed"


# ==================================================
# VALID WORKFLOW TRANSITIONS
# ==================================================

VALID_TRANSITIONS = {
    PENDING_APPROVAL: {
        APPROVED,
        REJECTED,
    },
    APPROVED: {
        EXECUTED,
    },
}


# ==================================================
# WORKFLOW STATE VALIDATION
# ==================================================

def is_valid_transition(current_status, new_status):
    """
    Check whether a requested workflow state transition
    is allowed by the Adensa Digital workflow.
    """

    allowed_states = VALID_TRANSITIONS.get(
        current_status,
        set(),
    )

    return new_status in allowed_states


def validate_transition(current_status, new_status):
    """
    Validate a workflow transition.

    Raises:
        RecoveryWorkflowError: If the requested transition is invalid.
    """

    if not is_valid_transition(
        current_status,
        new_status,
    ):
        raise RecoveryWorkflowError(
            f"Invalid workflow transition: "
            f"{current_status} → {new_status}"
        )


# ==================================================
# ACTION ID GENERATION
# ==================================================

def get_next_action_number(connection):
    """
    Determine the next recovery-action number from the
    existing database records.

    Thin wrapper kept for API compatibility; the data
    access lives in the recovery-actions repository.
    """

    return recovery_actions_repo.get_next_action_number(
        connection
    )


# ==================================================
# CREATE RECOVERY ACTION
# ==================================================

def create_recovery_action(
    connection,
    result,
    action_number,
):
    """
    Create a pending recovery action from a decision-engine
    recommendation.

    The workflow engine consumes the recommendation.
    It does not independently rank recovery options.
    """

    recommendation = result["recommendation"]

    if recommendation is None:
        return False

    # --------------------------------------------------
    # IDEMPOTENCY CHECK
    # --------------------------------------------------
    #
    # An exception should not receive multiple active
    # recovery actions at the same time.
    #

    existing_action = recovery_actions_repo.get_active_action_for_exception(
        connection,
        result["exception_id"],
    )

    if existing_action:
        return False

    action_id = f"ACT-{action_number:06d}"

    description = (
        f"Recommended recovery: switch shipment to "
        f"{recommendation['transport_mode']} using carrier "
        f"{recommendation['carrier_id']}. "
        f"Estimated cost: "
        f"€{recommendation['estimated_cost']:,.2f}. "
        f"Estimated transit: "
        f"{recommendation['estimated_transit_days']} days. "
        f"Risk score: "
        f"{recommendation['risk_score']}."
    )

    recovery_actions_repo.insert_recovery_action(
        connection,
        action_id=action_id,
        exception_id=result["exception_id"],
        option_id=recommendation["option_id"],
        action_type="Recovery",
        description=description,
        status=PENDING_APPROVAL,
    )

    return True


# ==================================================
# GENERATE WORKFLOW ACTIONS
# ==================================================

def generate_workflow_actions(connection):
    """
    Generate pending recovery actions for open exceptions
    that have a feasible recommendation.
    """

    cursor = connection.cursor()

    exceptions = cursor.execute(
        """
        SELECT exception_id
        FROM exceptions
        WHERE resolution_status = 'Open'
        ORDER BY exception_id
        """
    ).fetchall()

    created = 0
    skipped = 0
    no_recommendation = 0

    next_action_number = get_next_action_number(
        connection
    )

    for exception in exceptions:

        result = get_recommendation(
            connection,
            exception["exception_id"],
        )

        if result is None:
            no_recommendation += 1
            continue

        if result["recommendation"] is None:
            no_recommendation += 1
            continue

        action_created = create_recovery_action(
            connection,
            result,
            next_action_number,
        )

        if action_created:

            created += 1
            next_action_number += 1

        else:

            skipped += 1

    connection.commit()

    logger.info("Workflow Generation")
    logger.info("=" * 50)

    logger.info(
        f"Open exceptions evaluated: "
        f"{len(exceptions)}"
    )

    logger.info(
        f"Recovery actions created: "
        f"{created}"
    )

    logger.info(
        f"Exceptions without recommendation: "
        f"{no_recommendation}"
    )

    logger.info(
        f"Existing actions skipped: "
        f"{skipped}"
    )

    return {
        "evaluated": len(exceptions),
        "created": created,
        "without_recommendation": no_recommendation,
        "skipped": skipped,
    }


# ==================================================
# APPROVE RECOVERY ACTION
# ==================================================

def approve_action(
    connection,
    action_id,
    approved_by,
):
    """
    Approve a pending recovery action.

    Valid transition:

        Pending Approval → Approved

    Invalid transitions raise RecoveryWorkflowError.
    """

    cursor = connection.cursor()

    action = recovery_actions_repo.get_action_by_id(
        connection,
        action_id,
    )

    if action is None:
        raise RecoveryWorkflowError(
            f"Action {action_id} not found."
        )

    # --------------------------------------------------
    # VALIDATE STATE TRANSITION
    # --------------------------------------------------

    validate_transition(
        action["status"],
        APPROVED,
    )

    # --------------------------------------------------
    # CHECK EXCEPTION IS STILL OPEN
    # --------------------------------------------------

    exception = cursor.execute(
        """
        SELECT resolution_status
        FROM exceptions
        WHERE exception_id = ?
        """,
        (action["exception_id"],),
    ).fetchone()

    if exception is None:
        raise RecoveryWorkflowError(
            f"Exception for action {action_id} "
            f"was not found."
        )

    if exception["resolution_status"] != "Open":
        raise RecoveryWorkflowError(
            f"Action {action_id} cannot be approved "
            f"because its exception is no longer open."
        )

    # --------------------------------------------------
    # UPDATE ACTION
    # --------------------------------------------------

    rows_updated = recovery_actions_repo.update_action_status(
        connection,
        action_id=action_id,
        new_status=APPROVED,
        actor=approved_by,
        timestamp=SIMULATION_TIMESTAMP,
        expected_current_status=PENDING_APPROVAL,
    )

    if rows_updated != 1:
        raise RecoveryWorkflowError(
            f"Approval could not be completed for "
            f"action {action_id}."
        )

    connection.commit()

    logger.info(
        f"✓ Action {action_id} approved by "
        f"{approved_by}."
    )

    return True


# ==================================================
# REJECT RECOVERY ACTION
# ==================================================

def reject_action(
    connection,
    action_id,
    rejected_by,
):
    """
    Reject a pending recovery action.

    Valid transition:

        Pending Approval → Rejected

    The current database schema has no separate
    rejected_by or rejected_at fields, so the existing
    approval audit fields temporarily store the workflow
    actor and timestamp.

    Invalid transitions raise RecoveryWorkflowError.
    """

    action = recovery_actions_repo.get_action_status_and_id(
        connection,
        action_id,
    )

    if action is None:
        raise RecoveryWorkflowError(
            f"Action {action_id} not found."
        )

    # --------------------------------------------------
    # VALIDATE STATE TRANSITION
    # --------------------------------------------------

    validate_transition(
        action["status"],
        REJECTED,
    )

    # --------------------------------------------------
    # UPDATE ACTION
    # --------------------------------------------------

    rows_updated = recovery_actions_repo.update_action_status(
        connection,
        action_id=action_id,
        new_status=REJECTED,
        actor=rejected_by,
        timestamp=SIMULATION_TIMESTAMP,
        expected_current_status=PENDING_APPROVAL,
    )

    if rows_updated != 1:
        raise RecoveryWorkflowError(
            f"Rejection could not be completed for "
            f"action {action_id}."
        )

    connection.commit()

    logger.info(
        f"✓ Action {action_id} rejected by "
        f"{rejected_by}."
    )

    return True


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
# MAIN
# ==================================================

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    connection = get_connection()

    try:

        show_workflow_summary(
            connection
        )

        show_sample_actions(
            connection
        )

    finally:

        connection.close()